# Display module — renders annotated frames via cv2.imshow
import queue
import cv2
from modules.base_module import BaseModule


class DisplayModule(BaseModule):
    def __init__(
        self,
        frame_queue: queue.Queue,
        config,
        command_queue: queue.Queue,
        window_name: str = "MemoriaHome Monitor",
        max_fps: int | float | None = None,
    ):
        super().__init__(frame_queue, max_fps=max_fps)
        self._window_name = window_name
        self._command_queue = command_queue
        

    def _process_frame(self, frame) -> None:
        display = cv2.resize(frame, (960, 540))
        cv2.imshow(self._window_name, display)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            self.stop()
        elif key == ord('f'):
            self._command_queue.put("simulate_fall")
        elif key == ord('r'):
            self._command_queue.put("simulate_recovery")
    
    
