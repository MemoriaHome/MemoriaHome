import os
import pickle
import queue
import threading

import boto3
import cv2
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


class FaceTracker:
    def __init__(self, reidentify_every=REIDENTIFY_EVERY_N):
        self._tracks = []
        self._reid_n = reidentify_every

    def needs_recognition(self, bbox):
        for t in self._tracks:
            if compute_iou(bbox, t[0]) >= IOU_THRESHOLD:
                return t[5] >= self._reid_n
        return True

    def update(self, bbox, name, sim, is_match, angle):
        for t in self._tracks:
            if compute_iou(bbox, t[0]) >= IOU_THRESHOLD:
                t[0] = bbox
                t[1] = name
                t[2] = sim
                t[3] = is_match
                t[4] = angle
                t[5] = 0
                return
        self._tracks.append([bbox, name, sim, is_match, angle, 0])

    def tick(self, live_bboxes):
        kept = []
        for t in self._tracks:
            matched = any(
                compute_iou(t[0], lb) >= IOU_THRESHOLD for lb in live_bboxes
            )
            if matched:
                t[5] += 1
                kept.append(t)
        self._tracks = kept

        results = []
        for lb in live_bboxes:
            best_track = None
            best_iou = IOU_THRESHOLD
            for t in self._tracks:
                iou = compute_iou(lb, t[0])
                if iou >= best_iou:
                    best_iou = iou
                    best_track = t
            if best_track is not None:
                results.append(
                    (lb, best_track[1], best_track[2], best_track[3], best_track[4])
                )
            else:
                results.append((lb, "Unknown", 0.0, False, 0))
        return results


def find_match(
    unknown_embedding: np.ndarray,
    known_embeddings: np.ndarray,
    known_ids: list,
    threshold=0.4,
):
    if known_embeddings.size == 0 or not known_ids:
        return "Unknown", 0.0, False

    norm = np.linalg.norm(unknown_embedding)
    if norm < 1e-10:
        return "Unknown", 0.0, False
    unknown_embedding = unknown_embedding / norm

    sims = np.dot(known_embeddings, unknown_embedding)
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])

    if best_sim >= threshold:
        return known_ids[best_idx], best_sim, True
    return "Unknown", best_sim, False


