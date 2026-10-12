"""Half-frame red and blue fill from a camera image.

``project_blob`` measures how much of a drawn sphere overlaps each half.
A real frame is counted the other way: the fraction of pixels in that half
whose color falls in the red or blue range. Position inside the half does
not matter. The ranges are a first guess for a BGR frame and have not been
matched to a physical target.

OpenCV hue runs from 0 to 179. Red wraps past 0, so it is two intervals.
"""

from __future__ import annotations

import cv2
import numpy as np

# Inclusive HSV bounds. S and V floors drop gray floors and near-black pixels.
RED_LO = (0, 80, 50)
RED_HI = (10, 255, 255)
RED_WRAP_LO = (170, 80, 50)
RED_WRAP_HI = (179, 255, 255)
BLUE_LO = (100, 80, 50)
BLUE_HI = (130, 255, 255)


def _bounds(low: tuple[int, int, int], high: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    return np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8)


def _fill(mask: np.ndarray, x0: int, x1: int) -> float:
    part = mask[:, x0:x1]
    if part.size == 0:
        return 0.0
    return float(np.count_nonzero(part)) / float(part.size)


def half_counts(frame_bgr: np.ndarray, *, mirror: bool = False) -> tuple[float, float, float, float]:
    """Return ``(red_l, red_r, blue_l, blue_r)`` in 0..1.

    Column 0 is the left of the image. ``mirror`` swaps the halves after
    counting, for a camera whose picture is flipped left to right.
    """
    frame = np.asarray(frame_bgr)
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a BGR image")
    if frame.dtype != np.uint8:
        raise ValueError("frame must be uint8")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    red_lo, red_hi = _bounds(RED_LO, RED_HI)
    wrap_lo, wrap_hi = _bounds(RED_WRAP_LO, RED_WRAP_HI)
    blue_lo, blue_hi = _bounds(BLUE_LO, BLUE_HI)
    red = cv2.bitwise_or(cv2.inRange(hsv, red_lo, red_hi), cv2.inRange(hsv, wrap_lo, wrap_hi))
    blue = cv2.inRange(hsv, blue_lo, blue_hi)
    mid = frame.shape[1] // 2
    counts = (
        _fill(red, 0, mid),
        _fill(red, mid, frame.shape[1]),
        _fill(blue, 0, mid),
        _fill(blue, mid, frame.shape[1]),
    )
    if not mirror:
        return counts
    red_l, red_r, blue_l, blue_r = counts
    return red_r, red_l, blue_r, blue_l
