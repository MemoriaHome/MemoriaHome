import os
import csv
import queue
import threading
import time
import datetime
import tempfile
import warnings
import logging
import numpy as np
import torch
import torchaudio
import librosa
import requests

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*deprecated.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*newly initialized.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*CategoricalEncoder.expect_len.*")
logging.getLogger("speechbrain").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from speechbrain.inference.classifiers import EncoderClassifier
from shared.config import Config


class AudioDetectionModule:

    SAMPLE_RATE    = 16000
    CHUNK_DURATION = 3
    OVERLAP        = 0.5
    DISTRESS_EMOTIONS = ['ang', 'sad', 'fea', 'dis']
    STUTTER_SCORE_THRESHOLD = 0.55
    STUTTER_HISTORY_LIMIT = 20

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
        self._cooldown    = {}
        self._running     = False
        self._lock        = threading.Lock()
        self._speech_module = None
        self._suppress_distress_until = 0.0

        self.AUDIO_THRESHOLD  = config.audio_threshold
        self.COOLDOWN_SECONDS = config.audio_cooldown_seconds
        self.AUDIO_BLOCK_SECONDS = max(
            0.05,
            float(getattr(config, "audio_block_seconds", 0.25))
        )
        self.DISTRESS_WINDOW_SECONDS = max(
            self.AUDIO_BLOCK_SECONDS,
            float(getattr(config, "distress_window_seconds", 2.0))
        )
        self.DISTRESS_HOP_SECONDS = max(
            self.AUDIO_BLOCK_SECONDS,
            float(getattr(config, "distress_hop_seconds", 0.5))
        )
        self.STUTTER_WINDOW_SECONDS = max(
            self.AUDIO_BLOCK_SECONDS,
            float(getattr(config, "stutter_window_seconds", 3.0))
        )
        self.STUTTER_HOP_SECONDS = max(
            self.AUDIO_BLOCK_SECONDS,
            float(getattr(config, "stutter_hop_seconds", 1.5))
        )
        self.AUDIO_DEBUG = bool(getattr(config, "audio_debug", True))
        self.STUTTER_LOG_ONLY = bool(getattr(config, "stutter_log_only", True))

        queue_seconds = 12
        queue_size = max(8, int(queue_seconds / self.AUDIO_BLOCK_SECONDS))
        self._audio_queue = queue.Queue(maxsize=queue_size)
        self._stutter_queue = queue.Queue(maxsize=queue_size)

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
        if self.AUDIO_DEBUG:
            print("[AUDIO] Loading SpeechBrain emotion model...")
        try:
            self._emotion_model = EncoderClassifier.from_hparams(
                source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                savedir="pretrained_models/emotion",
                run_opts={"device": "cpu"}
            )
            if self.AUDIO_DEBUG:
                print("[AUDIO] SpeechBrain emotion model loaded")
        except Exception as e:
            print(f"[AUDIO] SpeechBrain emotion model failed: {e}")
            print("[AUDIO] Will use librosa fallback for emotion")
            self._emotion_model = None

        # wav2vec2 for stuttering detection
        if self.AUDIO_DEBUG:
            print("[AUDIO] Loading wav2vec2 stutter model...")
        try:
            from transformers import (
                Wav2Vec2ForSequenceClassification,
                Wav2Vec2Processor
            )

            # check if fine tuned model exists locally
            stutter_model_path = "stutter_model/final"
            if os.path.exists(stutter_model_path):
                if self.AUDIO_DEBUG:
                    print("[AUDIO] Loading fine-tuned stutter model...")
                model_source = stutter_model_path
                local_files_only = True
            else:
                if self.AUDIO_DEBUG:
                    print("[AUDIO] No fine-tuned model found - "
                          "using base wav2vec2 with rule-based fallback")
                model_source = "facebook/wav2vec2-base"
                local_files_only = False

            self._stutter_processor = Wav2Vec2Processor.from_pretrained(
                model_source,
                local_files_only=local_files_only
            )
            self._stutter_model = \
                Wav2Vec2ForSequenceClassification.from_pretrained(
                    model_source,
                    num_labels=len(self.STUTTER_LABELS),
                    ignore_mismatched_sizes=True,
                    local_files_only=local_files_only
            )
            self._stutter_model.eval()
            if self.AUDIO_DEBUG:
                print("[AUDIO] wav2vec2 stutter model loaded")

        except Exception as e:
            print(f"[AUDIO] wav2vec2 stutter model failed: {e}")
            print("[AUDIO] Will use librosa fallback for stuttering")
            self._stutter_model     = None
            self._stutter_processor = None

    # test utilities

    def test_with_file(self, wav_path: str, allow_distress_alerts: bool = True):
        print(f"[AUDIO TEST] Loading {wav_path}...")
        try:
            audio, _ = librosa.load(
                wav_path,
                sr=self.SAMPLE_RATE,
                mono=True
            )
            print(f"[AUDIO TEST] Loaded {len(audio)} samples "
                  f"({len(audio)/self.SAMPLE_RATE:.1f}s)")
            if not allow_distress_alerts:
                suppress_seconds = len(audio) / self.SAMPLE_RATE + 10
                self._suppress_distress_until = time.time() + suppress_seconds
                print("[AUDIO TEST] Distress alerts suppressed for this file")

            chunk_size = int(self.SAMPLE_RATE * self.AUDIO_BLOCK_SECONDS)
            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i + chunk_size]
                if len(chunk) > 0:
                    self._handle_audio_chunk(chunk.astype(np.float32))
                    time.sleep(self.AUDIO_BLOCK_SECONDS)

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
        self._stutter_thread = threading.Thread(
            target=self._stutter_processing_loop,
            daemon=True,
            name="StutterProcessing"
        )
        self._stutter_thread.start()

        try:
            import sounddevice as sd

            # Resolve Kinect mic device index
            device_index = None
            kinect_device = self._config.kinect_audio_device

            if kinect_device is not None:
                if isinstance(kinect_device, int):
                    device_index = kinect_device
                    print(f"[AUDIO] Using Kinect mic at index {device_index}")
                else:
                    devices = sd.query_devices()
                    for i, d in enumerate(devices):
                        if kinect_device.lower() in d['name'].lower():
                            device_index = i
                            if self.AUDIO_DEBUG:
                                print(f"[AUDIO] Kinect mic found: "
                                      f"'{d['name']}' (index {i})")
                            break
                    if device_index is None:
                        print(f"[AUDIO] Kinect mic '{kinect_device}' not found "
                              f"— using system default")

            self._mic_stream = sd.InputStream(
                device=device_index,
                samplerate=self.SAMPLE_RATE,
                channels=1,
                callback=self._audio_callback,
                blocksize=int(self.SAMPLE_RATE * self.AUDIO_BLOCK_SECONDS)
            )
            self._mic_stream.start()
            print("[AUDIO] Audio monitoring started")
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
        print("[AUDIO] Audio monitoring stopped")

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
        self._handle_audio_chunk(indata[:, 0].copy())

    def _handle_audio_chunk(self, chunk: np.ndarray):
        chunk = chunk.astype(np.float32, copy=False)
        self._put_latest(self._audio_queue, chunk.copy(), "distress")
        self._put_latest(self._stutter_queue, chunk.copy(), "stutter")

        if self._speech_module:
            self._speech_module.feed_audio(chunk.copy())

    def _put_latest(self, target_queue: queue.Queue, item, label: str):
        try:
            target_queue.put_nowait(item)
            return
        except queue.Full:
            pass

        try:
            target_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            target_queue.put_nowait(item)
            if self.AUDIO_DEBUG:
                print(f"[AUDIO DEBUG] Dropped stale {label} audio chunk")
        except queue.Full:
            if self.AUDIO_DEBUG:
                print(f"[AUDIO DEBUG] Skipped {label} audio chunk; queue full")

    def _should_alert(self, label: str) -> bool:
        if time.time() < self._suppress_distress_until:
            if self.AUDIO_DEBUG:
                print(f"[AUDIO DEBUG] Suppressed test-file distress alert: "
                      f"{label}")
            return False

        now = time.time()
        if label in self._cooldown:
            if now - self._cooldown[label] < self.COOLDOWN_SECONDS:
                return False
        self._cooldown[label] = now
        return True

    def _processing_loop(self):
        buffer     = np.array([], dtype=np.float32)
        chunk_size = int(self.SAMPLE_RATE * self.DISTRESS_WINDOW_SECONDS)
        step_size  = int(self.SAMPLE_RATE * self.DISTRESS_HOP_SECONDS)

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
                        if self.AUDIO_DEBUG:
                            print(f"[AUDIO DEBUG] Distress window silent "
                                  f"rms={rms:.4f}")
                        continue

                    start_time = time.perf_counter()
                    self._analyze_emotion(window.copy())
                    if self.AUDIO_DEBUG:
                        elapsed = time.perf_counter() - start_time
                        print(f"[AUDIO DEBUG] Distress window rms={rms:.4f} "
                              f"queue={self._audio_queue.qsize()} "
                              f"emotion_time={elapsed:.2f}s")

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[AUDIO ERROR] {e}")
                import traceback
                traceback.print_exc()

    def _stutter_processing_loop(self):
        buffer     = np.array([], dtype=np.float32)
        chunk_size = int(self.SAMPLE_RATE * self.STUTTER_WINDOW_SECONDS)
        step_size  = int(self.SAMPLE_RATE * self.STUTTER_HOP_SECONDS)

        while self._running:
            try:
                chunk = self._stutter_queue.get(timeout=1)
                buffer = np.concatenate([buffer, chunk])

                if len(buffer) >= chunk_size:
                    window = buffer[:chunk_size]
                    buffer = buffer[step_size:]

                    rms = float(np.sqrt(np.mean(window ** 2)))
                    if rms < 0.005:
                        with self._lock:
                            self.stutter_detected = False
                            self.stutter_type = ""
                            self.stutter_score = 0.0
                            self.is_concerning = False
                        if self.AUDIO_DEBUG:
                            print(f"[AUDIO DEBUG] Stutter window silent "
                                  f"rms={rms:.4f}")
                        continue

                    start_time = time.perf_counter()
                    self._analyze_stutter(window.copy(), rms=rms)
                    if self.AUDIO_DEBUG:
                        elapsed = time.perf_counter() - start_time
                        print(f"[AUDIO DEBUG] Stutter window rms={rms:.4f} "
                              f"queue={self._stutter_queue.qsize()} "
                              f"stutter_time={elapsed:.2f}s")

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[STUTTER ERROR] {e}")
                import traceback
                traceback.print_exc()

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

            out_prob, score, index, label = self._classify_emotion(waveform)

            emotion    = label[0].strip()
            confidence = float(score[0])
            is_distress = emotion in self.DISTRESS_EMOTIONS

            if emotion in ['ang', 'fea']:
                level = 'critical'
            elif emotion in ['sad', 'dis']:
                level = 'warning'
            else:
                level = 'neutral'

            if self.AUDIO_DEBUG:
                print(f"[AUDIO DEBUG] SpeechBrain: {emotion} "
                    f"({confidence:.0%}) - {level}")

            with self._lock:
                if is_distress and confidence >= self.AUDIO_THRESHOLD:
                    if self._should_alert(emotion):
                        print(f"[AUDIO] {level.upper()}: "
                            f"Emotion={emotion} ({confidence:.0%})")
                        self._send_distress_alert(
                            label=emotion,
                            level=level,
                            confidence=confidence,
                            detector="speechbrain_emotion",
                        )
                    self.distress_detected   = True
                    self.distress_label      = emotion
                    self.distress_level      = level
                    self.distress_confidence = confidence
                    self._last_distress_time = time.time()

        except Exception as e:
            print(f"[AUDIO] SpeechBrain emotion error: {e}")
            self._librosa_emotion_fallback(audio)

    def _classify_emotion(self, waveform: torch.Tensor):
        if hasattr(self._emotion_model.mods, "wav2vec2"):
            wav_lens = torch.ones(
                waveform.shape[0],
                device=self._emotion_model.device
            )
            waveform = waveform.to(self._emotion_model.device).float()
            with torch.no_grad():
                feats = self._emotion_model.mods.wav2vec2(waveform, wav_lens)
                pooled = self._emotion_model.mods.avg_pool(feats, wav_lens)
                logits = self._emotion_model.mods.output_mlp(pooled)
                out_prob = self._emotion_model.hparams.softmax(logits)
            scores = out_prob.squeeze(1) if out_prob.dim() == 3 else out_prob
            score, index = torch.max(scores, dim=-1)
            label = self._emotion_model.hparams.label_encoder.decode_torch(
                index
            )
            return out_prob, score, index, label

        return self._emotion_model.classify_batch(waveform)

    def _send_distress_alert(
            self,
            label: str,
            level: str,
            confidence: float,
            detector: str):
        payload = {
            "deviceId":   self._config.device_id,
            "patientId":  self._config.patient_id,
            "room":       self._config.room,
            "eventType":  "Distress Detected",
            "timestamp":  datetime.datetime.now().isoformat(),
            "source":     "audio_detection",
            "detector":   detector,
            "label":      label,
            "level":      level,
            "confidence": confidence,
        }

        print(f"[AUDIO] Sending distress alert: {label} ({level})")

        def post_with_retry():
            attempt = 0
            while self._running:
                try:
                    response = requests.post(
                        f"{self._config.backend_url}/alert/distress",
                        json=payload,
                        timeout=10,
                        verify=False,
                    )
                    if response.status_code == 201:
                        print("[AUDIO] Distress alert sent successfully.")
                        break
                    print(f"[AUDIO] Unexpected status {response.status_code}, "
                          f"retrying...")
                except requests.exceptions.RequestException as e:
                    print(f"[AUDIO] Alert attempt {attempt} failed: {e}, "
                          f"retrying in 5s...")
                attempt += 1
                time.sleep(5)

        threading.Thread(target=post_with_retry, daemon=True).start()

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

            if self.AUDIO_DEBUG:
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
                        self._send_distress_alert(
                            label=label,
                            level="warning",
                            confidence=0.6,
                            detector="librosa_fallback",
                        )
                    self.distress_detected   = True
                    self.distress_label      = label
                    self.distress_level      = 'warning'
                    self.distress_confidence = 0.6
                    self._last_distress_time = time.time()

        except Exception as e:
            print(f"[AUDIO] Librosa fallback error: {e}")

    # stutter detection (wav2vec2 + librosa fallback)
    def _analyze_stutter(self, audio: np.ndarray, rms: float | None = None):
        if self._stutter_model is not None:
            self._wav2vec2_stutter(audio, rms=rms)
        else:
            self._librosa_stutter_fallback(audio, rms=rms)

    # wav2vec2 to classify stutter type
    def _wav2vec2_stutter(self, audio: np.ndarray, rms: float | None = None):
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
            concerning_indexes = [
                idx for idx, label in self.STUTTER_LABELS.items()
                if label in self.CONCERNING_STUTTER_TYPES
            ]
            concern_score = float(probs[concerning_indexes].sum().item())
            no_dysfluency_score = float(probs[5].item())
            concern_idx = max(
                concerning_indexes,
                key=lambda idx: float(probs[idx].item())
            )
            concern_label = self.STUTTER_LABELS[concern_idx]
            is_stutter = concern_score >= self.STUTTER_SCORE_THRESHOLD
            display_label = concern_label if is_stutter else pred_label
            display_score = concern_score if is_stutter else pred_score
            top_indexes = torch.argsort(probs, descending=True)[:3].tolist()
            top3 = "; ".join(
                f"{self.STUTTER_LABELS[int(idx)]}:{float(probs[idx]):.4f}"
                for idx in top_indexes
            )
            rms = float(rms if rms is not None else np.sqrt(np.mean(audio ** 2)))

            if self.AUDIO_DEBUG:
                print(f"[AUDIO DEBUG] Stutter top={pred_label} "
                      f"top_score={pred_score:.0%} "
                      f"concern_score={concern_score:.0%} "
                      f"no_dysfluency={no_dysfluency_score:.0%}")

            with self._lock:
                self.stutter_detected = is_stutter
                self.stutter_type     = display_label if is_stutter else ""
                self.stutter_score    = display_score
                self.is_concerning    = is_stutter

                if is_stutter:
                    self.stutter_history.append({
                        'type':      display_label,
                        'score':     display_score,
                        'top_label': pred_label,
                        'top_score': pred_score,
                        'timestamp': time.time()
                    })
                    if len(self.stutter_history) > self.STUTTER_HISTORY_LIMIT:
                        self.stutter_history.pop(0)

                    if self.AUDIO_DEBUG:
                        print(f"[STUTTER] Logged candidate: {display_label} "
                              f"score={display_score:.0%}")

            if is_stutter:
                self._log_stutter(
                    stutter_type=display_label,
                    score=display_score,
                    is_concerning=True,
                    top_label=pred_label,
                    top_confidence=pred_score,
                    combined_score=concern_score,
                    no_dysfluency_score=no_dysfluency_score,
                    rms=rms,
                    top3=top3,
                )

        except Exception as e:
            print(f"[AUDIO] wav2vec2 stutter error: {e}")
            self._librosa_stutter_fallback(audio, rms=rms)

    # librosa fallback for stutter detection
    # detects repetitions and blocks acoustically
    def _librosa_stutter_fallback(self, audio: np.ndarray,
                                  rms: float | None = None):
        try:
            onsets   = librosa.onset.onset_detect(
                y=audio, sr=self.SAMPLE_RATE, units='time'
            )
            duration = len(audio) / self.SAMPLE_RATE

            if len(onsets) < 2:
                with self._lock:
                    self.stutter_detected = False
                    self.stutter_type = ""
                    self.stutter_score = 0.0
                    self.is_concerning = False
                return

            gaps       = np.diff(onsets)
            short_gaps = int(np.sum(gaps < 0.15))
            repetition = short_gaps > 2

            frame_rms     = librosa.feature.rms(y=audio)[0]
            silence_ratio = float(np.sum(frame_rms < 0.01) / len(frame_rms))
            blocking      = silence_ratio > 0.4 and duration > 1.0
            window_rms = float(
                rms if rms is not None else np.sqrt(np.mean(audio ** 2))
            )

            stutter_type = None
            if repetition:
                stutter_type = "Sound Repetition"
            elif blocking:
                stutter_type = "Block"

            if self.AUDIO_DEBUG:
                print(f"[AUDIO DEBUG] Librosa stutter - "
                      f"short_gaps={short_gaps} "
                      f"silence={silence_ratio:.2f} "
                      f"result={stutter_type or 'None'}")

            with self._lock:
                self.stutter_detected = stutter_type is not None
                self.stutter_type     = stutter_type or ""
                self.stutter_score    = 0.6 if stutter_type else 0.0
                self.is_concerning    = (
                    stutter_type in self.CONCERNING_STUTTER_TYPES
                )

                if stutter_type:
                    self.stutter_history.append({
                        'type':      stutter_type,
                        'score':     0.6,
                        'top_label': stutter_type,
                        'top_score': 0.6,
                        'timestamp': time.time()
                    })
                    if len(self.stutter_history) > self.STUTTER_HISTORY_LIMIT:
                        self.stutter_history.pop(0)

                    if self.AUDIO_DEBUG:
                        print(f"[STUTTER] Logged fallback candidate: "
                              f"{stutter_type}")

            if stutter_type:
                concerning = stutter_type in self.CONCERNING_STUTTER_TYPES
                self._log_stutter(
                    stutter_type=stutter_type,
                    score=0.6,
                    is_concerning=concerning,
                    top_label=stutter_type,
                    top_confidence=0.6,
                    combined_score=0.6 if concerning else 0.0,
                    no_dysfluency_score=0.0,
                    rms=window_rms,
                    top3=f"{stutter_type}:0.6000",
                )

        except Exception as e:
            print(f"[AUDIO] Librosa stutter fallback error: {e}")

    # CSV logging for stutter events

    def _log_stutter(
            self,
            stutter_type: str,
            score: float,
            is_concerning: bool,
            top_label: str = "",
            top_confidence: float = 0.0,
            combined_score: float = 0.0,
            no_dysfluency_score: float = 0.0,
            rms: float = 0.0,
            top3: str = ""):
        try:
            log_dir  = "logs"
            os.makedirs(log_dir, exist_ok=True)
            date_str = datetime.date.today().strftime('%Y-%m-%d')
            log_file = os.path.join(log_dir, f"stutter_{date_str}.csv")
            header = [
                "timestamp", "patient_id", "stutter_type", "confidence",
                "is_concerning", "top_label", "top_confidence",
                "combined_stutter_score", "no_dysfluency_score", "rms",
                "top3_probabilities"
            ]

            file_exists = os.path.isfile(log_file)
            if file_exists:
                with open(log_file, "r", newline="") as existing:
                    first_line = existing.readline().strip()
                if first_line and first_line.split(",") != header:
                    log_file = os.path.join(
                        log_dir,
                        f"stutter_rich_{date_str}.csv"
                    )
                    file_exists = os.path.isfile(log_file)

            with open(log_file, "a", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(header)
                writer.writerow([
                    datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    self._config.patient_id,
                    stutter_type,
                    f"{score:.4f}",
                    is_concerning,
                    top_label,
                    f"{top_confidence:.4f}",
                    f"{combined_score:.4f}",
                    f"{no_dysfluency_score:.4f}",
                    f"{rms:.4f}",
                    top3,
                ])
            if self.AUDIO_DEBUG:
                print(f"[STUTTER] Logged to {log_file}")
        except Exception as e:
            print(f"[STUTTER] CSV log error: {e}")
