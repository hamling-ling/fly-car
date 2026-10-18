"""Send wheel pulses to the sketch. Arguments are right, then left.

The law's command is logged by the caller. This module applies the table
start threshold first, so a logged pulse of 12 can still go out as stop.
"""

from __future__ import annotations

import time

from arduino.app_utils import Bridge

from flycar.pulse import motion_pulse


def send(right: int, left: int) -> bool:
    right = motion_pulse(right)
    left = motion_pulse(left)
    try:
        Bridge.call("setMotorSpeed", right, left)
    except Exception as exc:
        print(f"setMotorSpeed failed: {exc}")
        return False
    return True


def wait_until_bridge(attempts: int = 50, pause_s: float = 0.1) -> bool:
    """Stop the wheels, retrying while the sketch's Bridge is still coming up."""
    for _ in range(attempts):
        if send(0, 0):
            return True
        time.sleep(pause_s)
    return False
