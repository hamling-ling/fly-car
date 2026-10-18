"""Wheel speed in m/s to the servo pulse used by the Uno Q sketch.

The sketch takes the same -255..255 command as motor_test. Positive is
forward. 0.20 m/s is the frontal-red cruise noted in behavior.py, and 160
is the pulse the radio-control slider used for a comfortable roll. Nothing
here has been timed against the real wheels. ``motion_pulse`` drops
commands that, on the table on 2026-10-17, only twitched or stopped when
touched. The radio-control app does not call it.
"""

from __future__ import annotations

CRUISE_MPS = 0.20
CRUISE_PULSE = 160
PULSE_LIMIT = 255

# 2026-10-17 table. Both wheels: 1500 + trunc(pulse / 255 * 500) µs.
# Forward 13 is 1525 µs. 0..12 creeps or stops at a touch.
# Reverse 36 is 1430 µs. 1..35 in reverse yaws clockwise: the right wheel
# turns before the left. The floors are shared. No per-wheel reverse offset.
FORWARD_START = 13
REVERSE_START = 36


def wheel_pulse(meters_per_second: float) -> int:
    scaled = float(meters_per_second) / CRUISE_MPS * CRUISE_PULSE
    rounded = int(round(scaled))
    if rounded > PULSE_LIMIT:
        return PULSE_LIMIT
    if rounded < -PULSE_LIMIT:
        return -PULSE_LIMIT
    return rounded


def motion_pulse(pulse: int) -> int:
    """Return ``pulse``, or 0 when the chassis has not started moving.

    13 and above, and -36 and below, pass through. Each wheel is judged
    on its own, so a turn whose inner command is 12 or less stops that wheel.
    """
    command = int(pulse)
    if command >= FORWARD_START or command <= -REVERSE_START:
        return command
    return 0


def wheel_pulses(v_left: float, v_right: float) -> tuple[int, int]:
    """Return ``(right, left)`` in the order ``setMotorSpeed`` expects."""
    return wheel_pulse(v_right), wheel_pulse(v_left)
