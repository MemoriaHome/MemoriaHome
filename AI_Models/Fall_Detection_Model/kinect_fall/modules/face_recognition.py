import os
import pickle
import queue
import threading
import contextlib
import io
import warnings
from dataclasses import dataclass

import boto3
import cv2
warnings.filterwarnings("ignore", message=".*CUDAExecutionProvider.*")
import insightface
import numpy as np

from modules.base_module import BaseModule


REIDENTIFY_EVERY_N = 15
IOU_THRESHOLD = 0.35
PREFIX = "patients/"


def compute_iou(a, b):
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


@dataclass
class FaceTrack:
    bbox: list[int]
    name: str
    patient_id: str | None
    sim: float
    is_match: bool
    angle: int
    frames_since_reid: int = 0


class FaceTracker:
    def __init__(self, reidentify_every=REIDENTIFY_EVERY_N):
        self._tracks = []
        self._reid_n = reidentify_every

    def needs_recognition(self, bbox):
        for track in self._tracks:
            if compute_iou(bbox, track.bbox) >= IOU_THRESHOLD:
                return track.frames_since_reid >= self._reid_n
        return True

    def update(self, bbox, name, patient_id, sim, is_match, angle):
        for track in self._tracks:
            if compute_iou(bbox, track.bbox) >= IOU_THRESHOLD:
                track.bbox = bbox
                track.name = name
                track.patient_id = patient_id
                track.sim = sim
                track.is_match = is_match
                track.angle = angle
                track.frames_since_reid = 0
                return
        self._tracks.append(FaceTrack(bbox, name, patient_id, sim, is_match, angle))

    def tick(self, live_bboxes):
        kept = []
        for track in self._tracks:
            matched = any(
                compute_iou(track.bbox, lb) >= IOU_THRESHOLD for lb in live_bboxes
            )
            if matched:
                track.frames_since_reid += 1
                kept.append(track)
        self._tracks = kept

        results = []
        for lb in live_bboxes:
            best_track = None
            best_iou = IOU_THRESHOLD
            for track in self._tracks:
                iou = compute_iou(lb, track.bbox)
                if iou >= best_iou:
                    best_iou = iou
                    best_track = track
            if best_track is not None:
                results.append((
                    lb,
                    best_track.name,
                    best_track.patient_id,
                    best_track.sim,
                    best_track.is_match,
                    best_track.angle,
                ))
            else:
                results.append((lb, "Unknown", None, 0.0, False, 0))
        return results


def find_match(
    unknown_embedding: np.ndarray,
    known_embeddings: np.ndarray,
    known_names: list,
    known_ids: list,
    threshold=0.4,
):
    if known_embeddings.size == 0 or not known_names or not known_ids:
        return "Unknown", None, 0.0, False

    norm = np.linalg.norm(unknown_embedding)
    if norm < 1e-10:
        return "Unknown", None, 0.0, False
    unknown_embedding = unknown_embedding / norm

    sims = np.dot(known_embeddings, unknown_embedding)
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])

    if best_sim >= threshold:
        return known_names[best_idx], known_ids[best_idx], best_sim, True
    return "Unknown", None, best_sim, False


