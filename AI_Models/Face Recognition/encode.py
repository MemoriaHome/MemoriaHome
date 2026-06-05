import cv2
import insightface
import pickle
import os
import time
import argparse
import numpy as np

import boto3

from KinectCapture import KinectCapture

BUCKET= "memoriahome"
PREFIX = "patients/"

SAMPLE_EVERY_N = 15
MAX_DURATION = 20


s3 = boto3.client(
    service_name = 's3',
    endpoint_url='https://1496516e0587f1bcbed6294961f40390.r2.cloudflarestorage.com',
    aws_access_key_id='b97874c5d8eafde78997be23f05b6c95',
    aws_secret_access_key='1334256a544967429926a8f3046dbc0c0d0438297efc4f159c4d71f17f524d26',
    region_name='auto',
)


response = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX, Delimiter='/')
folders = response.get('CommonPrefixes', [])

embeddingsListKnown = []
patientIds = []

if not folders:
    print("No patients found in the database")
    embeddingsListKnown, patientIds = [], []
    
for person in folders:
    person_prefix = person['Prefix']
    person_id = person_prefix.rstrip('/').split('/')[-1]

    emb_path = f'{person_prefix}embedding.pkl'
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=emb_path)
        embeddings = pickle.loads(obj["Body"].read())
        for emb in embeddings:
            embeddingsListKnown.append(emb)
            patientIds.append(person_id)
        print(f"[INFO] Loaded {len(embeddings)} embedding(s) for ID {person_id}")
    except Exception as e:
        print(f"[WARNING] Could not load {emb_path}: {e}")

print(f"[INFO] Loaded {len(patientIds)} embedding(s) for {len(set(patientIds))} person(s).")


def get_face_embedding(frame):
    faces = app.get(frame)
    if not faces:
        print("No face detected")
        return None
    if faces:
        faces = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
        return faces[0].embedding
    

def enroll_patient(patientId):
    cap = KinectCapture()
    frame_idx = 0
    captured = 0
    tempEmbList = []
    tempIdList = []
    start_time = time.time()

    print(f"Enrolling: {patientId} | 'q' = save & quit | 'c' = cancel")

    while True:
        frame = cap.read()

        if frame is None:
            cv2.waitKey(1)
            continue

        elapsed = time.time() - start_time

        if frame_idx % SAMPLE_EVERY_N == 0:
            embedding = get_face_embedding(frame)
            if embedding is not None:
                tempEmbList.append(embedding)
                tempIdList.append(patientId)
                captured += 1
                print(f"Captured embedding #{captured} for {patientId}")
            else:
                print("No face detected, skipping frame")

        frame_idx += 1
        cv2.imshow("Kinect V2 — Enrollment", frame)
        key = cv2.waitKey(1) & 0xFF

        if elapsed > MAX_DURATION or key == ord('q'):
            if elapsed > MAX_DURATION:
                print("Enrollment complete")
            embeddingsListKnown.extend(tempEmbList)
            patientIds.extend(tempIdList)
            
            data = pickle.dumps(tempEmbList)
            person_key = f"patients/{patientId}/embedding.pkl"
            s3.put_object(Bucket=BUCKET, Key=person_key, Body=data)
            print(f"Saved {captured} embedding(s) for '{patientId}' to R2")
            break

        if key == ord('c'):
            print("Cancelled")
            break

    cap.close()
    cv2.destroyAllWindows()


def update_patient(patientId):
    if patientId not in patientIds:
        print(f"Patient '{patientId}' not found.")
        return
    # remove_patient(patientId, silent=True)
    print(f"Re-enrolling '{patientId}'...")
    enroll_patient(patientId)


def remove_patient(patientId, silent=False):
    indices = [i for i, pid in enumerate(patientIds) if pid == patientId]
    if not indices:
        print(f"Patient '{patientId}' not found.")
        return
    for i in sorted(indices, reverse=True):
        embeddingsListKnown.pop(i)
        patientIds.pop(i)

    s3.delete_object(Bucket=BUCKET, Key=f"patients/{patientId}/embedding.pkl")
    
    if not silent:
        print(f"Removed {len(indices)} embedding(s) for '{patientId}'.")



def inspect_patients():
    if not patientIds:
        print("No patients enrolled.")
        return
    ids = sorted(set(patientIds))
    print(f"\n{len(ids)} enrolled patient(s):")
    for pid in ids:
        count = patientIds.count(pid)
        print(f"{pid} : {count} embedding(s)")


app = insightface.app.FaceAnalysis('buffalo_l', providers=['CUDAExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))

# cap = cv2.VideoCapture(0) # KinectCapture()
# frame_idx = 0
# captured = 0

# start_time = time.time()
# tempEmbList = []
# tempIdList = []

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--mode", required=True, choices=['e', 'u', 'r', 's', 'q'])
parser.add_argument('-i', '--id', required=False)
args = parser.parse_args()

patientId = args.id

if args.mode == 'e':
    patientId = args.id
    if not patientId:
        print("ID cannot be empty.")
        input("Enter patient ID: ").strip()
    elif patientId in patientIds:
        print(f"Patient '{patientId}' already exists. Use 'u' to update.")
    else:
        enroll_patient(patientId)

elif args.mode == 'u':
    if not patientId:
        patientId = input("Enter patient ID to update: ").strip()
    update_patient(patientId)

elif args.mode == 'r':
    if not patientId:
        patientId = input("Enter patient ID to remove: ").strip()
    remove_patient(patientId)

elif args.mode == 's':
    inspect_patients()
        
else:
    print("Invalid choise")