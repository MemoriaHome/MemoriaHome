import queue
import threading
from abc import ABC, abstractmethod


class BaseModule(ABC):
    """
    Abstract base for all detection/processing modules.
    Subclasses implement _process_frame(); the threading boilerplate is handled here.
    """

    def __init__(self, frame_queue: queue.Queue):
        self._queue = frame_queue
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame = self._queue.get(timeout=1.0)
                self._process_frame(frame)
            except queue.Empty:
                continue

    @abstractmethod
    def _process_frame(self, frame) -> None:
        """Called for every frame this module receives. Implement in subclass."""
        ...