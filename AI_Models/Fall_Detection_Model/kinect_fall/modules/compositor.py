import queue

import cv2

from modules.base_module import BaseModule


class CompositorModule(BaseModule):
    """
    Drives on fall_annotated_queue (full-res BGR numpy arrays from FallDetectionModule).
    On each frame it drains face_results_queue to get the freshest recognition
    results, draws face bounding boxes on top, then forwards the composited
    frame to display_queue for DisplayModule to render.

    Coordinate note: face bboxes arriving in face_results_queue are already in
    full-resolution space (1920×1080), matching the fall-annotated frame, so no
    scaling is needed before drawing.
    """

    def __init__(
        self,
        fall_annotated_queue: queue.Queue,
        face_results_queue: queue.Queue,
        display_queue: queue.Queue,
    ):
        super().__init__(fall_annotated_queue)
        self._face_results_queue = face_results_queue
        self._display_queue = display_queue
        # Cache the last known face results so the display stays annotated
        # even when face recognition hasn't produced a newer batch yet.
        self._latest_face_results = []

    def _process_frame(self, frame) -> None:
        # frame is a full-res numpy BGR array produced by FallDetectionModule

        # Drain the face results queue — we only care about the newest batch.
        latest = None
        try:
            while True:
                latest = self._face_results_queue.get_nowait()
        except queue.Empty:
            pass

        if latest is not None:
            self._latest_face_results = latest

        # Stamp face annotations on top of the YOLO-annotated fall frame.
        # Work on a copy so we never mutate the object other threads may hold.
        display = frame.copy()

        for (bbox, name, sim, is_match, angle) in self._latest_face_results:
            x1, y1, x2, y2 = bbox[:4]
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                display,
                f"{name} {sim:.2f}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

        try:
            self._display_queue.put_nowait(display)
        except queue.Full:
            pass
