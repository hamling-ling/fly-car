"""Eye-range red and blue fill from a camera image.

``project_blob`` measures how much of a drawn sphere overlaps each eye.
A real frame is counted the other way: the fraction of pixels in that eye's
range whose color falls in the red or blue range. The left range is ``p``
from 0 to 0.65 and the right range is ``p`` from 0.35 to 1, so the middle
is in both. ``half_counts`` still splits the frame at the midline. The
color tests use that split. The motors read ``range_means``.

The blue fill is for the face and the log. It is not the DNp01 current.
``Counts.loom`` is that current, from ``flycar.loom``. Angle and expansion
come from the largest region. Each cell reads the vertical blue fraction
of the column at its stretched screen position.

The gates are read once from ``color_thresholds.json`` beside this file.
``research/color_capture_q/fit_thresholds.py`` writes that file. Restart the
app after replacing it. Hue in the file is degrees. OpenCV stores half of that.

The paper's red sits near hue 340. A pale phone cyan near hue 180 is not
this blue. A monitor or book spine in the same hue and saturation still
matches. Wood at hue 30, skin near saturation 80, and the cream wall stay
outside.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from flycar.loom import LEFT_HI, RIGHT_LO, LoomTrack, measure_blue

THRESHOLDS_PATH = Path(__file__).with_name("color_thresholds.json")


def _mapping(raw: object, label: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} がオブジェクトではない")
    return raw


def _integer(block: dict, key: str, low: int, high: int, label: str) -> int:
    if key not in block:
        raise ValueError(f"{label} に {key} が無い")
    value = block[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} の {key} が整数ではない")
    if value < low or value > high:
        raise ValueError(f"{label} の {key} が範囲外")
    return value


def load_cuts(path: Path) -> dict[str, int]:
    """Read the eight gates. Hue is in degrees, saturation and value are 0..255."""
    if not path.is_file():
        raise FileNotFoundError(f"色の設定が無い: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"色の設定が JSON ではない: {path}") from exc
    document = _mapping(raw, path.name)
    red = _mapping(document.get("red"), "赤")
    blue = _mapping(document.get("blue"), "青")
    red_s = _integer(red, "saturation", 0, 255, "赤")
    red_v = _integer(red, "value", 0, 255, "赤")
    red_low = _integer(red, "hue_low", -1, 360, "赤")
    red_wrap = _integer(red, "hue_wrap", 0, 360, "赤")
    blue_s = _integer(blue, "saturation", 0, 255, "青")
    blue_v = _integer(blue, "value", 0, 255, "青")
    blue_low = _integer(blue, "hue_low", 0, 360, "青")
    blue_high = _integer(blue, "hue_high", 0, 360, "青")
    if blue_low > blue_high:
        raise ValueError("青の色相の下限が上限を超えている")
    return {
        "RED_S": red_s,
        "RED_V": red_v,
        "RED_H_LOW": red_low,
        "RED_H_WRAP": red_wrap,
        "BLUE_S": blue_s,
        "BLUE_V": blue_v,
        "BLUE_H_LOW": blue_low,
        "BLUE_H_HIGH": blue_high,
    }


_CUTS = load_cuts(THRESHOLDS_PATH)
RED_S = _CUTS["RED_S"]
BLUE_S = _CUTS["BLUE_S"]
RED_V = _CUTS["RED_V"]
BLUE_V = _CUTS["BLUE_V"]
RED_H_LOW = _CUTS["RED_H_LOW"]
RED_H_WRAP = _CUTS["RED_H_WRAP"]
BLUE_H_LOW = _CUTS["BLUE_H_LOW"]
BLUE_H_HIGH = _CUTS["BLUE_H_HIGH"]


def color_masks(frame_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return boolean red and blue masks for a uint8 BGR frame."""
    frame = np.asarray(frame_bgr)
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a BGR image")
    if frame.dtype != np.uint8:
        raise ValueError("frame must be uint8")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16) * 2
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    red = (saturation >= RED_S) & (value >= RED_V) & ((hue <= RED_H_LOW) | (hue >= RED_H_WRAP))
    blue = (hue >= BLUE_H_LOW) & (hue <= BLUE_H_HIGH) & (saturation >= BLUE_S) & (value >= BLUE_V)
    return red, blue


def _fill(mask: np.ndarray, x0: int, x1: int) -> float:
    part = mask[:, x0:x1]
    if part.size == 0:
        return 0.0
    return float(np.count_nonzero(part)) / float(part.size)


