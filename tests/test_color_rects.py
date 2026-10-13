"""Rectangle checks for color_capture_q. The app itself needs the Uno Q."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "color_capture_q" / "python"))

from rects import marked_rects, parse_rect, rects_for_save, relabel_single  # noqa: E402


def test_blank_rect_is_absent() -> None:
    assert parse_rect(("", "", "", ""), 1280, 720, "赤") is None


def test_partial_rect_is_rejected() -> None:
    with pytest.raises(ValueError, match="全部入れる"):
        parse_rect(("10", "20", "", "30"), 1280, 720, "赤")


def test_rect_must_stay_inside_and_be_large_enough() -> None:
    with pytest.raises(ValueError, match="小さすぎる"):
        parse_rect(("0", "0", "7", "40"), 1280, 720, "青")
    with pytest.raises(ValueError, match="画面の外"):
        parse_rect(("1270", "0", "20", "40"), 1280, 720, "青")


def test_one_color_is_enough() -> None:
    red, blue = marked_rects(("10", "20", "30", "40"), ("", "", "", ""), 1280, 720)
    assert red == {"x": 10, "y": 20, "width": 30, "height": 40}
    assert blue is None


def test_neither_color_is_rejected() -> None:
    with pytest.raises(ValueError, match="矩形を描く"):
        marked_rects(("", "", "", ""), ("", "", "", ""), 1280, 720)


def test_neither_saves_no_rectangle() -> None:
    red, blue = rects_for_save(("", "", "", ""), ("", "", "", ""), 1280, 720, True)
    assert red is None and blue is None
    with pytest.raises(ValueError, match="矩形を消して"):
        rects_for_save(("1", "2", "30", "40"), ("", "", "", ""), 1280, 720, True)


def test_relabel_moves_the_only_rectangle() -> None:
    rect = {"x": 1, "y": 2, "width": 30, "height": 40}
    red, blue = relabel_single(rect, None, "blue")
    assert red is None
    assert blue == rect
    with pytest.raises(ValueError, match="1つではない"):
        relabel_single(rect, rect, "red")
