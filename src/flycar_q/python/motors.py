"""Send wheel pulses to the sketch. Arguments are right, then left."""

from __future__ import annotations

import time

from arduino.app_utils import Bridge


def send(right: int, left: int) -> bool:
    try:
        Bridge.call("setMotorSpeed", int(right), int(left))
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
