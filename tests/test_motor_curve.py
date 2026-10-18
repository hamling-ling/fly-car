"""Pulse-band mapping for the motor_adjust app. The app itself needs the Uno Q."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "motor_adjust" / "python"))

from curve import (  # noqa: E402
    DEFAULT_LIMITS,
    direct_commands,
    map_magnitude,
    map_wheel,
    map_wheels,
    mix,
)


def test_zero_stays_stopped_when_conversion_is_on() -> None:
    assert map_magnitude(0, 13, 255) == 0
    assert map_wheel(0, (13, 255), (36, 255), True) == 0


def test_full_scale_limits_leave_the_command_unchanged() -> None:
    for command in (1, 14, 128, 255, -1, -36, -255):
        assert map_wheel(command, (0, 255), (0, 255), True) == command


def test_full_stick_hits_the_upper_limit_and_the_first_step_rounds_half_up() -> None:
    assert map_magnitude(255, 13, 200) == 200
    assert map_magnitude(1, 13, 255) == 14
    assert map_magnitude(128, 36, 100) == 68


def test_reverse_and_the_two_wheels_use_their_own_bands() -> None:
    limits = {
        "right_forward": (13, 255),
        "right_back": (27, 255),
        "left_forward": (13, 255),
        "left_back": (42, 200),
    }
    right, left = map_wheels(160, -160, limits, True)
    assert right == map_wheel(160, (13, 255), (27, 255), True)
    assert left == map_wheel(-160, (13, 255), (42, 200), True)
    assert left < 0
    assert abs(left) == map_magnitude(160, 42, 200)


def test_conversion_off_returns_the_raw_command() -> None:
    assert map_wheels(12, -35, DEFAULT_LIMITS, False) == (12, -35)


def test_limits_outside_the_pulse_range_are_clamped() -> None:
    assert map_wheel(255, (-20, 400), (0, 255), True) == 255
    assert map_wheel(10, (0, 400), (0, 255), True) == map_magnitude(10, 0, 255)


def test_equal_limits_hold_one_pulse_except_at_zero() -> None:
    assert map_magnitude(1, 40, 40) == 40
    assert map_magnitude(200, 40, 40) == 40
    assert map_wheel(0, (40, 40), (40, 40), True) == 0


def test_a_lower_upper_than_lower_slopes_down() -> None:
    assert map_magnitude(1, 200, 10) == 199
    assert map_magnitude(255, 200, 10) == 10


def test_mix_keeps_the_remote_control_wheel_signs() -> None:
    assert mix(True, False, False, False, 160) == (160, 160)
    assert mix(False, False, False, True, 160) == (-160, 160)
    assert mix(True, False, False, True, 160) == (0, 160)
    assert mix(False, False, False, False, 160) == (0, 0)


def test_direct_commands_are_the_values_sent_to_the_mcu() -> None:
    assert direct_commands(True, False, False, False, 150, 149, 91, 77) == (150, 149)
    assert direct_commands(False, True, False, False, 150, 149, 91, 77) == (-91, -77)
    assert direct_commands(False, False, False, True, 150, 149, 91, 77) == (-91, 149)
    assert direct_commands(True, False, False, True, 150, 149, 91, 77) == (0, 149)
    assert direct_commands(False, False, False, False, 150, 149, 91, 77) == (0, 0)
    assert direct_commands(True, False, False, False, 400, -5, 91, 77) == (255, 0)


def test_a_spin_maps_one_wheel_forward_and_the_other_back() -> None:
    right, left = mix(False, False, False, True, 160)
    mapped_right, mapped_left = map_wheels(right, left, DEFAULT_LIMITS, True)
    assert mapped_right == map_wheel(right, DEFAULT_LIMITS["right_forward"], DEFAULT_LIMITS["right_back"], True)
    assert mapped_left == map_wheel(left, DEFAULT_LIMITS["left_forward"], DEFAULT_LIMITS["left_back"], True)
    assert mapped_right < 0
    assert mapped_left > 0
