"""Pixel fill of a BGR frame. Run from the repository root."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from flycar.occupancy import (
    BLUE_H_HIGH,
    BLUE_S,
    RED_H_WRAP,
    RED_S,
    RED_V,
    THRESHOLDS_PATH,
    half_counts,
    load_cuts,
)


def _frame(width: int = 8, height: int = 4) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def _document() -> dict:
    return {
        "red": {"saturation": 120, "value": 50, "hue_low": 10, "hue_wrap": 326},
        "blue": {"saturation": 140, "value": 30, "hue_low": 210, "hue_high": 240},
    }


def test_shipped_file_supplies_the_gates() -> None:
    loaded = load_cuts(THRESHOLDS_PATH)
    assert loaded["RED_S"] == RED_S
    assert loaded["RED_V"] == RED_V
    assert loaded["RED_H_WRAP"] == RED_H_WRAP
    assert loaded["BLUE_S"] == BLUE_S
    assert loaded["BLUE_H_HIGH"] == BLUE_H_HIGH


def test_loader_accepts_a_red_gate_with_no_low_side(tmp_path: Path) -> None:
    raw = _document()
    raw["red"]["hue_low"] = -1
    path = tmp_path / "color_thresholds.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_cuts(path)["RED_H_LOW"] == -1


def test_loader_rejects_a_fraction_and_an_inverted_blue_hue(tmp_path: Path) -> None:
    fraction = _document()
    fraction["red"]["value"] = 50.5
    path = tmp_path / "fraction.json"
    path.write_text(json.dumps(fraction), encoding="utf-8")
    with pytest.raises(ValueError, match="整数ではない"):
        load_cuts(path)
    inverted = _document()
    inverted["blue"]["hue_low"] = 250
    inverted["blue"]["hue_high"] = 210
    path.write_text(json.dumps(inverted), encoding="utf-8")
    with pytest.raises(ValueError, match="下限が上限"):
        load_cuts(path)


def test_loader_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="色の設定が無い"):
        load_cuts(tmp_path / "missing.json")


def test_black_is_empty() -> None:
    assert half_counts(_frame()) == (0.0, 0.0, 0.0, 0.0)


def test_red_on_the_left_and_blue_on_the_right() -> None:
    frame = _frame()
    frame[:, :4] = (0, 0, 255)
    # Pure blue is hue 240, inside the paper range. Pure cyan is hue 180.
    frame[:, 4:] = (255, 0, 0)
    red_l, red_r, blue_l, blue_r = half_counts(frame)
    assert red_l == 1.0
    assert red_r == 0.0
    assert blue_l == 0.0
    assert blue_r == 1.0


def test_partial_fill_is_the_pixel_fraction() -> None:
    frame = _frame()
    frame[:2, :4] = (0, 0, 255)
    red_l, red_r, _, _ = half_counts(frame)
    assert red_l == 0.5
    assert red_r == 0.0


def test_mirror_swaps_halves() -> None:
    frame = _frame()
    frame[:, :4] = (0, 0, 255)
    assert half_counts(frame, mirror=True)[1] == 1.0


def test_dark_phone_red_counts() -> None:
    """色相 356、彩度 173、明度 147。色紙の赤の範囲に入る。"""
    frame = _frame()
    frame[:, :4] = (52, 47, 147)
    red_l, red_r, blue_l, blue_r = half_counts(frame)
    assert red_l == 1.0
    assert red_r == 0.0
    assert blue_l == 0.0
    assert blue_r == 0.0


def test_orange_screen_wall_skin_and_wood_are_not_red() -> None:
    """オレンジ画面、クリーム色の壁、肌、木のドアは数えない。"""
    orange = _frame()
    orange[:, :4] = (150, 224, 255)
    wall = _frame()
    wall[:, :4] = (124, 193, 246)
    skin = _frame()
    skin[:, :4] = (138, 149, 199)
    door = _frame()
    door[:, :4] = (29, 84, 137)
    pale = _frame()
    pale[:, :4] = (180, 180, 255)
    assert half_counts(orange) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(wall) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(skin) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(door) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(pale) == (0.0, 0.0, 0.0, 0.0)


def test_paper_blue_counts_and_phone_cyan_does_not() -> None:
    """色紙と同じ色相の青は数える。スマホの水色は数えない。"""
    paper = _frame()
    paper[:, :4] = (255, 0, 0)
    book = _frame()
    book[:, :4] = (101, 46, 26)
    cyan = _frame()
    cyan[:, :4] = (255, 255, 0)
    pale = _frame()
    pale[:, :4] = (255, 255, 217)
    assert half_counts(paper)[2] == 1.0
    assert half_counts(book)[2] == 1.0
    assert half_counts(cyan) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(pale) == (0.0, 0.0, 0.0, 0.0)


def test_near_white_is_not_red() -> None:
    frame = _frame()
    frame[:, :4] = (240, 240, 255)
    assert half_counts(frame) == (0.0, 0.0, 0.0, 0.0)


def test_gray_is_not_a_color() -> None:
    frame = _frame()
    frame[:] = (128, 128, 128)
    assert half_counts(frame) == (0.0, 0.0, 0.0, 0.0)
