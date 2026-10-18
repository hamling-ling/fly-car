"""Heading and confidence intervals for motor_adjust straight trials."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "motor_adjust" / "python"))

from straight import group_rows, heading_deg, make_trial, summarize, t95  # noqa: E402


def test_parallel_offset_has_no_heading_and_nose_right_is_positive() -> None:
    assert heading_deg(5, 5, 170) == 0.0
    assert heading_deg(10, 0, 170) > 0.0
    assert heading_deg(0, 10, 170) < 0.0
    assert heading_deg(10, 0, 170) == math.degrees(math.atan2(10, 170))


def test_one_sample_has_no_interval_and_three_samples_use_students_t() -> None:
    assert summarize([4.0])["includes_zero"] is None
    summary = summarize([1.0, 2.0, 3.0])
    sem = 1.0 / math.sqrt(3.0)
    half = t95(2) * sem
    assert summary["n"] == 3
    assert summary["mean"] == 2.0
    assert math.isclose(summary["ci_low"], 2.0 - half)
    assert math.isclose(summary["ci_high"], 2.0 + half)
    assert summary["includes_zero"] is True


def test_a_steady_right_yaw_excludes_zero() -> None:
    summary = summarize([5.0, 6.0, 7.0])
    assert summary["includes_zero"] is False
    assert summary["mean"] == 6.0


def test_groups_keep_duration_apart_and_name_the_faster_wheel() -> None:
    trials = [
        make_trial(155, 147, 800, 20, 0, 170),
        make_trial(155, 147, 800, 22, 0, 170),
        make_trial(155, 86, 800, 0, 0, 170),
        make_trial(155, 86, 800, 1, 1, 170),
        make_trial(155, 147, 1200, 20, 0, 170),
    ]
    rows = group_rows(trials)
    assert [(row["right"], row["left"], row["ms"], row["n"]) for row in rows] == [
        (155, 86, 800, 2),
        (155, 147, 800, 2),
        (155, 147, 1200, 1),
    ]
    matched = rows[0]
    assert matched["includes_zero"] is True
    assert matched["reading"] == "区別できない"
    turned = rows[1]
    assert turned["reading"] == "左が速い"
    assert rows[2]["reading"] == "回数不足"


def test_length_and_offset_outside_the_bench_are_rejected() -> None:
    try:
        make_trial(150, 149, 800, 0, 0, 10)
    except ValueError as exc:
        assert "間隔" in str(exc)
    else:
        raise AssertionError("short length was accepted")
