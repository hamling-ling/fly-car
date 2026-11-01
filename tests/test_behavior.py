"""Fixed-frame checks for the five desktop steps.

Run from the repository root:

    python3 -m pytest tests/test_behavior.py

Each test holds one pair of half-screen counts. The view does not move with
the car. Heading 0 faces +x, positive heading is left, and positive y is left.
"""

from __future__ import annotations

import numpy as np
import pytest

from flycar.behavior import (
    BLUE_FORWARD,
    BLUE_YAW,
    COUNT_FLOOR,
    DT,
    FORWARD_PER_HZ,
    HOLD_STEPS,
    Hold,
    Plant,
    RED_RADIUS,
    RED_YAW,
    TAU_RATE_S,
    YAW_PER_HZ,
    hold,
    speed_and_yaw,
)
from flycar.hinge import calibrated_command
from flycar.loom import Disk, cells
from flycar.pulse import REVERSE_START, wheel_pulses

# Half-screen counts. The second number of each pair is the right half.
FRONT_RED = (0.45, 0.45)
RIGHT_RED = (0.02, 0.60)
LEFT_RED = (0.60, 0.02)
FULL_RED = (0.90, 0.90)
NO_RED = (0.0, 0.0)

FRONT_BLUE = (0.90, 0.90)
RIGHT_BLUE = (0.0, 0.90)
LEFT_BLUE = (0.90, 0.0)
NO_BLUE = (0.0, 0.0)


# A 40° disk and a fast expansion. This is the top of the hand-set sigmoid
# with the LC4 term multiplied by 5. One eye is well above 2.
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


def assert_rolling(got: Hold) -> None:
    assert got.mode == "cruise"
    assert got.speed > 0.02
    assert got.v_left > 0.02
    assert got.v_right > 0.02


def assert_spinning(got: Hold, turn: float) -> None:
    """片側の青は回りながら少し下がる。

    1.5 秒では方位が一周して出発点の近くに戻るので、終わりの方位では向きを見ない。
    """
    assert got.mode == "spin"
    assert turn * got.omega > 2.0
    assert turn * (got.v_right - got.v_left) > 0.0
    assert got.v_left * got.v_right < 0
    assert got.speed < -0.02
    assert abs(got.x) < 0.02
    assert abs(got.y) < 0.02


def assert_arc(got: Hold, turn: float) -> None:
    """turn > 0 is a left arc. Both wheels stay forward.

    The red-only radius is RED_RADIUS. The gates sit under that arc and
    under the sharper blue dodge.
    """
    assert_rolling(got)
    assert turn * got.omega > 0.05
    assert turn * got.y > 0.005
    assert turn * got.heading > 0.1


class TestStep1:
    def test_front_red_keeps_heading(self) -> None:
        """正面の赤は、方位を保ったまま進む。"""
        got = show(FRONT_RED, NO_BLUE)
        assert_rolling(got)
        assert got.heading == pytest.approx(0.0, abs=1e-9)
        assert got.y == pytest.approx(0.0, abs=1e-9)
        assert got.x > 0.2
        assert got.speed == pytest.approx(0.24, abs=0.01)
        assert got.omega == pytest.approx(0.0, abs=1e-9)

    def test_right_red_arcs_right(self) -> None:
        """右の赤は、両輪が前進のまま右へ弧を描く。"""
        assert_arc(show(RIGHT_RED, NO_BLUE), turn=-1.0)

    def test_left_red_arcs_left(self) -> None:
        """左の赤は、両輪が前進のまま左へ弧を描く。"""
        assert_arc(show(LEFT_RED, NO_BLUE), turn=1.0)

    def test_one_red_cell_turns_inside_a_room(self) -> None:
        """片側の赤だけの回転半径は 20 cm。両輪は前を向いたまま。"""
        got = show(LEFT_RED, NO_BLUE)
        assert got.speed / abs(got.omega) == pytest.approx(RED_RADIUS, abs=0.02)

    def test_red_covering_the_view_stops(self) -> None:
        """赤が左右の画面の大部分を覆うと止まる。"""
        assert_stopped(show(FULL_RED, NO_BLUE))


