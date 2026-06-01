import os
import queue
import threading
import time
import tempfile
import numpy as np
import torch
import torchaudio
import librosa

from speechbrain.inference.classifiers import EncoderClassifier
from shared.config import Config


class AudioDetectionModule:

    SAMPLE_RATE    = 16000
    CHUNK_DURATION = 3
    OVERLAP        = 0.5
    DISTRESS_EMOTIONS = ['ang', 'sad', 'fea', 'dis']

    # stutter types from sep-28k
    STUTTER_LABELS = {
        0: 'Prolongation',
        1: 'Block',
        2: 'Sound Repetition',
        3: 'Word Repetition',
        4: 'Interjection',
        5: 'No Dysfluency',
    }
    CONCERNING_STUTTER_TYPES = [
        'Prolongation', 'Block',
        'Sound Repetition', 'Word Repetition',
    ]

    def __init__(self, config: Config):
        self._config      = config
        self._audio_queue = queue.Queue()
        self._cooldown    = {}
        self._running     = False
        self._lock        = threading.Lock()
        self._speech_module = None

        self.AUDIO_THRESHOLD  = config.audio_threshold
        self.COOLDOWN_SECONDS = config.audio_cooldown_seconds

        # track last distress time for auto-clear
        self._last_distress_time     = 0
        self._DISTRESS_CLEAR_SECONDS = 5

        # emotion (speechbrain)
        self.distress_detected   = False
        self.distress_label      = ""
        self.distress_level      = ""
        self.distress_confidence = 0.0

        # stuttering (wav2vec2 + librosa fallback)
        self.stutter_detected  = False
        self.stutter_type      = ""
        self.stutter_score     = 0.0
        self.is_concerning     = False
        self.stutter_history   = []

        self._load_models()

    # model loading

    def _load_models(self):
        # speechbrain emotion recognition
        print("[AUDIO] Loading SpeechBrain emotion model...")
        try:
            self._emotion_model = EncoderClassifier.from_hparams(
                source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                savedir="pretrained_models/emotion",
                run_opts={"device": "cpu"}
            )
            print("[AUDIO] SpeechBrain emotion model loaded")
        except Exception as e:
            print(f"[AUDIO] SpeechBrain emotion model failed: {e}")
            print("[AUDIO] Will use librosa fallback for emotion")
            self._emotion_model = None

        # wav2vec2 for stuttering detection
        print("[AUDIO] Loading wav2vec2 stutter model...")
        try:
            from transformers import (
                Wav2Vec2ForSequenceClassification,
                Wav2Vec2Processor
            )

            # check if fine tuned model exists locally
            stutter_model_path = "stutter_model/final"
            if os.path.exists(stutter_model_path):
                print("[AUDIO] Loading fine-tuned stutter model...")
                model_source = stutter_model_path
            else:
                print("[AUDIO] No fine-tuned model found — "
                      "using base wav2vec2 with rule-based fallback")
                model_source = "facebook/wav2vec2-base"

            self._stutter_processor = Wav2Vec2Processor.from_pretrained(
                "facebook/wav2vec2-base"
            )
            self._stutter_model = \
                Wav2Vec2ForSequenceClassification.from_pretrained(
                    model_source,
                    num_labels=len(self.STUTTER_LABELS),
                    ignore_mismatched_sizes=True
                )
            self._stutter_model.eval()
            print("[AUDIO] wav2vec2 stutter model loaded")

        except Exception as e:
            print(f"[AUDIO] wav2vec2 stutter model failed: {e}")
            print("[AUDIO] Will use librosa fallback for stuttering")
            self._stutter_model     = None
            self._stutter_processor = None

    # test utilities

    def test_with_file(self, wav_path: str):
        print(f"[AUDIO TEST] Loading {wav_path}...")
        try:
            audio, _ = librosa.load(
                wav_path,
                sr=self.SAMPLE_RATE,
                mono=True
            )
            print(f"[AUDIO TEST] Loaded {len(audio)} samples "
                  f"({len(audio)/self.SAMPLE_RATE:.1f}s)")

            chunk_size = self.SAMPLE_RATE
            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i + chunk_size]
                if len(chunk) > 0:
                    self._audio_queue.put(chunk.astype(np.float32))
                    time.sleep(0.1)

            print("[AUDIO TEST] File feeding complete")

        except Exception as e:
            print(f"[AUDIO TEST] Failed: {e}")
            import traceback
            traceback.print_exc()

    def list_microphones(self):
        import sounddevice as sd
        print("\n[AUDIO] Available audio devices:")
        print(sd.query_devices())
        print()

    def set_speech_module(self, speech_module):
        self._speech_module = speech_module

    # public interface

    def start(self):
        self._running = True

        self._process_thread = threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="AudioProcessing"
        )
        self._process_thread.start()

        try:
            import sounddevice as sd
            self._mic_stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                callback=self._audio_callback,
                blocksize=self.SAMPLE_RATE
            )
            self._mic_stream.start()
            print("[AUDIO] Audio monitoring started...")
        except Exception as e:
            print(f"[AUDIO] Microphone not available: {e}")
            print("[AUDIO] Running in test-only mode")
            self._mic_stream = None

    def stop(self):
        self._running = False
        if hasattr(self, '_mic_stream') and self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
        print("[AUDIO] Audio monitoring stopped.")

    def get_state(self):
        with self._lock:
            # auto-clear distress after silence
            if (self.distress_detected and
                    time.time() - self._last_distress_time
                    > self._DISTRESS_CLEAR_SECONDS):
                self.distress_detected   = False
                self.distress_label      = ""
                self.distress_level      = ""
                self.distress_confidence = 0.0

            return {
                # emotion/distress
                'detected':        self.distress_detected,
                'label':           self.distress_label,
                'level':           self.distress_level,
                'confidence':      self.distress_confidence,
                # stuttering
                'stutter_detected': self.stutter_detected,
                'stutter_type':     self.stutter_type,
                'stutter_score':    self.stutter_score,
                'stutter_concern':  self.is_concerning,
                'stutter_history':  list(self.stutter_history),
            }

    # internal

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[AUDIO] Mic status: {status}")
        self._audio_queue.put(indata[:, 0].copy())

    def _should_alert(self, label: str) -> bool:
        now = time.time()
        if label in self._cooldown:
            if now - self._cooldown[label] < self.COOLDOWN_SECONDS:
                return False
        self._cooldown[label] = now
        return True

    def _processing_loop(self):
        buffer     = np.array([], dtype=np.float32)
        chunk_size = int(self.SAMPLE_RATE * self.CHUNK_DURATION)
        step_size  = int(chunk_size * (1 - self.OVERLAP))

        while self._running:
            try:
                chunk  = self._audio_queue.get(timeout=1)
                buffer = np.concatenate([buffer, chunk])

                if len(buffer) >= chunk_size:
                    window = buffer[:chunk_size]
                    buffer = buffer[step_size:]

                    # skip silent chunks
                    rms = np.sqrt(np.mean(window ** 2))
                    if rms < 0.01:
                        continue

                    # run both analyses in parallel
                    emotion_thread = threading.Thread(
                        target=self._analyze_emotion,
                        args=(window.copy(),),
                        daemon=True
                    )
                    stutter_thread = threading.Thread(
                        target=self._analyze_stutter,
                        args=(window.copy(),),
                        daemon=True
                    )
                    emotion_thread.start()
                    stutter_thread.start()

                    # feed to speech module if connected
                    if self._speech_module:
                        self._speech_module.feed_audio(window.copy())

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[AUDIO ERROR] {e}")
                import traceback
                traceback.print_exc()

        if hasattr(self, '_speech_module') and self._speech_module:
                self._speech_module.feed_audio(window)

    def set_speech_module(self, speech_module):
        self._speech_module = speech_module

    # emotion detection (speechbrain)

    def _analyze_emotion(self, audio: np.ndarray):
        if self._emotion_model is not None:
            self._speechbrain_emotion(audio)
        else:
            self._librosa_emotion_fallback(audio)

    # speechbrain iemocap model to detect distress emotions
    def _speechbrain_emotion(self, audio: np.ndarray):
        try:
            waveform = torch.FloatTensor(audio).unsqueeze(0)

            out_prob, score, index, label = \
                self._emotion_model.classify_batch(waveform)

            emotion    = label[0].strip()
            confidence = float(score[0])
            is_distress = emotion in self.DISTRESS_EMOTIONS

            # map emotion to distress level
            if emotion in ['ang', 'fea']:
                level = 'critical'
            elif emotion in ['sad', 'dis']:
                level = 'warning'
            else:
                level = 'neutral'

            # debug output
            print(f"[AUDIO DEBUG] Emotion: {emotion} "
                  f"({confidence:.0%}) — {level}")

            with self._lock:
                if is_distress and confidence >= self.AUDIO_THRESHOLD:
                    if self._should_alert(emotion):
                        print(f"[AUDIO] {level.upper()}: "
                              f"Emotion={emotion} "
                              f"({confidence:.0%})")
                    self.distress_detected   = True
                    self.distress_label      = emotion
                    self.distress_level      = level
                    self.distress_confidence = confidence
                    self._last_distress_time = time.time()
                else:
                    pass # let get_state() handle it

        except Exception as e:
            print(f"[AUDIO] SpeechBrain emotion error: {e}")
            self._librosa_emotion_fallback(audio)

    # fallback when speechbrain unavailable
    # detects distress via pitch, energy, and speech rate
    def _librosa_emotion_fallback(self, audio: np.ndarray):
        try:
            # high pitch variance = emotional distress
            pitches, magnitudes = librosa.piptrack(
                y=audio, sr=self.SAMPLE_RATE
            )
            valid = pitches[magnitudes > np.median(magnitudes)]
            pitch_var = float(np.std(valid)) if len(valid) > 0 else 0.0

            # high energy = shouting/screaming
            rms        = librosa.feature.rms(y=audio)[0]
            mean_energy = float(np.mean(rms))

            # fast speech rate = agitation
            onsets     = librosa.onset.onset_detect(
                y=audio, sr=self.SAMPLE_RATE
            )
            speech_rate = len(onsets) / (len(audio) / self.SAMPLE_RATE)

            is_distress = (
                pitch_var > 150 or
                mean_energy > 0.3 or
                speech_rate > 7.0
            )

            print(f"[AUDIO DEBUG] Librosa fallback: "
                  f"pitch_var={pitch_var:.1f} "
                  f"energy={mean_energy:.2f} "
                  f"rate={speech_rate:.1f}")

            with self._lock:
                if is_distress:
                    label = 'librosa_distress'
                    if self._should_alert(label):
                        print(f"[AUDIO] WARNING: "
                              f"Distress signals detected "
                              f"(librosa fallback)")
                    self.distress_detected   = True
                    self.distress_label      = label
                    self.distress_level      = 'warning'
                    self.distress_confidence = 0.6
                    self._last_distress_time = time.time()

        except Exception as e:
            print(f"[AUDIO] Librosa fallback error: {e}")

    # stutter detection (wav2vec2 + librosa fallback)
    def _analyze_stutter(self, audio: np.ndarray):
        if self._stutter_model is not None:
            self._wav2vec2_stutter(audio)
        else:
            self._librosa_stutter_fallback(audio)

    # wav2vec2 to classsify stutter type
    def _wav2vec2_stutter(self, audio: np.ndarray):
        try:
            inputs = self._stutter_processor(
                audio,
                sampling_rate=self.SAMPLE_RATE,
                return_tensors="pt",
                padding=True
            )

            with torch.no_grad():
                logits = self._stutter_model(**inputs).logits

            probs      = torch.softmax(logits, dim=-1)[0]
            pred_idx   = int(torch.argmax(probs).item())
            pred_score = float(probs[pred_idx].item())
            pred_label = self.STUTTER_LABELS[pred_idx]
            is_stutter = pred_label != 'No Dysfluency'
            concerning = pred_label in self.CONCERNING_STUTTER_TYPES

            print(f"[AUDIO DEBUG] Stutter: {pred_label} "
                  f"({pred_score:.0%})")

            with self._lock:
                self.stutter_detected = is_stutter
                self.stutter_type     = pred_label if is_stutter else ""
                self.stutter_score    = pred_score
                self.is_concerning    = concerning

                if is_stutter:
                    self.stutter_history.append({
                        'type':      pred_label,
                        'score':     pred_score,
                        'timestamp': time.time()
                    })
                    if len(self.stutter_history) > 10:
                        self.stutter_history.pop(0)

                    print(f"[AUDIO] STUTTER: {pred_label} "
                          f"({pred_score:.0%})"
                          + ("!!!" if concerning else ""))

        except Exception as e:
            print(f"[AUDIO] wav2vec2 stutter error: {e}")
            self._librosa_stutter_fallback(audio)

    # librosa fall for stutter detection
    # detects repetitions and blocks acoustically
    def _librosa_stutter_fallback(self, audio: np.ndarray):
        try:
            onsets   = librosa.onset.onset_detect(
                y=audio, sr=self.SAMPLE_RATE, units='time'
            )
            duration = len(audio) / self.SAMPLE_RATE

            if len(onsets) < 2:
                return

            gaps       = np.diff(onsets)
            short_gaps = int(np.sum(gaps < 0.15))
            repetition = short_gaps > 2

            rms           = librosa.feature.rms(y=audio)[0]
            silence_ratio = float(np.sum(rms < 0.01) / len(rms))
            blocking      = silence_ratio > 0.4 and duration > 1.0

            stutter_type = None
            if repetition:
                stutter_type = "Sound Repetition"
            elif blocking:
                stutter_type = "Block"

            print(f"[AUDIO DEBUG] Librosa stutter — "
                  f"short_gaps={short_gaps} "
                  f"silence={silence_ratio:.2f} "
                  f"result={stutter_type or 'None'}")

            with self._lock:
                self.stutter_detected = stutter_type is not None
                self.stutter_type     = stutter_type or ""
                self.is_concerning    = (
                    stutter_type in self.CONCERNING_STUTTER_TYPES
                )

                if stutter_type:
                    self.stutter_history.append({
                        'type':      stutter_type,
                        'score':     0.6,
                        'timestamp': time.time()
                    })
                    if len(self.stutter_history) > 10:
                        self.stutter_history.pop(0)

                    print(f"[AUDIO] STUTTER (librosa): {stutter_type}")

        except Exception as e:
            print(f"[AUDIO] Librosa stutter fallback error: {e}")