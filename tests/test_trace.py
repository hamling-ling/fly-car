"""Debug line for one wheel command."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

from trace import trace_line, trace_mark  # noqa: E402


def test_trace_line_names_the_yaw_gate_and_the_floor() -> None:
    """b と、床を通す前のパルスが、送ったパルスと別に出る。"""
    text = trace_line(
        (0.0, 0.0),
        (0.17, 0.06),
        (1.65, 0.82),
        0.0,
        math.radians(22.0),
        0.4,
        (104.0, 0.0),
        (0.0, 0.0),
        -0.023,
        0.0,
        (-0.023, -0.023),
        (-18, -18),
        (0, 0),
        "back",
    )
    assert "I 1.65 0.82" in text
    assert "b 0" in text
    assert "ratio 0.50" in text
    assert "DNp 104 0" in text
    assert "DNa 0 0" in text
    assert "deg 22" in text
    assert "exp 0.4" in text
    assert "raw R:-18 L:-18" in text
    assert "pulse R:0 L:0" in text
    assert text.endswith("back")


def test_trace_mark_ignores_a_rate_wiggle_under_five_hertz() -> None:
    base = trace_mark(0.0, (1.2, 1.1), 0.4, 0.42, (83.0, 80.0), (-28, -28), (0, 0), "back")
    wiggle = trace_mark(0.0, (1.2, 1.1), 0.4, 0.42, (84.0, 81.0), (-28, -28), (0, 0), "back")
    jumped = trace_mark(1.0, (1.2, 1.1), 0.4, 0.42, (84.0, 81.0), (-28, -28), (0, 0), "back")
    assert base == wiggle
    assert base != jumped
