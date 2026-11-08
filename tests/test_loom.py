"""Angular size, expansion, and the DNp01 current.

Run from the repository root:

    python3 -m pytest tests/test_loom.py
"""

from __future__ import annotations

import numpy as np
import pytest

from flycar.behavior import hold
from flycar.loom import (
    ALPHA,
    BLUE_MIN_FRACTION,
    CELLS_PATH,
    EXPANSION_FLOOR,
    K_S,
    SIGMOID_MID,
    SIGMOID_WIDTH,
    Disk,
    LoomTrack,
    camera_tangents,
    cells,
    expansion,
    measure_blue,
    size_term,
)
from flycar.occupancy import Counts


def _disk(theta_deg: float, cu: float) -> Disk:
    """Equal-area disk of ``theta_deg`` centered at image ``cu``."""
    tan_h, tan_v = camera_tangents()
    theta = float(np.deg2rad(theta_deg))
    cx = (cu * 2.0 - 1.0) * tan_h
    rod = float(np.tan(theta / 2.0) * np.sqrt(1.0 + cx * cx))
    return Disk(cu, 0.5, rod / tan_h / 2.0, rod / tan_v / 2.0, theta)


def test_sigmoid_is_the_poster_logistic() -> None:
    """中心 0.20 rad/s、幅 0.10 rad/s。停止は約 0.12 で、0.4 rad/s は 1 に近い。"""
    assert (K_S, SIGMOID_MID, SIGMOID_WIDTH) == (1.0, 0.20, 0.10)
    assert ALPHA == pytest.approx(4.0)
    assert expansion(0.0) == pytest.approx(0.1192, abs=1e-3)
    assert expansion(0.4) > 0.8
    assert expansion(0.0) < 0.2
    assert size_term(np.deg2rad(10.0), 0.4) == 1.0
    assert size_term(np.deg2rad(40.0), 0.4) == 1.0
    assert size_term(np.deg2rad(40.0), 0.0) == 0.0


def test_shipped_table_has_the_notebook_synapse_totals() -> None:
    assert CELLS_PATH.is_file()
    pack = cells()
    assert pack.lc4.side.size == 126
    assert pack.lplc2.side.size == 185
    assert pack.side_ref[0] == pytest.approx(6424.0)
    assert pack.side_ref[1] == pytest.approx(4800.0)


def test_a_stopped_sheet_filling_the_frame_stays_under_threshold() -> None:
    """画面を覆う止まった青は、視角の項が 0 なので閾値を超えない。"""
    disk = measure_blue(np.ones((72, 128), dtype=bool))
    assert disk is not None
    loom = cells().current(disk, 0.0)
    assert max(loom) < 1.0
    got = hold(0.0, 0.0, 1.0, 1.0, seconds=0.8, settle=0.3, loom=loom)
    assert got.mode == "stop"
    assert got.x == pytest.approx(0.0, abs=1e-9)
    assert got.heading == pytest.approx(0.0, abs=1e-9)


def test_jitter_below_the_expansion_floor_stays_under_threshold() -> None:
    """0.04 rad/s の視角の揺れはサイズ項を付けず、0.4 rad/s は発火する。"""
    disk = _disk(30.0, 0.50)
    assert EXPANSION_FLOOR == pytest.approx(0.10)
    quiet = cells().current(disk, 0.04)
    fired = cells().current(disk, 0.4)
    assert max(quiet) < 1.0
    assert min(fired) > 1.0
    assert size_term(disk.theta, 0.04) == 0.0
    assert size_term(disk.theta, EXPANSION_FLOOR) == 1.0


def test_an_expanding_frontal_disk_backs_both_wheels() -> None:
    """正面の 30° が 0.4 rad/s で広がると、左右とも閾値を超えて両輪が下がる。"""
    loom = cells().current(_disk(30.0, 0.50), 0.4)
    assert min(loom) > 1.0
    assert min(loom) / max(loom) > 0.9
    got = hold(0.0, 0.0, 0.0, 0.0, seconds=0.8, settle=0.3, loom=loom)
    assert got.mode == "back"
    assert got.v_left < -0.05
    assert got.v_right < -0.05
    assert got.heading == pytest.approx(0.0, abs=1e-3)
    assert got.omega == pytest.approx(0.0, abs=1e-3)


