"""赤と青の四角形を、保存前に画像の画素座標へ揃える。

4 点は打った順につなぐ。軸に沿った古い矩形は ``x, y, width, height`` のまま読める。
``points`` があるときは、それが囲いの本体で、残りの 4 つはその外接矩形である。
"""

from __future__ import annotations

import cv2
import numpy as np

MIN_SIDE = 8
MIN_AREA = MIN_SIDE * MIN_SIDE


def _cross(origin: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])


def _segments_cross(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int], d: tuple[int, int]) -> bool:
    """True when the open segments ab and cd cross."""
    return _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0


def _area(points: list[list[int]]) -> float:
    total = 0
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        total += start[0] * end[1] - end[0] * start[1]
    return abs(total) / 2


def parse_quad(raw: object, frame_w: int, frame_h: int, name: str) -> dict | None:
    """Return a 4-point mark, or None when ``raw`` is blank.

    Points are integer pixels, origin at the top left, in the order they were
    placed. The returned ``x, y, width, height`` is the axis-aligned box around
    those points, inclusive of both edges.
    """
    text = "" if raw is None else str(raw).strip()
    if text == "":
        return None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 8:
        raise ValueError(f"{name} は4点で囲む")
    try:
        numbers = [int(part) for part in parts]
    except ValueError as exc:
        raise ValueError(f"{name} の座標が整数ではない") from exc
    points = [[numbers[index], numbers[index + 1]] for index in range(0, 8, 2)]
    for x, y in points:
        if x < 0 or y < 0 or x >= frame_w or y >= frame_h:
            raise ValueError(f"{name} の点が画面の外")
    corners = [tuple(point) for point in points]
    crossed = _segments_cross(corners[0], corners[1], corners[2], corners[3]) or _segments_cross(
        corners[1], corners[2], corners[3], corners[0]
    )
    if crossed:
        raise ValueError(f"{name} の4点が交差している")
    if _area(points) < MIN_AREA:
        raise ValueError(f"{name} の範囲が小さすぎる")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x0, y0 = min(xs), min(ys)
    return {
        "points": points,
        "x": x0,
        "y": y0,
        "width": max(xs) - x0 + 1,
        "height": max(ys) - y0 + 1,
    }


def marked_quads(
    red: object,
    blue: object,
    frame_w: int,
    frame_h: int,
) -> tuple[dict | None, dict | None]:
    """Require at least one quadrilateral inside the frame."""
    red_quad = parse_quad(red, frame_w, frame_h, "赤")
    blue_quad = parse_quad(blue, frame_w, frame_h, "青")
    if red_quad is None and blue_quad is None:
        raise ValueError("赤か青を4点で囲む")
    return red_quad, blue_quad


def quads_for_save(
    red: object,
    blue: object,
    frame_w: int,
    frame_h: int,
    neither: bool,
) -> tuple[dict | None, dict | None]:
    """Marks for one shot. ``neither`` means the frame has no red and no blue."""
    if neither:
        if str(red).strip() or str(blue).strip():
            raise ValueError("点を消してから、赤も青も無い絵として保存する")
        return None, None
    return marked_quads(red, blue, frame_w, frame_h)


def relabel_single(red: dict | None, blue: dict | None, color: str) -> tuple[dict | None, dict | None]:
    """Move the only mark onto ``red`` or ``blue``."""
    if color not in ("red", "blue"):
        raise ValueError("色は赤か青")
    present = [mark for mark in (red, blue) if mark]
    if len(present) != 1:
        raise ValueError("矩形が1つではない")
    mark = present[0]
    if color == "red":
        return mark, None
    return None, mark


def region_mask(height: int, width: int, mark: dict | None) -> np.ndarray:
    """Pixels inside a saved mark. ``points`` wins over the bounding box."""
    mask = np.zeros((height, width), dtype=np.uint8)
    if not mark:
        return mask.astype(bool)
    points = mark.get("points")
    if points:
        polygon = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [polygon], 1)
        return mask.astype(bool)
    x, y = int(mark["x"]), int(mark["y"])
    w, h = int(mark["width"]), int(mark["height"])
    mask[y : y + h, x : x + w] = 1
    return mask.astype(bool)
