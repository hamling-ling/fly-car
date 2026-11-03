"""Red occupancy and a loom current to two wheel speeds.

Red counts run from 0 to 1 and are the filled fraction of each half of the
frame. Left and right are the two halves. Position inside one half does not
matter. Counts below ``COUNT_FLOOR`` are read as empty.

DNa02 takes that red count. DNp01 does not. Its current is computed by
``flycar.loom`` from the blue region's angular size and expansion, then
passed in as ``loom``. A blue fill with no loom current does not fire.
The wheels read the firing rates directly:

- forward speed is the red sum minus ``BLUE_FORWARD`` times the blue sum.
  A negative result reverses; it is not clipped to a stop
- red yaw is ``RED_YAW`` times the red difference and is split across both
  wheels. Positive yaw is a left turn, so a right-hand red turns right
- blue yaw is ``BLUE_YAW`` times the blue difference, and that term is
  dropped when both eyes share the sheet. It is extra reverse on the wheel
  away from the stronger eye. The near wheel keeps the path speed. A
  right-hand DNp01 turns left. Blue drives neither wheel forward

``BLUE_FORWARD`` is less than one, so matched rates leave the red forward
speed. ``RED_RADIUS`` is 0.20 m. At 0.10 m a diagonal red yawed out of the
camera before the two halves could even out. ``BLUE_YAW`` is 18 and the
rate filter is 50 ms, both hand-set. One new camera frame holds a current
for about 0.1 s and then expansion drops to 0. Split across both wheels,
3.6 turned that frame about 6° and 18 about 30°. Only the far wheel takes
the blue term now, so the body turns about half of that, near 15°. The far
wheel's reverse speed is the one the split law already used. The total
angle scales with this coefficient. It is not a fit.
``BILATERAL_RATIO`` is 0.25, also hand-set. When the weaker current is at
least this fraction of the stronger, the blue yaw is 0. A factor between
0 and 1 still turns, so the factor is only 0 or 1. A sheet on one eye
stays under the fraction and keeps the yaw. ``BLUE_SHARE`` is 0.15,
hand-set from a centered sheet whose mask was lopsided: both halves at or
above that fill drop the blue yaw even when the weak current is still 0.
A half under it, such as 0.46 against 0.05, keeps the yaw.

Nothing is firing, so an empty frame and a subthreshold red both stop.
Equal DNp01 rates cancel yaw. Both cells sit on the refractory ceiling once
their current is well above 1, so matched looming on both sides has no yaw
left and the negative forward term backs the car straight up. A shared
sheet also drops the blue yaw while the rates are still unequal, so a
near-frontal sheet holds still or backs up. One eye keeps a yaw. That yaw
adds reverse on the far wheel, and the near wheel stays on the reverse
path speed, so the car backs away without a wheel turning forward.

The one hand-written exception is a safety stop. When both red halves are
at least ``RED_FILL``, both wheels are held at rest even though DNa02 is
firing hard. A red that fills only one half still drives.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

# Membrane time constants match research/notebooks/chemotaxis_sim.ipynb.
# RED_REF does not. That notebook still divides red counts by 0.25.
# A half-count equal to this is DNa02 current 1. Exactly 1 never spikes.
# The reference matches COUNT_FLOOR, so a red the camera still counts can
# fire. 0.04 is a few percent of one half: a small saturated patch drives.
# The old 0.15 waited until the phone was close, and 0.25 left the
# front-scene red (about 0.19 a side) silent. Blue is not a count. loom.py
# turns angular size and expansion into the DNp01 current.
RED_REF = 0.04
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

# Counts. Independent of the synapse ratios above.
RED_FILL = 0.75
# Half-frame counts below this are read as empty, before the currents.
# Just above the saturated background of this room, so a small phone counts
# and the dull red in the walls does not.
COUNT_FLOOR = 0.04

# Front red 0.45/0.45 saturates near 196 Hz a side. That sum is about 0.24 m/s.
# FORWARD / (RED_YAW * YAW) is the turning radius while only one red cell
# is firing. 0.20 m halves the yaw rate of the 0.10 m arc, which swung a
# diagonal red out of the camera. The radius stays above TRACK/2, so both
# wheels stay forward and the inner one runs at 0.7 times the path speed.
# BLUE_YAW is 18. Split across both wheels, one 0.1 s frame near current
# 1.8 turned about 30°, and 3.6 turned it about 6°. Body yaw is now half
# of that split angle, because only the far wheel takes the blue term.
# Hand-set, not a fit.
# BLUE_FORWARD leaves forward speed when the rates match.
FORWARD_PER_HZ = 0.0006
YAW_PER_HZ = 0.0024
BLUE_YAW = 18.0
BLUE_FORWARD = 0.35
# Hand-set. The weaker DNp01 current has to be under this fraction of the
# stronger one for the blue yaw to stay on. At or above it, both eyes see
# the sheet and the blue yaw is 0. See the module docstring.
BILATERAL_RATIO = 0.25
# Hand-set. A centered sheet can still paint one half much more than the
# other, and the weak eye's current then stays 0, so the ratio above never
# opens. Both halves at or above this fill drop the blue yaw anyway.
# 0.15 is the weak half of a frame that spun hard (0.51 against 0.15).
# A weak half of 0.02 to 0.10 keeps the yaw.
BLUE_SHARE = 0.15
RED_RADIUS = 0.20
RED_YAW = FORWARD_PER_HZ / (YAW_PER_HZ * RED_RADIUS)


def present_count(count: float) -> float:
    value = float(count)
    if value < COUNT_FLOOR:
        return 0.0
    return value


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


def dna_current(red_l: float, red_r: float) -> tuple[float, float]:
    return (present_count(red_l) / RED_REF, present_count(red_r) / RED_REF)


def red_fills_the_frame(red_l: float, red_r: float) -> bool:
    """Safety stop. Both halves covered, whatever the cells are doing."""
    return min(present_count(red_l), present_count(red_r)) >= RED_FILL


def _loom_current(loom: tuple[float, float]) -> tuple[float, float]:
    """DNp01 current passed in from ``flycar.loom``. Negative values are dropped."""
    return (max(float(loom[0]), 0.0), max(float(loom[1]), 0.0))


def blue_yaw_scale(
    i_l: float,
    i_r: float,
    blue: tuple[float, float] = (0.0, 0.0),
) -> float:
    """1 when one eye owns the sheet, 0 when both eyes share it.

    Sharing means the weaker current is at least ``BILATERAL_RATIO`` times
    the stronger, or both half-fills are at least ``BLUE_SHARE``. With no
    current and a one-sided fill the scale stays 1, and the rates are 0.
    """
    left = max(float(i_l), 0.0)
    right = max(float(i_r), 0.0)
    stronger = max(left, right)
    shared_current = stronger > 0.0 and min(left, right) / stronger >= BILATERAL_RATIO
    shared_fill = min(max(float(blue[0]), 0.0), max(float(blue[1]), 0.0)) >= BLUE_SHARE
    if shared_current or shared_fill:
        return 0.0
    return 1.0


def speed_and_yaw(
    dna_l: float,
    dna_r: float,
    gf_l: float,
    gf_r: float,
    loom: tuple[float, float] = (0.0, 0.0),
    blue: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    """Forward speed in m/s and yaw in rad/s. Positive yaw turns left.

    Forward is the red sum minus a fraction of the DNp01 sum. A negative sum
    reverses at the same coefficient, so matched looming on both sides backs
    away even after the two cells have saturated and the yaw has cancelled.
    Red yaw is the red difference. Blue yaw is the DNp01 difference, omitted
    when ``blue_yaw_scale`` says both eyes share the sheet. The returned yaw
    is the yaw the wheels make: red is applied to both, and blue only as
    extra reverse on the wheel away from the stronger eye, so blue's share
    of the body yaw is half of ``BLUE_YAW`` times the rate difference.
    """
    speed, omega, _left, _right = wheel_speeds(dna_l, dna_r, gf_l, gf_r, loom, blue)
    return speed, omega


def wheel_speeds(
    dna_l: float,
    dna_r: float,
    gf_l: float,
    gf_r: float,
    loom: tuple[float, float] = (0.0, 0.0),
    blue: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float, float, float]:
    """Return path speed, body yaw, left wheel, and right wheel.

    Red yaw splits across the axle. Blue yaw only pushes the far wheel
    backward: a right-hand DNp01 reverses the left wheel and leaves the
    right wheel on the path speed. With no red, that path speed is reverse,
    so the right wheel creeps backward and the left wheel reverses harder.
    """
    forward = (dna_l + dna_r) - BLUE_FORWARD * (gf_l + gf_r)
    red_omega = RED_YAW * (dna_l - dna_r) * YAW_PER_HZ
    blue_omega = BLUE_YAW * blue_yaw_scale(*loom, blue) * (gf_r - gf_l) * YAW_PER_HZ
    speed = forward * FORWARD_PER_HZ
    v_left = speed - red_omega * TRACK / 2
    v_right = speed + red_omega * TRACK / 2
    if blue_omega > 0.0:
        v_left -= blue_omega * TRACK / 2
    elif blue_omega < 0.0:
        v_right -= -blue_omega * TRACK / 2
    omega = (v_right - v_left) / TRACK
    return speed, omega, v_left, v_right


def motion_mode(speed: float, v_left: float, v_right: float) -> str:
    """Label the wheels after the command. The label does not choose it."""
    if abs(v_left) < 1e-6 and abs(v_right) < 1e-6:
        return "stop"
    if speed < 1e-6 and v_left * v_right < 0.0:
        return "spin"
    if v_left < 0.0 and v_right < 0.0:
        return "back"
    return "cruise"


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
        self._step_s = 0.0
        self._step_n = 0

    def step(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        loom: tuple[float, float] = (0.0, 0.0),
    ) -> Step:
        i_gf = _loom_current(loom)
        i_dna = dna_current(red_l, red_r)
        self.gf_l.step(i_gf[0])
        self.gf_r.step(i_gf[1])
        self.dna_l.step(i_dna[0])
        self.dna_r.step(i_dna[1])
        return self._emit(red_l, red_r, blue_l, blue_r, i_gf, DT)

    def steps(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        n: int = HOLD_STEPS,
        loom: tuple[float, float] = (0.0, 0.0),
    ) -> Step:
        """Hold one frame for ``n`` milliseconds of membrane time.

        Red occupancy and the loom current are read once. Only the membranes
        advance on each 1 ms tick. Forward speed, yaw, and the wheel speeds
        are read once from the rates at the end of the window. ``blue_l`` and
        ``blue_r`` do not drive DNp01.
        """
        if n < 1:
            raise ValueError("n must be at least 1")
        began = time.monotonic()
        i_gf = _loom_current(loom)
        i_dna = dna_current(red_l, red_r)
        for _ in range(n):
            self.gf_l.step(i_gf[0])
            self.gf_r.step(i_gf[1])
            self.dna_l.step(i_dna[0])
            self.dna_r.step(i_dna[1])
        step = self._emit(red_l, red_r, blue_l, blue_r, i_gf, DT * n)
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

    def _emit(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        loom: tuple[float, float],
        dt: float,
    ) -> Step:
        if red_fills_the_frame(red_l, red_r):
            speed = 0.0
            omega = 0.0
            v_left, v_right = 0.0, 0.0
        else:
            speed, omega, v_left, v_right = wheel_speeds(
                self.dna_l.rate,
                self.dna_r.rate,
                self.gf_l.rate,
                self.gf_r.rate,
                loom,
                (blue_l, blue_r),
            )
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
