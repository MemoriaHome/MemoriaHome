from dataclasses import dataclass, field
import numpy as np
import time


@dataclass
class BodySummary:
    """Small Kinect body snapshot in full-resolution color coordinates."""

    tracking_id: str
    body_index: int
    color_bbox: tuple[int, int, int, int] | None = None
    head: tuple[int, int] | None = None
    spine_base: tuple[int, int] | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class KinectFrame:
    color: np.ndarray               # BGR color image (1920x1080)
    depth: np.ndarray | None        # Raw depth array (512x424), or None
    infrared: np.ndarray | None     # Raw infrared array (512x424), or None
    body_frame: object | None       # PyKinect body frame, or None
    body_summaries: list[BodySummary] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
