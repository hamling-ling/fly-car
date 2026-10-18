"""Straight-line hinge used by the remote_control page. The app needs the Uno Q."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "remote_control" / "python"))

from hinge import (  # noqa: E402
    FORWARD,
    REVERSE,
    Hinge,
    apply_straight,
    clean_hinge,
    commands,
    left_magnitude,
    straight_preview,
)


def test_forward_samples_follow_the_notebook_line() -> None:
    assert left_magnitude(0, FORWARD) == 0
    assert left_magnitude(1, FORWARD) == 0
    assert left_magnitude(13, FORWARD) == 9
    assert left_magnitude(90, FORWARD) == 82
    assert left_magnitude(100, FORWARD) == 84
    assert left_magnitude(125, FORWARD) == 91
    assert left_magnitude(160, FORWARD) == 101
    assert left_magnitude(255, FORWARD) == 126


def test_reverse_samples_follow_the_notebook_line() -> None:
    assert left_magnitude(36, REVERSE) == 39
    assert left_magnitude(75, REVERSE) == 78
    assert left_magnitude(100, REVERSE) == 92
    assert left_magnitude(160, REVERSE) == 124
    assert left_magnitude(255, REVERSE) == 175


def test_half_up_and_the_pulse_cap() -> None:
    flat = Hinge(offset=0.5, slope=0.0, slope_after=0.0, knot=255.0)
    assert left_magnitude(10, flat) == 1
    assert left_magnitude(10, Hinge(0.499, 0.0, 0.0, 255.0)) == 0
    steep = Hinge(offset=0.0, slope=0.0, slope_after=10.0, knot=0.0)
    assert left_magnitude(255, steep) == 255


def test_straight_forward_replaces_only_the_left_command() -> None:
    assert commands(True, False, False, False, 160, FORWARD, REVERSE, True) == (160, 101)


def test_straight_back_uses_the_reverse_line() -> None:
    assert commands(False, True, False, False, 100, FORWARD, REVERSE, True) == (-100, -92)


def test_turns_and_spins_keep_the_typed_speed() -> None:
    assert commands(True, False, False, True, 160, FORWARD, REVERSE, True) == (0, 160)
    assert commands(True, False, True, False, 160, FORWARD, REVERSE, True) == (160, 0)
    assert commands(False, False, False, True, 160, FORWARD, REVERSE, True) == (-160, 160)
    assert apply_straight(0, 0, FORWARD, REVERSE, True) == (0, 0)


def test_disabled_line_sends_the_same_magnitude_to_both_wheels() -> None:
    assert commands(True, False, False, False, 160, FORWARD, REVERSE, False) == (160, 160)
    assert straight_preview(160, FORWARD, REVERSE, False) == {
        "forward_right": 160,
        "forward_left": 160,
        "back_right": -160,
        "back_left": -160,
    }


def test_preview_uses_the_same_line_as_a_straight_command() -> None:
    preview = straight_preview(160, FORWARD, REVERSE, True)
    assert preview["forward_right"] == 160
    assert preview["forward_left"] == 101
    assert preview["back_right"] == -160
    assert preview["back_left"] == -124


def test_a_blank_coefficient_falls_back_and_an_extreme_one_is_clamped() -> None:
    cleaned = clean_hinge("nope", 99, -99, 400, FORWARD)  # type: ignore[arg-type]
    assert cleaned.offset == FORWARD.offset
    assert cleaned.slope == 10.0
    assert cleaned.slope_after == -10.0
    assert cleaned.knot == 255.0
