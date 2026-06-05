import os
import queue
import threading
import time
import numpy as np
import torch
from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor

from shared.config import Config


class StutterDetectionModule:

    SAMPLE_RATE    = 16000
    WINDOW_SECONDS = 3
    OVERLAP        = 0.5

    # stutter types from sep-28k dataset
    STUTTER_LABELS = {
        0: 'Prolongation',
        1: 'Block',
        2: 'Sound Repetition',
        3: 'Word Repetition',
        4: 'Interjection',
        5: 'No Dysfluency',
    }

    # which types indicate distress or cognitive issue
    CONCERNING_TYPES = [
        'Prolongation',
        'Block',
        'Sound Repetition',
        'Word Repetition',
    ]

    def __init__(self, config: Config):
        self._config      = config
        self._lock        = threading.Lock()
        self._audio_queue = queue.Queue()
        self._running     = False

        # Assign execution device dynamically 
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # public state
        self.stutter_detected  = False
        self.stutter_type      = ""
        self.stutter_score     = 0.0
        self.is_concerning     = False
        self.stutter_history   = []  # last 10 detections

        self._load_model()

    def _load_model(self):
        # FIX 1: Point path to your local fine-tuned outputs folder
        model_path = 'stutter_model/final'
        
        if not os.path.exists(model_path):
            print(f"[STUTTER] Fine-tuned path '{model_path}' not found. Falling back to base configurations...")
            model_path = "facebook/wav2vec2-base"

        print(f"[STUTTER] Loading wav2vec2 model from: {model_path} on {self.device}...")
        try:
            self._processor = Wav2Vec2Processor.from_pretrained(model_path)
            
            # Load weights and immediately map them onto target computing architecture
            self._model = Wav2Vec2ForSequenceClassification.from_pretrained(
                model_path,
                num_labels=len(self.STUTTER_LABELS),
                ignore_mismatched_sizes=True
            ).to(self.device)
            
            self._model.eval()
            print("[STUTTER] Model loaded successfully.")
        except Exception as e:
            print(f"[STUTTER] Model load failed: {e}")
            self._model     = None
            self._processor = None

    # public interface
    def feed_audio(self, audio_chunk: np.ndarray):
        self._audio_queue.put(audio_chunk.copy())

    def start(self):
        self._running = True
        threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="StutterDetection"
        ).start()
        print("[STUTTER] Stutter detection started")

    def stop(self):
        self._running = False
        print("[STUTTER] Stutter detection stopped")

    def get_state(self):
        with self._lock:
            return {
                'detected':    self.stutter_detected,
                'type':        self.stutter_type,
                'score':       self.stutter_score,
                'concerning':  self.is_concerning,
                'history':     list(self.stutter_history),
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
                    self._analyze(window)

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[STUTTER ERROR] {e}")

    def _analyze(self, audio: np.ndarray):
        # skip silent chunks
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.005:
            return

        if self._model is None:
            self._rule_based_detection(audio)
            return

        try:
            # Tokenize audio stream array
            inputs = self._processor(
                audio,
                sampling_rate=self.SAMPLE_RATE,
                return_tensors="pt",
                padding=True
            )

            # FIX 2: Explicitly move processed input tensors onto the correct execution device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                # FIX 3: Unpack keys directly (**inputs) to carry attention masks along cleanly
                logits = self._model(**inputs).logits

            probs      = torch.softmax(logits, dim=-1)[0]
            pred_idx   = torch.argmax(probs).item()
            pred_score = probs[pred_idx].item()
            pred_label = self.STUTTER_LABELS[pred_idx]

            is_stutter    = pred_label != 'No Dysfluency'
            is_concerning = pred_label in self.CONCERNING_TYPES

            with self._lock:
                self.stutter_detected = is_stutter
                self.stutter_type     = pred_label if is_stutter else ""
                self.stutter_score    = pred_score
                self.is_concerning    = is_concerning

                if is_stutter:
                    self.stutter_history.append({
                        'type':      pred_label,
                        'score':     pred_score,
                        'timestamp': time.time()
                    })
                    if len(self.stutter_history) > 10:
                        self.stutter_history.pop(0)

                    print(f"[STUTTER] {pred_label} "
                          f"({pred_score:.0%})"
                          + (" !!!" if is_concerning else ""))

        except Exception as e:
            print(f"[STUTTER] Analysis error: {e}")
            self._rule_based_detection(audio)

    def _rule_based_detection(self, audio: np.ndarray):
        try:
            import librosa

            # detect onsets (syllable-like events)
            onsets   = librosa.onset.onset_detect(
                y=audio, sr=self.SAMPLE_RATE, units='time'
            )
            duration = len(audio) / self.SAMPLE_RATE

            if len(onsets) < 2:
                return

            # check for repetitive patterns
            gaps        = np.diff(onsets)
            short_gaps    = np.sum(gaps < 0.15)  # < 150ms = repetition
            repetition    = short_gaps > 2

            # check for long silences (blocks)
            rms           = librosa.feature.rms(y=audio)[0]
            silence_segs  = np.sum(rms < 0.01)
            silence_ratio = silence_segs / len(rms)
            blocking      = silence_ratio > 0.4 and duration > 1.0

            stutter_type = None
            if repetition:
                stutter_type = "Sound Repetition"
            elif blocking:
                stutter_type = "Block"

            with self._lock:
                self.stutter_detected = stutter_type is not None
                self.stutter_type     = stutter_type or ""
                self.is_concerning    = stutter_type in self.CONCERNING_TYPES

                if stutter_type:
                    print(f"[STUTTER] Rule-based: {stutter_type}")

        except Exception as e:
            print(f"[STUTTER] Rule-based error: {e}")