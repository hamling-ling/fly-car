"""8×13 の点灯パターン。行優先で、要素は 0 か 1。

基板の下辺が車の前なので、絵は 180 度回してから返す。後ろから見ると、下が前、
左が車の左になる。前側の 2 行が赤、中央 2 行が青、後ろ側の 2 行が車輪。
バーは外側から仕切りへ伸びる。占有は 0.04 未満を消灯にし、0.04 から 0.16 刻みで
1 点足す。車輪は送ったパルスで、前進 13 未満と後退 −36 より大きい負は消灯のまま。
仕切りは床を掛ける前のモード。赤が左右とも 0.75 以上のときは仕切りを全部点ける。

点そのものは青い LED だけなので色は出せない。``lamps`` が RGB LED の点灯を返す。
赤の検知と前進は赤、青の検知と後退は青。
"""

from __future__ import annotations

COLS = 13
ROWS = 8

_COUNT_EDGES = (0.04, 0.20, 0.36, 0.52, 0.68, 0.84)
_RED_FILL = 0.75
_FORWARD_START = 13
_REVERSE_START = 36
_PULSE_LIMIT = 255


def frame(
    red_l: float,
    red_r: float,
    blue_l: float,
    blue_r: float,
    right: int,
    left: int,
    mode: str,
) -> list[int]:
    """Return 104 levels, ``frame[row * 13 + col]``, already turned for this car."""
    pixels = [0] * (ROWS * COLS)
    _bars(pixels, 0, red_l, red_r)
    _bars(pixels, 1, red_l, red_r)
    _bars(pixels, 3, blue_l, blue_r)
    _bars(pixels, 4, blue_l, blue_r)
    _wheels(pixels, 6, right, left, forward=True)
    _wheels(pixels, 7, right, left, forward=False)
    _gutter(pixels, red_l, red_r, mode)
    return _mount(pixels)


def lamps(
    red_l: float,
    red_r: float,
    blue_l: float,
    blue_r: float,
    right: int,
    left: int,
) -> tuple[int, int, int, int]:
    """Return ``(see_red, see_blue, go_forward, go_back)`` as 0 or 1.

    A color counts once either half clears 0.04. A wheel counts once its sent
    pulse clears the start floor.
    """
    floor = _COUNT_EDGES[0]
    see_red = int(float(red_l) >= floor or float(red_r) >= floor)
    see_blue = int(float(blue_l) >= floor or float(blue_r) >= floor)
    right_pulse = int(right)
    left_pulse = int(left)
    go_forward = int(right_pulse >= _FORWARD_START or left_pulse >= _FORWARD_START)
    go_back = int(right_pulse <= -_REVERSE_START or left_pulse <= -_REVERSE_START)
    return see_red, see_blue, go_forward, go_back


def _mount(pixels: list[int]) -> list[int]:
    """Turn the picture so the board's bottom edge is the front of the car."""
    mounted = [0] * (ROWS * COLS)
    for index, level in enumerate(pixels):
        row, col = divmod(index, COLS)
        mounted[(ROWS - 1 - row) * COLS + (COLS - 1 - col)] = level
    return mounted


def _segments(count: float) -> int:
    lit = 0
    for edge in _COUNT_EDGES:
        if float(count) >= edge:
            lit += 1
        else:
            break
    return lit


def _pulse_segments(pulse: int, *, forward: bool) -> int:
    command = int(pulse)
    if forward:
        if command < _FORWARD_START:
            return 0
        span = command - _FORWARD_START
        width = _PULSE_LIMIT - _FORWARD_START
    else:
        if command > -_REVERSE_START:
            return 0
        span = -command - _REVERSE_START
        width = _PULSE_LIMIT - _REVERSE_START
    return 1 + span * 5 // width


def _paint(pixels: list[int], row: int, col: int) -> None:
    pixels[row * COLS + col] = 1


def _bars(pixels: list[int], row: int, left_count: float, right_count: float) -> None:
    for index in range(_segments(left_count)):
        _paint(pixels, row, index)
    for index in range(_segments(right_count)):
        _paint(pixels, row, COLS - 1 - index)


def _wheels(pixels: list[int], row: int, right: int, left: int, *, forward: bool) -> None:
    for index in range(_pulse_segments(left, forward=forward)):
        _paint(pixels, row, index)
    for index in range(_pulse_segments(right, forward=forward)):
        _paint(pixels, row, COLS - 1 - index)


def _gutter(pixels: list[int], red_l: float, red_r: float, mode: str) -> None:
    if float(red_l) >= _RED_FILL and float(red_r) >= _RED_FILL:
        rows = range(ROWS)
    elif mode == "cruise":
        rows = (0,)
    elif mode == "back":
        rows = (ROWS - 1,)
    elif mode == "spin":
        rows = (0, ROWS - 1)
    else:
        return
    for row in rows:
        _paint(pixels, row, COLS // 2)
