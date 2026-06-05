import insightface
import cv2
import numpy as np
import pickle
import boto3


from KinectCapture import KinectCapture

REIDENTIFY_EVERY_N = 15
IOU_THRESHOLD = 0.35 

BUCKET= "memoriahome"
PREFIX = "patients/"

s3 = boto3.client(
    service_name = 's3',
    endpoint_url='https://1496516e0587f1bcbed6294961f40390.r2.cloudflarestorage.com',
    aws_access_key_id='b97874c5d8eafde78997be23f05b6c95',
    aws_secret_access_key='1334256a544967429926a8f3046dbc0c0d0438297efc4f159c4d71f17f524d26',
    region_name='auto',
)


def load_encodings():
    print(f"[INFO] Loading encodings from database...")

    embeddingsListKnown = []
    known_ids = []

    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX, Delimiter='/')
    folders = response.get('CommonPrefixes', [])

    if not folders:
        print("No patients found in the database")
        return np.array([]), []
        
    for person in folders:
        person_prefix = person['Prefix']
        person_id = person_prefix.rstrip('/').split('/')[-1]

        emb_path = f'{person_prefix}embedding.pkl'
        try:
            obj = s3.get_object(Bucket=BUCKET, Key=emb_path)
            embeddings = pickle.loads(obj["Body"].read())
            for emb in embeddings:
                embeddingsListKnown.append(emb)
                known_ids.append(person_id)
            print(f"[INFO] Loaded {len(embeddings)} embedding(s) for ID {person_id}")
        except Exception as e:
            print(f"[WARNING] Could not load {emb_path}: {e}")
            
    known_embeddings = np.array(embeddingsListKnown, dtype=np.float32)

    norms = np.linalg.norm(known_embeddings, axis=1, keepdims=True)
    known_embeddings = known_embeddings / np.clip(norms, 1e-10, None)

    print(f"[INFO] Loaded {len(known_ids)} embedding(s) "
          f"for {len(set(known_ids))} identity/identities.")
    return known_embeddings, known_ids


def compute_iou(a, b):
    ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
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
                t[0] = bbox; t[1] = name; t[2] = sim
                t[3] = is_match; t[4] = angle; t[5] = 0
                return
        self._tracks.append([bbox, name, sim, is_match, angle, 0])

    def tick(self, live_bboxes):
        kept = []
        for t in self._tracks:
            matched = any(compute_iou(t[0], lb) >= IOU_THRESHOLD for lb in live_bboxes)
            if matched:
                t[5] += 1
                kept.append(t)
        self._tracks = kept

        results = []
        for lb in live_bboxes:
            best_track = None
            best_iou   = IOU_THRESHOLD
            for t in self._tracks:
                iou = compute_iou(lb, t[0])
                if iou >= best_iou:
                    best_iou = iou
                    best_track = t
            if best_track is not None:
                results.append((lb, best_track[1], best_track[2], best_track[3], best_track[4]))
            else:
                results.append((lb, "Unknown", 0.0, False, 0))
        return results


def find_match(unknown_embedding: np.ndarray, known_embeddings: np.ndarray, known_ids: list, threshold=0.4):
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
        bbox_full  = (bbox_small * 2).astype(int)

        if not tracker.needs_recognition(bbox_full):
            continue

        name, sim, is_match = find_match(face.embedding, known_embeddings, known_ids)

        if not is_match:
            x1, y1, x2, y2 = bbox_small
            pad = 15
            h, w = imgS.shape[:2]
            x1c = max(0, x1 - pad); y1c = max(0, y1 - pad)
            x2c = min(w, x2 + pad); y2c = min(h, y2 + pad)
            face_crop = imgS[y1c:y2c, x1c:x2c]

            angle_used = 0
            if face_crop.size > 0:
                for angle in [30, -30, 60, -60]:
                    crop_h, crop_w = face_crop.shape[:2]
                    center = (crop_w // 2, crop_h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    rotated = cv2.warpAffine(face_crop, M, (crop_w, crop_h))

                    rot_faces = app_small.get(rotated)
                    if not rot_faces:
                        continue
                    rot_faces = sorted(rot_faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
                    rot_name, rot_sim, rot_is_match = find_match(rot_faces[0].embedding, known_embeddings, known_ids)
                    if rot_is_match:
                        name, sim, is_match = rot_name, rot_sim, rot_is_match
                        angle_used = angle
                        break
        else:
            angle_used = 0

        tracker.update(bbox_full, name, sim, is_match, angle_used)

    live_bboxes_full = [(b * 2).tolist() for b in live_bboxes_small]
    return tracker.tick(live_bboxes_full)



def main():
    known_embeddings, known_ids = load_encodings()

    app = insightface.app.FaceAnalysis('buffalo_l', providers=['CUDAExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(640, 640))

    app_small = insightface.app.FaceAnalysis('buffalo_l', providers=['CUDAExecutionProvider'])
    app_small.prepare(ctx_id=0, det_size=(320, 320))

    tracker = FaceTracker(reidentify_every=REIDENTIFY_EVERY_N)
    cap = KinectCapture()
    prev_time = 0

    while True:
        img = cap.read()

        if img is None:
            cv2.waitKey(1)
            continue

        imgS = cv2.resize(img, (960, 540))
        display = imgS.copy()

        results = at_diff_angles(imgS, app, app_small, known_embeddings, known_ids, tracker)

        for (bbox, name, sim, is_match, angle) in results:
            print(f"[MATCH] name={name}  sim={sim:.4f}  matched={is_match}  angle={angle}")
            x1, y1, x2, y2 = [c // 2 for c in bbox]
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            cv2.putText(display, f"{name} {sim:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        curr_time = cv2.getTickCount()
        fps = cv2.getTickFrequency() / (curr_time - prev_time) if prev_time > 0 else 0
        prev_time = curr_time
        cv2.putText(display, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

        cv2.imshow("Kinect V2 — Face Recognition", display)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Quit.")
            break

    cap.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()