def at_diff_angles(
    imgS,
    app,
    app_small,
    known_embeddings,
    known_names,
    known_ids,
    tracker: FaceTracker,
):
    faces = app.get(imgS)
    live_bboxes_small = [f.bbox.astype(int) for f in faces]

    for face in faces:
        bbox_small = face.bbox.astype(int)
        bbox_full = (bbox_small * 2).astype(int)

        if not tracker.needs_recognition(bbox_full):
            continue

        name, patient_id, sim, is_match = find_match(
            face.embedding, known_embeddings, known_names, known_ids
        )

        if not is_match:
            x1, y1, x2, y2 = bbox_small
            pad = 15
            h, w = imgS.shape[:2]
            x1c = max(0, x1 - pad)
            y1c = max(0, y1 - pad)
            x2c = min(w, x2 + pad)
            y2c = min(h, y2 + pad)
            face_crop = imgS[y1c:y2c, x1c:x2c]

            angle_used = 0
            if face_crop.size > 0:
                for angle in [30, -30, 60, -60]:
                    crop_h, crop_w = face_crop.shape[:2]
                    center = (crop_w // 2, crop_h // 2)
                    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
                    rotated = cv2.warpAffine(face_crop, matrix, (crop_w, crop_h))

                    rot_faces = app_small.get(rotated)
                    if not rot_faces:
                        continue
                    rot_faces = sorted(
                        rot_faces,
                        key=lambda f: (
                            (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
                        ),
                        reverse=True,
                    )
                    rot_name, rot_patient_id, rot_sim, rot_is_match = find_match(
                        rot_faces[0].embedding,
                        known_embeddings,
                        known_names,
                        known_ids,
                    )
                    if rot_is_match:
                        name, sim, is_match = rot_name, rot_sim, rot_is_match
                        patient_id = rot_patient_id
                        angle_used = angle
                        break
        else:
            angle_used = 0

        tracker.update(bbox_full, name, patient_id, sim, is_match, angle_used)

    # Return bboxes in full-resolution (1920×1080) coordinate space so the
    # CompositorModule can draw them directly onto the full-res fall frame.
    live_bboxes_full = [(b * 2).tolist() for b in live_bboxes_small]
    return tracker.tick(live_bboxes_full)


class FaceRecognitionModule(BaseModule):
    """
    Subscribes to the frame bus, runs InsightFace recognition, and pushes
    raw result tuples — (bbox, name, sim, is_match, angle) — to
    face_results_queue.  All rendering is delegated to CompositorModule.
    """

    def __init__(
        self,
        frame_queue: queue.Queue,
        config,
        face_results_queue: queue.Queue | list[queue.Queue] = None,
        max_fps: int | float | None = None,
    ):
        super().__init__(frame_queue, max_fps=max_fps)
        self._config = config
        self._quiet = not bool(getattr(config, "audio_debug", False))
        if isinstance(face_results_queue, list):
            self._face_results_queues = face_results_queue
        elif face_results_queue is not None:
            self._face_results_queues = [face_results_queue]
        else:
            self._face_results_queues = []
        self._bucket = os.getenv("R2_BUCKET_FACE")

        self._s3 = boto3.client(
            service_name="s3",
            endpoint_url=os.getenv("R2_ENDPOINT"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
            region_name="auto",
        )

        self._known_embeddings, self._known_names, self._known_ids = self._load_encodings()
        if self._known_embeddings.size == 0 or not self._known_names:
            print("[WARNING] No face encodings loaded; face recognition disabled.")

        if self._quiet:
            with contextlib.redirect_stdout(io.StringIO()):
                self._app = insightface.app.FaceAnalysis(
                    "buffalo_l", providers=["CUDAExecutionProvider"]
                )
                self._app.prepare(ctx_id=0, det_size=(640, 640))

                self._app_small = insightface.app.FaceAnalysis(
                    "buffalo_l", providers=["CUDAExecutionProvider"]
                )
                self._app_small.prepare(ctx_id=0, det_size=(320, 320))
        else:
            self._app = insightface.app.FaceAnalysis(
                "buffalo_l", providers=["CUDAExecutionProvider"]
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))

            self._app_small = insightface.app.FaceAnalysis(
                "buffalo_l", providers=["CUDAExecutionProvider"]
            )
            self._app_small.prepare(ctx_id=0, det_size=(320, 320))

        self._tracker = FaceTracker()

        self._identity_lock = threading.Lock()
        self._current_identity = None
        self._current_identity_name = None
        self._latest_faces = []
        self._latest_faces_timestamp = 0.0

    def get_latest_faces(self) -> tuple[list[tuple], float]:
        """Return the freshest face result batch and its timestamp."""
        with self._identity_lock:
            return list(self._latest_faces), self._latest_faces_timestamp

    def get_current_identity(self) -> str | None:
        """
        Returns the most recently recognized patient ID, or None if no face
        has been matched yet. Thread-safe — safe to call from any module.
        """
        with self._identity_lock:
            return self._current_identity

    def _load_encodings(self):
        if not self._quiet:
            print("[INFO] Loading encodings from database...")

        if not self._bucket:
            print("[WARNING] R2_BUCKET is not set; no face encodings loaded.")
            return np.array([], dtype=np.float32), [], []

        embeddings_list_known = []
        known_names = []
        known_ids = []
        id_to_name = {}

        try:
            response = self._s3.list_objects_v2(
                Bucket=self._bucket, Prefix=PREFIX, Delimiter="/"
            )
        except Exception as e:
            print(f"[WARNING] Could not list face encoding folders: {e}")
            return np.array([], dtype=np.float32), [], []

        folders = response.get("CommonPrefixes", [])
        if not folders:
            print("[WARNING] No patients found in the database.")
            return np.array([], dtype=np.float32), [], []

        for person in folders:
            person_prefix = person["Prefix"]
            person_id = person_prefix.rstrip("/").split("/")[-1]
            emb_path = f"{person_prefix}embedding.pkl"

            try:
                obj = self._s3.get_object(Bucket=self._bucket, Key=emb_path)
                embeddings = pickle.loads(obj["Body"].read())
                objects = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=person_prefix)
                actual_name = person_id
                if 'Contents' in objects:
                    for item in objects['Contents']:
                        key = item['Key']
                        if not key.endswith('embedding.pkl') and key != person_prefix:
                            actual_name = key.split('/')[-1]
                            break

                id_to_name[person_id] = actual_name

                for emb in embeddings:
                    embeddings_list_known.append(emb)
                    known_names.append(actual_name)
                    known_ids.append(person_id)

                if not self._quiet:
                    print(
                        f"[INFO] Loaded {len(embeddings)} "
                        f"embedding(s) for ID {person_id}"
                    )
            except Exception as e:
                print(f"[WARNING] Could not load {emb_path}: {e}")

        if not embeddings_list_known:
            return np.array([], dtype=np.float32), [], []

        known_embeddings = np.array(embeddings_list_known, dtype=np.float32)
        norms = np.linalg.norm(known_embeddings, axis=1, keepdims=True)
        known_embeddings = known_embeddings / np.clip(norms, 1e-10, None)

        if not self._quiet:
            print(
                f"[INFO] Loaded {len(known_names)} embedding(s) "
                f"for {len(set(known_names))} identity/identities."
            )
        return known_embeddings, known_names, known_ids

    def _process_frame(self, frame) -> None:
        color = frame.color
        if color is None:
            return

        if self._known_embeddings.size == 0 or not self._known_ids:
            return

        # Inference runs on a half-res copy; at_diff_angles scales bboxes
        # back to full-res (×2) before returning so the compositor can draw
        # them directly onto the full-res fall-annotated frame.
        imgS = cv2.resize(color, (960, 540))

        results = at_diff_angles(
            imgS,
            self._app,
            self._app_small,
            self._known_embeddings,
            self._known_names,
            self._known_ids,
            self._tracker,
        )

        for result_queue in self._face_results_queues:
            try:
                result_queue.put_nowait(results)
            except queue.Full:
                pass

        best = next(
            ((name, patient_id) for _, name, patient_id, _sim, is_match, _angle in
             sorted(results, key=lambda r: r[3], reverse=True)
             if is_match and patient_id),
            (None, None),
        )
        with self._identity_lock:
            self._latest_faces = list(results)
            self._latest_faces_timestamp = frame.timestamp
            self._current_identity_name, self._current_identity = best

    def begin_session(self) -> None:
        """Compatibility hook for callers that want to clear current identity."""
        with self._identity_lock:
            self._current_identity = None
            self._current_identity_name = None

    def end_session(self) -> None:
        """Compatibility hook for callers that want to clear current identity."""
        with self._identity_lock:
            self._current_identity = None
            self._current_identity_name = None

    def get_identity(self) -> str | None:
        """Return the best patient ID in the most recent face batch."""
        with self._identity_lock:
            return self._current_identity
