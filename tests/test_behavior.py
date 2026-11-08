"""Fixed-frame checks for the poster wheel law.

Run from the repository root:

    python3 -m pytest tests/test_behavior.py

Each test holds one pair of eye-range concentrations. The view does not
move with the car. Heading 0 faces +x, positive heading is left, and
positive y is left. A one-eyed red rolls both wheels, and the far wheel is faster.
"""

from __future__ import annotations

import numpy as np
import pytest

from flycar.behavior import (
    CATCH_UP_S,
    DT,
    FULL_RATE,
    HOLD_STEPS,
    MOVE_MPS,
    Plant,
    TRACK,
    TAU_RATE_S,
    Hold,
    catch_up_steps,
    YAW_CAP,
    KAPPA,
    dna_current,
    hold,
    prime_concentration,
    wheel_speeds,
)
from flycar.hinge import calibrated_command
from flycar.loom import Disk, cells
from flycar.pulse import REVERSE_START, wheel_pulses

# Eye-range concentrations. The second number of each pair is the right eye.
FRONT_RED = (0.45, 0.45)
RIGHT_RED = (0.02, 0.60)
LEFT_RED = (0.60, 0.02)
FULL_RED = (0.90, 0.90)
NO_RED = (0.0, 0.0)

FRONT_BLUE = (0.90, 0.90)
RIGHT_BLUE = (0.0, 0.90)
LEFT_BLUE = (0.90, 0.0)
NO_BLUE = (0.0, 0.0)


def _eye(center_u: float, radius_u: float) -> tuple[float, float]:
    disk = Disk(center_u, 0.5, radius_u, 0.60, float(np.deg2rad(40.0)))
    return cells().current(disk, 50.0)


LOOM_LEFT = _eye(0.25, 0.30)
LOOM_RIGHT = _eye(0.75, 0.30)
LOOM_BOTH = _eye(0.50, 0.55)


def show(
    red: tuple[float, float],
    blue: tuple[float, float] = NO_BLUE,
    loom: tuple[float, float] = (0.0, 0.0),
) -> Hold:
    return hold(red[0], red[1], blue[0], blue[1], loom=loom)


def assert_stopped(got: Hold) -> None:
    assert got.mode == "stop"
    assert got.x == pytest.approx(0.0, abs=1e-9)
    assert got.y == pytest.approx(0.0, abs=1e-9)
    assert got.heading == pytest.approx(0.0, abs=1e-9)
    assert got.v_left == pytest.approx(0.0, abs=1e-9)
    assert got.v_right == pytest.approx(0.0, abs=1e-9)


class TestRed:
    def test_front_red_crawls_straight(self) -> None:
        """左右がそろった赤は這って直進する。"""
        got = show(FRONT_RED, NO_BLUE)
        assert dna_current(*FRONT_RED) == pytest.approx((1.98, 1.98))
        assert got.mode == "cruise"
        assert got.heading == pytest.approx(0.0, abs=1e-6)
        assert got.y == pytest.approx(0.0, abs=1e-6)
        assert got.omega == pytest.approx(0.0, abs=1e-6)
        assert got.v_left > 0.02
        assert got.v_right > 0.02
        assert got.speed == pytest.approx(got.v_left)
        assert got.x > 0.02

    def test_a_held_paper_crawls_on_both_wheels(self) -> None:
        """手で持った赤紙は左右およそ 0.10 で、両輪が這う。"""
        paper = (0.09, 0.10)
        assert dna_current(*paper) == pytest.approx((1.3714285714285714, 1.5095238095238095))
        got = show(paper, NO_BLUE)
        assert got.mode == "cruise"
        assert got.v_left > got.v_right > 0.02
        assert got.x > 0.02

    def test_right_red_arcs_forward_on_both_wheels(self) -> None:
        """右の赤は両輪が前へ出て、左輪が速く、頭は右へ向く。"""
        got = show(RIGHT_RED, NO_BLUE)
        assert dna_current(*RIGHT_RED)[0] < 0.0
        assert dna_current(*RIGHT_RED)[1] > 1.0
        assert got.mode == "cruise"
        assert got.v_left > got.v_right > 0.02
        assert got.omega == pytest.approx(-YAW_CAP, abs=0.005)
        assert got.heading < -0.10
        assert got.x > 0.02
        assert got.y < 0.0

    def test_left_red_arcs_forward_on_both_wheels(self) -> None:
        """左の赤は両輪が前へ出て、右輪が速く、頭は左へ向く。"""
        got = show(LEFT_RED, NO_BLUE)
        assert got.mode == "cruise"
        assert got.v_right > got.v_left > 0.02
        assert got.omega == pytest.approx(YAW_CAP, abs=0.005)
        assert got.heading > 0.10
        assert got.x > 0.02
        assert got.y > 0.0

    def test_red_covering_both_ranges_stops(self) -> None:
        """赤が左右の範囲の大部分を覆うと止まる。"""
        assert_stopped(show(FULL_RED, NO_BLUE))


