"""LED マトリクスに出す 8×13 のパターン。基板の下辺が車の前。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

from face import COLS, ROWS, frame, lamps  # noqa: E402


def _at(pixels: list[int], row: int, col: int) -> int:
    return pixels[row * COLS + col]


def _cols(pixels: list[int], row: int) -> list[int]:
    return [col for col in range(COLS) if _at(pixels, row, col)]


def _inward(segments: int) -> list[int]:
    """車の左へ、外側の列 12 から仕切りへ伸びる列。"""
    return list(range(COLS - segments, COLS))


def test_frame_is_104_binary_levels() -> None:
    pixels = frame(1.0, 1.0, 1.0, 1.0, 255, -255, "spin")
    assert len(pixels) == ROWS * COLS
    assert set(pixels) <= {0, 1}


def test_count_below_the_floor_is_dark() -> None:
    pixels = frame(0.039, 0.0, 0.0, 0.03, 0, 0, "stop")
    assert pixels == [0] * (ROWS * COLS)


def test_count_edges_light_one_more_segment() -> None:
    expect = {
        0.04: 1,
        0.20: 2,
        0.36: 3,
        0.52: 4,
        0.68: 5,
        0.75: 5,
        0.84: 6,
        1.0: 6,
    }
    for count, segments in expect.items():
        pixels = frame(count, 0.0, 0.0, 0.0, 0, 0, "stop")
        assert _cols(pixels, 7) == _inward(segments)
        assert _cols(pixels, 6) == _inward(segments)
        assert _cols(pixels, 4) == []


def test_right_bar_grows_inward_from_the_cars_right() -> None:
    pixels = frame(0.0, 0.20, 0.0, 0.04, 0, 0, "stop")
    assert _cols(pixels, 7) == [0, 1]
    assert _cols(pixels, 4) == [0]
    assert _cols(pixels, 3) == [0]


def test_red_and_blue_keep_a_blank_row_between_them() -> None:
    pixels = frame(0.20, 0.20, 0.20, 0.20, 0, 0, "stop")
    assert _cols(pixels, 5) == []
    assert _cols(pixels, 2) == []
    assert 6 not in _cols(pixels, 7)
    assert 6 not in _cols(pixels, 4)


def test_forward_floor_and_full_scale() -> None:
    dark = frame(0.0, 0.0, 0.0, 0.0, 12, 12, "cruise")
    assert _cols(dark, 7) == [6]
    assert _cols(dark, 1) == []
    assert _cols(dark, 0) == []
    one = frame(0.0, 0.0, 0.0, 0.0, 13, 13, "cruise")
    assert _cols(one, 1) == [0, 12]
    full = frame(0.0, 0.0, 0.0, 0.0, 255, 255, "cruise")
    assert _cols(full, 1) == [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]
    assert _cols(full, 0) == []


def test_reverse_floor_and_full_scale() -> None:
    dark = frame(0.0, 0.0, 0.0, 0.0, -35, -35, "back")
    assert _cols(dark, 1) == []
    assert _cols(dark, 0) == [6]
    one = frame(0.0, 0.0, 0.0, 0.0, -36, -36, "back")
    assert _cols(one, 0) == [0, 6, 12]
    full = frame(0.0, 0.0, 0.0, 0.0, -255, -255, "back")
    assert _cols(full, 0) == list(range(COLS))
    assert _cols(full, 1) == []


def test_stopped_pulse_leaves_the_wheel_dark() -> None:
    pixels = frame(0.0, 0.0, 0.0, 0.0, 0, 0, "stop")
    assert _cols(pixels, 1) == []
    assert _cols(pixels, 0) == []


def test_modes_use_only_the_gutter() -> None:
    cruise = frame(0.0, 0.0, 0.0, 0.0, 0, 0, "cruise")
    assert _cols(cruise, 7) == [6]
    assert _cols(cruise, 0) == []
    back = frame(0.0, 0.0, 0.0, 0.0, 0, 0, "back")
    assert _cols(back, 0) == [6]
    assert _cols(back, 7) == []
    spin = frame(0.0, 0.0, 0.0, 0.0, 0, 0, "spin")
    assert _cols(spin, 7) == [6]
    assert _cols(spin, 0) == [6]
    assert _cols(spin, 4) == []
    assert frame(0.0, 0.0, 0.0, 0.0, 0, 0, "nope") == [0] * (ROWS * COLS)


def test_red_fill_lights_the_whole_gutter() -> None:
    pixels = frame(0.75, 0.75, 0.0, 0.0, 0, 0, "stop")
    for row in range(ROWS):
        assert _at(pixels, row, 6) == 1
    assert _cols(pixels, 7) == [0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 12]


def test_logged_blue_keeps_one_wheel_and_the_back_mark() -> None:
    """青 0.05/0.08、送ったパルス 右 0 左 −51、モード back。"""
    pixels = frame(0.0, 0.0, 0.05, 0.08, 0, -51, "back")
    assert _cols(pixels, 7) == []
    assert _cols(pixels, 4) == [0, 12]
    assert _cols(pixels, 3) == [0, 12]
    assert _cols(pixels, 1) == []
    assert _cols(pixels, 0) == [6, 12]


def test_lamps_follow_the_floor() -> None:
    assert lamps(0.039, 0.0, 0.0, 0.03, 12, -35) == (0, 0, 0, 0)
    assert lamps(0.04, 0.0, 0.0, 0.0, 0, 0) == (1, 0, 0, 0)
    assert lamps(0.0, 0.0, 0.0, 0.04, 0, 0) == (0, 1, 0, 0)
    assert lamps(0.0, 0.0, 0.0, 0.0, 13, 0) == (0, 0, 1, 0)
    assert lamps(0.0, 0.0, 0.0, 0.0, 0, -36) == (0, 0, 0, 1)
    assert lamps(0.20, 0.0, 0.10, 0.0, 40, -50) == (1, 1, 1, 1)