class TestNothing:
    def test_nothing_in_view_stops(self) -> None:
        """何も写っていないときは止まる。"""
        assert_stopped(show(NO_RED, NO_BLUE))

    def test_counts_below_the_floor_stop(self) -> None:
        """COUNT_FLOOR 未満は空とみなして止まる。"""
        faint = (COUNT_FLOOR - 0.01, 0.0)
        assert_stopped(show(faint, faint))

    def test_rates_from_both_pathways_add(self) -> None:
        """前後は赤の和から青の和の BLUE_FORWARD 倍を引き、ヨーは重み付きの差を足す。"""
        speed, omega = speed_and_yaw(5.0, 20.0, 10.0, 40.0)
        forward = (5.0 + 20.0) - BLUE_FORWARD * (10.0 + 40.0)
        yaw = RED_YAW * (5.0 - 20.0) + BLUE_YAW * (40.0 - 10.0)
        assert speed == pytest.approx(forward * FORWARD_PER_HZ)
        assert omega == pytest.approx(yaw * YAW_PER_HZ)

    def test_red_sum_keeps_forward_against_a_smaller_blue(self) -> None:
        """青の重み付き和が赤の和より小さいと、前進が残る。"""
        speed, omega = speed_and_yaw(80.0, 80.0, 0.0, 40.0)
        assert speed == pytest.approx((160.0 - BLUE_FORWARD * 40.0) * FORWARD_PER_HZ)
        assert omega == pytest.approx(BLUE_YAW * 40.0 * YAW_PER_HZ)

    def test_red_at_the_floor_does_not_fire(self) -> None:
        """床ちょうどは電流 1 で、スパイクせず止まる。"""
        assert_stopped(show((COUNT_FLOOR, 0.0), NO_BLUE))

    def test_a_small_patch_above_the_floor_drives(self) -> None:
        """床の少し上の赤でも車輪が回る。"""
        got = show((COUNT_FLOOR + 0.02, 0.0), NO_BLUE)
        assert got.mode == "cruise"
        assert got.v_left > 0.0
        assert got.v_right > 0.0


class TestStep2:
    def test_blue_fill_alone_does_not_move(self) -> None:
        """青の占有だけでは動かない。拡大が無いからである。"""
        assert_stopped(show(NO_RED, FRONT_BLUE))
        assert_stopped(show(NO_RED, RIGHT_BLUE))
        assert_stopped(show(NO_RED, LEFT_BLUE))

    def test_looming_on_both_sides_backs_up(self) -> None:
        """左右の DNp01 が発火すると、方位を保って下がる。"""
        got = show(NO_RED, loom=LOOM_BOTH)
        assert got.mode == "back"
        assert got.heading == pytest.approx(0.0, abs=1e-6)
        assert got.y == pytest.approx(0.0, abs=1e-6)
        assert got.x < -0.04
        assert got.omega == pytest.approx(0.0, abs=1e-6)
        assert got.v_left < -0.03
        assert got.v_right < -0.03

    def test_right_loom_spins_left(self) -> None:
        """赤が無いとき、右の DNp01 で下がりながら左へ回る。"""
        assert_spinning(show(NO_RED, loom=LOOM_RIGHT), turn=1.0)

    def test_left_loom_spins_right(self) -> None:
        """赤が無いとき、左の DNp01 で下がりながら右へ回る。"""
        assert_spinning(show(NO_RED, loom=LOOM_LEFT), turn=-1.0)

    def test_bilateral_loom_clears_the_reverse_floor(self) -> None:
        """左右の DNp01 が頭打ちのとき、送る両輪が後退の下限を超える。"""
        got = show(NO_RED, loom=LOOM_BOTH)
        sent = calibrated_command(*wheel_pulses(got.v_left, got.v_right))
        assert got.mode == "back"
        assert sent[0] <= -REVERSE_START
        assert sent[1] <= -REVERSE_START


class TestStep3:
    def test_blue_fill_does_not_slow_a_front_red(self) -> None:
        """止まった青の占有は、正面の赤の速さを変えない。"""
        alone = show(FRONT_RED)
        got = show(FRONT_RED, FRONT_BLUE)
        assert got.speed == pytest.approx(alone.speed)
        assert got.heading == pytest.approx(alone.heading, abs=1e-9)
        assert got.mode == "cruise"

    def test_bilateral_loom_slows_a_stronger_front_red(self) -> None:
        """左右の DNp01 は正面の赤を削る。赤の和が勝ち、直進が残る。"""
        alone = show(FRONT_RED)
        got = show(FRONT_RED, loom=LOOM_BOTH)
        assert got.mode == "cruise"
        assert got.heading == pytest.approx(0.0, abs=1e-6)
        assert got.y == pytest.approx(0.0, abs=1e-6)
        assert 0.02 < got.speed < alone.speed

    def test_right_loom_dodges_left(self) -> None:
        """正面の赤に右の速い loom が重なると、左輪が後退して大きく左へ回る。"""
        got = show(FRONT_RED, loom=LOOM_RIGHT)
        assert got.speed > 0.1
        assert got.omega > 2.0
        assert got.v_left < 0.0
        assert got.v_right > 0.2

    def test_left_loom_dodges_right(self) -> None:
        """正面の赤に左の速い loom が重なると、右輪が後退して大きく右へ回る。"""
        got = show(FRONT_RED, loom=LOOM_LEFT)
        assert got.speed > 0.1
        assert got.omega < -2.0
        assert got.v_right < 0.0
        assert got.v_left > 0.2