def test_twenty_degrees_on_the_right_reverses_the_far_wheel() -> None:
    """右の 20° は 0.4 rad/s で右だけが閾値を超え、左輪だけが下がる。停止では超えない。"""
    disk = _disk(20.0, 0.75)
    approach = cells().current(disk, 0.4)
    still = cells().current(disk, 0.0)
    assert approach[1] > 1.0
    assert approach[0] < 1.0
    assert max(still) < 1.0
    stopped = hold(0.0, 0.0, 0.0, 0.9, loom=still)
    assert stopped.mode == "stop"
    moved = hold(0.0, 0.0, 0.0, 0.0, seconds=0.8, settle=0.3, loom=approach)
    assert moved.mode == "back"
    assert moved.v_left < moved.v_right
    assert moved.v_left < -0.05
    assert moved.v_right == pytest.approx(0.0, abs=1e-4)
    assert moved.omega > 0.3
    assert moved.heading > 0.3


def test_a_disk_near_the_middle_drives_both_eyes() -> None:
    """重なりがあるので、中央付近の円は左右の両方に入る。"""
    left, right = cells().current(_disk(30.0, 0.50), 0.4)
    assert left > 1.0
    assert right > 1.0


def test_a_small_disk_on_the_right_leaves_the_left_quiet() -> None:
    """右に寄った小さい円は、左の電流を出さない。"""
    left, right = cells().current(
        Disk(0.75, 0.5, 0.12, 0.25, theta=float(np.deg2rad(40.0))),
        20.0,
    )
    assert left == pytest.approx(0.0, abs=1e-6)
    assert right > 1.0


def test_a_degree_off_center_yaws_while_both_wheels_reverse() -> None:
    """中心から約 1° ずらした 22° は両輪が下がり、帯が無いので少し回る。"""
    loom = cells().current(_disk(22.0, 0.48), 0.4)
    assert min(loom) > 1.0
    got = hold(0.0, 0.0, 0.0, 0.0, seconds=0.8, settle=0.3, loom=loom)
    assert got.mode == "back"
    assert got.v_left < 0.0
    assert got.v_right < 0.0
    assert abs(got.omega) > 0.05
    assert abs(got.heading) < 0.5


def test_a_slightly_right_sheet_backs_and_yaws() -> None:
    """右寄りの紙は右の電流が強く、左輪がより強く下がる。"""
    mask = np.zeros((180, 320), dtype=bool)
    mask[:, int(np.floor(0.42 * 320)) : int(np.ceil(0.80 * 320))] = True
    disk = measure_blue(mask)
    assert disk is not None
    left, right = cells().current(disk, 0.9, mask)
    assert right > left > 1.0
    got = hold(0.0, 0.0, 0.0, 0.0, seconds=0.8, settle=0.3, loom=(left, right))
    assert got.mode == "back"
    assert got.v_left < got.v_right < 0.0
    assert got.omega > 0.0


def test_a_right_hand_sheet_keeps_one_eye() -> None:
    """真ん中をまたがない右の紙は、左の電流を出さない。"""
    mask = np.zeros((180, 320), dtype=bool)
    mask[:, int(np.floor(0.62 * 320)) : int(np.ceil(0.90 * 320))] = True
    disk = measure_blue(mask)
    assert disk is not None
    left, right = cells().current(disk, 0.9, mask)
    assert left == pytest.approx(0.0, abs=1e-6)
    assert right > 1.0


def test_counts_pass_the_mask_into_the_current() -> None:
    """青の画素は、円ではなくそのマスクの列の割合として電流になる。"""
    height, width = 180, 320
    mask = np.zeros((height, width), dtype=bool)
    mask[45:135, 108:256] = True
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    counts = Counts()
    frame[mask] = (255, 0, 0)
    assert counts.update(frame, now=0.0)
    grown = mask.copy()
    grown[40:140, 100:260] = True
    frame[:] = 0
    frame[grown] = (255, 0, 0)
    assert counts.update(frame, now=0.10)
    disk = measure_blue(grown)
    assert disk is not None
    assert counts.theta_dot > 0.0
    assert counts.loom == pytest.approx(cells().current(disk, counts.theta_dot, grown))
    assert max(counts.loom) > 1.0


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
    track.update(Disk(0.75, 0.5, 0.08, 0.14, theta=0.30), 0.30)
    assert track.theta_dot == 0.0
    track.update(None, 0.40)
    assert track.current == (0.0, 0.0)
    track.update(grown, 0.50)
    assert track.theta_dot == 0.0


def test_a_speck_is_not_a_disk() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[0, 0] = True
    assert measure_blue(mask) is None
