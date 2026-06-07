from dataclasses import dataclass, field
import time


@dataclass
class BodyOverlay:
    """Body detection box in full-resolution RGB coordinates."""

    bbox: tuple[int, int, int, int]
    label: str = "Body"
    confidence: float | None = None


@dataclass
class FallOverlay:
    """Low-cost overlay metadata shared by display and live streaming."""

    bodies: list[BodyOverlay] = field(default_factory=list)
    fallen: bool = False
    status: str = "STATUS: SAFE"
    velocity: float = 0.0
    floor_timer_seconds: float | None = None
    floor_timer_limit: float | None = None
    timestamp: float = field(default_factory=time.time)
