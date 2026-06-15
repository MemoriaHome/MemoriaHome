import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import queue
import threading
import time
import datetime
import numpy as np
import torch
import torchaudio
import requests

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        self._audio_queue = queue.Queue()
        self._running     = False

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
        print("[SPEECH] Loading SpeechBrain models...")

        # emotion recognition
        try:
            self._emotion_classifier = EncoderClassifier.from_hparams(
                source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                savedir="pretrained_models/emotion",
                run_opts={"device": "cpu"}
            )
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
            print("[SPEECH] ASR model loaded")
        except Exception as e:
            print(f"[SPEECH] ASR model failed: {e}")
            self._asr = None

        print("[SPEECH] SpeechBrain models ready")

    # public interface

    def feed_audio(self, audio_chunk: np.ndarray):
        self._audio_queue.put(audio_chunk.copy())

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
        step_size  = int(chunk_size * (1 - self.OVERLAP))

        while self._running:
            try:
                chunk  = self._audio_queue.get(timeout=1)
                buffer = np.concatenate([buffer, chunk])

                if len(buffer) >= chunk_size:
                    window = buffer[:chunk_size]
                    buffer = buffer[step_size:]
                    self._analyze_window(window)

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[SPEECH ERROR] {e}")

    def _analyze_window(self, audio: np.ndarray):
        if self._stutter_module:
            self._stutter_module.feed_audio(audio)

        # skip silent windows
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.005:
            with self._lock:
                self.speech_active = False
            return

        # convert to tensor
        waveform = torch.FloatTensor(audio).unsqueeze(0)

        # voice activity detection
        speech_detected = self._run_vad(waveform)
        with self._lock:
            self.speech_active = speech_detected

        if not speech_detected:
            return

        # emotion recognition
        emotion, score = self._run_emotion(waveform)

        # speech recognition + keyword check
        transcript, keyword, confusion = self._run_asr(audio)

        # update public state
        with self._lock:
            self.emotion             = emotion
            self.emotion_score       = score
            self.is_distress_emotion = emotion in self.DISTRESS_EMOTIONS
            self.transcript          = transcript
            self.keyword_detected    = keyword is not None
            self.keyword             = keyword or ""
            self.confusion_detected  = confusion is not None

            if self.is_distress_emotion:
                print(f"[SPEECH] Distress emotion: "
                      f"{emotion} ({score:.0%})")
            if keyword:
                print(f"[SPEECH] Distress keyword: '{keyword}'")
            if confusion:
                print(f"[SPEECH] Confusion phrase: '{confusion}'")
            if transcript:
                print(f"[SPEECH] Heard: {transcript}")

        # fire distress alert outside the lock
        if keyword and self._should_alert(keyword):
            self._send_distress_alert(keyword)

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

        print(f"[SPEECH] Sending distress alert — keyword: '{keyword}'")

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

            torchaudio.save(tmp_path, waveform, self.SAMPLE_RATE)
            prob = self._vad.get_speech_prob_file(tmp_path)
            os.remove(tmp_path)

            return float(prob.mean()) > 0.5

        except Exception as e:
            print(f"[SPEECH] VAD error: {e}")
            return True

    def _run_emotion(self, waveform: torch.Tensor):
        if self._emotion_classifier is None:
            return "neutral", 0.0

        try:
            out_prob, score, index, label = \
                self._emotion_classifier.classify_batch(waveform)

            emotion = label[0].strip()
            confidence = float(score[0])
            return emotion, confidence

        except Exception as e:
            print(f"[SPEECH] Emotion error: {e}")
            return "neutral", 0.0

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

            torchaudio.save(tmp_path, waveform, self.SAMPLE_RATE)
            transcript = self._asr.transcribe_file(tmp_path)
            os.remove(tmp_path)

            transcript = transcript.lower().strip()

            keyword_hit = None
            for kw in self.DISTRESS_KEYWORDS:
                if kw in transcript:
                    keyword_hit = kw
                    break

            confusion_hit = None
            for phrase in self.CONFUSION_PHRASES:
                if phrase in transcript:
                    confusion_hit = phrase
                    break

            return transcript, keyword_hit, confusion_hit

        except Exception as e:
            print(f"[SPEECH] ASR error: {e}")
            return "", None, None