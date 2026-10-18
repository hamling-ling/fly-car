"""直進のとき、右の指令から左の指令を決める折れ線。

research/notebooks/straight_limits.ipynb のフィットと同じ式である。
左 = 切片 + 傾き×右。右が折れ目を超えると、傾きがあとの傾きに替わる。
ページが係数を送り、ここが指令の整数にする。旋回とその場の回転は掛けない。
"""

from __future__ import annotations

from dataclasses import dataclass

PULSE_LIMIT = 255
SLOPE_LIMIT = 10.0


@dataclass(frozen=True)
class Hinge:
    """右の指令を横軸にした、左の指令の折れ線。"""

    offset: float
    slope: float
    slope_after: float
    knot: float


# 2026-10-18 の生値。前進は右 108 の左 104 を外し、左 85 だけを使った。
# 前進の折れ目は 90、後退の折れ目は 75。
FORWARD = Hinge(
    offset=-3.1047767904,
    slope=0.9428435978,
    slope_after=0.2694042727,
    knot=90.0,
)
REVERSE = Hinge(
    offset=1.6622116836,
    slope=1.0234964432,
    slope_after=0.5368484587,
    knot=75.0,
)


def clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _finite(value: float, fallback: float, lo: float, hi: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number == float("inf") or number == float("-inf"):
        return fallback
    if number < lo:
        return lo
    if number > hi:
        return hi
    return number


def clean_hinge(
    offset: float,
    slope: float,
    slope_after: float,
    knot: float,
    fallback: Hinge,
) -> Hinge:
    """ページの係数を範囲へ収め、数値でないものはフィットの値に戻す。"""
    return Hinge(
        offset=_finite(offset, fallback.offset, -PULSE_LIMIT, PULSE_LIMIT),
        slope=_finite(slope, fallback.slope, -SLOPE_LIMIT, SLOPE_LIMIT),
        slope_after=_finite(slope_after, fallback.slope_after, -SLOPE_LIMIT, SLOPE_LIMIT),
        knot=_finite(knot, fallback.knot, 0, PULSE_LIMIT),
    )


def left_magnitude(right: int, hinge: Hinge) -> int:
    """右の大きさに対する左の大きさ。0 は 0。負の予測と 255 の外は端に寄せる。"""
    command = clamp(int(right), 0, PULSE_LIMIT)
    if command == 0:
        return 0
    extra = command - hinge.knot
    if extra < 0:
        extra = 0.0
    bend = hinge.slope_after - hinge.slope
    value = hinge.offset + hinge.slope * command + bend * extra
    if value <= 0:
        return 0
    return clamp(int(value + 0.5), 0, PULSE_LIMIT)


def mix(up: bool, down: bool, left: bool, right: bool, speed: int) -> tuple[int, int]:
    """押されているキーから、右と左の指令 -255..255 を作る。

    折れ線の前の値。右旋回は左輪が外側で、yaw が正のとき左を進め、右を戻す。
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


def apply_straight(
    right: int,
    left: int,
    forward: Hinge,
    back: Hinge,
    enabled: bool,
) -> tuple[int, int]:
    """左右が同じ向きのときだけ、左を右の折れ線に置き換える。"""
    if not enabled or right == 0 or left == 0 or (right > 0) != (left > 0):
        return right, left
    if right > 0:
        return right, left_magnitude(right, forward)
    return right, -left_magnitude(-right, back)


def commands(
    up: bool,
    down: bool,
    left: bool,
    right: bool,
    speed: int,
    forward: Hinge,
    back: Hinge,
    enabled: bool,
) -> tuple[int, int]:
    """キーと速度から、マイコンへ渡す右と左を作る。"""
    raw_right, raw_left = mix(up, down, left, right, speed)
    return apply_straight(raw_right, raw_left, forward, back, enabled)


def straight_preview(speed: int, forward: Hinge, back: Hinge, enabled: bool) -> dict[str, int]:
    """止めたまま、この速度の直進と後退がどの指令になるかを返す。"""
    command = clamp(int(speed), 0, PULSE_LIMIT)
    if not enabled:
        return {
            "forward_right": command,
            "forward_left": command,
            "back_right": -command,
            "back_left": -command,
        }
    return {
        "forward_right": command,
        "forward_left": left_magnitude(command, forward),
        "back_right": -command,
        "back_left": -left_magnitude(command, back),
    }
