"""Angular size, expansion, and the DNp01 current.

Run from the repository root:

    python3 -m pytest tests/test_loom.py
"""

from __future__ import annotations

import numpy as np
import pytest

from flycar.behavior import hold
from flycar.loom import (
    BLUE_MIN_FRACTION,
    CELLS_PATH,
    EARLY_MID,
    EARLY_WIDTH,
    LC4_GAIN,
    R_MAX,
    R_REF,
    Disk,
    LoomTrack,
    anchored_sigmoid,
    camera_tangents,
    cells,
    measure_blue,
    size_gain,
)


def _disk(theta_deg: float, cu: float) -> Disk:
    """Equal-area disk of ``theta_deg`` centered at image ``cu``."""
    tan_h, tan_v = camera_tangents()
    theta = float(np.deg2rad(theta_deg))
    cx = (cu * 2.0 - 1.0) * tan_h
    rod = float(np.tan(theta / 2.0) * np.sqrt(1.0 + cx * cx))
    return Disk(cu, 0.5, rod / tan_h / 2.0, rod / tan_v / 2.0, theta)


def test_sigmoid_keeps_the_notebook_shape_at_the_camera_center() -> None:
    """ノートの早めた列は中心 8、幅 5。車は 20° が 0.4 rad/s で開くように置いてある。"""
    assert anchored_sigmoid(0.0, 8.0, 5.0) == pytest.approx(0.0, abs=1e-12)
    assert anchored_sigmoid(12.0, 8.0, 5.0) == pytest.approx(0.627, abs=1e-3)
    assert (EARLY_MID, EARLY_WIDTH) == (0.20, 0.10)
    assert LC4_GAIN == 5.0
    assert (R_MAX, R_REF) == (100.0, 50.0)
    assert anchored_sigmoid(0.0) == pytest.approx(0.0, abs=1e-12)
    assert 0.3 < anchored_sigmoid(0.2) < 0.6
    assert anchored_sigmoid(0.4) > 0.8
    assert size_gain(np.deg2rad(40.0)) == pytest.approx(1.0)
    assert size_gain(np.deg2rad(10.0)) == pytest.approx(0.325, abs=1e-2)


def test_shipped_table_has_the_notebook_synapse_totals() -> None:
    assert CELLS_PATH.is_file()
    pack = cells()
    assert pack.lc4.side.size == 126
    assert pack.lplc2.side.size == 185
    assert pack.side_ref[0] == pytest.approx(6424.0)
    assert pack.side_ref[1] == pytest.approx(4800.0)


def test_a_stopped_full_eye_stays_under_threshold() -> None:
    """左眼を覆う 40° は、止まっていれば閾値を超えない。"""
    disk = Disk(0.25, 0.5, 0.30, 0.60, theta=float(np.deg2rad(40.0)))
    still = cells().current(disk, 0.0)
    assert still[0] < 1.0
    assert still[0] > 0.5
    got = hold(0.0, 0.0, 0.9, 0.0, loom=still)
    assert got.mode == "stop"
    assert got.x == pytest.approx(0.0, abs=1e-9)


def test_twenty_degrees_on_the_right_eye_crosses_around_a_half_meter() -> None:
    """右目中央の 20° は、0.4 rad/s で閾値を超え、停止では超えない。

    この紙のおよそ 50 cm である。右目中央の 10° は、拡大が頭打ちのとき超える。
    """
    disk = _disk(20.0, 0.75)
    approach = cells().current(disk, 0.4)
    still = cells().current(disk, 0.0)
    assert approach[0] == 0.0
    assert approach[1] > 1.0
    assert still[1] < 1.0
    assert still[1] > 0.3
    stopped = hold(0.0, 0.0, 0.0, 0.9, loom=still)
    assert stopped.mode == "stop"
    moved = hold(0.0, 0.0, 0.0, 0.0, seconds=0.4, settle=0.1, loom=approach)
    assert moved.mode == "spin"
    assert moved.omega > 1.0
    assert moved.heading > 0.2
    assert moved.v_left < 0.0 < moved.v_right
    far = cells().current(_disk(10.0, 0.75), 50.0)
    assert far[1] > 1.0


def test_a_disk_on_the_right_does_not_drive_the_left() -> None:
    disk = Disk(0.75, 0.5, 0.12, 0.25, theta=float(np.deg2rad(40.0)))
    left, right = cells().current(disk, 20.0)
    assert left == 0.0
    assert right > 0.0


def test_raster_disk_recovers_its_angular_size() -> None:
    tan_h, tan_v = camera_tangents()
    height, width = 180, 320
    radius_over_depth = 0.15
    ys, xs = np.mgrid[0:height, 0:width]
    u = (xs + 0.5) / width
    v = (ys + 0.5) / height
    nx = (2.0 * u - 1.0) * tan_h
    ny = (1.0 - 2.0 * v) * tan_v
    mask = nx * nx + ny * ny <= radius_over_depth**2
    assert mask.mean() > BLUE_MIN_FRACTION
    disk = measure_blue(mask)
    assert disk is not None
    assert disk.theta == pytest.approx(2.0 * np.arctan(radius_over_depth), rel=0.02)
    assert disk.cu == pytest.approx(0.5, abs=0.01)
    assert disk.cv == pytest.approx(0.5, abs=0.01)


def test_expansion_waits_for_a_second_frame_and_ignores_shrinkage() -> None:
    track = LoomTrack()
    still = Disk(0.75, 0.5, 0.10, 0.18, theta=0.40)
    track.update(still, 0.0)
    assert track.theta_dot == 0.0
    track.update(still, 0.10)
    assert track.theta_dot == 0.0
    grown = Disk(0.75, 0.5, 0.12, 0.20, theta=0.55)
    track.update(grown, 0.20)
    assert track.theta_dot == pytest.approx(1.5)
    shrunk = Disk(0.75, 0.5, 0.08, 0.14, theta=0.30)
    track.update(shrunk, 0.30)
    assert track.theta_dot == 0.0
    track.update(None, 0.40)
    assert track.current == (0.0, 0.0)
    track.update(grown, 0.50)
    assert track.theta_dot == 0.0


def test_a_speck_is_not_a_disk() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[0, 0] = True
    assert measure_blue(mask) is None
