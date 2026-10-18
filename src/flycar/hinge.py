"""Left-wheel command that keeps the chassis straight.

The right pulse is the reference measured on 2026-10-18. The left motor is
faster at the same pulse, so the left command is read off a hinge: offset
plus slope times the matched pulse, and a shallower slope past the knot.
The numbers are the same fit as research/remote_control/python/hinge.py and
research/notebooks/straight_limits.ipynb. A stopped command stays stopped.
"""

from __future__ import annotations

from dataclasses import dataclass

from flycar.pulse import PULSE_LIMIT, motion_pulse

FORWARD_OFFSET = -3.1047767904
FORWARD_SLOPE = 0.9428435978
FORWARD_SLOPE_AFTER = 0.2694042727
FORWARD_KNOT = 90.0
REVERSE_OFFSET = 1.6622116836
REVERSE_SLOPE = 1.0234964432
REVERSE_SLOPE_AFTER = 0.5368484587
REVERSE_KNOT = 75.0


@dataclass(frozen=True)
class Hinge:
    """Right-command axis, left-command value."""

    offset: float
    slope: float
    slope_after: float
    knot: float


FORWARD = Hinge(FORWARD_OFFSET, FORWARD_SLOPE, FORWARD_SLOPE_AFTER, FORWARD_KNOT)
REVERSE = Hinge(REVERSE_OFFSET, REVERSE_SLOPE, REVERSE_SLOPE_AFTER, REVERSE_KNOT)


def _clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def left_magnitude(matched: int, hinge: Hinge) -> int:
    """Left magnitude for a matched pulse. 0 stays 0. Results stay in 0..255."""
    command = _clamp(int(matched), 0, PULSE_LIMIT)
    if command == 0:
        return 0
    extra = command - hinge.knot
    if extra < 0:
        extra = 0.0
    bend = hinge.slope_after - hinge.slope
    value = hinge.offset + hinge.slope * command + bend * extra
    if value <= 0:
        return 0
    return _clamp(int(value + 0.5), 0, PULSE_LIMIT)


def straighten(right: int, left: int) -> tuple[int, int]:
    """Keep ``right``. Pass ``left`` through the hinge of its own direction.

    The law's pulses are what a matched pair of motors would be given. The
    right wheel is the reference, so its pulse is unchanged. The left wheel
    gets the command that matched that pulse on the straight-line fit. A
    turn still uses the left pulse the law asked for, not the right wheel's.
    """
    command = int(left)
    if command > 0:
        return int(right), left_magnitude(command, FORWARD)
    if command < 0:
        return int(right), -left_magnitude(-command, REVERSE)
    return int(right), 0


def calibrated_command(right: int, left: int) -> tuple[int, int]:
    """Straighten the left wheel, then drop commands below the start floor."""
    right, left = straighten(right, left)
    return motion_pulse(right), motion_pulse(left)
