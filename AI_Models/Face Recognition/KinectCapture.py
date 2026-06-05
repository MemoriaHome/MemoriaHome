import threading
import queue
from pykinect2 import PyKinectV2
from pykinect2.PyKinectV2 import *
from pykinect2 import PyKinectRuntime
import cv2
import numpy as np

class KinectCapture:
    def __init__(self):
        self._kinect = PyKinectRuntime.PyKinectRuntime(PyKinectV2.FrameSourceTypes_Color)
        self._queue  = queue.Queue(maxsize=2)
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            if not self._kinect.has_new_color_frame():
                continue
            frame = self._kinect.get_last_color_frame()
            frame = frame.reshape((1080, 1920, 4)).astype(np.uint8)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            self._queue.put(frame)

    def read(self):
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        self._kinect.close()
