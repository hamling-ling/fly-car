"""Quadrilateral checks for color_capture_q. The app itself needs the Uno Q."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "color_capture_q" / "python"))

from rects import marked_quads, parse_quad, quads_for_save, region_mask, relabel_single  # noqa: E402

SQUARE = "0,0,20,0,20,20,0,20"
BOWTIE = "0,0,20,20,0,20,20,0"


def test_blank_quad_is_absent() -> None:
    assert parse_quad("", 1280, 720, "赤") is None
    assert parse_quad(None, 1280, 720, "赤") is None


def test_quad_needs_four_points() -> None:
    with pytest.raises(ValueError, match="4点で囲む"):
        parse_quad("0,0,20,0,20,20", 1280, 720, "赤")


def test_quad_must_stay_inside_and_cover_area() -> None:
    with pytest.raises(ValueError, match="画面の外"):
        parse_quad("0,0,1280,0,1280,20,0,20", 1280, 720, "青")
    with pytest.raises(ValueError, match="小さすぎる"):
        parse_quad("0,0,4,0,4,4,0,4", 1280, 720, "青")
    with pytest.raises(ValueError, match="交差"):
        parse_quad(BOWTIE, 1280, 720, "赤")


def test_one_color_is_enough() -> None:
    red, blue = marked_quads(SQUARE, "", 1280, 720)
    assert red is not None and blue is None
    assert red["points"] == [[0, 0], [20, 0], [20, 20], [0, 20]]
    assert red["x"] == 0 and red["y"] == 0
    assert red["width"] == 21 and red["height"] == 21


def test_tilted_quad_keeps_click_order() -> None:
    red, _blue = marked_quads("10,10,40,14,36,40,8,30", "", 1280, 720)
    assert red is not None
    assert red["points"] == [[10, 10], [40, 14], [36, 40], [8, 30]]
    assert red["x"] == 8 and red["y"] == 10
    assert red["width"] == 33 and red["height"] == 31


def test_neither_color_is_rejected() -> None:
    with pytest.raises(ValueError, match="4点で囲む"):
        marked_quads("", "", 1280, 720)


def test_neither_saves_no_quadrilateral() -> None:
    red, blue = quads_for_save("", "", 1280, 720, True)
    assert red is None and blue is None
    with pytest.raises(ValueError, match="点を消して"):
        quads_for_save(SQUARE, "", 1280, 720, True)


def test_relabel_moves_the_only_quadrilateral() -> None:
    mark = {"points": [[0, 0], [20, 0], [20, 20], [0, 20]], "x": 0, "y": 0, "width": 21, "height": 21}
    red, blue = relabel_single(mark, None, "blue")
    assert red is None
    assert blue == mark
    with pytest.raises(ValueError, match="1つではない"):
        relabel_single(mark, mark, "red")


def test_region_mask_follows_points_and_falls_back_to_box() -> None:
    quad = region_mask(5, 5, {"points": [[0, 0], [4, 0], [4, 4], [0, 4]]})
    assert quad[2, 2]
    assert int(quad.sum()) > 0
    box = region_mask(6, 6, {"x": 1, "y": 2, "width": 2, "height": 1})
    assert box[2, 1] and box[2, 2]
    assert int(box.sum()) == 2
    assert not region_mask(2, 2, None).any()
    assert isinstance(quad, np.ndarray)
