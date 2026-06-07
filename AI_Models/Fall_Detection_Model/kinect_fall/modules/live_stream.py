import queue

import cv2
import numpy as np

from modules.base_module import BaseModule
from shared.stream_overlay import FallOverlay
from webrtc.stream_hub import AnnotatedStreamHub, STREAM_TYPES


class LiveStreamModule(BaseModule):
    """Renders annotated RGB/depth/IR frames into a WebRTC stream hub."""

    def __init__(
        self,
        frame_queue: queue.Queue,
        face_results_queue: queue.Queue,
        fall_overlay_queue: queue.Queue,
        stream_hub: AnnotatedStreamHub,
    ):
        super().__init__(frame_queue)
        self._face_results_queue = face_results_queue
        self._fall_overlay_queue = fall_overlay_queue
        self._stream_hub = stream_hub
        self._latest_faces = []
        self._latest_fall_overlay = FallOverlay()

    def _process_frame(self, frame) -> None:
        self._drain_overlay_queues()

        for stream_type in STREAM_TYPES:
            if not self._stream_hub.has_subscribers(stream_type):
                continue
            rendered = self._render_stream(frame, stream_type)
            if rendered is not None:
                self._stream_hub.update(stream_type, rendered)

    def _drain_overlay_queues(self) -> None:
        latest_faces = None
        try:
            while True:
                latest_faces = self._face_results_queue.get_nowait()
        except queue.Empty:
            pass
        if latest_faces is not None:
            self._latest_faces = latest_faces

        latest_fall = None
        try:
            while True:
                latest_fall = self._fall_overlay_queue.get_nowait()
        except queue.Empty:
            pass
        if latest_fall is not None:
            self._latest_fall_overlay = latest_fall

    def _render_stream(self, frame, stream_type: str) -> np.ndarray | None:
        if stream_type == "rgb":
            image = frame.color.copy() if frame.color is not None else None
        elif stream_type == "depth":
            image = self._render_depth(frame.depth)
        elif stream_type == "ir":
            image = self._render_infrared(frame.infrared)
        else:
            return None

        if image is None:
            return None

        target_size = (self._stream_hub.width, self._stream_hub.height)
        image = cv2.resize(image, target_size, interpolation=cv2.INTER_AREA)
        overlay_source_size = (
            frame.color.shape[:2] if frame.color is not None else image.shape[:2]
        )
        self._draw_fall_overlay(image, overlay_source_size)
        self._draw_face_overlay(image, overlay_source_size)
        return image

    @staticmethod
    def _render_depth(depth: np.ndarray | None) -> np.ndarray | None:
        if depth is None:
            return None
        clipped = np.clip(depth.astype(np.float32), 500, 4500)
        normalized = cv2.normalize(clipped, None, 0, 255, cv2.NORM_MINMAX)
        gray = normalized.astype(np.uint8)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _render_infrared(infrared: np.ndarray | None) -> np.ndarray | None:
        if infrared is None:
            return None
        clipped = np.clip(infrared.astype(np.float32), 0, 65535)
        normalized = cv2.normalize(clipped, None, 0, 255, cv2.NORM_MINMAX)
        gray = normalized.astype(np.uint8)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def _scale_bbox(
        self,
        bbox: tuple[int, int, int, int] | list[int],
        source_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        source_h, source_w = source_size
        scale_x = self._stream_hub.width / max(source_w, 1)
        scale_y = self._stream_hub.height / max(source_h, 1)
        x1, y1, x2, y2 = bbox[:4]
        return (
            int(x1 * scale_x),
            int(y1 * scale_y),
            int(x2 * scale_x),
            int(y2 * scale_y),
        )

    def _draw_fall_overlay(
        self,
        image: np.ndarray,
        source_size: tuple[int, int],
    ) -> None:
        overlay = self._latest_fall_overlay
        status_color = (0, 0, 255) if overlay.fallen else (0, 255, 0)
        cv2.putText(
            image,
            overlay.status,
            (24, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            status_color,
            2,
        )
        cv2.putText(
            image,
            f"Velocity: {overlay.velocity:.2f}m/s",
            (24, 68),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 0),
            1,
        )
        if overlay.floor_timer_seconds is not None and overlay.floor_timer_limit:
            cv2.putText(
                image,
                f"Floor timer: {overlay.floor_timer_seconds:.1f}s / {overlay.floor_timer_limit:.0f}s",
                (24, 96),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 165, 255),
                1,
            )

        for body in overlay.bodies:
            x1, y1, x2, y2 = self._scale_bbox(body.bbox, source_size)
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 200, 255), 2)
            label = body.label
            if body.confidence is not None:
                label = f"{label} {body.confidence:.2f}"
            cv2.putText(
                image,
                label,
                (x1, max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 200, 255),
                1,
            )

    def _draw_face_overlay(
        self,
        image: np.ndarray,
        source_size: tuple[int, int],
    ) -> None:
        for bbox, name, sim, _is_match, _angle in self._latest_faces:
            x1, y1, x2, y2 = self._scale_bbox(bbox, source_size)
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                image,
                f"{name} {sim:.2f}",
                (x1, max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
            )
