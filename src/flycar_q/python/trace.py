"""One debug line for the wheel command.

The 1 Hz line missed the count that actually moved the car. This one adds
the yaw gate, the four rates, and the pulses before the start floor.
"""

from __future__ import annotations

import math


def trace_line(
    red: tuple[float, float],
    blue: tuple[float, float],
    loom: tuple[float, float],
    yaw_scale: float,
    theta: float,
    theta_dot: float,
    dnp: tuple[float, float],
    dna: tuple[float, float],
    speed: float,
    omega: float,
    wheel: tuple[float, float],
    raw: tuple[int, int],
    sent: tuple[int, int],
    mode: str,
) -> str:
    """Format one command. ``wheel`` and the pulses are right, then left."""
    stronger = max(loom)
    ratio = min(loom) / stronger if stronger > 0.0 else 0.0
    right_v, left_v = wheel
    raw_r, raw_l = raw
    sent_r, sent_l = sent
    return (
        f"red {red[0]:.2f} {red[1]:.2f}  "
        f"blue {blue[0]:.2f} {blue[1]:.2f}  "
        f"I {loom[0]:.2f} {loom[1]:.2f}  "
        f"b {yaw_scale:.0f}  ratio {ratio:.2f}  "
        f"DNp {dnp[0]:.0f} {dnp[1]:.0f}  "
        f"DNa {dna[0]:.0f} {dna[1]:.0f}  "
        f"deg {math.degrees(theta):.0f}  exp {theta_dot:.1f}  "
        f"v {speed:.3f}  yaw {omega:.2f}  "
        f"wheel R:{right_v:.3f} L:{left_v:.3f}  "
        f"raw R:{raw_r} L:{raw_l}  "
        f"pulse R:{sent_r} L:{sent_l}  {mode}"
    )


def trace_mark(
    yaw_scale: float,
    loom: tuple[float, float],
    theta: float,
    theta_dot: float,
    dnp: tuple[float, float],
    raw: tuple[int, int],
    sent: tuple[int, int],
    mode: str,
) -> tuple[object, ...]:
    """Identity of a line. A new mark is worth printing before the next period."""
    return (
        round(yaw_scale),
        round(loom[0], 1),
        round(loom[1], 1),
        round(math.degrees(theta)),
        round(theta_dot, 1),
        round(dnp[0] / 5.0) * 5,
        round(dnp[1] / 5.0) * 5,
        raw,
        sent,
        mode,
    )
