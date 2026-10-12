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


def test_gray_is_not_a_color() -> None:
    frame = _frame()
    frame[:] = (128, 128, 128)
    assert half_counts(frame) == (0.0, 0.0, 0.0, 0.0)
