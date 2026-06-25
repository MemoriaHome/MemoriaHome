from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import argparse
import queue
import threading

import cv2

from capture.kinect_capture import KinectCapture
# ultralytics and torchvision must load before SpeechBrain to avoid
# a k2 lazy-import conflict triggered by torchvision's meta registrations
from modules.fall_detection import FallDetectionModule
from modules.face_recognition import FaceRecognitionModule
from modules.audio_detection import AudioDetectionModule
from modules.compositor import CompositorModule
from modules.live_stream import LiveStreamModule
from modules.speech_analysis import SpeechAnalysisModule
from shared.config import Config
from shared.frame_bus import FrameBus
from webrtc.service import KinectWebRTCService
from webrtc.stream_hub import AnnotatedStreamHub

WINDOW_NAME = "MemoriaHome Monitor"


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
    fall_queue   = bus.register()
    face_queue   = bus.register()
    stream_queue = bus.register()

    fall_annotated_queue      = queue.Queue(maxsize=4)   # small: display only needs latest
    face_results_queue        = queue.Queue(maxsize=10)
    stream_face_results_queue = queue.Queue(maxsize=10)
    stream_fall_overlay_queue = queue.Queue(maxsize=20)
    # display_queue is drained on the MAIN THREAD via cv2.imshow — keep it small
    # so we always show the freshest composited frame.
    display_queue             = queue.Queue(maxsize=4)
    command_queue             = queue.Queue()

    stream_hub     = AnnotatedStreamHub(config.stream_width, config.stream_height)
    webrtc_service = KinectWebRTCService(config, stream_hub)

    face_module = FaceRecognitionModule(
        face_queue,
        config,
        [face_results_queue, stream_face_results_queue],
        max_fps=config.face_recognition_fps,
    )
    fall_module = FallDetectionModule(
        fall_queue,
        config,
        annotated_queue=fall_annotated_queue,
        command_queue=command_queue,
        stream_overlay_queue=stream_fall_overlay_queue,
        verbose=args.verbose,
        face_module=face_module,
        max_fps=config.fall_detection_fps,
    )
    compositor_module = CompositorModule(
        fall_annotated_queue,
        face_results_queue,
        display_queue,
        max_fps=config.compositor_fps,
    )
    live_stream_module = LiveStreamModule(
        stream_queue,
        stream_face_results_queue,
        stream_fall_overlay_queue,
        stream_hub,
        max_fps=config.live_stream_fps,
    )
    # DisplayModule is intentionally removed: cv2.imshow / cv2.waitKey MUST run
    # on the main thread on Windows. The display loop below (inside capture.run)
    # handles rendering directly.

    # Audio pipeline
    audio_module  = AudioDetectionModule(config)
    speech_module = SpeechAnalysisModule(config)
    audio_module.set_speech_module(speech_module)
    fall_module.set_audio_module(audio_module)

    face_module.start()
    fall_module.start()
    live_stream_module.start()
    compositor_module.start()
    webrtc_service.start()
    speech_module.start()
    audio_module.start()

    # ── Main-thread display callback ──────────────────────────────────────────
    # KinectCapture.run() calls this once per captured frame so cv2 operations
    # always execute on the main thread (Windows requirement).
    def display_tick():
        """Drain the display queue and show the freshest composited frame."""
        frame = None
        try:
            while True:
                frame = display_queue.get_nowait()
        except queue.Empty:
            pass

        if frame is not None:
            cv2.imshow(WINDOW_NAME, cv2.resize(frame, (960, 540)))

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            return False          # signal capture loop to stop
        if key == ord('f'):
            command_queue.put("simulate_fall")
        elif key == ord('r'):
            command_queue.put("simulate_recovery")
        elif key == ord('s'):
            command_queue.put("simulate_slow_fall")
        elif key == ord('1'):
            threading.Thread(
                target=audio_module.test_with_file,
                args=("test_sounds/scream.wav",),
                daemon=True,
            ).start()
        elif key == ord('2'):
            threading.Thread(
                target=audio_module.test_with_file,
                args=("test_sounds/groan.wav",),
                daemon=True,
            ).start()
        elif key == ord('3'):
            threading.Thread(
                target=audio_module.test_with_file,
                args=("test_sounds/stutter.wav", False),
                daemon=True,
            ).start()
        return True               # continue running

    # Pass display_tick to KinectCapture so it can be called each loop iteration.
    # KinectCapture.run() should call display_tick() after publishing each frame
    # and stop its loop when display_tick() returns False.
    capture = KinectCapture(bus, capture_fps=config.capture_fps,
                            display_tick=display_tick)
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
        webrtc_service.stop()
        # Bug 5 fix: only stop audio/speech if they were actually started
        if 'audio_module' in dir():
            audio_module.stop()
        if 'speech_module' in dir():
            speech_module.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
