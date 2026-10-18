"""Fixed-period deadlines for the flycar_q loop."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

from schedule import Next  # noqa: E402


def test_before_the_deadline_does_not_fire() -> None:
    clock = Next(0.25, start=1.0)
    assert clock.tick(0.99) is False
    assert clock.tick(1.0) is True


def test_on_time_keeps_the_original_phase() -> None:
    clock = Next(0.25, start=1.0)
    assert clock.tick(1.0) is True
    assert clock.at == 1.25
    assert clock.tick(1.25) is True
    assert clock.at == 1.5


def test_a_late_call_skips_the_missed_repeats() -> None:
    clock = Next(0.25, start=1.0)
    assert clock.tick(1.5) is True
    assert clock.at == 1.75
    assert clock.tick(1.5) is False
    assert clock.tick(1.75) is True
