import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import queue
import threading
import time
import datetime
import difflib
import warnings
import logging
import numpy as np
import torch
import torchaudio
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
from speechbrain.inference.VAD import VAD
from speechbrain.inference.ASR import EncoderDecoderASR

from shared.config import Config


class SpeechAnalysisModule:

    SAMPLE_RATE    = 16000
    WINDOW_SECONDS = 3
    OVERLAP        = 0.5

    # emotions that indicate distress for dementia patients
    DISTRESS_EMOTIONS = [
        'ang',   # angry
        'sad',   # sad
        'fea',   # fearful
        'dis',   # disgusted
    ]

    # keywords to detect in transcription
    DISTRESS_KEYWORDS = [
        'help', 'pain', 'hurt', 'fall',
        'please', 'anyone', 'emergency',
        'stop', 'no', 'scared'
    ]

    CONFUSION_PHRASES = [
        'where am i', 'i dont know',
        'who are you', 'i want to go home',
        'whats happening', 'i dont understand',
        'where is', 'i forgot'
    ]

    def __init__(self, config: Config):
        self._config      = config
        self._lock        = threading.Lock()
        self._running     = False
        self.WINDOW_SECONDS = max(
            0.5,
            float(getattr(config, "distress_window_seconds", 2.0))
        )
        self.HOP_SECONDS = max(
            0.25,
            float(getattr(config, "distress_hop_seconds", 0.5))
        )
        self.AUDIO_BLOCK_SECONDS = max(
            0.05,
            float(getattr(config, "audio_block_seconds", 0.25))
        )
        self.SPEECH_QUEUE_SECONDS = max(
            self.AUDIO_BLOCK_SECONDS,
            float(getattr(config, "speech_queue_seconds", 3.0))
        )
        self.SPEECH_SILENCE_RMS = max(
            0.0001,
            float(getattr(config, "speech_silence_rms", 0.003))
        )
        self.SPEECH_TARGET_RMS = max(
            self.SPEECH_SILENCE_RMS,
            float(getattr(config, "speech_target_rms", 0.03))
        )
        self.SPEECH_MAX_GAIN = max(
            1.0,
            float(getattr(config, "speech_max_gain", 8.0))
        )
        self.SPEECH_VAD_THRESHOLD = max(
            0.05,
            min(0.95, float(getattr(config, "speech_vad_threshold", 0.35)))
        )
        self.SPEECH_FORCE_ASR_RMS = max(
            self.SPEECH_SILENCE_RMS,
            float(getattr(config, "speech_force_asr_rms", 0.01))
        )
        self.AUDIO_DEBUG = bool(getattr(config, "audio_debug", True))

        queue_size = max(4, int(self.SPEECH_QUEUE_SECONDS /
                                self.AUDIO_BLOCK_SECONDS))
        self._audio_queue = queue.Queue(maxsize=queue_size)

        self.emotion_detected    = False
        self.emotion             = "neutral"
        self.emotion_score       = 0.0
        self.is_distress_emotion = False
        self.keyword_detected    = False
        self.keyword             = ""
        self.confusion_detected  = False
        self.speech_active       = False
        self.transcript          = ""
        self._stutter_module     = None

        # cooldown: only alert once per keyword per window
        self._alert_cooldown     = {}
        self._ALERT_COOLDOWN_SEC = 60

        self._load_models()

    def set_stutter_module(self, stutter_module):
        self._stutter_module = stutter_module

    def _load_models(self):
        if self.AUDIO_DEBUG:
            print("[SPEECH] Loading SpeechBrain models...")

        # emotion recognition
        try:
            self._emotion_classifier = EncoderClassifier.from_hparams(
                source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                savedir="pretrained_models/emotion",
                run_opts={"device": "cpu"}
            )
            if self.AUDIO_DEBUG:
                print("[SPEECH] Emotion model loaded")
        except Exception as e:
            print(f"[SPEECH] Emotion model failed: {e}")
            self._emotion_classifier = None

        # voice activity detection
        try:
            self._vad = VAD.from_hparams(
                source="speechbrain/vad-crdnn-libriparty",
                savedir="pretrained_models/vad",
                run_opts={"device": "cpu"}
            )
            if self.AUDIO_DEBUG:
                print("[SPEECH] VAD model loaded")
        except Exception as e:
            print(f"[SPEECH] VAD model failed: {e}")
            self._vad = None

        # speech recognition (ASR)
        try:
            self._asr = EncoderDecoderASR.from_hparams(
                source="speechbrain/asr-conformer-transformerlm-librispeech",
                savedir="pretrained_models/asr",
                run_opts={"device": "cpu"}
            )
            if self.AUDIO_DEBUG:
                print("[SPEECH] ASR model loaded")
        except Exception as e:
            print(f"[SPEECH] ASR model failed: {e}")
            self._asr = None

        print("[SPEECH] Speech analysis models ready")

    # public interface

    def feed_audio(self, audio_chunk: np.ndarray):
        chunk = audio_chunk.astype(np.float32, copy=False).copy()
        try:
            self._audio_queue.put_nowait(chunk)
            return
        except queue.Full:
            pass

        try:
            self._audio_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self._audio_queue.put_nowait(chunk)
            if self.AUDIO_DEBUG:
                print("[SPEECH DEBUG] Dropped stale speech audio chunk")
        except queue.Full:
            if self.AUDIO_DEBUG:
                print("[SPEECH DEBUG] Skipped speech audio chunk; queue full")

    def start(self):
        self._running = True
        threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="SpeechAnalysis"
        ).start()
        print("[SPEECH] Speech analysis started")

    def stop(self):
        self._running = False
        print("[SPEECH] Speech analysis stopped")

    def get_state(self):
        with self._lock:
            return {
                'emotion':           self.emotion,
                'emotion_score':     self.emotion_score,
                'is_distress':       self.is_distress_emotion,
                'keyword_detected':  self.keyword_detected,
                'keyword':           self.keyword,
                'confusion':         self.confusion_detected,
                'speech_active':     self.speech_active,
                'transcript':        self.transcript,
            }

    # internal

    def _processing_loop(self):
        buffer     = np.array([], dtype=np.float32)
        chunk_size = int(self.SAMPLE_RATE * self.WINDOW_SECONDS)
        step_size  = int(self.SAMPLE_RATE * self.HOP_SECONDS)

        while self._running:
            try:
                chunks = [self._audio_queue.get(timeout=1)]
                while True:
                    try:
                        chunks.append(self._audio_queue.get_nowait())
                    except queue.Empty:
                        break

                buffer = np.concatenate([buffer, *chunks])
                if len(buffer) > chunk_size:
                    if self.AUDIO_DEBUG and len(chunks) > 1:
                        print(f"[SPEECH DEBUG] Caught up with "
                              f"{len(chunks)} queued chunks")
                    buffer = buffer[-chunk_size:]

                if len(buffer) >= chunk_size:
                    window = buffer[-chunk_size:]
                    keep = max(0, chunk_size - step_size)
                    buffer = buffer[-keep:] if keep else np.array(
                        [], dtype=np.float32
                    )
                    self._analyze_window(window)

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[SPEECH ERROR] {e}")

    def _analyze_window(self, audio: np.ndarray):
        if self._stutter_module:
            self._stutter_module.feed_audio(audio)

        # skip silent windows
        started_at = time.perf_counter()
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < self.SPEECH_SILENCE_RMS:
            with self._lock:
                self.speech_active = False
                self.keyword_detected = False
                self.keyword = ""
            return

        analysis_audio, gain = self._normalize_speech_audio(audio, rms)

        # convert to tensor
        waveform = torch.FloatTensor(analysis_audio).unsqueeze(0)

        # voice activity detection
        vad_started = time.perf_counter()
        speech_detected = self._run_vad(waveform)
        vad_seconds = time.perf_counter() - vad_started
        if not speech_detected and rms >= self.SPEECH_FORCE_ASR_RMS:
            speech_detected = True
            if self.AUDIO_DEBUG:
                print(f"[SPEECH DEBUG] Forcing ASR despite VAD "
                      f"rms={rms:.4f}")
        with self._lock:
            self.speech_active = speech_detected

        if not speech_detected:
            if self.AUDIO_DEBUG:
                print(f"[SPEECH DEBUG] No speech rms={rms:.4f} "
                      f"vad_time={vad_seconds:.2f}s")
            return

        # speech recognition + keyword check
        asr_started = time.perf_counter()
        transcript, keyword, confusion = self._run_asr(analysis_audio)
        asr_seconds = time.perf_counter() - asr_started

        # emotion recognition
        emotion_started = time.perf_counter()
        emotion, score = self._run_emotion(waveform)
        emotion_seconds = time.perf_counter() - emotion_started

        # update public state
        with self._lock:
            self.emotion             = emotion
            self.emotion_score       = score
            self.is_distress_emotion = emotion in self.DISTRESS_EMOTIONS
            self.transcript          = transcript
            self.keyword_detected    = keyword is not None
            self.keyword             = keyword or ""
            self.confusion_detected  = confusion is not None

            if self.is_distress_emotion and self.AUDIO_DEBUG:
                print(f"[SPEECH] Distress emotion: "
                      f"{emotion} ({score:.0%})")
            if keyword:
                print(f"[SPEECH] Distress keyword: '{keyword}'")
            if confusion:
                print(f"[SPEECH] Confusion phrase: '{confusion}'")
            if transcript and self.AUDIO_DEBUG:
                print(f"[SPEECH] Heard: {transcript}")

            if self.AUDIO_DEBUG:
                total_seconds = time.perf_counter() - started_at
                print(f"[SPEECH DEBUG] rms={rms:.4f} "
                      f"gain={gain:.1f}x "
                      f"queue={self._audio_queue.qsize()} "
                      f"vad={vad_seconds:.2f}s "
                      f"asr={asr_seconds:.2f}s "
                      f"emotion={emotion_seconds:.2f}s "
                      f"total={total_seconds:.2f}s")

        # fire distress alert outside the lock
        if keyword and self._should_alert(keyword):
            self._send_distress_alert(keyword)

    def _normalize_speech_audio(self, audio: np.ndarray, rms: float):
        if rms <= 0:
            return audio, 1.0

        gain = min(self.SPEECH_MAX_GAIN, self.SPEECH_TARGET_RMS / rms)
        if gain <= 1.01:
            return audio, 1.0

        normalized = np.clip(audio * gain, -1.0, 1.0).astype(np.float32)
        return normalized, gain

    def _should_alert(self, keyword: str) -> bool:
        now = time.time()
        last = self._alert_cooldown.get(keyword, 0)
        if now - last < self._ALERT_COOLDOWN_SEC:
            return False
        self._alert_cooldown[keyword] = now
        return True

    def _send_distress_alert(self, keyword: str):
        payload = {
            "deviceId":  self._config.device_id,
            "patientId": self._config.patient_id,
            "room":      self._config.room,
            "eventType": "Distress Detected",
            "timestamp": datetime.datetime.now().isoformat(),
            "keyword":   keyword,
        }

        print(f"[SPEECH] Sending distress alert: keyword='{keyword}'")

        def post_with_retry():
            attempt = 0
            while True:
                try:
                    response = requests.post(
                        f"{self._config.backend_url}/alert/distress",
                        json=payload,
                        timeout=10,
                        verify=False,
                    )
                    if response.status_code == 201:
                        print("[SPEECH] Distress alert sent successfully.")
                        break
                    else:
                        print(f"[SPEECH] Unexpected status "
                              f"{response.status_code}, retrying...")
                except requests.exceptions.RequestException as e:
                    print(f"[SPEECH] Alert attempt {attempt} failed: "
                          f"{e}, retrying in 5s...")
                attempt += 1
                time.sleep(5)

        threading.Thread(target=post_with_retry, daemon=True).start()

    def _run_vad(self, waveform: torch.Tensor) -> bool:
        if self._vad is None:
            return True  # assume speech if VAD unavailable

        try:
            import tempfile
            with tempfile.NamedTemporaryFile(
                suffix='.wav', delete=False
            ) as tmp:
                tmp_path = tmp.name
            speechbrain_path = os.path.abspath(tmp_path).replace("\\", "/")

            torchaudio.save(tmp_path, waveform, self.SAMPLE_RATE)
            prob = self._vad.get_speech_prob_file(speechbrain_path)
            os.remove(tmp_path)

            return float(prob.mean()) > self.SPEECH_VAD_THRESHOLD

        except Exception as e:
            print(f"[SPEECH] VAD error: {e}")
            return True

    def _run_emotion(self, waveform: torch.Tensor):
        if self._emotion_classifier is None:
            return "neutral", 0.0

        try:
            out_prob, score, index, label = self._classify_emotion(waveform)

            emotion = label[0].strip()
            confidence = float(score[0])
            return emotion, confidence

        except Exception as e:
            print(f"[SPEECH] Emotion error: {e}")
            return "neutral", 0.0

    def _classify_emotion(self, waveform: torch.Tensor):
        if hasattr(self._emotion_classifier.mods, "wav2vec2"):
            wav_lens = torch.ones(
                waveform.shape[0],
                device=self._emotion_classifier.device
            )
            waveform = waveform.to(self._emotion_classifier.device).float()
            with torch.no_grad():
                feats = self._emotion_classifier.mods.wav2vec2(
                    waveform,
                    wav_lens
                )
                pooled = self._emotion_classifier.mods.avg_pool(
                    feats,
                    wav_lens
                )
                logits = self._emotion_classifier.mods.output_mlp(pooled)
                out_prob = self._emotion_classifier.hparams.softmax(logits)
            scores = out_prob.squeeze(1) if out_prob.dim() == 3 else out_prob
            score, index = torch.max(scores, dim=-1)
            label = self._emotion_classifier.hparams.label_encoder.decode_torch(
                index
            )
            return out_prob, score, index, label

        return self._emotion_classifier.classify_batch(waveform)

    def _run_asr(self, audio: np.ndarray):
        if self._asr is None:
            return "", None, None

        try:
            import tempfile
            waveform = torch.FloatTensor(audio).unsqueeze(0)

            with tempfile.NamedTemporaryFile(
                suffix='.wav', delete=False
            ) as tmp:
                tmp_path = tmp.name
            speechbrain_path = os.path.abspath(tmp_path).replace("\\", "/")

            torchaudio.save(tmp_path, waveform, self.SAMPLE_RATE)
            transcript = self._asr.transcribe_file(speechbrain_path)
            os.remove(tmp_path)

            transcript = transcript.lower().strip()

            keyword_hit = self._match_distress_keyword(transcript)

            confusion_hit = None
            for phrase in self.CONFUSION_PHRASES:
                if phrase in transcript:
                    confusion_hit = phrase
                    break

            return transcript, keyword_hit, confusion_hit

        except Exception as e:
            print(f"[SPEECH] ASR error: {e}")
            return "", None, None

    def _match_distress_keyword(self, transcript: str):
        words = [
            word.strip(".,!?;:-()[]{}\"'")
            for word in transcript.split()
        ]
        words = [word for word in words if word]

        for kw in self.DISTRESS_KEYWORDS:
            if kw in transcript:
                return kw

        # SpeechBrain ASR often returns short near-misses for urgent words on
        # low-volume Kinect mic audio. Keep this conservative and keyword-only.
        for word in words:
            for kw in self.DISTRESS_KEYWORDS:
                if len(kw) < 4 or len(word) < 3:
                    continue
                ratio = difflib.SequenceMatcher(None, word, kw).ratio()
                if ratio >= 0.72:
                    if self.AUDIO_DEBUG:
                        print(f"[SPEECH DEBUG] Fuzzy keyword match: "
                              f"{word!r} -> {kw!r} ({ratio:.2f})")
                    return kw

        help_near_misses = {
            "elp", "halp", "hell", "held", "helt", "hep", "hop", "up"
        }
        help_asr_aliases = {
            "hope", "herb", "helped", "helpe"
        }
        if any(word in help_near_misses for word in words):
            if self.AUDIO_DEBUG:
                print(f"[SPEECH DEBUG] Help near-miss transcript: "
                      f"{transcript!r}")
            return "help"

        if len(words) <= 3 and any(word in help_asr_aliases
                                   for word in words):
            if self.AUDIO_DEBUG:
                print(f"[SPEECH DEBUG] Kinect help alias transcript: "
                      f"{transcript!r}")
            return "help"

        return None