class TestQuiet:
    def test_nothing_in_view_stops(self) -> None:
        """何も写っていないときは止まる。"""
        assert_stopped(show(NO_RED, NO_BLUE))

    def test_a_weak_concentration_stays_under_threshold(self) -> None:
        """割合 0.01 は電流が閾値の下で、車輪は出ない。"""
        assert dna_current(0.01, 0.0)[0] < 1.0
        assert_stopped(show((0.01, 0.0), NO_BLUE))

    def test_a_small_patch_above_threshold_arcs_forward(self) -> None:
        """右の割合 0.02 は閾値を超え、両輪が前へ出て左輪が速い。"""
        assert dna_current(0.0, 0.02)[1] > 1.0
        got = show((0.0, 0.02), NO_BLUE)
        assert got.mode == "cruise"
        assert got.v_left > got.v_right > 0.0
        assert got.heading < 0.0


class TestWheels:
    def test_one_cell_on_the_right_rolls_both_wheels_forward(self) -> None:
        """右の細胞が不応期いっぱいに発火すると、左輪が速く、右輪も前へ出る。"""
        speed, omega, v_left, v_right = wheel_speeds(0.0, FULL_RATE, 0.0, 0.0, 0.0, 1.0)
        half = YAW_CAP * TRACK / 2.0
        assert v_left == pytest.approx(MOVE_MPS / 2.0 + half)
        assert v_right == pytest.approx(MOVE_MPS / 2.0 - half)
        assert speed == pytest.approx(MOVE_MPS / 2.0)
        assert omega == pytest.approx(-YAW_CAP)

    def test_the_same_fraction_is_stronger_at_the_edge(self) -> None:
        """同じ割合 0.10 でも、端では電流が大きく、無い側の割合は 0 のままである。"""
        center = dna_current(0.0, 0.10, 0.0)
        edge = dna_current(0.0, 0.10, 0.88)
        assert center[1] == pytest.approx(4.0 * (0.10 / 0.15))
        assert edge[1] > center[1]
        assert edge[0] < center[0] < 0.0
        primed_l, primed_r = prime_concentration(0.0, 0.10, 1.0)
        assert primed_l == 0.0
        assert primed_r == pytest.approx(0.10 * (1.0 + KAPPA))

    def test_edge_red_reaches_the_cap_and_the_hinge_keeps_a_turn(self) -> None:
        """右端の薄い赤は上限まで回り、補正のあとも左がおよそ 10 パルス勝つ。"""
        plain = wheel_speeds(0.0, 134.0, 0.0, 0.0, 0.0, 0.02, 0.0)
        edge = wheel_speeds(0.0, 134.0, 0.0, 0.0, 0.0, 0.02, 1.0)
        assert plain[1] > edge[1]
        assert edge[1] == pytest.approx(-YAW_CAP)
        raw = wheel_pulses(edge[2], edge[3])
        sent = calibrated_command(*raw)
        assert sent[1] - sent[0] >= 8
        assert sent[0] > 0
        centered = wheel_speeds(118.0, 116.0, 0.0, 0.0, 0.13, 0.14, 0.10)
        assert abs(centered[1]) < YAW_CAP / 2

    def test_a_saturated_pair_still_yaws_toward_the_heavier_eye(self) -> None:
        """両方が不応期付近でも、右の割合が大きければ右へ回る。"""
        speed, omega, v_left, v_right = wheel_speeds(121.0, 146.0, 0.0, 0.0, 0.33, 0.54)
        assert v_left > v_right > 0.02
        assert omega == pytest.approx(-YAW_CAP)
        assert speed == pytest.approx(0.5 * (121.0 + 146.0) / FULL_RATE * MOVE_MPS)

    def test_the_filter_lags_one_step(self) -> None:
        """20 ms では車輪が指令に追いつかず、落ち着いたあとに後退する。"""
        plant = Plant()
        early = plant.step(0.0, 0.0, 0.0, 0.0, loom=(4.0, 4.0))
        for _ in range(19):
            early = plant.step(0.0, 0.0, 0.0, 0.0, loom=(4.0, 4.0))
        late = hold(0.0, 0.0, 0.0, 0.0, seconds=0.8, settle=0.5, loom=(4.0, 4.0))
        assert abs(early.v_left) < abs(late.v_left) * 0.5
        assert late.mode == "back"
        assert late.v_left == pytest.approx(late.v_right)
        assert late.v_left < -0.05
        assert late.heading == pytest.approx(0.0, abs=1e-6)


