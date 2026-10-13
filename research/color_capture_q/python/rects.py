"""赤と青の矩形を、保存前に画像の画素座標へ揃える。"""

from __future__ import annotations

MIN_SIDE = 8


def parse_rect(
    raw: tuple[object, object, object, object],
    frame_w: int,
    frame_h: int,
    name: str,
) -> dict | None:
    """Return ``{x, y, width, height}`` or None when the four fields are blank.

    The origin is the top-left pixel. ``x + width`` may sit on the right edge.
    """
    texts = ["" if value is None else str(value).strip() for value in raw]
    if all(text == "" for text in texts):
        return None
    if any(text == "" for text in texts):
        raise ValueError(f"{name} の矩形は、位置と大きさを全部入れる")
    try:
        x, y, width, height = (int(text) for text in texts)
    except ValueError as exc:
        raise ValueError(f"{name} の座標が整数ではない") from exc
    if width < MIN_SIDE or height < MIN_SIDE:
        raise ValueError(f"{name} の矩形が小さすぎる")
    if x < 0 or y < 0 or x + width > frame_w or y + height > frame_h:
        raise ValueError(f"{name} の矩形が画面の外")
    return {"x": x, "y": y, "width": width, "height": height}


def marked_rects(
    red: tuple[object, object, object, object],
    blue: tuple[object, object, object, object],
    frame_w: int,
    frame_h: int,
) -> tuple[dict | None, dict | None]:
    """Require at least one rectangle inside the frame."""
    red_rect = parse_rect(red, frame_w, frame_h, "赤")
    blue_rect = parse_rect(blue, frame_w, frame_h, "青")
    if red_rect is None and blue_rect is None:
        raise ValueError("赤か青の矩形を描く")
    return red_rect, blue_rect


def _blank(raw: tuple[object, object, object, object]) -> bool:
    return all(str(value).strip() == "" for value in raw)


def rects_for_save(
    red: tuple[object, object, object, object],
    blue: tuple[object, object, object, object],
    frame_w: int,
    frame_h: int,
    neither: bool,
) -> tuple[dict | None, dict | None]:
    """Rectangles for one shot. ``neither`` means the frame has no red and no blue."""
    if neither:
        if not _blank(red) or not _blank(blue):
            raise ValueError("矩形を消してから、赤も青も無い絵として保存する")
        return None, None
    return marked_rects(red, blue, frame_w, frame_h)


def relabel_single(red: dict | None, blue: dict | None, color: str) -> tuple[dict | None, dict | None]:
    """Move the only rectangle onto ``red`` or ``blue``."""
    if color not in ("red", "blue"):
        raise ValueError("色は赤か青")
    present = [rect for rect in (red, blue) if rect]
    if len(present) != 1:
        raise ValueError("矩形が1つではない")
    rect = present[0]
    if color == "red":
        return rect, None
    return None, rect
