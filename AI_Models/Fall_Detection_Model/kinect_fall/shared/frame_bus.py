import queue
from typing import List

command_queue = queue.Queue() ##command q so we dont have to fall all the damn time


class FrameBus:
    """
    Fan-out publisher. The capture thread calls publish() once per frame.
    Each registered module gets its own queue and consumes at its own pace.
    """

    def __init__(self, maxsize: int = 30):
        self._queues: List[queue.Queue] = []
        self._maxsize = maxsize

    def register(self) -> queue.Queue:
        """Register a new subscriber. Returns its dedicated queue."""
        q = queue.Queue(maxsize=self._maxsize)
        self._queues.append(q)
        return q

    def publish(self, frame) -> None:
        """Push frame to every subscriber queue. Drop if a queue is full."""
        for q in self._queues:
            try:
                q.put_nowait(frame)
            except queue.Full:
                pass  # Module is falling behind — drop the frame silently