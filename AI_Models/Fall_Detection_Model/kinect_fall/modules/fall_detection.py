import os
import io
import time
import json
import queue
import datetime
import tempfile
import threading
import subprocess
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np
import boto3
import requests
from botocore.config import Config as BotoConfig
from ultralytics import YOLO
from pykinect2.PyKinectV2 import JointType_SpineBase

from modules.base_module import BaseModule
from shared.config import Config
from shared.stream_overlay import BodyOverlay, FallOverlay
from modules.audio_detection import AudioDetectionModule


BODY_TRACK_TIMEOUT = 3.0
FACE_ASSOCIATION_TIMEOUT = 2.0


@dataclass
class BodyTrackState:
    tracking_id: str
    body_index: int
    last_seen: float
    color_bbox: tuple[int, int, int, int] | None = None
    spine_history: deque = field(default_factory=deque)
    floor_contact_start: float | None = None
    current_height: float = 0.0
    current_abs_height: float = 0.0
    current_velocity: float = 0.0
    is_on_floor: bool = False
    patient_id: str | None = None
    patient_name: str | None = None
    identity_confidence: float = 0.0
    identity_last_seen: float = 0.0
    fall_patient_id: str | None = None
    fall_patient_name: str | None = None


class FallDetectionModule(BaseModule):

    MIN_ELAPSED_TIME          = 10
    VIDEO_FPS                 = 10
    MAX_AFTER_FRAMES          = 150
    MAX_BEFORE_FRAMES         = 100
    FLOOR_FALLEN_THRESHOLD    = 0.4
    FLOOR_RECOVERED_THRESHOLD = 0.6
    FALL_VELOCITY_THRESHOLD   = 0.3
    SLOW_FALL_FLOOR_DURATION  = 5.0
    VELOCITY_JITTER_FLOOR     = 0.05
    POST_FALL_COOLDOWN        = 10.0

    def __init__(self, frame_queue: queue.Queue, config: Config,
                 annotated_queue: queue.Queue = None,
                 command_queue: queue.Queue = None,
                 stream_overlay_queue: queue.Queue = None,
                 verbose: bool = False,
                 face_module=None,
                 max_fps: int | float | None = None):
        super().__init__(frame_queue, max_fps=max_fps)
        self._verbose         = verbose
        self._face_module     = face_module
        self._config          = config
        self._annotated_queue = annotated_queue
        self._stream_overlay_queue = stream_overlay_queue
        self._command_queue   = command_queue
        self._model           = YOLO('yolo models/yolov8n-pose.pt')

        r2_account_id        = os.environ["R2_ACCOUNT_ID"]
        r2_access_key_id     = os.environ["R2_ACCESS_KEY_ID"]
        r2_secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"]
        self._r2_public_url  = os.environ["R2_PUBLIC_URL"]
        self._bucket         = os.environ.get("R2_BUCKET_FALL", "fall-detection")

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
        self._active_fall_tracking_id    = None
        self._taking_video               = False
        self._video_frames_before        = deque(maxlen=self.MAX_BEFORE_FRAMES)
        self._video_frames_after         = deque(maxlen=self.MAX_AFTER_FRAMES)
        self._frozen_video_frames_before = []
        self._video_blob_name            = ""
        self._incident_name              = ""
        self._blob_number                = 1
        self._audio_module               = None
        self._body_tracks                = {}
        self._cooldown_until: float      = 0.0

    def set_audio_module(self, audio_module: AudioDetectionModule):
        self._audio_module = audio_module

    def _process_frame(self, frame) -> None:
        self._handle_commands()
        color = frame.color
        if color is None:
            return

        self._video_frames_before.append(color.copy())
        if self._taking_video:
            self._video_frames_after.append(color.copy())

        results = self._model.predict(color, conf=0.4, verbose=False)
        r = results[0]

        tracked_states = self._update_body_tracks(frame)
        self._associate_faces_to_body_tracks(frame.timestamp)

        audio_distress = False
        if self._audio_module:
            audio_state = self._audio_module.get_state()
            audio_distress = audio_state['detected']
            if audio_distress and self._verbose:
                print(f"[AUDIO] Distress: {audio_state['label']} "
                      f"({audio_state['confidence']:.0%})")

        velocity = max((state.current_velocity for state in tracked_states), default=0.0)
        self._evaluate_fall_triggers(tracked_states, audio_distress)
        self._monitor_active_fall()

        if self._annotated_queue is not None:
            self._publish_annotated_frame(r, tracked_states, velocity)

        if self._stream_overlay_queue is not None:
            self._publish_stream_overlay(r, tracked_states, velocity)

    def _update_body_tracks(self, frame) -> list[BodyTrackState]:
        bodies = frame.body_frame
        if bodies is None:
            self._prune_body_tracks(time.time())
            return []

        now = time.time()
        summaries_by_index = {
            summary.body_index: summary
            for summary in getattr(frame, "body_summaries", [])
        }
        tracked_states = []
        floor_plane = bodies.floor_clip_plane

        for body_index in range(6):
            body = bodies.bodies[body_index]
            if not body.is_tracked:
                continue

            tracking_id = self._body_tracking_id(body, body_index)
            state = self._body_tracks.get(tracking_id)
            if state is None:
                state = BodyTrackState(
                    tracking_id=tracking_id,
                    body_index=body_index,
                    last_seen=now,
                )
                self._body_tracks[tracking_id] = state

            summary = summaries_by_index.get(body_index)
            state.body_index = body_index
            state.last_seen = now
            state.color_bbox = summary.color_bbox if summary else None

            spine = body.joints[JointType_SpineBase].Position
            height_from_floor = self._height_above_floor(spine, floor_plane)
            abs_height = abs(height_from_floor)
            state.current_height = height_from_floor
            state.current_abs_height = abs_height
            state.is_on_floor = abs_height < self.FLOOR_FALLEN_THRESHOLD

            state.spine_history.append((now, abs_height))
            cutoff = now - 2.0
            while state.spine_history and state.spine_history[0][0] < cutoff:
                state.spine_history.popleft()
            state.current_velocity = self._calculate_velocity(state)

            if self._verbose:
                name = state.patient_name or "Unknown"
                print(f"[Body {body_index} #{tracking_id}] {name} | "
                      f"height={height_from_floor:.2f}m "
                      f"abs={abs_height:.2f}m "
                      f"velocity={state.current_velocity:.2f}m/s")

            tracked_states.append(state)

        self._prune_body_tracks(now)
        return tracked_states

    def _evaluate_fall_triggers(
        self,
        tracked_states: list[BodyTrackState],
        audio_distress: bool,
    ) -> None:
        if self._fallen_state:
            return

        for state in tracked_states:
            if not state.is_on_floor:
                state.floor_contact_start = None
                continue

            is_fast_drop = state.current_velocity > self.FALL_VELOCITY_THRESHOLD
            if is_fast_drop:
                print(f"ALERT: Fast fall detected for body {state.body_index}. "
                      f"{state.current_velocity:.2f}m/s. Monitoring...")
                self._trigger_fall(state, reason="fast_drop")
                return

            if audio_distress:
                print(f"ALERT: Floor contact + audio distress for body "
                      f"{state.body_index}. Monitoring...")
                self._trigger_fall(state, reason="audio_distress")
                return

            if state.floor_contact_start is None:
                state.floor_contact_start = time.time()
            elif self._verbose:
                print(f"Body {state.body_index} floor contact but slow descent "
                      f"({state.current_velocity:.2f}m/s)")

            elapsed_floor = time.time() - state.floor_contact_start
            if elapsed_floor >= self.SLOW_FALL_FLOOR_DURATION:
                print(f"ALERT: Prolonged floor contact for body {state.body_index} "
                      f"({elapsed_floor:.1f}s).")
                self._trigger_fall(state, reason="prolonged_floor_contact")
                return

    def _monitor_active_fall(self) -> None:
        if not self._fallen_state:
            return

        active = self._active_body_track()
        if active is None:
            if self._active_fall_tracking_id is not None:
                print("Falling body lost from frame - cancelling fall alert")
                self._reset_fall_state()
            return

        elapsed = time.time() - self._fall_start_time
        if active.current_abs_height > self.FLOOR_RECOVERED_THRESHOLD:
            print("Recovery detected.")
            self._save_active_incident("Recovered Fall", active)
            self._reset_fall_state()
        elif elapsed >= self.MIN_ELAPSED_TIME:
            print("FALL CONFIRMED.")
            self._save_active_incident("Unrecovered Fall", active)
            self._reset_fall_state()

    def _save_active_incident(self, event_type: str, active: BodyTrackState) -> None:
        patient_id, patient_name = self._identity_for_track(active)
        threading.Thread(
            target=self._save_video_clip,
            args=(event_type,
                  list(self._frozen_video_frames_before),
                  list(self._video_frames_after),
                  patient_id,
                  patient_name),
            daemon=True,
        ).start()

    def _trigger_fall(self, state: BodyTrackState | None, reason: str = ""):
        if time.time() < self._cooldown_until:
            remaining = self._cooldown_until - time.time()
            if self._verbose:
                print(f"[FALL] Trigger suppressed - cooldown active "
                      f"({remaining:.1f}s remaining)")
            return

        self._fallen_state = True
        self._fall_start_time = time.time()
        self._active_fall_tracking_id = state.tracking_id if state else None
        self._taking_video = True
        self._frozen_video_frames_before = list(self._video_frames_before)
        if state:
            state.fall_patient_id = state.patient_id
            state.fall_patient_name = state.patient_name
            state.floor_contact_start = None
        if reason:
            body_label = f"body {state.body_index}" if state else "manual"
            print(f"[FALL] Triggered for {body_label} - reason: {reason}")

    def _reset_fall_state(self):
        self._cooldown_until = time.time() + self.POST_FALL_COOLDOWN
        self._fallen_state = False
        self._fall_start_time = None
        self._active_fall_tracking_id = None
        self._taking_video = False
        self._video_frames_after = deque(maxlen=self.MAX_AFTER_FRAMES)
        self._frozen_video_frames_before = []
        for state in self._body_tracks.values():
            state.floor_contact_start = None
            state.fall_patient_id = None
            state.fall_patient_name = None
        print(f"[FALL] Reset - cooldown active for {self.POST_FALL_COOLDOWN:.0f}s")

    def _publish_annotated_frame(
        self,
        result,
        tracked_states: list[BodyTrackState],
        velocity: float,
    ) -> None:
        annotated = result.plot()
        status = "STATUS: FALLING" if self._fallen_state else "STATUS: SAFE"
        color_text = (0, 0, 255) if self._fallen_state else (0, 255, 0)
        cv2.putText(annotated, status, (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, color_text, 2)
        cv2.putText(annotated,
                    f"Velocity: {velocity:.2f}m/s",
                    (50, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 0), 1)

        floor_timer = self._active_floor_timer(tracked_states)
        if floor_timer is not None and not self._fallen_state:
            cv2.putText(annotated,
                        f"Floor timer: {floor_timer:.1f}s / "
                        f"{self.SLOW_FALL_FLOOR_DURATION:.0f}s",
                        (50, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 165, 255), 1)

        remaining_cooldown = self._cooldown_until - time.time()
        if remaining_cooldown > 0:
            cv2.putText(annotated,
                        f"Cooldown: {remaining_cooldown:.0f}s",
                        (50, 150),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (128, 128, 128), 1)

        for state in tracked_states:
            if not state.color_bbox:
                continue
            x1, y1, x2, y2 = state.color_bbox
            color = (0, 255, 0) if state.patient_id else (0, 165, 255)
            label = self._body_label(state)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, label, (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        try:
            self._annotated_queue.put_nowait(annotated)
        except queue.Full:
            pass

    def _publish_stream_overlay(
        self,
        result,
        tracked_states: list[BodyTrackState],
        velocity: float,
    ) -> None:
        bodies = [
            BodyOverlay(
                state.color_bbox,
                label=self._body_label(state),
                confidence=state.identity_confidence if state.patient_id else None,
            )
            for state in tracked_states
            if state.color_bbox
        ]

        if not bodies:
            boxes = getattr(result, "boxes", None)
            if boxes is not None and getattr(boxes, "xyxy", None) is not None:
                xyxy = boxes.xyxy.cpu().numpy()
                conf = boxes.conf.cpu().numpy() if getattr(boxes, "conf", None) is not None else []
                for i, box in enumerate(xyxy):
                    x1, y1, x2, y2 = [int(v) for v in box[:4]]
                    confidence = float(conf[i]) if i < len(conf) else None
                    bodies.append(BodyOverlay((x1, y1, x2, y2), confidence=confidence))

        floor_timer_seconds = None
        if not self._fallen_state:
            floor_timer_seconds = self._active_floor_timer(tracked_states)

        overlay = FallOverlay(
            bodies=bodies,
            fallen=self._fallen_state,
            status="STATUS: FALLING" if self._fallen_state else "STATUS: SAFE",
            velocity=velocity,
            floor_timer_seconds=floor_timer_seconds,
            floor_timer_limit=self.SLOW_FALL_FLOOR_DURATION,
        )

        try:
            self._stream_overlay_queue.put_nowait(overlay)
        except queue.Full:
            pass

    def _associate_faces_to_body_tracks(self, frame_timestamp: float) -> None:
        if self._face_module is None or not hasattr(self._face_module, "get_latest_faces"):
            return

        faces, face_timestamp = self._face_module.get_latest_faces()
        now = time.time()
        if not faces or abs(frame_timestamp - face_timestamp) > FACE_ASSOCIATION_TIMEOUT:
            self._expire_stale_identities(now)
            return

        assignments = {}
        for face_result in faces:
            face = self._parse_face_result(face_result)
            if face is None:
                continue
            face_bbox, name, patient_id, sim, is_match = face
            if not is_match or not patient_id:
                continue

            face_center = self._bbox_center(face_bbox)
            best_state = None
            best_score = float("inf")
            for state in self._body_tracks.values():
                if now - state.last_seen > BODY_TRACK_TIMEOUT or not state.color_bbox:
                    continue
                if not self._face_belongs_to_body(face_center, state.color_bbox):
                    continue
                score = self._face_body_score(face_center, state.color_bbox)
                if score < best_score:
                    best_score = score
                    best_state = state

            if best_state is None:
                continue
            current = assignments.get(best_state.tracking_id)
            if current is None or sim > current[2]:
                assignments[best_state.tracking_id] = (name, patient_id, sim)

        for tracking_id, (name, patient_id, sim) in assignments.items():
            state = self._body_tracks.get(tracking_id)
            if state is None:
                continue
            state.patient_name = name
            state.patient_id = str(patient_id)
            state.identity_confidence = float(sim)
            state.identity_last_seen = now

        self._expire_stale_identities(now)

    def _expire_stale_identities(self, now: float) -> None:
        for state in self._body_tracks.values():
            if state.patient_id and now - state.identity_last_seen > FACE_ASSOCIATION_TIMEOUT:
                state.patient_id = None
                state.patient_name = None
                state.identity_confidence = 0.0

    def _prune_body_tracks(self, now: float) -> None:
        active_id = self._active_fall_tracking_id
        stale_ids = [
            tracking_id for tracking_id, state in self._body_tracks.items()
            if tracking_id != active_id and now - state.last_seen > BODY_TRACK_TIMEOUT
        ]
        for tracking_id in stale_ids:
            del self._body_tracks[tracking_id]

    def _active_body_track(self) -> BodyTrackState | None:
        if self._active_fall_tracking_id is None:
            return None
        active = self._body_tracks.get(self._active_fall_tracking_id)
        if active is None:
            return None
        if time.time() - active.last_seen > BODY_TRACK_TIMEOUT:
            return None
        return active

    def _active_floor_timer(
        self,
        tracked_states: list[BodyTrackState],
    ) -> float | None:
        timers = [
            time.time() - state.floor_contact_start
            for state in tracked_states
            if state.floor_contact_start is not None
        ]
        return max(timers) if timers else None

    def _body_label(self, state: BodyTrackState) -> str:
        name = state.patient_name if state.patient_id else "Unknown"
        return f"Body {state.body_index}: {name}"

    def _identity_for_track(self, state: BodyTrackState) -> tuple[str | None, str]:
        if state.fall_patient_id:
            return (
                state.fall_patient_id,
                state.fall_patient_name or f"Patient {state.fall_patient_id}",
            )
        if state.patient_id:
            return state.patient_id, state.patient_name or f"Patient {state.patient_id}"
        return None, "Unknown person"

    @staticmethod
    def _body_tracking_id(body, body_index: int) -> str:
        return str(getattr(body, "tracking_id", None) or f"body-{body_index}")

    @staticmethod
    def _calculate_velocity(state: BodyTrackState) -> float:
        if len(state.spine_history) < 3:
            return 0.0

        oldest_t, oldest_h = state.spine_history[0]
        latest_t, latest_h = state.spine_history[-1]
        dt = latest_t - oldest_t
        if dt < 1e-6:
            return 0.0

        velocity = (oldest_h - latest_h) / dt
        if abs(velocity) < FallDetectionModule.VELOCITY_JITTER_FLOOR:
            return 0.0
        return velocity

    @staticmethod
    def _height_above_floor(joint_position, floor_plane) -> float:
        A, B, C, D = floor_plane.x, floor_plane.y, floor_plane.z, floor_plane.w
        x, y, z = joint_position.x, joint_position.y, joint_position.z
        return (A * x) + (B * y) + (C * z) + D

    @staticmethod
    def _parse_face_result(face_result):
        if len(face_result) == 6:
            bbox, name, patient_id, sim, is_match, _angle = face_result
        else:
            bbox, name, sim, is_match, _angle = face_result
            patient_id = None
        return bbox, name, patient_id, float(sim), bool(is_match)

    @staticmethod
    def _bbox_center(bbox) -> tuple[float, float]:
        x1, y1, x2, y2 = bbox[:4]
        return (float(x1 + x2) / 2.0, float(y1 + y2) / 2.0)

    @staticmethod
    def _face_belongs_to_body(
        face_center: tuple[float, float],
        body_bbox: tuple[int, int, int, int],
    ) -> bool:
        x, y = face_center
        x1, y1, x2, y2 = body_bbox
        width = max(x2 - x1, 1)
        height = max(y2 - y1, 1)
        return (
            x1 - width * 0.15 <= x <= x2 + width * 0.15
            and y1 - height * 0.10 <= y <= y1 + height * 0.75
        )

    @staticmethod
    def _face_body_score(
        face_center: tuple[float, float],
        body_bbox: tuple[int, int, int, int],
    ) -> float:
        x, y = face_center
        x1, y1, x2, y2 = body_bbox
        body_x = (x1 + x2) / 2.0
        upper_y = y1 + (y2 - y1) * 0.22
        return float(np.hypot(x - body_x, y - upper_y))

    def _save_video_clip(self, event_type: str, before_frames: list,
                         after_frames: list,
                         recognized_patient_id: str | None = None,
                         recognized_patient_name: str | None = None):
        clip_frames = before_frames + after_frames
        if not clip_frames:
            return

        print(f"Saving clip for event: {event_type}")
        h, w, _ = clip_frames[0].shape

        date_str = datetime.date.today().strftime('%Y-%m-%d')
        time_str = datetime.datetime.now().strftime('%H-%M-%S')
        local_dir = os.path.join(self._config.recording_path, date_str)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"Fall_{time_str}.mp4")

        out_local = cv2.VideoWriter(
            local_path, cv2.VideoWriter_fourcc(*'mp4v'), self.VIDEO_FPS, (w, h)
        )
        for frm in clip_frames:
            out_local.write(frm)
        out_local.release()
        print("[LOG] Local copy saved.")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            temp_path = tmp.name

        out_cloud = cv2.VideoWriter(
            temp_path, cv2.VideoWriter_fourcc(*'mp4v'), self.VIDEO_FPS, (w, h)
        )
        for frm in clip_frames:
            out_cloud.write(frm)
        out_cloud.release()

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

        self._upload_clip_to_r2(h264_path)
        self._save_info_in_r2()
        self._send_api_call(
            event_type,
            recognized_patient_id,
            recognized_patient_name or "Unknown person",
        )

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
                "status": "Fallen",
                "timestamp": str(time.time()),
                "filename": self._video_blob_name,
            }
            self._incident_name = f"incident_{self._blob_number}_{int(time.time())}"
            self._blob_number += 1
            self._s3.upload_fileobj(
                io.BytesIO(json.dumps(info).encode("utf-8")),
                self._bucket,
                self._incident_name,
            )
            print(f"Uploaded incident JSON: {self._incident_name}")
        except Exception as e:
            print(f"Error uploading incident JSON: {e}")

    def _send_api_call(self, event_type: str,
                       recognized_patient_id: str | None = None,
                       recognized_patient_name: str | None = None):
        subject_label = recognized_patient_name or "Unknown person"
        payload = {
            "deviceId": self._config.device_id,
            "patientId": self._config.patient_id,
            "recognizedPatientId": recognized_patient_id,
            "recognizedPatientName": subject_label,
            "subjectLabel": subject_label,
            "room": self._config.room,
            "eventType": event_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "videoUrl": f"{self._r2_public_url}/{self._video_blob_name}",
            "incidentName": self._incident_name,
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
                        print(f"Fall alert sent successfully for {subject_label}.")
                        break
                    print(f"Unexpected status {response.status_code}, retrying...")
                except requests.exceptions.RequestException as e:
                    print(f"Alert attempt {attempt} failed: {e}, retrying in 5s...")
                attempt += 1
                time.sleep(5)

        threading.Thread(target=post_with_retry, daemon=True).start()

        log_file = "fall_incidents.csv"
        file_exists = os.path.isfile(log_file)
        with open(log_file, "a") as f:
            if not file_exists:
                f.write("Timestamp,Incident_Name,Video_URL,RecognizedPatientId,Subject\n")
            f.write(
                f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},"
                f"{self._incident_name},"
                f"{self._r2_public_url}/{self._video_blob_name},"
                f"{recognized_patient_id or ''},"
                f"{subject_label}\n"
            )
        print(f"Incident logged locally to {log_file}")

    def _handle_commands(self):
        if self._command_queue is None:
            return
        try:
            while True:
                cmd = self._command_queue.get_nowait()

                if cmd == "simulate_fall" and not self._fallen_state:
                    print("[SIM] Fall simulated via keypress")
                    self._trigger_fall(self._first_live_track(), reason="simulated")

                elif cmd == "simulate_recovery":
                    print("[SIM] Recovery simulated via keypress")
                    active = self._active_body_track() or self._first_live_track()
                    if active is not None:
                        self._save_active_incident("Recovered Fall", active)
                    else:
                        threading.Thread(
                            target=self._save_video_clip,
                            args=("Recovered Fall",
                                  list(self._frozen_video_frames_before),
                                  list(self._video_frames_after),
                                  None,
                                  "Unknown person"),
                            daemon=True,
                        ).start()
                    self._reset_fall_state()

                elif cmd == "simulate_slow_fall" and not self._fallen_state:
                    print("[SIM] Slow-fall simulated via keypress")
                    first = self._first_live_track()
                    if first is not None:
                        first.floor_contact_start = (
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

    def _first_live_track(self) -> BodyTrackState | None:
        now = time.time()
        live = [
            state for state in self._body_tracks.values()
            if now - state.last_seen <= BODY_TRACK_TIMEOUT
        ]
        if not live:
            return None
        return sorted(live, key=lambda s: s.last_seen, reverse=True)[0]
