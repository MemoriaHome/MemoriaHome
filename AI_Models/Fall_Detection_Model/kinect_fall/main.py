from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import argparse
import queue
from shared.config import Config
from shared.frame_bus import FrameBus
from capture.kinect_capture import KinectCapture
from modules.fall_detection import FallDetectionModule
from modules.face_recognition import FaceRecognitionModule
from modules.compositor import CompositorModule
from modules.display import DisplayModule


def main():
    parser = argparse.ArgumentParser(description="MemoriaHome Kinect Monitor")
    parser.add_argument("--verbose", action="store_true",
                        help="Show per-frame body tracking info")
    args = parser.parse_args()

    config = Config.load()

    bus = FrameBus(maxsize=30)
    fall_queue = bus.register()
    face_queue = bus.register()

    fall_annotated_queue = queue.Queue(maxsize=10)  # FallDetection → Compositor
    face_results_queue   = queue.Queue(maxsize=5)   # FaceRecognition → Compositor
    display_queue        = queue.Queue(maxsize=10)  # Compositor → Display
    command_queue        = queue.Queue()

    face_module       = FaceRecognitionModule(face_queue, config, face_results_queue)
    fall_module       = FallDetectionModule(fall_queue, config, fall_annotated_queue, command_queue, verbose=args.verbose, face_module=face_module)
    compositor_module = CompositorModule(fall_annotated_queue, face_results_queue, display_queue)
    display_module    = DisplayModule(display_queue, config, command_queue)

    face_module.start()
    fall_module.start()
    display_module.start()
    compositor_module.start()

    capture = KinectCapture(bus)
    try:
        print("MemoriaHome Kinect Monitor starting...")
        capture.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        fall_module.stop()
        face_module.stop()
        compositor_module.stop()
        display_module.stop()


if __name__ == "__main__":
    main()