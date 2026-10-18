"""Send wheel pulses to the sketch. Arguments are right, then left.

The left command is read off the straight-line hinge, then each wheel is
dropped to 0 when it is below the table start threshold. The returned pair
is what was passed to setMotorSpeed.
"""

from __future__ import annotations

import time

from arduino.app_utils import Bridge

from flycar.hinge import calibrated_command


def send(right: int, left: int) -> tuple[int, int] | None:
    right, left = calibrated_command(right, left)
    try:
        Bridge.call("setMotorSpeed", right, left)
    except Exception as exc:
        print(f"setMotorSpeed failed: {exc}")
        return None
    return right, left


def wait_until_bridge(attempts: int = 50, pause_s: float = 0.1) -> bool:
    """Stop the wheels, retrying while the sketch's Bridge is still coming up."""
    for _ in range(attempts):
        if send(0, 0) is not None:
            return True
        time.sleep(pause_s)
    return False
