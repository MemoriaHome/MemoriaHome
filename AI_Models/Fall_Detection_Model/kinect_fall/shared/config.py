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
            )
        except KeyError as e:
            sys.exit(f"[ERROR] Missing required config key: {e} ...Exiting")