class TestEscape:
    def test_blue_fill_alone_does_not_move(self) -> None:
        """青の割合だけでは動かない。拡大が無いからである。"""
        assert_stopped(show(NO_RED, FRONT_BLUE))
        assert_stopped(show(NO_RED, RIGHT_BLUE))
        assert_stopped(show(NO_RED, LEFT_BLUE))

    def test_looming_on_both_sides_backs_up(self) -> None:
        """左右の DNp01 が発火すると、方位を保って下がる。"""
        got = show(NO_RED, loom=LOOM_BOTH)
        sent = calibrated_command(*wheel_pulses(got.v_left, got.v_right))
        assert got.mode == "back"
        assert got.heading == pytest.approx(0.0, abs=1e-6)
        assert got.y == pytest.approx(0.0, abs=1e-6)
        assert got.omega == pytest.approx(0.0, abs=1e-6)
        assert got.v_left < -0.05
        assert got.v_right < -0.05
        assert sent[0] <= -REVERSE_START
        assert sent[1] <= -REVERSE_START

    def test_right_loom_reverses_only_the_left_wheel(self) -> None:
        """右の DNp01 は左輪だけを後退させ、右輪は止まる。"""
        got = show(NO_RED, loom=LOOM_RIGHT)
        assert got.mode == "back"
        assert got.v_left < -0.05
        assert got.v_right == pytest.approx(0.0, abs=1e-6)
        assert got.omega > 0.5
        assert got.heading > 0.5

    def test_left_loom_reverses_only_the_right_wheel(self) -> None:
        """左の DNp01 は右輪だけを後退させ、左輪は止まる。"""
        got = show(NO_RED, loom=LOOM_LEFT)
        assert got.mode == "back"
        assert got.v_right < -0.05
        assert got.v_left == pytest.approx(0.0, abs=1e-6)
        assert got.omega < -0.5
        assert got.heading < -0.5


class TestTogether:
    def test_blue_fill_does_not_slow_a_front_red(self) -> None:
        """止まった青の割合は、正面の赤の速さを変えない。"""
        alone = show(FRONT_RED)
        got = show(FRONT_RED, FRONT_BLUE)
        assert got.speed == pytest.approx(alone.speed)
        assert got.heading == pytest.approx(alone.heading, abs=1e-9)
        assert got.mode == "cruise"

    def test_bilateral_loom_reverses_both_wheels_and_keeps_heading(self) -> None:
        """左右の DNp01 は両輪から同じだけ引き、方位は残る。"""
        alone = show(FRONT_RED)
        got = show(FRONT_RED, loom=LOOM_BOTH)
        assert got.mode == "back"
        assert got.heading == pytest.approx(0.0, abs=1e-6)
        assert got.omega == pytest.approx(0.0, abs=1e-6)
        assert got.v_left == pytest.approx(got.v_right)
        assert got.v_left < 0.0
        assert got.speed < alone.speed

    def test_right_loom_spins_away_from_a_front_red(self) -> None:
        """正面の赤に右の loom が重なると、左輪が後退して左へ回る。"""
        got = show(FRONT_RED, loom=LOOM_RIGHT)
        assert got.mode == "spin"
        assert got.v_left < 0.0
        assert got.v_right > 0.0
        assert got.omega > 0.5

    def test_right_loom_overcomes_a_right_red(self) -> None:
        """同じ側の loom が片側の赤を上回ると、左輪が後退して左へ回る。"""
        alone = show(RIGHT_RED)
        got = show(RIGHT_RED, loom=LOOM_RIGHT)
        assert alone.omega < 0.0
        assert got.omega > 0.0
        assert got.v_left < 0.0
        assert got.v_right > 0.0

    def test_left_loom_adds_to_a_right_red(self) -> None:
        """右の赤と左の DNp01 は同じ向きに回り、右輪が後退する。"""
        alone = show(RIGHT_RED)
        got = show(RIGHT_RED, loom=LOOM_LEFT)
        assert got.omega < alone.omega
        assert got.v_right < 0.0
        assert got.v_left > 0.0
        assert got.mode == "spin"


