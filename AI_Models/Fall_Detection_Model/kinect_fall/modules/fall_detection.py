import os
import io
import time
import json
import queue
import datetime
import tempfile
import threading
import subprocess

import cv2
import numpy as np
import boto3
import requests
from botocore.config import Config as BotoConfig
from ultralytics import YOLO
from pykinect2.PyKinectV2 import JointType_SpineBase

from modules.base_module import BaseModule
from shared.config import Config
from modules.audio_detection import AudioDetectionModule


class FallDetectionModule(BaseModule):

    MIN_ELAPSED_TIME          = 10
    VIDEO_FPS                 = 15
    MAX_AFTER_FRAMES          = 150
    MAX_BEFORE_FRAMES         = 100
    FLOOR_FALLEN_THRESHOLD    = 0.4
    FLOOR_RECOVERED_THRESHOLD = 0.6
    FALL_VELOCITY_THRESHOLD   = 0.3
    SLOW_FALL_FLOOR_DURATION  = 5.0
    VELOCITY_JITTER_FLOOR     = 0.05


    def __init__(self, frame_queue: queue.Queue, config: Config,
                 annotated_queue: queue.Queue = None,
                 command_queue: queue.Queue = None,
                 verbose: bool = False):
        super().__init__(frame_queue)
        self._verbose         = verbose
        self._config          = config
        self._annotated_queue = annotated_queue
        self._command_queue   = command_queue
        self._model           = YOLO('yolo models/yolov8n-pose.pt')

        r2_account_id        = os.environ["R2_ACCOUNT_ID"]
        r2_access_key_id     = os.environ["R2_ACCESS_KEY_ID"]
        r2_secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"]
        self._r2_public_url  = os.environ["R2_PUBLIC_URL"]
        self._bucket         = os.environ.get("R2_BUCKET", "fall-detection")

        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=r2_access_key_id,
            aws_secret_access_key=r2_secret_access_key,
            config=BotoConfig(signature_version='s3v4'),
            region_name="auto",
        )

        self._fallen_state               = False
        self._fall_start_time            = None
        self._taking_video               = False
        self._video_frames_before        = []
        self._video_frames_after         = []
        self._frozen_video_frames_before = []
        self._video_blob_name            = ""
        self._incident_name              = ""
        self._blob_number                = 1
        self._audio_module               = None

        self._spine_history = [] 

        self._floor_contact_start: float | None = None

        self._locked_body_index: int | None = None
        self._locked_body_last_seen: float  = 0.0
        BODY_LOCK_TIMEOUT                   = 3.0


    def set_audio_module(self, audio_module: AudioDetectionModule):
        self._audio_module = audio_module

    # Core frame processing

    def _process_frame(self, frame) -> None:
        self._handle_commands()
        color = frame.color
        if color is None:
            return

        # Rolling before-buffer
        self._video_frames_before.append(color.copy())
        if len(self._video_frames_before) > self.MAX_BEFORE_FRAMES:
            self._video_frames_before.pop(0)

        # After-buffer when fall is triggered
        if self._taking_video:
            self._video_frames_after.append(color.copy())
            if len(self._video_frames_after) > self.MAX_AFTER_FRAMES:
                self._video_frames_after.pop(0)

        # YOLO inference
        results = self._model.predict(color, conf=0.4, verbose=False)
        r       = results[0]

        # Body tracking
        height_from_floor  = 0.0
        is_on_floor        = False
        body_frame_updated = False
        bodies             = None

        if frame.body_frame:
            bodies      = frame.body_frame
            floor_plane = bodies.floor_clip_plane

            # Resolve which body index to evaluate this frame
            body_index = self._resolve_body_index(bodies)

            if body_index is not None:
                body              = bodies.bodies[body_index]
                spine             = body.joints[JointType_SpineBase].Position
                height_from_floor = self._height_above_floor(spine, floor_plane)
                abs_height        = abs(height_from_floor)

                is_on_floor        = abs_height < self.FLOOR_FALLEN_THRESHOLD
                body_frame_updated = True

                now = time.time()
                self._spine_history.append((now, abs_height))
                # Keep only the last 2 seconds of samples
                cutoff = now - 2.0
                self._spine_history = [
                    (t, h) for t, h in self._spine_history if t >= cutoff
                ]

                velocity = self._calculate_velocity()
                if self._verbose:
                    print(f"[Body {body_index}] Raw: {height_from_floor:.2f}m | "
                          f"Abs: {abs_height:.2f}m | "
                          f"Velocity: {velocity:.2f}m/s")

        # Audio state
        audio_distress = False
        if self._audio_module:
            audio_state    = self._audio_module.get_state()
            audio_distress = audio_state['detected']
            if audio_distress:
                print(f"[AUDIO] Distress: {audio_state['label']} "
                      f"({audio_state['confidence']:.0%})")

        # Fall trigger logic
        velocity     = self._calculate_velocity()
        is_fast_drop = velocity > self.FALL_VELOCITY_THRESHOLD

        if is_on_floor and not self._fallen_state:
            if is_fast_drop:
                print(f"ALERT: Fast fall detected. "
                      f"{velocity:.2f}m/s. Monitoring...")
                self._trigger_fall(reason="fast_drop")

            elif audio_distress:
                print("ALERT: Floor contact + audio distress. Monitoring...")
                self._trigger_fall(reason="audio_distress")

            else:
                if self._floor_contact_start is None:
                    self._floor_contact_start = time.time()
                if self._verbose:
                        print(f"Floor contact but slow descent "
                              f"({velocity:.2f}m/s) — starting slow-fall timer")

                elapsed_floor = time.time() - self._floor_contact_start
                if elapsed_floor >= self.SLOW_FALL_FLOOR_DURATION:
                    print(f"ALERT: Prolonged floor contact "
                          f"({elapsed_floor:.1f}s) — possible slow collapse")
                    self._trigger_fall(reason="prolonged_floor_contact")

        elif not is_on_floor:
            # Person stood up (or was never on floor), clear slow-fall timer
            self._floor_contact_start = None

        # Post-trigger monitoring
        if self._fallen_state and body_frame_updated:
            elapsed = time.time() - self._fall_start_time

            if bodies is not None:
                any_tracked = any(
                    bodies.bodies[i].is_tracked for i in range(6)
                )
                if not any_tracked:
                    print("Body lost from frame — cancelling fall alert")
                    self._reset_fall_state()
                    return

            if abs(height_from_floor) > self.FLOOR_RECOVERED_THRESHOLD:
                print("Recovery detected.")
                threading.Thread(
                    target=self._save_video_clip,
                    args=("Recovered Fall",
                          list(self._frozen_video_frames_before),
                          list(self._video_frames_after)),
                    daemon=True,
                ).start()
                self._reset_fall_state()
            elif elapsed >= self.MIN_ELAPSED_TIME:
                print("FALL CONFIRMED.")
                threading.Thread(
                    target=self._save_video_clip,
                    args=("Unrecovered Fall",
                          list(self._frozen_video_frames_before),
                          list(self._video_frames_after)),
                    daemon=True,
                ).start()
                self._reset_fall_state()

        # Annotated display
        if self._annotated_queue is not None:
            annotated  = r.plot()
            status     = "STATUS: FALLING" if self._fallen_state else "STATUS: SAFE"
            color_text = (0, 0, 255) if self._fallen_state else (0, 255, 0)
            cv2.putText(annotated, status, (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, color_text, 2)
            cv2.putText(annotated,
                        f"Velocity: {velocity:.2f}m/s",
                        (50, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 0), 1)

            # Show slow-fall timer on screen when active
            if self._floor_contact_start is not None and not self._fallen_state:
                elapsed_floor = time.time() - self._floor_contact_start
                cv2.putText(annotated,
                            f"Floor timer: {elapsed_floor:.1f}s / "
                            f"{self.SLOW_FALL_FLOOR_DURATION:.0f}s",
                            (50, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 165, 255), 1)

            try:
                self._annotated_queue.put_nowait(annotated)
            except queue.Full:
                pass

    # Body index resolution

    def _resolve_body_index(self, bodies) -> int | None:
        BODY_LOCK_TIMEOUT = 3.0
        now = time.time()

        # Check if locked body is still tracked
        if self._locked_body_index is not None:
            body = bodies.bodies[self._locked_body_index]
            if body.is_tracked:
                self._locked_body_last_seen = now
                return self._locked_body_index

            # If lock expired
            if now - self._locked_body_last_seen > BODY_LOCK_TIMEOUT:
                if self._verbose:
                    print(f"[BODY] Lock on body {self._locked_body_index} expired "
                          f"— releasing")
                self._locked_body_index = None
            else:
                return None

        # Acquire a new lock on the first tracked body
        for i in range(6):
            if bodies.bodies[i].is_tracked:
                self._locked_body_index     = i
                self._locked_body_last_seen = now
                if self._verbose:
                    print(f"[BODY] Locked onto body index {i}")
                return i

        return None

    # Fall state transitions

    def _trigger_fall(self, reason: str = ""):
        self._fallen_state               = True
        self._fall_start_time            = time.time()
        self._taking_video               = True
        self._frozen_video_frames_before = list(self._video_frames_before)
        self._floor_contact_start        = None   # stop slow-fall timer
        if reason:
            print(f"[FALL] Triggered — reason: {reason}")

    def _reset_fall_state(self):
        self._fallen_state               = False
        self._taking_video               = False
        self._video_frames_after         = []
        self._frozen_video_frames_before = []
        self._spine_history              = []
        self._floor_contact_start        = None
        self._locked_body_index          = None

    # Velocity calculation

    def _calculate_velocity(self) -> float:
        if len(self._spine_history) < 3:
            return 0.0

        oldest_t, oldest_h = self._spine_history[0]
        latest_t,  latest_h = self._spine_history[-1]
        dt = latest_t - oldest_t

        if dt < 1e-6:
            return 0.0

        # Positive when height decreased (person moved toward floor)
        drop = oldest_h - latest_h
        velocity = drop / dt

        # Suppress Kinect jitter
        if abs(velocity) < self.VELOCITY_JITTER_FLOOR:
            return 0.0

        return velocity

    # Helpers

    @staticmethod
    def _height_above_floor(joint_position, floor_plane) -> float:
        A, B, C, D = floor_plane.x, floor_plane.y, floor_plane.z, floor_plane.w
        x, y, z   = joint_position.x, joint_position.y, joint_position.z
        return (A * x) + (B * y) + (C * z) + D

    # Video & upload

    def _save_video_clip(self, event_type: str, before_frames: list, after_frames: list):
        clip_frames = before_frames + after_frames
        if not clip_frames:
            return

        print(f"Saving clip for event: {event_type}")
        h, w, _ = clip_frames[0].shape

        # Local save
        date_str   = datetime.date.today().strftime('%Y-%m-%d')
        time_str   = datetime.datetime.now().strftime('%H-%M-%S')
        local_dir  = os.path.join(self._config.recording_path, date_str)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"Fall_{time_str}.mp4")

        out_local = cv2.VideoWriter(
            local_path, cv2.VideoWriter_fourcc(*'mp4v'), self.VIDEO_FPS, (w, h)
        )
        for frm in clip_frames:
            out_local.write(frm)
        out_local.release()
        print("[LOG] Local copy saved.")

        # Temp file for R2 upload
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            temp_path = tmp.name

        out_cloud = cv2.VideoWriter(
            temp_path, cv2.VideoWriter_fourcc(*'mp4v'), self.VIDEO_FPS, (w, h)
        )
        for frm in clip_frames:
            out_cloud.write(frm)
        out_cloud.release()
        print("[LOG] Temp created")

        h264_path = temp_path.replace(".mp4", "_h264.mp4")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", temp_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-preset", "medium",
            "-crf", "23",
            h264_path,
        ]
        subprocess.run(ffmpeg_cmd, check=True)
        print("[LOG] Conversion complete.")

        self._upload_clip_to_r2(h264_path)
        self._save_info_in_r2()
        self._send_api_call(event_type)

        for path in (temp_path, h264_path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _upload_clip_to_r2(self, clip_path: str):
        try:
            name = f"fallen_clip_{int(time.time())}.mp4"
            with open(clip_path, "rb") as f:
                self._s3.upload_fileobj(f, self._bucket, name)
            self._video_blob_name = name
            print(f"Uploaded video: {name}")
        except Exception as e:
            print(f"Error uploading video: {e}")

    def _save_info_in_r2(self):
        try:
            info = {
                "status":    "Fallen",
                "timestamp": str(time.time()),
                "filename":  self._video_blob_name,
            }
            self._incident_name = f"incident_{self._blob_number}_{int(time.time())}"
            self._blob_number  += 1
            self._s3.upload_fileobj(
                io.BytesIO(json.dumps(info).encode("utf-8")),
                self._bucket,
                self._incident_name,
            )
            print(f"Uploaded incident JSON: {self._incident_name}")
        except Exception as e:
            print(f"Error uploading incident JSON: {e}")

    def _send_api_call(self, event_type: str):
        speech_state = {}
        if (self._audio_module and
                hasattr(self._audio_module, '_speech_module') and
                self._audio_module._speech_module):
            speech_state = self._audio_module._speech_module.get_state()

        payload = {
            "deviceId":      self._config.device_id,
            "patientId":     self._config.patient_id,
            "room":          self._config.room,
            "eventType":     event_type,
            "timestamp":     datetime.datetime.now().isoformat(),
            "videoUrl":      f"{self._r2_public_url}/{self._video_blob_name}",
            "incidentName":  self._incident_name,
            "emotion":       speech_state.get('emotion', ''),
            "distressWord":  speech_state.get('keyword', ''),
            "confusion":     speech_state.get('confusion', False),
            "transcript":    speech_state.get('transcript', ''),
        }

        def post_with_retry():
            attempt = 0
            while True:
                try:
                    response = requests.post(
                        f"{self._config.backend_url}/alert/fall",
                        json=payload,
                        timeout=10,
                        verify=False,
                    )
                    if response.status_code == 201:
                        print("Alert sent successfully.")
                        break
                    else:
                        print(f"Unexpected status {response.status_code}, "
                              f"retrying...")
                except requests.exceptions.RequestException as e:
                    print(f"Alert attempt {attempt} failed: {e}, "
                          f"retrying in 5s...")
                attempt += 1
                time.sleep(5)

        threading.Thread(target=post_with_retry, daemon=True).start()

        log_file    = "fall_incidents.csv"
        file_exists = os.path.isfile(log_file)
        with open(log_file, "a") as f:
            if not file_exists:
                f.write("Timestamp,Incident_Name,Video_URL\n")
            f.write(
                f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},"
                f"{self._incident_name},"
                f"{self._r2_public_url}/{self._video_blob_name}\n"
            )
        print(f"Incident logged locally to {log_file}")

    # Command handling

    def _handle_commands(self):
        if self._command_queue is None:
            return
        try:
            while True:
                cmd = self._command_queue.get_nowait()

                if cmd == "simulate_fall" and not self._fallen_state:
                    print("[SIM] Fall simulated via keypress")
                    self._trigger_fall(reason="simulated")

                elif cmd == "simulate_recovery":
                    print("[SIM] Recovery simulated via keypress")
                    threading.Thread(
                        target=self._save_video_clip,
                        args=("Recovered Fall",
                              list(self._frozen_video_frames_before),
                              list(self._video_frames_after)),
                        daemon=True,
                    ).start()
                    self._reset_fall_state()

                elif cmd == "simulate_slow_fall" and not self._fallen_state:
                    # Force the slow-fall timer to expire immediately
                    print("[SIM] Slow-fall simulated via keypress")
                    self._floor_contact_start = (
                        time.time() - self.SLOW_FALL_FLOOR_DURATION
                    )

                elif cmd == "test_audio_scream" and self._audio_module:
                    threading.Thread(
                        target=self._audio_module.test_with_file,
                        args=("test_sounds/scream.wav",),
                        daemon=True,
                    ).start()

                elif cmd == "test_audio_groan" and self._audio_module:
                    threading.Thread(
                        target=self._audio_module.test_with_file,
                        args=("test_sounds/groan.wav",),
                        daemon=True,
                    ).start()

                elif cmd == "test_audio_thud" and self._audio_module:
                    threading.Thread(
                        target=self._audio_module.test_with_file,
                        args=("test_sounds/thud.wav",),
                        daemon=True,
                    ).start()

        except queue.Empty:
            pass