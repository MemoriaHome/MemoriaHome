from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import argparse
import queue

from capture.kinect_capture import KinectCapture
from modules.compositor import CompositorModule
from modules.display import DisplayModule
from modules.face_recognition import FaceRecognitionModule
from modules.fall_detection import FallDetectionModule
from modules.live_stream import LiveStreamModule
from shared.config import Config
from shared.frame_bus import FrameBus
from webrtc.service import KinectWebRTCService
from webrtc.stream_hub import AnnotatedStreamHub


def main():
    parser = argparse.ArgumentParser(description="MemoriaHome Kinect Monitor")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-frame body tracking info",
    )
    args = parser.parse_args()

    config = Config.load()

    bus = FrameBus(maxsize=30)
    fall_queue = bus.register()
    face_queue = bus.register()
    stream_queue = bus.register()

    fall_annotated_queue = queue.Queue(maxsize=10)
    face_results_queue = queue.Queue(maxsize=5)
    stream_face_results_queue = queue.Queue(maxsize=5)
    stream_fall_overlay_queue = queue.Queue(maxsize=10)
    display_queue = queue.Queue(maxsize=10)
    command_queue = queue.Queue()

    stream_hub = AnnotatedStreamHub(config.stream_width, config.stream_height)
    webrtc_service = KinectWebRTCService(config, stream_hub)

    face_module = FaceRecognitionModule(
        face_queue,
        config,
        [face_results_queue, stream_face_results_queue],
    )
    fall_module = FallDetectionModule(
        fall_queue,
        config,
        annotated_queue=fall_annotated_queue,
        command_queue=command_queue,
        stream_overlay_queue=stream_fall_overlay_queue,
        verbose=args.verbose,
        face_module=face_module,
    )
    compositor_module = CompositorModule(
        fall_annotated_queue,
        face_results_queue,
        display_queue,
    )
    live_stream_module = LiveStreamModule(
        stream_queue,
        stream_face_results_queue,
        stream_fall_overlay_queue,
        stream_hub,
    )
    display_module = DisplayModule(display_queue, config, command_queue)

    face_module.start()
    fall_module.start()
    live_stream_module.start()
    display_module.start()
    compositor_module.start()
    webrtc_service.start()

    capture = KinectCapture(bus)
    try:
        print("MemoriaHome Kinect Monitor starting...")
        capture.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        fall_module.stop()
        face_module.stop()
        live_stream_module.stop()
        compositor_module.stop()
        display_module.stop()
        webrtc_service.stop()


if __name__ == "__main__":
    main()
