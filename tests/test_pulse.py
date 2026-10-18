"""Servo pulse scale. Run from the repository root."""

from __future__ import annotations

from flycar.pulse import (
    CRUISE_MPS,
    CRUISE_PULSE,
    FORWARD_START,
    PULSE_LIMIT,
    REVERSE_START,
    motion_pulse,
    wheel_pulse,
    wheel_pulses,
)


def test_cruise_speed_maps_to_the_radio_control_pulse() -> None:
    assert wheel_pulse(CRUISE_MPS) == CRUISE_PULSE
    assert wheel_pulse(0.0) == 0


def test_reverse_and_the_sketch_argument_order() -> None:
    assert wheel_pulse(-CRUISE_MPS) == -CRUISE_PULSE
    right, left = wheel_pulses(CRUISE_MPS, -CRUISE_MPS)
    assert (right, left) == (-CRUISE_PULSE, CRUISE_PULSE)


def test_clamps_to_the_sketch_limit() -> None:
    assert wheel_pulse(CRUISE_MPS * 10) == PULSE_LIMIT
    assert wheel_pulse(-CRUISE_MPS * 10) == -PULSE_LIMIT


def test_motion_floor_keeps_only_commands_that_start_the_chassis() -> None:
    assert motion_pulse(0) == 0
    assert motion_pulse(FORWARD_START - 1) == 0
    assert motion_pulse(FORWARD_START) == FORWARD_START
    assert motion_pulse(-(REVERSE_START - 1)) == 0
    assert motion_pulse(-REVERSE_START) == -REVERSE_START
    assert motion_pulse(PULSE_LIMIT) == PULSE_LIMIT
    assert motion_pulse(-PULSE_LIMIT) == -PULSE_LIMIT
    assert motion_pulse(wheel_pulse(CRUISE_MPS)) == CRUISE_PULSE
