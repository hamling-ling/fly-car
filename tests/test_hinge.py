"""Straight-line hinge applied before flycar_q sends wheel pulses."""

from __future__ import annotations

import sys
from pathlib import Path

from flycar.hinge import (
    FORWARD,
    REVERSE,
    calibrated_command,
    left_magnitude,
    straighten,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "remote_control" / "python"))

from hinge import FORWARD as REMOTE_FORWARD  # noqa: E402
from hinge import REVERSE as REMOTE_REVERSE  # noqa: E402
from hinge import left_magnitude as remote_left_magnitude  # noqa: E402


def test_coefficients_match_the_remote_control_fit() -> None:
    assert (FORWARD.offset, FORWARD.slope, FORWARD.slope_after, FORWARD.knot) == (
        REMOTE_FORWARD.offset,
        REMOTE_FORWARD.slope,
        REMOTE_FORWARD.slope_after,
        REMOTE_FORWARD.knot,
    )
    assert (REVERSE.offset, REVERSE.slope, REVERSE.slope_after, REVERSE.knot) == (
        REMOTE_REVERSE.offset,
        REMOTE_REVERSE.slope,
        REMOTE_REVERSE.slope_after,
        REMOTE_REVERSE.knot,
    )
    for matched in (0, 1, 13, 80, 90, 100, 125, 160, 255):
        assert left_magnitude(matched, FORWARD) == remote_left_magnitude(matched, REMOTE_FORWARD)
    for matched in (36, 75, 100, 160, 255):
        assert left_magnitude(matched, REVERSE) == remote_left_magnitude(matched, REMOTE_REVERSE)


def test_straight_cruise_lowers_only_the_left_command() -> None:
    assert straighten(160, 160) == (160, 101)
    assert straighten(-100, -100) == (-100, -92)


def test_a_turn_uses_the_left_wheels_own_pulse() -> None:
    assert straighten(160, 80) == (160, left_magnitude(80, FORWARD))
    assert straighten(160, 80) != (160, left_magnitude(160, FORWARD))


def test_a_stopped_left_wheel_stays_stopped() -> None:
    assert straighten(160, 0) == (160, 0)
    assert straighten(0, 0) == (0, 0)


def test_a_spin_uses_the_hinge_of_the_left_wheels_direction() -> None:
    assert straighten(-160, 160) == (-160, 101)
    assert straighten(160, -160) == (160, -124)


def test_floor_runs_after_the_hinge() -> None:
    assert calibrated_command(160, 160) == (160, 101)
    assert calibrated_command(12, 12) == (0, 0)
    assert calibrated_command(20, 20) == (20, left_magnitude(20, FORWARD))
