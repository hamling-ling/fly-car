"""Pixel fill of a BGR frame. Run from the repository root."""

from __future__ import annotations

import numpy as np

from flycar.occupancy import half_counts


def _frame(width: int = 8, height: int = 4) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_black_is_empty() -> None:
    assert half_counts(_frame()) == (0.0, 0.0, 0.0, 0.0)


def test_red_on_the_left_and_blue_on_the_right() -> None:
    frame = _frame()
    frame[:, :4] = (0, 0, 255)
    # Pure cyan is the phone screen. Pure blue (255, 0, 0) is hue 120.
    frame[:, 4:] = (255, 255, 0)
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


def test_a_bright_phone_red_counts() -> None:
    """遠い赤のスマホは色相 13、彩度 103、明度 255。そこは赤として数える。"""
    frame = _frame()
    frame[:, :4] = (152, 197, 255)
    red_l, red_r, blue_l, blue_r = half_counts(frame)
    assert red_l == 1.0
    assert red_r == 0.0
    assert blue_l == 0.0
    assert blue_r == 0.0


def test_pale_red_and_skin_are_not_red() -> None:
    """彩度 75 の薄い赤と、明度 214 の肌は数えない。"""
    pale = _frame()
    pale[:, :4] = (180, 180, 255)
    skin = _frame()
    skin[:, :4] = (128, 151, 214)
    assert half_counts(pale) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(skin) == (0.0, 0.0, 0.0, 0.0)


def test_book_blue_and_pure_blue_are_not_blue() -> None:
    """本棚の青は色相 112 で暗い。純青は色相 120。どちらもスマホの水色ではない。"""
    book = _frame()
    book[:, :4] = (101, 46, 26)
    pure = _frame()
    pure[:, :4] = (255, 0, 0)
    assert half_counts(book) == (0.0, 0.0, 0.0, 0.0)
    assert half_counts(pure) == (0.0, 0.0, 0.0, 0.0)


def test_near_white_is_not_red() -> None:
    frame = _frame()
    frame[:, :4] = (240, 240, 255)
    assert half_counts(frame) == (0.0, 0.0, 0.0, 0.0)


def test_gray_is_not_a_color() -> None:
    frame = _frame()
    frame[:] = (128, 128, 128)
    assert half_counts(frame) == (0.0, 0.0, 0.0, 0.0)
