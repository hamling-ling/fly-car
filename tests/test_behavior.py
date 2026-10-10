"""Fixed-frame checks for the five desktop steps.

Run from the repository root:

    python3 -m pytest tests/test_behavior.py

Each test holds one pair of half-screen counts. The view does not move with
the car. Heading 0 faces +x, positive heading is left, and positive y is left.
"""

from __future__ import annotations

import pytest

from flycar.behavior import COUNT_FLOOR, Hold, hold, yaw_command

# Half-screen counts. The second number of each pair is the right half.
FRONT_RED = (0.45, 0.45)
RIGHT_RED = (0.05, 0.60)
LEFT_RED = (0.60, 0.05)
FULL_RED = (0.90, 0.90)
NO_RED = (0.0, 0.0)

FRONT_BLUE = (0.90, 0.90)
RIGHT_BLUE = (0.0, 0.90)
LEFT_BLUE = (0.90, 0.0)
NO_BLUE = (0.0, 0.0)


def show(red: tuple[float, float], blue: tuple[float, float]) -> Hold:
    return hold(red[0], red[1], blue[0], blue[1])


def assert_stopped(got: Hold) -> None:
    assert got.mode == "stop"
    assert got.x == pytest.approx(0.0, abs=1e-9)
    assert got.y == pytest.approx(0.0, abs=1e-9)
    assert got.heading == pytest.approx(0.0, abs=1e-9)
    assert got.v_left == pytest.approx(0.0, abs=1e-9)
    assert got.v_right == pytest.approx(0.0, abs=1e-9)


def assert_rolling(got: Hold) -> None:
    assert got.mode == "cruise"
    assert got.speed == pytest.approx(0.15)
    assert got.v_left > 0.02
    assert got.v_right > 0.02


def assert_spinning(got: Hold, turn: float) -> None:
    assert got.mode == "spin"
    assert got.x == pytest.approx(0.0, abs=1e-9)
    assert got.y == pytest.approx(0.0, abs=1e-9)
    assert turn * got.omega > 0.5
    assert turn * got.heading > 0.5
    assert got.v_left * got.v_right < 0


def assert_arc(got: Hold, turn: float) -> None:
    """turn > 0 is a left arc. Both wheels stay forward."""
    assert_rolling(got)
    assert turn * got.omega > 0.5
    assert turn * got.y > 0.05
    assert turn * got.heading > 0.5


class TestStep1:
    def test_front_red_keeps_heading(self) -> None:
        """正面の赤は、方位を保ったまま進む。"""
        got = show(FRONT_RED, NO_BLUE)
        assert_rolling(got)
        assert got.heading == pytest.approx(0.0, abs=1e-9)
        assert got.y == pytest.approx(0.0, abs=1e-9)
        assert got.x > 0.2
        assert got.omega == pytest.approx(0.0, abs=1e-9)

    def test_right_red_arcs_right(self) -> None:
        """右の赤は、両輪が前進のまま右へ弧を描く。"""
        assert_arc(show(RIGHT_RED, NO_BLUE), turn=-1.0)

    def test_left_red_arcs_left(self) -> None:
        """左の赤は、両輪が前進のまま左へ弧を描く。"""
        assert_arc(show(LEFT_RED, NO_BLUE), turn=1.0)

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

    def test_remaining_blue_keeps_the_yaw_when_red_is_absent(self) -> None:
        """赤が無いあいだは、0.72 未満の青でも DNp01 の差を使う。"""
        command, override = yaw_command(0.0, 0.0, 10.0, 40.0, 0.0, 0.50, 0.0, 0.0)
        assert override
        assert command == pytest.approx(10.0 - 40.0)

    def test_weak_blue_does_not_override_a_visible_red(self) -> None:
        """赤が写っているとき、0.72 未満の青は DNa02 を置き換えない。"""
        command, override = yaw_command(5.0, 20.0, 10.0, 40.0, 0.0, 0.50, 0.40, 0.0)
        assert not override
        assert command == pytest.approx(20.0 - 5.0)

    def test_red_at_the_floor_still_cruises(self) -> None:
        """床ちょうど以上の赤は、片方だけでも前進する。"""
        got = show((COUNT_FLOOR, 0.0), NO_BLUE)
        assert_rolling(got)
        assert got.omega == pytest.approx(0.0, abs=1e-9)


class TestStep2:
    def test_front_blue_stops_without_red(self) -> None:
        """赤が無いとき、正面の青で止まる。"""
        assert_stopped(show(NO_RED, FRONT_BLUE))

    def test_right_blue_spins_left(self) -> None:
        """赤が無いとき、右の青でその場で左へ回る。"""
        assert_spinning(show(NO_RED, RIGHT_BLUE), turn=1.0)

    def test_left_blue_spins_right(self) -> None:
        """赤が無いとき、左の青でその場で右へ回る。"""
        assert_spinning(show(NO_RED, LEFT_BLUE), turn=-1.0)


class TestStep3:
    def test_front_blue_stops_in_front_of_red(self) -> None:
        """正面に赤があるとき、正面の青で止まる。"""
        assert_stopped(show(FRONT_RED, FRONT_BLUE))

    def test_right_blue_dodges_left(self) -> None:
        """正面に赤があるとき、右の青を左に避けて進む。"""
        assert_arc(show(FRONT_RED, RIGHT_BLUE), turn=1.0)

    def test_left_blue_dodges_right(self) -> None:
        """正面に赤があるとき、左の青を右に避けて進む。"""
        assert_arc(show(FRONT_RED, LEFT_BLUE), turn=-1.0)


class TestStep4:
    def test_right_blue_overrides_right_red(self) -> None:
        """右に赤があるとき、右の青を左に避けて進む。"""
        alone = show(RIGHT_RED, NO_BLUE)
        got = show(RIGHT_RED, RIGHT_BLUE)
        assert_arc(got, turn=1.0)
        assert got.omega * alone.omega < 0

    def test_left_blue_dodges_right_past_right_red(self) -> None:
        """右に赤があるとき、左の青を右に避けて進む。"""
        assert_arc(show(RIGHT_RED, LEFT_BLUE), turn=-1.0)


class TestStep5:
    def test_left_blue_overrides_left_red(self) -> None:
        """左に赤があるとき、左の青を右に避けて進む。"""
        alone = show(LEFT_RED, NO_BLUE)
        got = show(LEFT_RED, LEFT_BLUE)
        assert_arc(got, turn=-1.0)
        assert got.omega * alone.omega < 0

    def test_right_blue_dodges_left_past_left_red(self) -> None:
        """左に赤があるとき、右の青を左に避けて進む。"""
        assert_arc(show(LEFT_RED, RIGHT_BLUE), turn=1.0)
