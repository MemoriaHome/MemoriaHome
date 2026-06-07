from dataclasses import dataclass, field
import numpy as np
import time


@dataclass
class KinectFrame:
    color: np.ndarray               # BGR color image (1920x1080)
    depth: np.ndarray | None        # Raw depth array (512x424), or None
    infrared: np.ndarray | None     # Raw infrared array (512x424), or None
    body_frame: object | None       # PyKinect body frame, or None
    timestamp: float = field(default_factory=time.time)
