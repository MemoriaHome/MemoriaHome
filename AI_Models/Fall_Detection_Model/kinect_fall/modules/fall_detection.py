import os
import io
import time
import json
import queue
import datetime
import tempfile
import threading

import cv2
import numpy as np
import boto3
import requests
from botocore.config import Config as BotoConfig
from ultralytics import YOLO
from pykinect2.PyKinectV2 import JointType_SpineBase

from modules.base_module import BaseModule
from shared.config import Config


class FallDetectionModule(BaseModule):

    MIN_ELAPSED_TIME    = 10
    VIDEO_FPS           = 15
    MAX_AFTER_FRAMES    = 150
    MAX_BEFORE_FRAMES   = 100
    FLOOR_FALLEN_THRESHOLD    = 0.4
    FLOOR_RECOVERED_THRESHOLD = 0.6

    def __init__(self, frame_queue: queue.Queue, config: Config, annotated_queue: queue.Queue = None):
        super().__init__(frame_queue)
        self._config = config
        self._annotated_queue = annotated_queue  # optional — display module reads from this

        self._model = YOLO('yolo models/yolov8n-pose.pt')

        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
            config=BotoConfig(signature_version='s3v4'),
            region_name="auto",
        )
        self._bucket        = os.getenv('R2_BUCKET_NAME')
        self._r2_public_url = os.getenv('R2_PUBLIC_URL')

        # Fall state
        self._fallen_state              = False
        self._fall_start_time           = None
        self._taking_video              = False
        self._video_frames_before       = []
        self._video_frames_after        = []
        self._frozen_video_frames_before = []
        self._video_blob_name           = ""
        self._incident_name             = ""
        self._blob_number               = 1

    # --- Core frame processing ---

    def _process_frame(self, frame) -> None:
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
        r = results[0]

        # Body tracking
        height_from_floor  = 0.0
        is_on_floor        = False
        body_frame_updated = False

        if frame.body_frame:
            bodies      = frame.body_frame
            floor_plane = bodies.floor_clip_plane
            for i in range(6):  # Kinect v2 tracks up to 6 bodies
                body = bodies.bodies[i]
                if body.is_tracked:
                    spine             = body.joints[JointType_SpineBase].Position
                    height_from_floor = self._height_above_floor(spine, floor_plane)
                    is_on_floor       = abs(height_from_floor) < self.FLOOR_FALLEN_THRESHOLD
                    body_frame_updated = True
                    print(f"Spine height from floor: {height_from_floor:.2f}m")
                    break

        # Keypoint check
        if len(r.keypoints.xy) > 0 and len(r.keypoints.xy[0]) > 0:
            y_vals = [kp[1].item() for kp in r.keypoints.xy[0] if kp[1] > 0]
        else:
            y_vals = []

        # Fall detection logic
        if is_on_floor and len(y_vals) >= 6 and not self._fallen_state:
            print("ALERT: Possible Fall Detected. Monitoring...")
            self._fallen_state               = True
            self._fall_start_time            = time.time()
            self._taking_video               = True
            self._frozen_video_frames_before = list(self._video_frames_before)

        if self._fallen_state and body_frame_updated:
            elapsed = time.time() - self._fall_start_time
            if abs(height_from_floor) > self.FLOOR_RECOVERED_THRESHOLD:
                print("Recovery detected.")
                self._save_video_clip(event_type="Recovered Fall")
                self._reset_fall_state()
            elif elapsed >= self.MIN_ELAPSED_TIME:
                print("FALL CONFIRMED.")
                self._save_video_clip(event_type="Unrecovered Fall")
                self._reset_fall_state()

        # Push annotated frame to display module
        if self._annotated_queue is not None:
            annotated  = r.plot()
            status     = "STATUS: FALLING" if self._fallen_state else "STATUS: SAFE"
            color_text = (0, 0, 255) if self._fallen_state else (0, 255, 0)
            cv2.putText(annotated, status, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color_text, 2)
            try:
                self._annotated_queue.put_nowait(annotated)
            except queue.Full:
                pass

    def _reset_fall_state(self):
        self._fallen_state               = False
        self._taking_video               = False
        self._video_frames_after         = []
        self._frozen_video_frames_before = []

    # --- Helpers ---

    @staticmethod
    def _height_above_floor(joint_position, floor_plane) -> float:
        A, B, C, D = floor_plane.x, floor_plane.y, floor_plane.z, floor_plane.w
        x, y, z   = joint_position.x, joint_position.y, joint_position.z
        return (A * x) + (B * y) + (C * z) + D

    # --- Video & upload ---

    def _save_video_clip(self, event_type: str):
        clip_frames = self._frozen_video_frames_before + self._video_frames_after
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

        out_local = cv2.VideoWriter(local_path, cv2.VideoWriter_fourcc(*'mp4v'), self.VIDEO_FPS, (w, h))
        for frm in clip_frames:
            out_local.write(frm)
        out_local.release()
        print("[LOG] Local copy saved.")

        # Temp file for R2 upload
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            temp_path = tmp.name

        out_cloud = cv2.VideoWriter(temp_path, cv2.VideoWriter_fourcc(*'mp4v'), self.VIDEO_FPS, (w, h))
        for frm in clip_frames:
            out_cloud.write(frm)
        out_cloud.release()
        print("[LOG] Cloud copy ready.")

        self._upload_clip_to_r2(temp_path)
        self._save_info_in_r2()
        self._send_api_call(event_type)

        try:
            os.remove(temp_path)
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
                "status": "Fallen",
                "timestamp": str(time.time()),
                "filename": self._video_blob_name
            }
            self._incident_name = f"incident_{self._blob_number}_{int(time.time())}"
            self._blob_number  += 1
            self._s3.upload_fileobj(
                io.BytesIO(json.dumps(info).encode("utf-8")),
                self._bucket,
                self._incident_name
            )
            print(f"Uploaded incident JSON: {self._incident_name}")
        except Exception as e:
            print(f"Error uploading incident JSON: {e}")

    def _send_api_call(self, event_type: str):
        payload = {
            "deviceId":     self._config.device_id,
            "patientId":    self._config.patient_id,
            "room":         self._config.room,
            "eventType":    event_type,
            "timestamp":    datetime.datetime.now().isoformat(),
            "videoUrl":     f"{self._r2_public_url}/{self._video_blob_name}",
            "incidentName": self._incident_name
        }

        def post_with_retry():
            attempt = 0
            while True:
                try:
                    response = requests.post(
                        f"{self._config.backend_url}/alert/fall",
                        json=payload,
                        timeout=10,
                        verify=False
                    )
                    if response.status_code == 201:
                        print("Alert sent successfully.")
                        break
                    else:
                        print(f"Unexpected status {response.status_code}, retrying...")
                except requests.exceptions.RequestException as e:
                    print(f"Alert attempt {attempt} failed: {e}, retrying in 5s...")
                attempt += 1
                time.sleep(5)

        threading.Thread(target=post_with_retry, daemon=True).start()

        log_file   = "fall_incidents.csv"
        file_exists = os.path.isfile(log_file)
        with open(log_file, "a") as f:
            if not file_exists:
                f.write("Timestamp,Incident_Name,Video_URL\n")
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},"
                    f"{self._incident_name},"
                    f"{self._r2_public_url}/{self._video_blob_name}\n")
        print(f"Incident logged locally to {log_file}")