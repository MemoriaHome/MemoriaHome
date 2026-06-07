import threading
import time
from collections import defaultdict

import numpy as np


STREAM_TYPES = ("rgb", "depth", "ir")


class StreamSelector:
    """Per-viewer stream selection shared with the active video track."""

    def __init__(self, stream_type: str = "depth"):
        self._stream_type = stream_type
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            return self._stream_type

    def set(self, stream_type: str) -> str:
        if stream_type not in STREAM_TYPES:
            raise ValueError(f"Unsupported stream type: {stream_type}")
        with self._lock:
            self._stream_type = stream_type
            return self._stream_type


class AnnotatedStreamHub:
    """Latest-frame store with subscription counts for demand-driven rendering."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._frames: dict[str, np.ndarray] = {}
        self._versions: dict[str, int] = defaultdict(int)
        self._subscriptions: dict[str, int] = defaultdict(int)
        self._condition = threading.Condition()

    def subscribe(self, stream_type: str) -> None:
        with self._condition:
            self._subscriptions[stream_type] += 1
            self._condition.notify_all()

    def unsubscribe(self, stream_type: str) -> None:
        with self._condition:
            if self._subscriptions[stream_type] > 0:
                self._subscriptions[stream_type] -= 1
            self._condition.notify_all()

    def switch_subscription(self, old_stream: str, new_stream: str) -> None:
        if old_stream == new_stream:
            return
        with self._condition:
            if self._subscriptions[old_stream] > 0:
                self._subscriptions[old_stream] -= 1
            self._subscriptions[new_stream] += 1
            self._condition.notify_all()

    def has_subscribers(self, stream_type: str) -> bool:
        with self._condition:
            return self._subscriptions[stream_type] > 0

    def update(self, stream_type: str, frame: np.ndarray) -> None:
        with self._condition:
            self._frames[stream_type] = frame
            self._versions[stream_type] += 1
            self._condition.notify_all()

    def wait_for_frame(
        self,
        stream_type: str,
        last_version: int,
        timeout: float = 1.0,
    ) -> tuple[np.ndarray | None, int]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._versions[stream_type] <= last_version:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            return self._frames.get(stream_type), self._versions[stream_type]
