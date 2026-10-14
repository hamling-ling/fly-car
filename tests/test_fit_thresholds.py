"""色紙の下限を、印付き JPEG 無しで確かめる。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "color_capture_q"))

from fit_thresholds import (  # noqa: E402
    OUTPUT,
    PaperSample,
    blue_hue_bounds,
    fit_thresholds,
    frame_halves,
    red_hue_bounds,
    snap_blue,
    snap_red_low,
    snap_red_wrap,
    strictest_sv,
    write_thresholds,
)
from flycar.occupancy import THRESHOLDS_PATH, load_cuts  # noqa: E402


def _sheet(stamp: str, kind: str, hue: int, saturation: int, value: int, n: int = 10) -> PaperSample:
    return PaperSample(
        stamp,
        kind,
        np.full(n, hue, dtype=np.int16),
        np.full(n, saturation, dtype=np.uint8),
        np.full(n, value, dtype=np.uint8),
    )


def test_hue_snaps_match_the_paper_rule() -> None:
    assert snap_red_wrap(328) == 326
    assert snap_red_wrap(340) == 338
    assert snap_red_low(7.52) == 10
    assert snap_red_low(8) == 10
    assert snap_red_low(None) == -1
    assert snap_blue(216, 238) == (210, 240)
    assert snap_blue(220, 240) == (220, 240)


def test_red_cluster_and_wrapped_tail_set_both_edges() -> None:
    # 0 度付近は 360 度足すと高い側になるので、10% 点は 328 のまま。
    hue = np.array([328] * 90 + [8] * 10, dtype=np.int16)
    low, wrap = red_hue_bounds([hue, np.full(10, 350, dtype=np.int16)])
    assert (low, wrap) == (10, 326)


def test_blue_uses_the_outer_tenth_of_each_sheet() -> None:
    low, high = blue_hue_bounds(
        [
            np.full(10, 216, dtype=np.int16),
            np.full(10, 238, dtype=np.int16),
        ]
    )
    assert (low, high) == (210, 240)


def test_uniform_sheet_snaps_from_its_own_pixels() -> None:
    fit = fit_thresholds(
        [
            _sheet("red", "red", hue=340, saturation=180, value=90),
            _sheet("blue", "blue", hue=220, saturation=180, value=90),
        ]
    )
    assert fit.red.hue_low == -1
    assert fit.red.hue_high == 338
    assert (fit.red.saturation, fit.red.value) == (180, 90)
    assert (fit.blue.hue_low, fit.blue.hue_high) == (220, 220)
    assert fit.red.worst == 1.0


def test_thresholds_stay_on_the_ten_step_grid() -> None:
    fit = fit_thresholds(
        [
            _sheet("red", "red", hue=340, saturation=185, value=35),
            _sheet("blue", "blue", hue=220, saturation=185, value=35),
        ]
    )
    assert (fit.red.saturation, fit.red.value) == (180, 30)
    assert (fit.blue.saturation, fit.blue.value) == (180, 30)


def test_higher_saturation_wins_over_higher_value() -> None:
    hue = np.array([340] * 8 + [340] * 2, dtype=np.int16)
    saturation = np.array([150] * 6 + [150, 150, 40, 40], dtype=np.uint8)
    value = np.array([150] * 6 + [20, 20, 150, 150], dtype=np.uint8)
    red = PaperSample("mixed", "red", hue, saturation, value)
    blue = _sheet("blue", "blue", hue=220, saturation=200, value=200)
    fit = fit_thresholds([red, blue])
    assert (fit.red.saturation, fit.red.value) == (150, 20)
    assert fit.red.worst == pytest.approx(0.8)


def test_red_tail_below_180_stays_inside_the_gate() -> None:
    hue = np.array([6] * 73 + [340] * 27, dtype=np.int16)
    red = PaperSample(
        "tail",
        "red",
        hue,
        np.full(100, 200, dtype=np.uint8),
        np.full(100, 200, dtype=np.uint8),
    )
    blue = _sheet("blue", "blue", hue=220, saturation=200, value=200)
    fit = fit_thresholds([red, blue])
    assert fit.red.hue_low == 8
    assert fit.red.worst == 1.0


def test_strictest_raises_when_the_hue_gate_already_misses() -> None:
    sample = _sheet("short", "red", hue=340, saturation=255, value=255)
    keep = np.zeros(10, dtype=bool)
    keep[:7] = True
    with pytest.raises(RuntimeError, match="0.80"):
        strictest_sv([sample], [keep])


def test_written_file_is_what_occupancy_reads(tmp_path) -> None:
    fit = fit_thresholds(
        [
            _sheet("red", "red", hue=340, saturation=180, value=90),
            _sheet("blue", "blue", hue=220, saturation=180, value=90),
        ]
    )
    path = tmp_path / "color_thresholds.json"
    write_thresholds(fit, path)
    cuts = load_cuts(path)
    assert cuts["RED_S"] == 180
    assert cuts["RED_V"] == 90
    assert cuts["RED_H_LOW"] == -1
    assert cuts["RED_H_WRAP"] == 338
    assert cuts["BLUE_H_LOW"] == 220
    assert cuts["BLUE_H_HIGH"] == 220
    assert not path.with_suffix(".json.tmp").exists()


def test_output_path_is_the_file_beside_occupancy() -> None:
    assert OUTPUT.resolve() == THRESHOLDS_PATH.resolve()


def test_pure_red_and_blue_fill_their_halves() -> None:
    fit = fit_thresholds(
        [
            _sheet("red", "red", hue=0, saturation=255, value=255),
            _sheet("blue", "blue", hue=240, saturation=255, value=255),
        ]
    )
    frame = np.zeros((4, 8, 3), dtype=np.uint8)
    frame[:, :4] = (0, 0, 255)
    frame[:, 4:] = (255, 0, 0)
    assert frame_halves(frame, fit) == (1.0, 0.0, 0.0, 1.0)
    cyan = np.zeros((4, 8, 3), dtype=np.uint8)
    cyan[:, :4] = (255, 255, 0)
    assert frame_halves(cyan, fit) == (0.0, 0.0, 0.0, 0.0)
