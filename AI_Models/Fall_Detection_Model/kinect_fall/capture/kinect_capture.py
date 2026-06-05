import cv2
import numpy as np
from pykinect2 import PyKinectRuntime
from pykinect2.PyKinectV2 import FrameSourceTypes_Color, FrameSourceTypes_Depth, FrameSourceTypes_Body
from shared.frame import KinectFrame
from shared.frame_bus import FrameBus


class KinectCapture:
    """
    Owns the Kinect sensor and the capture loop.
    Publishes KinectFrame objects to the FrameBus on every new color frame.
    """

    def __init__(self, bus: FrameBus):
        self._bus = bus
        self._kinect = PyKinectRuntime.PyKinectRuntime(
            FrameSourceTypes_Color | FrameSourceTypes_Depth | FrameSourceTypes_Body
        )
        self.color_w = self._kinect.color_frame_desc.Width
        self.color_h = self._kinect.color_frame_desc.Height
        self.depth_w = self._kinect.depth_frame_desc.Width
        self.depth_h = self._kinect.depth_frame_desc.Height

    def run(self) -> None:
        """Blocking capture loop. Run this on the main thread."""
        try:
            while True:
                self._tick()
        finally:
            self._kinect.close()

    def _tick(self) -> None:
        if not self._kinect.has_new_color_frame():
            return

        color = self._get_color()
        depth = self._get_depth()
        body_frame = self._get_body_frame()

        frame = KinectFrame(color=color, depth=depth, body_frame=body_frame)
        self._bus.publish(frame)

    def _get_color(self) -> np.ndarray:
        raw = self._kinect.get_last_color_frame()
        img = raw.reshape((self.color_h, self.color_w, 4)).astype(np.uint8)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _get_depth(self):
        if self._kinect.has_new_depth_frame():
            raw = self._kinect.get_last_depth_frame()
            return raw.reshape((self.depth_h, self.depth_w))
        return None

    def _get_body_frame(self):
        if self._kinect.has_new_body_frame():
            return self._kinect.get_last_body_frame()
        return None