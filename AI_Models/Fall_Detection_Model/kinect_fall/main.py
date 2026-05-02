

import os
import time
import cv2
import numpy as np
import tempfile
import boto3
import io
import json
import sys
import datetime
import requests
from threading import Thread
from copy import deepcopy
from botocore.config import Config
from ultralytics import YOLO
from pykinect2 import PyKinectV2
from pykinect2.PyKinectV2 import *
from pykinect2 import PyKinectRuntime

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

model = YOLO('yolo models/yolov8n-pose.pt')

try:
    with open('config.json', 'r') as file: #contains device config values
        data = json.load(file)
except FileNotFoundError:
    sys.exit("[ERROR]Config.json File Not Found...Exiting")
except json.JSONDecodeError:
    sys.exit("[ERROR]Config.json File Contains Invalid Json. Check syntax...Exiting")

DEVICE_ID = data['device_id']
PATIENT_ID = data['patient_id']
ROOM = data['room']
BACKEND_URL = data['backend_url']
RECORDING_PATH = data['recording_path']

print(data)

kinect = PyKinectRuntime.PyKinectRuntime(
    FrameSourceTypes_Color | FrameSourceTypes_Depth | FrameSourceTypes_Body
)

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    config=Config(signature_version='s3v4'),
    region_name="auto",
)

COLOR_WIDTH, COLOR_HEIGHT = kinect.color_frame_desc.Width, kinect.color_frame_desc.Height
DEPTH_WIDTH, DEPTH_HEIGHT = kinect.depth_frame_desc.Width, kinect.depth_frame_desc.Height
MIN_ELAPSED_TIME_THRESHOLD = 10
VIDEO_FPS = 10
MAX_AFTER_FRAMES = 150

fallen_state = False
fall_start_time = None
taking_video = False
video_frames_before = []
video_frames_after = []
frozen_video_frames_before = []
video_blob_name = ""
incident_name = ""
blob_number = 1

# ---

def get_kinect_frames():
    color = None
    depth = None
    if kinect.has_new_color_frame():
        raw = kinect.get_last_color_frame()
        color = raw.reshape((COLOR_HEIGHT, COLOR_WIDTH, 4)).astype(np.uint8)
        color = cv2.cvtColor(color, cv2.COLOR_BGRA2BGR)

    if kinect.has_new_depth_frame():
        raw = kinect.get_last_depth_frame()
        depth = raw.reshape((DEPTH_HEIGHT, DEPTH_WIDTH))

    return color, depth

def get_height_above_floor(joint_position, floor_plane):
    A, B, C, D = floor_plane.x, floor_plane.y, floor_plane.z, floor_plane.w
    x, y, z = joint_position.x, joint_position.y, joint_position.z
    height = (A * x) + (B * y) + (C * z) + D
    return height

def upload_clip_to_r2(clip_path):
    global video_blob_name
    try:
        video_object_name = f"fallen_clip_{int(time.time())}.mp4"
        with open(clip_path, "rb") as clip_file:
            s3.upload_fileobj(clip_file, R2_BUCKET_NAME, video_object_name)
        video_blob_name = video_object_name
        print(f"Uploaded video: {video_blob_name}")
    except Exception as e:
        print(f"Error uploading video: {e}")

def save_info_in_r2():
    global blob_number, incident_name
    try:
        fallen_info = {
            "status": "Fallen",
            "timestamp": str(time.time()),
            "filename": video_blob_name
        }
        fall_info_json = json.dumps(fallen_info).encode("utf-8")
        incident_name = f"incident_{blob_number}_{int(time.time())}"
        blob_number += 1
        s3.upload_fileobj(io.BytesIO(fall_info_json), R2_BUCKET_NAME, incident_name)
        print(f"Uploaded JSON: {incident_name}")
    except Exception as e:
        print(f"Error uploading JSON: {e}")

def send_api_call(event_type="Unknown"):
    log_file = "fall_incidents.csv"
    file_exists = os.path.isfile(log_file)
    payload = {
        "deviceId": DEVICE_ID,
        "patientId": PATIENT_ID,
        "room": ROOM,
        "eventType": event_type,
        "timestamp": datetime.datetime.now().isoformat(),
        "videoUrl": f"{R2_PUBLIC_URL}/{video_blob_name}",
        "incidentName": incident_name
    }

    def post_with_retry():
        attempt = 0
        while True:
            try:
                response = requests.post(
                    f"{BACKEND_URL}/alert/fall",
                    json=payload,
                    timeout=10,
                    verify = False
                )
                if response.status_code == 201:
                    print(f"Alert sent successfully.")
                    break
                else:
                    print(f"Unexpected status {response.status_code}, retrying...")
            except requests.exceptions.RequestException as e:
                print(f"Alert attempt {attempt} failed: {e}, retrying in 5s...")
            attempt += 1
            time.sleep(5)

    Thread(target=post_with_retry, daemon=True).start()

    with open(log_file, "a") as f:
        video_url = f"{R2_PUBLIC_URL}/{video_blob_name}"
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        if not file_exists:
            f.write("Timestamp,Incident_Name,Video_URL\n")
        f.write(f"{timestamp},{incident_name},{video_url}\n")
    print(f"Incident logged locally to {log_file}")