class TestSteps:
    def test_window_matches_the_last_one_millisecond_step(self) -> None:
        """The 20 ms window reads the same final wheels as twenty single steps."""
        single = Plant()
        last = single.step(*FRONT_RED, *NO_BLUE)
        for _ in range(HOLD_STEPS - 1):
            last = single.step(*FRONT_RED, *NO_BLUE)
        window = Plant().steps(*FRONT_RED, *NO_BLUE, n=HOLD_STEPS)
        assert window.v_left == pytest.approx(last.v_left)
        assert window.v_right == pytest.approx(last.v_right)
        assert window.speed == pytest.approx(last.speed)
        assert window.omega == pytest.approx(last.omega)
        assert window.mode == last.mode
        assert window.x == pytest.approx(last.x)
        assert window.heading == pytest.approx(last.heading)

    def test_full_red_stays_stopped(self) -> None:
        got = Plant().steps(*FULL_RED, *NO_BLUE, n=HOLD_STEPS)
        assert got.mode == "stop"
        assert got.v_left == pytest.approx(0.0, abs=1e-9)
        assert got.v_right == pytest.approx(0.0, abs=1e-9)
        assert got.x == pytest.approx(0.0, abs=1e-9)

    def test_rejects_an_empty_window(self) -> None:
        with pytest.raises(ValueError):
            Plant().steps(*NO_RED, *NO_BLUE, n=0)


def test_catch_up_follows_the_gap_and_stops_at_the_cap() -> None:
    """定刻は 20 ステップ、開いた時間はそのミリ秒、0.70 秒を超えては進まない。"""
    assert CATCH_UP_S == pytest.approx(0.70)
    assert catch_up_steps(0.02) == HOLD_STEPS
    assert catch_up_steps(0.001) == HOLD_STEPS
    assert catch_up_steps(-1.0) == HOLD_STEPS
    assert catch_up_steps(0.10) == 100
    assert catch_up_steps(0.70) == 700
    assert catch_up_steps(5.0) == 700


def test_a_quiet_catch_up_drops_a_full_reverse_to_a_zero_pulse() -> None:
    """全速の後退は、電流が消えた 0.70 秒で送出パルス 0 まで落ちる。"""
    plant = Plant()
    driven = plant.steps(0.0, 0.0, 0.0, 0.0, n=catch_up_steps(CATCH_UP_S), loom=(4.0, 4.0))
    moving = calibrated_command(*wheel_pulses(driven.v_left, driven.v_right))
    assert moving[0] < 0
    assert moving[1] < 0
    quiet = plant.steps(0.0, 0.0, 0.0, 0.0, n=catch_up_steps(CATCH_UP_S), loom=(0.0, 0.0))
    assert calibrated_command(*wheel_pulses(quiet.v_left, quiet.v_right)) == (0, 0)


def test_one_camera_sample_of_moderate_loom_clears_the_reverse_floor() -> None:
    """右の電流 1.22 は 0.1 秒以内に、左輪の後退が床を超える。"""
    assert TAU_RATE_S == pytest.approx(0.05)
    plant = Plant()
    cleared = None
    n = int(round(0.10 / DT))
    for i in range(n):
        step = plant.step(0.0, 0.0, 0.0, 0.0, loom=(0.0, 1.22))
        sent = calibrated_command(*wheel_pulses(step.v_left, step.v_right))
        if sent[1] <= -REVERSE_START:
            cleared = (i + 1) * DT
            break
    assert cleared is not None
    assert cleared <= 0.10


def test_an_omitted_window_follows_the_wall_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """回数を省くと、前回からの経過ぶん膜が進む。0.40 秒の強い電流は後退パルスになる。"""
    clock = {"t": 0.0}
    monkeypatch.setattr("flycar.behavior.time.monotonic", lambda: clock["t"])
    plant = Plant()
    clock["t"] = 0.001
    plant.steps(0.0, 0.0, 0.0, 0.0, loom=(4.0, 4.0))
    assert plant.gf_l.rate < 80.0
    clock["t"] = 0.401
    caught = plant.steps(0.0, 0.0, 0.0, 0.0, loom=(4.0, 4.0))
    assert plant.gf_l.rate > 100.0
    sent = calibrated_command(*wheel_pulses(caught.v_left, caught.v_right))
    assert sent[0] <= -REVERSE_START
    assert sent[1] <= -REVERSE_START
    clock["t"] = 1.101
    quiet = plant.steps(0.0, 0.0, 0.0, 0.0, loom=(0.0, 0.0))
    assert calibrated_command(*wheel_pulses(quiet.v_left, quiet.v_right)) == (0, 0)


def test_mean_ms_averages_steps_then_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((0.0, 0.0, 0.002, 1.0, 1.004))
    monkeypatch.setattr("flycar.behavior.time.monotonic", lambda: next(clock))
    plant = Plant()
    plant.steps(0.0, 0.0, 0.0, 0.0, n=HOLD_STEPS)
    plant.steps(0.0, 0.0, 0.0, 0.0, n=HOLD_STEPS)
    assert plant.mean_ms() == pytest.approx(3.0)
    assert plant.mean_ms() == 0.0
