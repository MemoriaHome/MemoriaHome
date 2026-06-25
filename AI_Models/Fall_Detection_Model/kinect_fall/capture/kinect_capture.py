import cv2
import numpy as np
import time
from pykinect2 import PyKinectRuntime
from pykinect2.PyKinectV2 import (
    FrameSourceTypes_Body,
    FrameSourceTypes_Color,
    FrameSourceTypes_Depth,
    FrameSourceTypes_Infrared,
    JointType_Head,
    JointType_HipLeft,
    JointType_HipRight,
    JointType_Neck,
    JointType_ShoulderLeft,
    JointType_ShoulderRight,
    JointType_SpineBase,
    JointType_SpineMid,
    JointType_SpineShoulder,
)
from shared.frame import BodySummary, KinectFrame
from shared.frame_bus import FrameBus


BODY_BOX_JOINTS = (
    JointType_Head,
    JointType_Neck,
    JointType_SpineShoulder,
    JointType_ShoulderLeft,
    JointType_ShoulderRight,
    JointType_SpineMid,
    JointType_SpineBase,
    JointType_HipLeft,
    JointType_HipRight,
)


class KinectCapture:
    """
    Owns the Kinect sensor and the capture loop.
    Publishes KinectFrame objects to the FrameBus on every new color frame.
    """

    def __init__(self, bus: FrameBus, capture_fps: int | float | None = None,
                 display_tick=None):
        self._bus = bus
        self._capture_interval = 1.0 / capture_fps if capture_fps and capture_fps > 0 else 0.0
        self._last_publish_time = 0.0
        # Called once per loop iteration on the main thread so cv2.imshow /
        # cv2.waitKey always run here (Windows requirement).  Returns False to
        # request a clean shutdown (e.g. user pressed 'q').
        self._display_tick = display_tick
        self._kinect = PyKinectRuntime.PyKinectRuntime(
            FrameSourceTypes_Color
            | FrameSourceTypes_Depth
            | FrameSourceTypes_Infrared
            | FrameSourceTypes_Body
        )
        self.color_w = self._kinect.color_frame_desc.Width
        self.color_h = self._kinect.color_frame_desc.Height
        self.depth_w = self._kinect.depth_frame_desc.Width
        self.depth_h = self._kinect.depth_frame_desc.Height
        self.infrared_w = self.depth_w
        self.infrared_h = self.depth_h
        self._infrared_supported = hasattr(self._kinect, "get_last_infrared_frame")
        if not self._infrared_supported:
            print("[KINECT] Infrared frames are not supported by this pykinect2 runtime.")

    def run(self) -> None:
        """Blocking capture loop. Run this on the main thread."""
        try:
            while True:
                self._tick()
                # Drive the display and handle keypresses on the main thread.
                # display_tick() returns False when the user requests shutdown.
                if self._display_tick is not None and not self._display_tick():
                    break
        finally:
            self._kinect.close()

    def _tick(self) -> None:
        if not self._kinect.has_new_color_frame():
            return
        now = time.monotonic()
        if self._capture_interval and now - self._last_publish_time < self._capture_interval:
            return
        self._last_publish_time = now
        color = self._get_color()
        depth = self._get_depth()
        infrared = self._get_infrared()
        body_frame = self._get_body_frame()
        body_summaries = self._get_body_summaries(body_frame)
        frame = KinectFrame(
            color=color,
            depth=depth,
            infrared=infrared,
            body_frame=body_frame,
            body_summaries=body_summaries,
        )
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

    def _get_infrared(self):
        if self._infrared_supported and self._kinect.has_new_infrared_frame():
            raw = self._kinect.get_last_infrared_frame()
            return raw.reshape((self.infrared_h, self.infrared_w))
        return None

    def _get_body_frame(self):
        if self._kinect.has_new_body_frame():
            return self._kinect.get_last_body_frame()
        return None

    def _get_body_summaries(self, body_frame) -> list[BodySummary]:
        if body_frame is None:
            return []

        summaries = []
        for body_index in range(6):
            body = body_frame.bodies[body_index]
            if not body.is_tracked:
                continue

            tracking_id = str(getattr(body, "tracking_id", None) or f"body-{body_index}")
            color_points = self._project_body_joints(body)
            bbox = self._body_bbox_from_points(color_points)
            summaries.append(
                BodySummary(
                    tracking_id=tracking_id,
                    body_index=body_index,
                    color_bbox=bbox,
                    head=color_points.get(JointType_Head),
                    spine_base=color_points.get(JointType_SpineBase),
                )
            )
        return summaries

    def _project_body_joints(self, body) -> dict[int, tuple[int, int]]:
        try:
            projected = self._kinect.body_joints_to_color_space(body.joints)
        except Exception:
            return {}

        points = {}
        for joint_type in BODY_BOX_JOINTS:
            point = projected[joint_type]
            x = float(getattr(point, "x", float("nan")))
            y = float(getattr(point, "y", float("nan")))
            if not np.isfinite(x) or not np.isfinite(y):
                continue
            if x < -self.color_w or x > self.color_w * 2:
                continue
            if y < -self.color_h or y > self.color_h * 2:
                continue
            points[joint_type] = (
                int(np.clip(x, 0, self.color_w - 1)),
                int(np.clip(y, 0, self.color_h - 1)),
            )
        return points

    def _body_bbox_from_points(
        self,
        color_points: dict[int, tuple[int, int]],
    ) -> tuple[int, int, int, int] | None:
        if len(color_points) < 2:
            return None

        xs = [p[0] for p in color_points.values()]
        ys = [p[1] for p in color_points.values()]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        width = max(x2 - x1, 80)
        height = max(y2 - y1, 180)
        pad_x = int(width * 0.55)
        pad_top = int(height * 0.45)
        pad_bottom = int(height * 0.25)
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_top),
            min(self.color_w - 1, x2 + pad_x),
            min(self.color_h - 1, y2 + pad_bottom),
        )