def red_place(mask: np.ndarray) -> float:
    """Red centroid as -1 at the left edge and +1 at the right edge.

    Empty red is 0, so a blank frame does not amplify the wheel difference.
    ``p`` is 0 at the left edge and 1 at the right edge.
    """
    image = np.asarray(mask)
    if image.ndim != 2 or image.size == 0:
        return 0.0
    width = int(image.shape[1])
    if width == 0:
        return 0.0
    columns = np.asarray(image, dtype=np.float64).sum(axis=0)
    total = float(columns.sum())
    if total <= 0.0:
        return 0.0
    p = (np.arange(width) + 0.5) / float(width)
    centroid = float(np.dot(columns, p) / total)
    place = (centroid - 0.5) / 0.5
    if place > 1.0:
        return 1.0
    if place < -1.0:
        return -1.0
    return place


def range_means(mask: np.ndarray) -> tuple[float, float]:
    """Mean of ``mask`` on the left eye and the right eye.

    ``p`` is 0 at the left edge and 1 at the right edge. The left eye reads
    columns with ``p <= LEFT_HI``. The right eye reads ``p >= RIGHT_LO``.
    The two ranges overlap, so a pixel near the middle is in both.
    """
    image = np.asarray(mask)
    if image.ndim != 2:
        raise ValueError("mask must be a 2D image")
    width = int(image.shape[1])
    if width == 0 or image.size == 0:
        return 0.0, 0.0
    p = (np.arange(width) + 0.5) / float(width)
    field = np.asarray(image, dtype=np.float64)
    left = field[:, p <= LEFT_HI]
    right = field[:, p >= RIGHT_LO]
    left_mean = float(left.mean()) if left.size else 0.0
    right_mean = float(right.mean()) if right.size else 0.0
    return left_mean, right_mean


def half_counts(frame_bgr: np.ndarray, *, mirror: bool = False) -> tuple[float, float, float, float]:
    """Return ``(red_l, red_r, blue_l, blue_r)`` in 0..1.

    Column 0 is the left of the image. ``mirror`` flips the picture left to
    right before the split, for a camera whose left is the car's right.
    """
    red, blue = color_masks(frame_bgr)
    return _halves(red, blue, mirror=mirror)


def _halves(
    red: np.ndarray, blue: np.ndarray, *, mirror: bool
) -> tuple[float, float, float, float]:
    if mirror:
        red = np.ascontiguousarray(np.fliplr(red))
        blue = np.ascontiguousarray(np.fliplr(blue))
    mid = red.shape[1] // 2
    return (
        _fill(red, 0, mid),
        _fill(red, mid, red.shape[1]),
        _fill(blue, 0, mid),
        _fill(blue, mid, blue.shape[1]),
    )


class Counts:
    """Last eye-range fractions, and the loom current of the blue region."""

    def __init__(self) -> None:
        self.values = (0.0, 0.0, 0.0, 0.0)
        self.place = 0.0
        self.loom = (0.0, 0.0)
        self.theta = 0.0
        self.theta_dot = 0.0
        self._track = LoomTrack()

    def update(
        self,
        frame: np.ndarray | None,
        *,
        mirror: bool = False,
        now: float | None = None,
    ) -> bool:
        """Keep the previous reading when ``frame`` is None.

        Return False when the frame cannot be counted. The caller stops the wheels.
        ``now`` is the sample time in seconds. Expansion is zero until two
        frames both contain a blue region.
        """
        if frame is None:
            return True
        try:
            red, blue = color_masks(frame)
        except ValueError as exc:
            print(f"counts: {exc}")
            self.values = (0.0, 0.0, 0.0, 0.0)
            self.place = 0.0
            self._clear_loom()
            return False
        if mirror:
            red = np.ascontiguousarray(np.fliplr(red))
            blue = np.ascontiguousarray(np.fliplr(blue))
        self.values = (*range_means(red), *range_means(blue))
        self.place = red_place(red)
        when = 0.0 if now is None else float(now)
        self.loom = self._track.update(measure_blue(blue), when, blue)
        self.theta = self._track.theta
        self.theta_dot = self._track.theta_dot
        return True

    def _clear_loom(self) -> None:
        self._track = LoomTrack()
        self.loom = (0.0, 0.0)
        self.theta = 0.0
        self.theta_dot = 0.0