class TestStep4:
    def test_right_loom_out_turns_a_right_red(self) -> None:
        """片側の赤を、同じ側の速い loom が上回って左へ回る。内側の左輪は後退する。"""
        alone = show(RIGHT_RED)
        got = show(RIGHT_RED, loom=LOOM_RIGHT)
        assert got.mode == "cruise"
        assert alone.omega < -0.5
        assert got.omega > 2.0
        assert got.speed < alone.speed
        assert got.v_left < 0.0
        assert got.v_right > 0.2

    def test_left_loom_adds_to_a_right_red(self) -> None:
        """右の赤と左の DNp01 は同じ向きのヨーなので、赤だけのときより強く回る。"""
        alone = show(RIGHT_RED)
        got = show(RIGHT_RED, loom=LOOM_LEFT)
        assert got.omega < alone.omega - 0.5
        assert got.speed < alone.speed


class TestStep5:
    def test_left_loom_out_turns_a_left_red(self) -> None:
        """片側の赤を、同じ側の速い loom が上回って右へ回る。内側の右輪は後退する。"""
        alone = show(LEFT_RED)
        got = show(LEFT_RED, loom=LOOM_LEFT)
        assert got.mode == "cruise"
        assert alone.omega > 0.5
        assert got.omega < -2.0
        assert got.speed < alone.speed
        assert got.v_right < 0.0
        assert got.v_left > 0.2

    def test_right_loom_adds_to_a_left_red(self) -> None:
        """左の赤と右の DNp01 は同じ向きのヨーなので、赤だけのときより強く回る。"""
        alone = show(LEFT_RED)
        got = show(LEFT_RED, loom=LOOM_RIGHT)
        assert got.omega > alone.omega + 0.5
        assert got.speed < alone.speed


class TestSteps:
    def test_window_matches_the_last_one_millisecond_step(self) -> None:
        """The 20 ms window reads the same final rates as twenty single steps."""
        single = Plant()
        last = single.step(*FRONT_RED, *NO_BLUE)
        for _ in range(HOLD_STEPS - 1):
            last = single.step(*FRONT_RED, *NO_BLUE)
        window = Plant().steps(*FRONT_RED, *NO_BLUE)
        assert window.v_left == pytest.approx(last.v_left)
        assert window.v_right == pytest.approx(last.v_right)
        assert window.speed == pytest.approx(last.speed)
        assert window.omega == pytest.approx(last.omega)
        assert window.mode == last.mode

    def test_full_red_stays_stopped(self) -> None:
        got = Plant().steps(*FULL_RED, *NO_BLUE)
        assert got.mode == "stop"
        assert got.v_left == pytest.approx(0.0, abs=1e-9)
        assert got.v_right == pytest.approx(0.0, abs=1e-9)
        assert got.x == pytest.approx(0.0, abs=1e-9)

    def test_rejects_an_empty_window(self) -> None:
        with pytest.raises(ValueError):
            Plant().steps(*NO_RED, *NO_BLUE, n=0)


def test_one_camera_sample_of_moderate_loom_clears_the_reverse_floor() -> None:
    """右の電流 1.22 は 0.1 秒以内に、左輪の後退が床を超える。"""
    assert TAU_RATE_S == pytest.approx(0.05)
    assert BLUE_YAW == pytest.approx(18.0)
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


def test_mean_ms_averages_steps_then_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((0.0, 0.002, 1.0, 1.004))
    monkeypatch.setattr("flycar.behavior.time.monotonic", lambda: next(clock))
    plant = Plant()
    plant.steps(0.0, 0.0, 0.0, 0.0)
    plant.steps(0.0, 0.0, 0.0, 0.0)
    assert plant.mean_ms() == pytest.approx(3.0)
    assert plant.mean_ms() == 0.0
