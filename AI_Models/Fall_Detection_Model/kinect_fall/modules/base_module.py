import queue
import threading
import time
from abc import ABC, abstractmethod


class BaseModule(ABC):
    """
    Abstract base for all detection/processing modules.
    Subclasses implement _process_frame(); the threading boilerplate is handled here.
    """

    def __init__(self, frame_queue: queue.Queue, max_fps: int | float | None = None):
        self._queue = frame_queue
        self._process_interval = 1.0 / max_fps if max_fps and max_fps > 0 else 0.0
        self._last_process_time = 0.0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            # Block waiting for the next frame (short timeout to stay responsive to stop)
            try:
                frame = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # FPS throttle: drop this frame if we processed one too recently.
            # Loop back immediately so we consume (and discard) queued frames
            # quickly rather than letting the queue fill up and block the
            # FrameBus / capture thread.
            now = time.monotonic()
            if self._process_interval and now - self._last_process_time < self._process_interval:
                continue

            # Drain any backlog that built up while _process_frame() was running.
            # We only care about the freshest frame — processing a stale one would
            # introduce visible lag and waste inference time.
            try:
                while True:
                    frame = self._queue.get_nowait()
            except queue.Empty:
                pass

            self._last_process_time = time.monotonic()
            self._process_frame(frame)

    @abstractmethod
    def _process_frame(self, frame) -> None:
        """Called for every frame this module should process. Implement in subclass."""
        ...