import json
import sys
from dataclasses import dataclass


@dataclass
class Config:
    device_id: str
    patient_id: str
    room: str
    backend_url: str
    recording_path: str
    signaling_url: str = ""
    kinect_audio_device: str | int | None = None
    stream_width: int = 960
    stream_height: int = 540
    stream_fps: int = 15
    capture_fps: int = 15
    fall_detection_fps: int = 10
    face_recognition_fps: int = 5
    live_stream_fps: int = 15
    compositor_fps: int = 15
    display_fps: int = 15
    audio_threshold: float = 0.6
    audio_cooldown_seconds: int = 30
    audio_block_seconds: float = 0.25
    distress_window_seconds: float = 2.0
    distress_hop_seconds: float = 0.5
    speech_queue_seconds: float = 3.0
    speech_silence_rms: float = 0.003
    speech_target_rms: float = 0.03
    speech_max_gain: float = 8.0
    speech_vad_threshold: float = 0.35
    speech_force_asr_rms: float = 0.01
    stutter_window_seconds: float = 3.0
    stutter_hop_seconds: float = 1.5
    audio_debug: bool = True
    stutter_log_only: bool = True

    @staticmethod
    def load(path: str = "config.json") -> "Config":
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            sys.exit(f"[ERROR] Config file not found: {path} ...Exiting")
        except json.JSONDecodeError:
            sys.exit("[ERROR] config.json contains invalid JSON. Check syntax ...Exiting")

        try:
            return Config(
                device_id=data['device_id'],
                patient_id=data['patient_id'],
                room=data['room'],
                backend_url=data['backend_url'],
                recording_path=data['recording_path'],
                signaling_url=data.get('signaling_url', data['backend_url']),
                kinect_audio_device=data.get('kinect_audio_device'),
                stream_width=int(data.get('stream_width', 960)),
                stream_height=int(data.get('stream_height', 540)),
                stream_fps=int(data.get('stream_fps', 15)),
                capture_fps=int(data.get('capture_fps', 15)),
                fall_detection_fps=int(data.get('fall_detection_fps', 10)),
                face_recognition_fps=int(data.get('face_recognition_fps', 5)),
                live_stream_fps=int(data.get('live_stream_fps', 15)),
                compositor_fps=int(data.get('compositor_fps', 15)),
                display_fps=int(data.get('display_fps', 15)),
                audio_threshold=float(data.get('audio_threshold', 0.6)),
                audio_cooldown_seconds=int(data.get('audio_cooldown_seconds', 30)),
                audio_block_seconds=float(data.get('audio_block_seconds', 0.25)),
                distress_window_seconds=float(data.get('distress_window_seconds', 2.0)),
                distress_hop_seconds=float(data.get('distress_hop_seconds', 0.5)),
                speech_queue_seconds=float(data.get('speech_queue_seconds', 3.0)),
                speech_silence_rms=float(data.get('speech_silence_rms', 0.003)),
                speech_target_rms=float(data.get('speech_target_rms', 0.03)),
                speech_max_gain=float(data.get('speech_max_gain', 8.0)),
                speech_vad_threshold=float(data.get('speech_vad_threshold', 0.35)),
                speech_force_asr_rms=float(data.get('speech_force_asr_rms', 0.01)),
                stutter_window_seconds=float(data.get('stutter_window_seconds', 3.0)),
                stutter_hop_seconds=float(data.get('stutter_hop_seconds', 1.5)),
                audio_debug=bool(data.get('audio_debug', True)),
                stutter_log_only=bool(data.get('stutter_log_only', True)),
            )
        except KeyError as e:
            sys.exit(f"[ERROR] Missing required config key: {e} ...Exiting")