def save_video_clip(event_type="Unknown"):
    global frozen_video_frames_before, video_frames_after
    clip_frames = frozen_video_frames_before + video_frames_after

    Date = str(datetime.date)
    Time = str(datetime.time)

    Local_save_path = os.path.join(RECORDING_PATH, Date)
    output_filename = f"Fall_{Time}.mp4"

    full_path_local_save = os.path.join(Local_save_path, output_filename)

    if not clip_frames:
        return

    print(f"Saving clip for event: {event_type}")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        temp_file_path = tmp.name

    h, w, _ = clip_frames[0].shape

    out_local = cv2.VideoWriter(full_path_local_save, cv2.VideoWriter_fourcc(*'mp4v'), VIDEO_FPS, (w, h))
    out_cloud = cv2.VideoWriter(temp_file_path, cv2.VideoWriter_fourcc(*'mp4v'), VIDEO_FPS, (w, h))

    for frame in clip_frames:
        out_cloud.write(frame)
    out_cloud.release()

    for frame in clip_frames:
        out_local.write(frame)
    out_local.release()

    upload_clip_to_r2(temp_file_path)
    save_info_in_r2()
    send_api_call()

    try:
        os.remove(temp_file_path)
    except OSError:
        pass

# ---

print("Kinect Fall Detection System starting...")
try:
    while True:
        current_color, current_depth = get_kinect_frames()
        if current_color is None:
            continue

        video_frames_before.append(current_color.copy())
        if len(video_frames_before) > 100:
            video_frames_before.pop(0)

        if taking_video:
            video_frames_after.append(current_color.copy())
            if len(video_frames_after) > MAX_AFTER_FRAMES:
                video_frames_after.pop(0)

        results = model.predict(current_color, conf=0.4, verbose=False)
        r = results[0]

        height_from_floor = 0.0
        is_on_floor = False
        body_frame_updated = False

        if kinect.has_new_body_frame():
            bodies = kinect.get_last_body_frame()
            if bodies:
                floor_plane = bodies.floor_clip_plane
                for i in range(kinect.max_body_count):
                    body = bodies.bodies[i]
                    if body.is_tracked:
                        spine_joint = body.joints[JointType_SpineBase].Position
                        height_from_floor = get_height_above_floor(spine_joint, floor_plane)
                        # print(f"Height from floor: {height_from_floor:.2f}m")
                        is_on_floor = (abs(height_from_floor) < 0.4)
                        body_frame_updated = True
                        print(f"Spine height from floor: {height_from_floor:.2f}m")
                        break

        if len(r.keypoints.xy) > 0 and len(r.keypoints.xy[0]) > 0:
            y_vals = [kp[1].item() for kp in r.keypoints.xy[0] if kp[1] > 0]
        else:
            y_vals = []

        if is_on_floor and len(y_vals) >= 6:
            if not fallen_state:
                print("ALERT: Possible Fall Detected. Monitoring for 10 seconds...")
                fallen_state = True
                fall_start_time = time.time()
                taking_video = True
                frozen_video_frames_before = list(video_frames_before)

        if fallen_state and body_frame_updated:
            elapsed = time.time() - fall_start_time
            if abs(height_from_floor) > 0.6:
                print("Recovery detected. Alerting caregiver...")
                save_video_clip(event_type="Recovered Fall")

                fallen_state = False
                taking_video = False
                video_frames_after = []
                frozen_video_frames_before = []

            elif elapsed >= MIN_ELAPSED_TIME_THRESHOLD:
                print("FALL CONFIRMED. Finalizing video and alerting...")
                save_video_clip(event_type="Unrecovered Fall")

                fallen_state = False
                taking_video = False
                video_frames_after = []
                frozen_video_frames_before = []

        display_frame = r.plot()
        status_text = "STATUS: FALLING" if fallen_state else "STATUS: SAFE"
        cv2.putText(display_frame, status_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 0, 255) if fallen_state else (0, 255, 0), 2)

        cv2.imshow("Kinect V2 Fall Detection", cv2.resize(display_frame, (960, 540)))

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    cv2.destroyAllWindows()
    kinect.close()