import queue
import sys
from shared.config import Config
from shared.frame_bus import FrameBus
from capture.kinect_capture import KinectCapture
from modules.fall_detection import FallDetectionModule
from modules.display import DisplayModule


def main():
    config = Config.load()

    bus = FrameBus(maxsize=30)
    fall_queue = bus.register()

    annotated_queue = queue.Queue(maxsize=10)
    command_queue = queue.Queue()

    fall_module    = FallDetectionModule(fall_queue, config, annotated_queue, command_queue)
    display_module = DisplayModule(annotated_queue, config, command_queue)

    fall_module.start()
    display_module.start()

    capture = KinectCapture(bus)
    try:
        print("MemoriaHome Kinect Monitor starting...")
        capture.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        fall_module.stop()
        display_module.stop()


if __name__ == "__main__":
    main()