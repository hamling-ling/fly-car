"""Red concentration and a loom current to two wheel speeds.

Red runs from 0 to 1 and is the filled fraction of one eye's range. The
ranges overlap: the left reads the image from the left edge through 0.65,
and the right reads from 0.35 through the right edge. That fraction
saturates in a PN. Each DNa02 keeps the ipsilateral PN and subtracts
``BETA`` times the other side. A negative result pulls the membrane down
and does not spike.

DNp01 does not read the red fraction. Its current is computed by
``flycar.loom`` from the blue columns, then passed in as ``loom``. A blue
fill with no loom current does not fire.

A red centroid toward an image edge multiplies both eye fractions by
``1 + KAPPA * |place|`` before the PN. The empty eye stays at 0. At the
center the factor is 1, so the fractions pass through. The wheels do not
read the centroid or the concentrations. The left wheel is ``k`` times the
right DNa02 rate minus the right DNp01 rate, and the right wheel swaps the
sides. ``k`` is ``FORWARD_PER_HZ``. DNa02 drives forward and DNp01 drives
reverse. One side firing alone stops the near wheel, so the turning radius
stays at least half the track. Equal rates stay straight. ``MOVE_MPS`` is
the speed of one cell at its refractory rate. A paper held in front fills
about 0.10 of each eye. ``BETA`` of 0.45 puts both of those currents just
over threshold, so the paper crawls. A speck of 0.01 at the center stays
under. The same speck at an edge is scaled with the other fractions.
``poster/draw_fig5.py`` keeps 0.70 for the DNa02 current. Its approach
wheels call ``wheel_speeds``.

``Plant`` smooths each wheel with time constant ``TAU_V``. ``wheel_speeds``
itself is the instantaneous command, so a formula check does not depend on
filter state. After the filter, ``limit_rotation`` keeps the mean speed and
shrinks a yaw past ``OMEGA_SAFE``. Ordinary one-sided red stays under that
cap. ``catch_up_steps`` turns a late camera tick into milliseconds of
membrane time, and stops at ``CATCH_UP_S`` so one noisy frame cannot run
the filter for seconds.

The safety stop overrides the cap. When both eye ranges are at least
``RED_FILL``, both wheels drop to rest on that update even though DNa02 is
firing. A red that fills only one range still drives.

``blue_yaw_scale`` is still computed for the log. The wheels do not read it.
``COUNT_FLOOR`` is the small-patch mark used by the color-threshold script
and the face lamps. The membrane does not apply it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

# Membrane time constants match research/notebooks/chemotaxis_sim.ipynb.
TAU_MS = 5.0
V_THRESHOLD = 1.0
REFRAC_MS = 5.0
DT = 0.001
# One camera command. fov.simulate still calls step() this many times.
HOLD_STEPS = 20
# 50 ms, not the notebook's 100 ms. Expansion is sampled every 0.1 s and
# often falls to 0 on the repeated camera frame. The shorter filter lets
# that sample reach the wheel floor. Hand-set, not a fit.
TAU_RATE_S = 0.050
TRACK = 0.12

# Safety stop. Both eye-range fractions at or above this hold the wheels.
RED_FILL = 0.75
# Small-patch mark for the color script and the face lamps. The membrane
# does not treat a fraction below this as empty.
COUNT_FLOOR = 0.04

# n and c0 are the PN saturation. ALPHA matches the poster figures. BETA is
# the live contralateral coefficient: a paper held in front fills about
# 0.10 of each eye, 0.70 leaves that pair under threshold, and 0.45 puts
# both currents just over 1. A 0.01 speck at the center stays under. The
# same speck at an edge is scaled with the other fractions.
# poster/draw_fig5.py keeps 0.70 for the DNa02 current. One cell at the
# refractory rate is a wheel command of ±MOVE_MPS. FORWARD_PER_HZ is the
# poster's k in equations (17) and (18). 0.0009 m/s per hertz is 1.5 times
# the previous 0.0006, so MOVE_MPS is 0.15.
N_ORN = 1.0
C0 = 0.05
ALPHA = 4.0
BETA = 0.45
# ``place`` is -1 at the left edge and +1 at the right edge, the poster's
# p-hat. Both fractions are multiplied by 1 + KAPPA * |place| before the PN.
# That is poster equation (5). The number stays out of poster.md. An empty
# frame has place 0 so the factor is 1. The wheels read firing rates, so
# this factor reaches a wheel only by changing the current.
KAPPA = 1.5
# Body-yaw cap after the wheel filter, in rad/s. The poster's ω_safe.
# One-sided red peaks near 1.15. Red and blue together can reach about 2.4.
# 1.5 sits between them, so a red sheet alone does not trip it.
OMEGA_SAFE = 1.5
FORWARD_PER_HZ = 0.0009
# Refractory period 5 ms plus the step that crosses threshold is 6 ms.
FULL_RATE = 1.0 / 0.006
MOVE_MPS = FORWARD_PER_HZ * FULL_RATE
# Wheel command filter. Long enough that one spike does not reach the motor.
TAU_V = 0.10
# Seven wheel time constants. At MOVE_MPS 0.15 a full reverse falls through
# the pulse floor in one late tick once the current is gone. Six constants
# left a residual that the reverse shift sent as a start pulse. A longer
# stall does not integrate a held current past this cap.
CATCH_UP_S = 0.70


def catch_up_steps(elapsed_s: float) -> int:
    """Membrane steps for the wall time since the previous tick.

    A tick on time stays at ``HOLD_STEPS``. A late tick follows the gap,
    and a stall longer than ``CATCH_UP_S`` does not run past that cap.
    """
    span = min(max(float(elapsed_s), HOLD_STEPS * DT), CATCH_UP_S)
    return max(1, int(round(span / DT)))


# Logged only. The wheels ignore this gate. See blue_yaw_scale.
BILATERAL_RATIO = 0.25
BLUE_SHARE = 0.15


def pn(concentration: float) -> float:
    """PN saturation. A negative concentration is read as empty."""
    c = max(float(concentration), 0.0)
    return N_ORN * c / (N_ORN * c + C0)


def concentration_gain(place: float) -> float:
    """Poster factor on both eye fractions. 1 at the center, ``1 + KAPPA`` at an edge."""
    span = abs(float(place))
    if span > 1.0:
        span = 1.0
    return 1.0 + KAPPA * span


def prime_concentration(
    red_l: float, red_r: float, place: float = 0.0
) -> tuple[float, float]:
    """Eye fractions after the edge factor. An empty eye stays at 0."""
    gain = concentration_gain(place)
    return (gain * float(red_l), gain * float(red_r))


def dna_current(
    red_l: float, red_r: float, place: float = 0.0
) -> tuple[float, float]:
    """DNa02 current. Each side keeps its PN and subtracts the other.

    ``place`` scales both fractions first. The center leaves them unchanged.
    """
    c_l, c_r = prime_concentration(red_l, red_r, place)
    u_l = pn(c_l)
    u_r = pn(c_r)
    return (ALPHA * (u_l - BETA * u_r), ALPHA * (u_r - BETA * u_l))


def red_fills_the_frame(red_l: float, red_r: float) -> bool:
    """Safety stop. Both eye ranges covered, whatever the cells are doing."""
    return min(float(red_l), float(red_r)) >= RED_FILL


def blue_yaw_scale(
    i_l: float,
    i_r: float,
    blue: tuple[float, float] = (0.0, 0.0),
) -> float:
    """1 when one eye owns the sheet, 0 when both eyes share it.

    The log still prints this. The wheel command does not read it. Sharing
    means the weaker current is at least ``BILATERAL_RATIO`` times the
    stronger, or both blue fractions are at least ``BLUE_SHARE``.
    """
    left = max(float(i_l), 0.0)
    right = max(float(i_r), 0.0)
    stronger = max(left, right)
    shared_current = stronger > 0.0 and min(left, right) / stronger >= BILATERAL_RATIO
    shared_fill = min(max(float(blue[0]), 0.0), max(float(blue[1]), 0.0)) >= BLUE_SHARE
    if shared_current or shared_fill:
        return 0.0
    return 1.0


def wheel_speeds(
    dna_l: float,
    dna_r: float,
    gf_l: float,
    gf_r: float,
) -> tuple[float, float, float, float]:
    """Instantaneous path speed, body yaw, left wheel, and right wheel.

    The left wheel reads the right DNa02 and DNp01 rates. The right wheel
    reads the left pair. DNa02 drives forward and DNp01 drives reverse.
    Speeds are meters per second. Positive yaw turns left. Yaw is the wheel
    difference over the track. A silent cell stops its wheel, so one-sided
    red keeps the near wheel at rest and the turning radius stays at least
    half the track.
    """
    v_left = FORWARD_PER_HZ * (float(dna_r) - float(gf_r))
    v_right = FORWARD_PER_HZ * (float(dna_l) - float(gf_l))
    speed = 0.5 * (v_left + v_right)
    omega = (v_right - v_left) / TRACK
    return speed, omega, v_left, v_right


def limit_rotation(v_left: float, v_right: float) -> tuple[float, float]:
    """Shrink a smoothed pair whose yaw exceeds ``OMEGA_SAFE``.

    The mean speed stays. A pair already inside the cap is returned as it
    stands. The caller applies the safety stop after this and can replace
    the pair with rest.
    """
    left = float(v_left)
    right = float(v_right)
    omega = (right - left) / TRACK
    if abs(omega) <= OMEGA_SAFE:
        return left, right
    mean = 0.5 * (left + right)
    sign = 1.0 if omega >= 0.0 else -1.0
    half = sign * OMEGA_SAFE * TRACK / 2.0
    return mean - half, mean + half


def speed_and_yaw(
    dna_l: float,
    dna_r: float,
    gf_l: float,
    gf_r: float,
) -> tuple[float, float]:
    """Forward speed in m/s and yaw in rad/s. Positive yaw turns left.

    This is the instantaneous command. ``Plant`` smooths it with ``TAU_V``
    and then applies ``limit_rotation``.
    """
    speed, omega, _left, _right = wheel_speeds(dna_l, dna_r, gf_l, gf_r)
    return speed, omega


def motion_mode(_speed: float, v_left: float, v_right: float) -> str:
    """Label the wheels after the command. The label does not choose it.

    One wheel at rest still counts. Opposite signs are a spin. Any reverse
    wheel, including a single reversing wheel, is reverse.
    """
    if abs(v_left) < 1e-6 and abs(v_right) < 1e-6:
        return "stop"
    if v_left * v_right < 0.0:
        return "spin"
    if v_left < 0.0 or v_right < 0.0:
        return "back"
    return "cruise"


class Lif:
    """Current-based LIF. State carries across frames, as in the notebook."""

    def __init__(self) -> None:
        self.v = 0.0
        self.silent_until = 0
        self.i = 0
        self.rate = 0.0

    def step(self, drive: float) -> tuple[float, bool]:
        self.i += 1
        step = (DT * 1000) / TAU_MS
        spiked = False
        if self.i < self.silent_until:
            self.v = 0.0
        else:
            self.v += step * (-self.v + float(drive))
            if self.v >= V_THRESHOLD:
                spiked = True
                self.v = 0.0
                self.silent_until = self.i + int(round(REFRAC_MS / (DT * 1000)))
        impulse = (1.0 / DT) if spiked else 0.0
        self.rate += (DT / TAU_RATE_S) * (-self.rate + impulse)
        return self.v, spiked


@dataclass
class Step:
    mode: str
    speed: float
    omega: float
    v_left: float
    v_right: float
    x: float
    y: float
    heading: float


class Plant:
    """Four cells and a differential-drive pose. Heading 0 faces +x."""

    def __init__(self) -> None:
        self.gf_l = Lif()
        self.gf_r = Lif()
        self.dna_l = Lif()
        self.dna_r = Lif()
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.wheel_left = 0.0
        self.wheel_right = 0.0
        self._step_s = 0.0
        self._step_n = 0
        self._wall = time.monotonic()

    def step(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        loom: tuple[float, float] = (0.0, 0.0),
        place: float = 0.0,
    ) -> Step:
        i_gf = (float(loom[0]), float(loom[1]))
        i_dna = dna_current(red_l, red_r, place)
        self.gf_l.step(i_gf[0])
        self.gf_r.step(i_gf[1])
        self.dna_l.step(i_dna[0])
        self.dna_r.step(i_dna[1])
        return self._emit(red_l, red_r, DT)

    def steps(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        n: int | None = None,
        loom: tuple[float, float] = (0.0, 0.0),
        place: float = 0.0,
    ) -> Step:
        """Hold one frame and advance the membranes by ``n`` milliseconds.

        ``n`` omitted follows the wall clock since the previous call, from
        one 20 ms window up to ``CATCH_UP_S``. The app loop on the board
        calls this without ``n``, and that loop is slower than 20 ms, so
        the gap has to be read here. Red concentration and the loom current
        are read once. ``blue_l`` and ``blue_r`` do not drive DNp01.
        """
        began = time.monotonic()
        if n is None:
            n = catch_up_steps(began - self._wall)
        self._wall = began
        if n < 1:
            raise ValueError("n must be at least 1")
        i_gf = (float(loom[0]), float(loom[1]))
        i_dna = dna_current(red_l, red_r, place)
        step: Step | None = None
        for _ in range(n):
            self.gf_l.step(i_gf[0])
            self.gf_r.step(i_gf[1])
            self.dna_l.step(i_dna[0])
            self.dna_r.step(i_dna[1])
            step = self._emit(red_l, red_r, DT)
        if step is None:
            raise RuntimeError("steps advanced no membrane time")
        self._step_s += time.monotonic() - began
        self._step_n += 1
        return step

    def mean_ms(self) -> float:
        """Mean wall time of ``steps`` since the previous read, in milliseconds."""
        if self._step_n == 0:
            return 0.0
        mean = self._step_s / self._step_n * 1000.0
        self._step_s = 0.0
        self._step_n = 0
        return mean

    def _emit(self, red_l: float, red_r: float, dt: float) -> Step:
        if red_fills_the_frame(red_l, red_r):
            self.wheel_left = 0.0
            self.wheel_right = 0.0
            speed = 0.0
            omega = 0.0
            v_left, v_right = 0.0, 0.0
        else:
            _speed, _omega, target_left, target_right = wheel_speeds(
                self.dna_l.rate,
                self.dna_r.rate,
                self.gf_l.rate,
                self.gf_r.rate,
            )
            follow = dt / TAU_V
            self.wheel_left += follow * (-self.wheel_left + target_left)
            self.wheel_right += follow * (-self.wheel_right + target_right)
            v_left, v_right = limit_rotation(self.wheel_left, self.wheel_right)
            speed = 0.5 * (v_left + v_right)
            omega = (v_right - v_left) / TRACK
        mode = motion_mode(speed, v_left, v_right)
        self.x += speed * float(np.cos(self.heading)) * dt
        self.y += speed * float(np.sin(self.heading)) * dt
        self.heading = float((self.heading + omega * dt + np.pi) % (2 * np.pi) - np.pi)
        return Step(
            mode=mode,
            speed=speed,
            omega=omega,
            v_left=v_left,
            v_right=v_right,
            x=self.x,
            y=self.y,
            heading=self.heading,
        )


@dataclass(frozen=True)
class Hold:
    """Pose at the end of a fixed frame, and wheel speeds after the membrane settles."""

    x: float
    y: float
    heading: float
    v_left: float
    v_right: float
    speed: float
    omega: float
    mode: str


def hold(
    red_l: float,
    red_r: float,
    blue_l: float,
    blue_r: float,
    seconds: float = 1.5,
    settle: float = 0.5,
    loom: tuple[float, float] = (0.0, 0.0),
) -> Hold:
    """Show one frame for ``seconds``. Wheel speeds are the mean after ``settle``."""
    plant = Plant()
    n = int(round(seconds / DT))
    n_settle = int(round(settle / DT))
    settled: list[Step] = []
    last: Step | None = None
    for i in range(n):
        last = plant.step(red_l, red_r, blue_l, blue_r, loom=loom)
        if i >= n_settle:
            settled.append(last)
    if last is None or not settled:
        raise RuntimeError("hold duration is shorter than the settle window")
    return Hold(
        x=last.x,
        y=last.y,
        heading=last.heading,
        v_left=float(np.mean([s.v_left for s in settled])),
        v_right=float(np.mean([s.v_right for s in settled])),
        speed=float(np.mean([s.speed for s in settled])),
        omega=float(np.mean([s.omega for s in settled])),
        mode=last.mode,
    )
