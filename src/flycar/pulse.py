"""Wheel speed in m/s to the servo pulse used by the Uno Q sketch.

The sketch takes the same -255..255 command as motor_test. Positive is
forward. 0.20 m/s is the frontal-red cruise noted in behavior.py, and 160
is the pulse the radio-control slider used for a comfortable roll. Nothing
here has been timed against the real wheels, and a small pulse can sit
inside the servo's dead band.
"""

from __future__ import annotations

CRUISE_MPS = 0.20
CRUISE_PULSE = 160
PULSE_LIMIT = 255


def wheel_pulse(meters_per_second: float) -> int:
    scaled = float(meters_per_second) / CRUISE_MPS * CRUISE_PULSE
    rounded = int(round(scaled))
    if rounded > PULSE_LIMIT:
        return PULSE_LIMIT
    if rounded < -PULSE_LIMIT:
        return -PULSE_LIMIT
    return rounded


def wheel_pulses(v_left: float, v_right: float) -> tuple[int, int]:
    """Return ``(right, left)`` in the order ``setMotorSpeed`` expects."""
    return wheel_pulse(v_right), wheel_pulse(v_left)
