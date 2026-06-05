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
            )
        except KeyError as e:
            sys.exit(f"[ERROR] Missing required config key: {e} ...Exiting")