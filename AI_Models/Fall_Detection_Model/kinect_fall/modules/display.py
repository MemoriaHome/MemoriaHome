# Display module — renders annotated frames via cv2.imshow
import queue
import cv2
from modules.base_module import BaseModule


class DisplayModule(BaseModule):
    def __init__(self, frame_queue: queue.Queue, config, window_name: str = "MemoriaHome Monitor"):
        super().__init__(frame_queue)
        self._window_name = window_name

    def _process_frame(self, frame) -> None:
        if frame.color is None:
            return
        display = cv2.resize(frame.color, (960, 540))
        cv2.imshow(self._window_name, display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.stop()