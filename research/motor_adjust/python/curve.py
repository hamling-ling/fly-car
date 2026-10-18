"""十字キーから、マイコンへ渡す左右の指令を作る。

ページが使うのは direct_commands。前進側の数は正、後退側の数は負になり、
押した向きの車輪へそのまま載る。map_magnitude 以下は、直進の記録を
notebook が同じ式で描くための変換で、ページはもう呼ばない。
"""

from __future__ import annotations

PULSE_LIMIT = 255

# 2026-10-17 のテーブルで車体が動き出した値。上限は指令の端。
DEFAULT_LIMITS = {
    "right_forward": (13, 255),
    "right_back": (36, 255),
    "left_forward": (13, 255),
    "left_back": (36, 255),
}


def clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def clean_limit(value: int) -> int:
    return clamp(int(value), 0, PULSE_LIMIT)


def clean_limits(limits: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    cleaned = {}
    for name, default in DEFAULT_LIMITS.items():
        pair = limits.get(name, default)
        cleaned[name] = (clean_limit(pair[0]), clean_limit(pair[1]))
    return cleaned


def map_magnitude(magnitude: int, low: int, high: int) -> int:
    """正の速度を、下限から上限までの直線へ載せる。0 は 0。"""
    if magnitude <= 0:
        return 0
    if magnitude >= PULSE_LIMIT:
        return high
    span = high - low
    numer = magnitude * span
    negative = numer < 0
    absolute = -numer if negative else numer
    whole = absolute // PULSE_LIMIT
    if (absolute % PULSE_LIMIT) * 2 >= PULSE_LIMIT:
        whole += 1
    mapped = low - whole if negative else low + whole
    return clamp(mapped, 0, PULSE_LIMIT)


def map_wheel(
    command: int,
    forward: tuple[int, int],
    back: tuple[int, int],
    enabled: bool,
) -> int:
    """正は前進の帯、負は後退の帯。切っているときと 0 はそのまま。"""
    command = clamp(int(command), -PULSE_LIMIT, PULSE_LIMIT)
    if not enabled or command == 0:
        return command
    low, high = forward if command > 0 else back
    magnitude = map_magnitude(abs(command), clean_limit(low), clean_limit(high))
    if command > 0:
        return magnitude
    return -magnitude


def map_wheels(
    right: int,
    left: int,
    limits: dict[str, tuple[int, int]],
    enabled: bool,
) -> tuple[int, int]:
    bands = clean_limits(limits)
    return (
        map_wheel(right, bands["right_forward"], bands["right_back"], enabled),
        map_wheel(left, bands["left_forward"], bands["left_back"], enabled),
    )


def direct_commands(
    up: bool,
    down: bool,
    left: bool,
    right: bool,
    forward_right: int,
    forward_left: int,
    back_right: int,
    back_left: int,
) -> tuple[int, int]:
    """十字キーの向きに、マイコンへ渡す左右の指令をそのまま載せる。

    前進側の数は正、後退側の数は負になる。曲がる側の車輪は止める。
    """
    forward = (1 if up else 0) - (1 if down else 0)
    yaw = (1 if right else 0) - (1 if left else 0)
    return (
        _signed(forward - yaw, forward_right, back_right),
        _signed(forward + yaw, forward_left, back_left),
    )


def _signed(direction: int, forward_magnitude: int, back_magnitude: int) -> int:
    if direction > 0:
        return clean_limit(forward_magnitude)
    if direction < 0:
        return -clean_limit(back_magnitude)
    return 0


def mix(up: bool, down: bool, left: bool, right: bool, speed: int) -> tuple[int, int]:
    """押されているキーから、右と左の指令 -255..255 を作る。

    変換の前の値。右旋回は左輪が外側で、yaw が正のとき左を進め、右を戻す。
    """
    forward = (1 if up else 0) - (1 if down else 0)
    yaw = (1 if right else 0) - (1 if left else 0)
    right_cmd = forward - yaw
    left_cmd = forward + yaw
    peak = max(abs(right_cmd), abs(left_cmd), 1)
    scale = clamp(int(speed), 0, PULSE_LIMIT) / peak
    return (
        int(round(right_cmd * scale)),
        int(round(left_cmd * scale)),
    )
