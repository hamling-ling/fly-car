"""Capture rate reported by the Uno Q camera thread."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

from camera import CaptureRate  # noqa: E402


def test_read_is_frames_over_the_window() -> None:
    rate = CaptureRate(10.0, 100)
    assert rate.read(11.0, 115) == pytest.approx(15.0)
    assert rate.read(12.0, 125) == pytest.approx(10.0)


def test_a_zero_span_reports_zero_and_moves_the_mark() -> None:
    rate = CaptureRate(10.0, 100)
    assert rate.read(10.0, 104) == 0.0
    assert rate.read(11.0, 114) == pytest.approx(10.0)