def at_diff_angles(imgS, app, app_small, known_embeddings, known_ids, tracker: FaceTracker):
    faces = app.get(imgS)
    live_bboxes_small = [f.bbox.astype(int) for f in faces]

    for face in faces:
        bbox_small = face.bbox.astype(int)
        bbox_full = (bbox_small * 2).astype(int)

        if not tracker.needs_recognition(bbox_full):
            continue

        name, sim, is_match = find_match(face.embedding, known_embeddings, known_ids)

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
                    rot_name, rot_sim, rot_is_match = find_match(
                        rot_faces[0].embedding, known_embeddings, known_ids
                    )
                    if rot_is_match:
                        name, sim, is_match = rot_name, rot_sim, rot_is_match
                        angle_used = angle
                        break
        else:
            angle_used = 0

        tracker.update(bbox_full, name, sim, is_match, angle_used)

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
        face_results_queue: queue.Queue = None,
    ):
        super().__init__(frame_queue)
        self._config = config
        self._face_results_queue = face_results_queue
        self._bucket = os.getenv("R2_BUCKET")

        self._s3 = boto3.client(
            service_name="s3",
            endpoint_url=os.getenv("R2_ENDPOINT"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
            region_name="auto",
        )

        self._known_embeddings, self._known_ids = self._load_encodings()
        if self._known_embeddings.size == 0 or not self._known_ids:
            print("[WARNING] No face encodings loaded; face recognition disabled.")

        self._app = insightface.app.FaceAnalysis(
            "buffalo_l", providers=["CUDAExecutionProvider"]
        )
        self._app.prepare(ctx_id=0, det_size=(640, 640))

        self._app_small = insightface.app.FaceAnalysis(
            "buffalo_l", providers=["CUDAExecutionProvider"]
        )
        self._app_small.prepare(ctx_id=0, det_size=(320, 320))

        self._tracker = FaceTracker()

        self._identity_lock    = threading.Lock()
        self._current_identity = None   # best match in the most recent frame
        self._session_identity = None   # latched identity for the current tracking session

    def get_identity(self) -> str | None:
        """
        Returns the most recently recognized patient ID, or None if no face
        has been matched yet. Thread-safe — safe to call from any module.
        """
        with self._identity_lock:
            return self._current_identity

    def _load_encodings(self):
        print("[INFO] Loading encodings from database...")

        if not self._bucket:
            print("[WARNING] R2_BUCKET is not set; no face encodings loaded.")
            return np.array([], dtype=np.float32), []

        embeddings_list_known = []
        known_ids = []

        try:
            response = self._s3.list_objects_v2(
                Bucket=self._bucket, Prefix=PREFIX, Delimiter="/"
            )
        except Exception as e:
            print(f"[WARNING] Could not list face encoding folders: {e}")
            return np.array([], dtype=np.float32), []

        folders = response.get("CommonPrefixes", [])
        if not folders:
            print("[WARNING] No patients found in the database.")
            return np.array([], dtype=np.float32), []

        for person in folders:
            person_prefix = person["Prefix"]
            person_id = person_prefix.rstrip("/").split("/")[-1]
            emb_path = f"{person_prefix}embedding.pkl"

            try:
                obj = self._s3.get_object(Bucket=self._bucket, Key=emb_path)
                embeddings = pickle.loads(obj["Body"].read())
                for emb in embeddings:
                    embeddings_list_known.append(emb)
                    known_ids.append(person_id)
                print(
                    f"[INFO] Loaded {len(embeddings)} embedding(s) for ID {person_id}"
                )
            except Exception as e:
                print(f"[WARNING] Could not load {emb_path}: {e}")

        if not embeddings_list_known:
            return np.array([], dtype=np.float32), []

        known_embeddings = np.array(embeddings_list_known, dtype=np.float32)
        norms = np.linalg.norm(known_embeddings, axis=1, keepdims=True)
        known_embeddings = known_embeddings / np.clip(norms, 1e-10, None)

        print(
            f"[INFO] Loaded {len(known_ids)} embedding(s) "
            f"for {len(set(known_ids))} identity/identities."
        )
        return known_embeddings, known_ids

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
            self._known_ids,
            self._tracker,
        )

        if self._face_results_queue is not None:
            try:
                self._face_results_queue.put_nowait(results)
            except queue.Full:
                pass

        # Update the shared identity: pick the highest-similarity matched face,
        # fall back to None if nobody was recognized this frame.
        best = next(
            (name for _, name, _, is_match, _ in
             sorted(results, key=lambda r: r[2], reverse=True)
             if is_match),
            None,
        )
        with self._identity_lock:
            self._current_identity = best
            # Latch the first confident match as the session identity.
            # Once set, it stays frozen for the lifetime of the tracking
            # session so the fall alert always names who started being tracked.
            if self._session_identity is None and best is not None:
                self._session_identity = best
                print(f"[FACE] Identity latched for session: {best}")

    def begin_session(self) -> None:
        """Called when the body tracker locks onto a new body.
        Clears any previous session identity so identification starts fresh."""
        with self._identity_lock:
            self._session_identity = None
            self._current_identity = None

    def end_session(self) -> None:
        """Called when the fall state is reset (incident resolved or body lost).
        Clears the session identity ready for the next tracking session."""
        with self._identity_lock:
            self._session_identity = None
            self._current_identity = None

    def get_identity(self) -> str | None:
        """Return the patient ID latched at the start of the current tracking
        session, or None if no face has been matched yet this session."""
        with self._identity_lock:
            return self._session_identity