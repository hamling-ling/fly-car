"""Half-screen red and blue counts to two wheel speeds.

Counts run from 0 to 1 and are the filled fraction of each half of the
frame. Left and right are the two halves. Position inside one half does not
matter. Coverage that falls outside the frame simply lowers that half's
count. Counts below ``COUNT_FLOOR`` are read as empty. That floor is tuned
when the camera is connected.

Each count is a current into one LIF cell. DNa02 takes red, DNp01 takes
blue. The wheels read the firing rates directly:

- forward speed is the red sum minus ``BLUE_FORWARD`` times the blue sum,
  and it does not reverse
- yaw is ``RED_YAW`` times the red difference plus ``BLUE_YAW`` times the
  blue difference. Positive yaw is a left turn, so a right-hand red turns
  right and a right-hand blue turns left

``BLUE_FORWARD`` is less than one, so a one-sided blue turns harder than it
brakes. ``RED_RADIUS`` is 0.10 m: a phone moved across the frame stays in
view while the heading catches it. ``BLUE_YAW`` is raised with that tighter
arc so a frontal red and a right-hand blue still pass on the blue's left
with both wheels forward. At equal firing rates the red yaw coefficient is
slightly larger than the blue one.

Nothing is firing, so an empty frame and a subthreshold color both stop.
Equal blue on both sides cancels yaw and subtracts from forward, which is a
stop when that weighted blue sum outweighs red. One side of blue with no
red has no forward term left, so the car spins in place.

The one hand-written exception is a safety stop. When both red halves are
at least ``RED_FILL``, both wheels are held at rest even though DNa02 is
firing hard. A red that fills only one half still drives.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Membrane time constants match research/notebooks/chemotaxis_sim.ipynb.
# The count references do not. That notebook still divides red counts by
# 0.25, and it turns a loom rate into current with R_MAX / R_REF. Half-frame
# fill is not a loom rate, so both colors use a count reference here.
# A half-count equal to this is current 1. Exactly 1 never spikes. The
# reference matches COUNT_FLOOR, so a color the camera still counts can fire.
# 0.04 is a few percent of one half: a small saturated patch drives. The old
# 0.15 waited until the phone was close, and 0.25 left the front-scene red
# (about 0.19 a side) silent. The old blue scale (80/50) left a blue that
# filled about 0.6 of one half below threshold.
RED_REF = 0.04
BLUE_REF = 0.04
TAU_MS = 5.0
V_THRESHOLD = 1.0
REFRAC_MS = 5.0
DT = 0.001
# One camera command. fov.simulate still calls step() this many times.
HOLD_STEPS = 20
TAU_RATE_S = 0.100
TRACK = 0.12

# Counts. Independent of the synapse ratios above.
RED_FILL = 0.75
# Half-frame counts below this are read as empty, before the currents.
# Just above the saturated background of this room, so a small phone counts
# and the dull red in the walls does not.
COUNT_FLOOR = 0.04

# Front red 0.45/0.45 saturates near 196 Hz a side. That sum is about 0.24 m/s.
# FORWARD / (RED_YAW * YAW) is the turning radius while only one red cell
# is firing. 0.10 m is small enough that a hand-moved phone stays in frame
# while the car yaws onto it. 0.15 m still loses that sweep, and 0.30 m
# never centers a phone 0.40 m ahead. The radius stays above TRACK/2, so
# both wheels stay forward and the inner one runs at 0.4 times the path
# speed. BLUE_YAW is high enough that the blue dodge still misses the
# sphere with both wheels forward. BLUE_FORWARD leaves forward speed when
# the rates match.
FORWARD_PER_HZ = 0.0006
YAW_PER_HZ = 0.0024
BLUE_YAW = 2.4
BLUE_FORWARD = 0.35
RED_RADIUS = 0.10
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


def gf_current(blue_l: float, blue_r: float) -> tuple[float, float]:
    # Same occupancy-to-current map as DNa02. Side totals cancel, so the
    # feather weights are not needed for the left/right current.
    return (present_count(blue_l) / BLUE_REF, present_count(blue_r) / BLUE_REF)


def red_fills_the_frame(red_l: float, red_r: float) -> bool:
    """Safety stop. Both halves covered, whatever the cells are doing."""
    return min(present_count(red_l), present_count(red_r)) >= RED_FILL


def speed_and_yaw(dna_l: float, dna_r: float, gf_l: float, gf_r: float) -> tuple[float, float]:
    """Forward speed in m/s and yaw in rad/s. Positive yaw turns left.

    Forward is the red sum minus a fraction of the blue sum, clipped so the
    car does not reverse. Yaw weights the blue difference more than the red
    difference, so a one-sided obstacle out-turns the attractant.
    """
    forward = (dna_l + dna_r) - BLUE_FORWARD * (gf_l + gf_r)
    yaw = RED_YAW * (dna_l - dna_r) + BLUE_YAW * (gf_r - gf_l)
    speed = max(0.0, forward * FORWARD_PER_HZ)
    omega = yaw * YAW_PER_HZ
    return speed, omega


def motion_mode(speed: float, v_left: float, v_right: float) -> str:
    """Label the wheels after the command. The label does not choose it."""
    if abs(v_left) < 1e-6 and abs(v_right) < 1e-6:
        return "stop"
    if speed < 1e-6 and v_left * v_right < 0.0:
        return "spin"
    return "cruise"


def wheels(omega: float, speed: float) -> tuple[float, float]:
    v_left = speed - omega * TRACK / 2
    v_right = speed + omega * TRACK / 2
    return v_left, v_right


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

    def step(self, red_l: float, red_r: float, blue_l: float, blue_r: float) -> Step:
        i_gf = gf_current(blue_l, blue_r)
        i_dna = dna_current(red_l, red_r)
        self.gf_l.step(i_gf[0])
        self.gf_r.step(i_gf[1])
        self.dna_l.step(i_dna[0])
        self.dna_r.step(i_dna[1])
        return self._emit(red_l, red_r, blue_l, blue_r, DT)

    def steps(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        n: int = HOLD_STEPS,
    ) -> Step:
        """Hold one frame for ``n`` milliseconds of membrane time.

        The occupancy is turned into current once. Only the membranes advance
        on each 1 ms tick. Forward speed, yaw, and the wheel speeds are read
        once from the rates at the end of the window.
        """
        if n < 1:
            raise ValueError("n must be at least 1")
        i_gf = gf_current(blue_l, blue_r)
        i_dna = dna_current(red_l, red_r)
        for _ in range(n):
            self.gf_l.step(i_gf[0])
            self.gf_r.step(i_gf[1])
            self.dna_l.step(i_dna[0])
            self.dna_r.step(i_dna[1])
        return self._emit(red_l, red_r, blue_l, blue_r, DT * n)

    def _emit(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        dt: float,
    ) -> Step:
        if red_fills_the_frame(red_l, red_r):
            speed = 0.0
            omega = 0.0
        else:
            speed, omega = speed_and_yaw(
                self.dna_l.rate,
                self.dna_r.rate,
                self.gf_l.rate,
                self.gf_r.rate,
            )
        v_left, v_right = wheels(omega, speed)
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
) -> Hold:
    """Show one frame for ``seconds``. Wheel speeds are the mean after ``settle``."""
    plant = Plant()
    n = int(round(seconds / DT))
    n_settle = int(round(settle / DT))
    settled: list[Step] = []
    last: Step | None = None
    for i in range(n):
        last = plant.step(red_l, red_r, blue_l, blue_r)
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
