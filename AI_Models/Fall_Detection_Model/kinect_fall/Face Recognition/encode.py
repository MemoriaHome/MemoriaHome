import cv2
import insightface
import pickle
from dotenv import load_dotenv
import os
import time
import argparse
import numpy as np

import boto3

from KinectCapture import KinectCapture

load_dotenv()

BUCKET = os.getenv('R2_BUCKET')
PREFIX = "patients/"

SAMPLE_EVERY_N = 15
MAX_DURATION = 20

s3 = boto3.client(
    service_name = 's3',
    endpoint_url=os.getenv('R2_ENDPOINT'),
    aws_access_key_id=os.getenv('R2_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('R2_SECRET_KEY'),
    region_name='auto',
)

response = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX, Delimiter='/')
folders = response.get('CommonPrefixes', [])

embeddingsListKnown = []
patientNames = []
patientIds = []

id_to_name = {}

if not folders:
    print("No patients found in the database")
    embeddingsListKnown, patientNames = [], []
    
for person in folders:
    person_prefix = person['Prefix']
    person_id = person_prefix.rstrip('/').split('/')[-1]

    emb_path = f'{person_prefix}embedding.pkl'
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=emb_path)
        embeddings = pickle.loads(obj["Body"].read())

        # Resolve folder contents to find the name file dynamically
        objects = s3.list_objects_v2(Bucket=BUCKET, Prefix=person_prefix)
        actual_name = person_id
        if 'Contents' in objects:
            for item in objects['Contents']:
                key = item['Key']
                if not key.endswith('embedding.pkl') and key != person_prefix:
                    actual_name = key.split('/')[-1]
                    break

        id_to_name[person_id] = actual_name
        for emb in embeddings:
            embeddingsListKnown.append(emb)
            patientNames.append(actual_name)
            patientIds.append(person_id)
        print(f"[INFO] Loaded {len(embeddings)} embedding(s) for ID {person_id} ({actual_name})")
    except Exception as e:
        print(f"[WARNING] Could not load {emb_path}: {e}")

print(f"[INFO] Loaded {len(patientNames)} embedding(s) for {len(set(patientNames))} person(s).")


def get_face_embedding(frame):
    faces = app.get(frame)
    if not faces:
        print("No face detected")
        return None
    if faces:
        faces = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
        return faces[0].embedding
    

def enroll_patient(patientName, patient_id):
    cap = KinectCapture()
    frame_idx = 0
    captured = 0
    tempEmbList = []
    tempNameList = []
    patientId = patient_id
    start_time = time.time()

    print(f"Enrolling: {patientName} | 'q' = save & quit | 'c' = cancel")

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
                tempNameList.append(patientName)
                captured += 1
                print(f"Captured embedding #{captured} for {patientName}")
            else:
                print("No face detected, skipping frame")

        frame_idx += 1
        cv2.imshow("Kinect V2 — Enrollment", frame)
        key = cv2.waitKey(1) & 0xFF

        if elapsed > MAX_DURATION or key == ord('q'):
            if elapsed > MAX_DURATION:
                print("Enrollment complete")
            embeddingsListKnown.extend(tempEmbList)
            patientNames.extend(tempNameList)
            id_to_name[str(patientId)] = patientName
            data = pickle.dumps(tempEmbList)
            person_key = f"patients/{patientId}/embedding.pkl"
            person_name = f'patients/{patientId}/{patientName}'
            s3.put_object(Bucket=BUCKET, Key=person_key, Body=data)
            s3.put_object(Bucket=BUCKET, Key=person_name, Body=patientName)

            print(f"Saved {captured} embedding(s) for '{patientName}' to R2")
            break

        if key == ord('c'):
            print("Cancelled")
            break

    cap.close()
    cv2.destroyAllWindows()


def update_patient(patientName, patientId = None):
    if patientName not in patientNames:
        print(f"Patient '{patientName}' not found.")
        return
    print(f"Re-enrolling '{patientName}'...")
    if patientId is None:
        target_id = None
        for k, v in id_to_name.items():
            if v == patientName:
                target_id = k
                break
        enroll_patient(patientName, target_id)
    else:
        remove_patient(patientName, silent=True)
        enroll_patient(patientName, patientId)


def remove_patient(patientName, silent=False):
    indices = [i for i, pid in enumerate(patientNames) if pid == patientName]
    if not indices:
        print(f"Patient '{patientName}' not found.")
        return
        
    target_id = None
    for k, v in id_to_name.items():
        if v == patientName:
            target_id = k
            break

    for i in sorted(indices, reverse=True):
        embeddingsListKnown.pop(i)
        patientNames.pop(i)

    if target_id is not None:
        s3.delete_object(Bucket=BUCKET, Key=f"patients/{target_id}/embedding.pkl")
        s3.delete_object(Bucket=BUCKET, Key=f"patients/{target_id}/{patientName}")
    
    if not silent:
        print(f"Removed {len(indices)} embedding(s) for '{patientName}'.")


def inspect_patients():
    if not patientNames:
        print("No patients enrolled.")
        return
    ids = sorted(set(patientNames))
    print(f"\n{len(ids)} enrolled patient(s):")
    for pid in ids:
        count = patientNames.count(pid)
        print(f"{pid} : {count} embedding(s)")


app = insightface.app.FaceAnalysis('buffalo_l', providers=['CUDAExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))

# cap = cv2.VideoCapture(0) # KinectCapture()
# frame_idx = 0
# captured = 0

# start_time = time.time()
# tempEmbList = []
# tempNameList = []

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--mode", required=True, choices=['e', 'u', 'r', 's', 'q'])
parser.add_argument('-i', '--id', required=False)
parser.add_argument('-n', '--name', required=True)
args = parser.parse_args()

patientName = args.name
patientId = args.id

if args.mode == 'e':
    if not patientName or not patientId:
        print("ID cannot be empty.")
        patientName = input("Enter patient Name: ").strip()
        patientId = input("Enter patient Id: ").strip()
    if patientName in patientNames or patientId in patientIds:
        print(f"Patient '{patientName}' already exists. Use 'u' to update.")
    elif patientName:
        enroll_patient(patientName, patientId)

elif args.mode == 'u':
    if not patientName:
        patientName = input("Enter patient Name to update: ").strip()
    new_id = input("Do you want to update the patient's ID? (y, n) ") 
    if new_id == "y" or new_id == "Y":
        patientId = input("Enter new ID: ")
        update_patient(patientName, patientId)
    else :   
        update_patient(patientName)

elif args.mode == 'r':
    if not patientName:
        patientName = input("Enter patient Name to remove: ").strip()

    remove_patient(patientName)

elif args.mode == 's':
    inspect_patients()
        
else:
    print("Invalid choice")