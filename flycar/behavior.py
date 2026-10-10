"""Half-screen red and blue counts to two wheel speeds.

Counts run from 0 to 1 and are the filled fraction of each half of the
frame. Left and right are the two halves. A color is "in front" when both
halves are filled. Position inside one half does not matter. Coverage that
falls outside the frame simply lowers that half's count. Counts below
``COUNT_FLOOR`` are read as empty. That floor is tuned when the camera is
connected.

Translation has three modes.

- stop: both wheels at rest. Blue fills both halves, red fills both halves
  while blue is not confined to one side, or neither color is in the frame.
- spin: turn in place, away from a blue that fills only one half, when red
  is absent.
- cruise: cruise speed plus yaw. Any visible red that does not fill the
  frame, and a one-sided blue while any red is still visible.

Yaw matches ``notebooks/chemotaxis_sim.ipynb``. A positive command turns
right. On a frame whose larger blue count is at least ``BLUE_OVERRIDE``,
DNa02 is dropped and the DNp01 difference is used. When red is absent, that
DNp01 difference is kept until the blue count falls below ``COUNT_FLOOR``.
Red counts as arrived only when both halves are at least ``RED_FILL``. A red
that fills one half still arcs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Membrane and readout. Same values as notebooks/chemotaxis_sim.ipynb.
R_MAX = 80.0
R_REF = 50.0
RED_REF = 0.25
TAU_MS = 5.0
V_THRESHOLD = 1.0
REFRAC_MS = 5.0
DT = 0.001
TAU_RATE_S = 0.100
BLUE_OVERRIDE = 0.72
RATE_SCALE = 100.0
V_CRUISE = 0.15
OMEGA_MAX = 1.6
TRACK = 0.12

# Counts. Independent of the synapse ratios above.
RED_FILL = 0.75
RED_PRESENT = 0.15
# Half-frame counts below this are read as empty, before the other thresholds.
# Tune when the camera is connected.
COUNT_FLOOR = 0.15


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
    # Whole VPN population at one rate. Side totals cancel, so the feather
    # weights are not needed for the left/right current.
    rate_l = float(np.clip(present_count(blue_l), 0.0, 1.0) * R_MAX)
    rate_r = float(np.clip(present_count(blue_r), 0.0, 1.0) * R_MAX)
    return (rate_l / R_REF, rate_r / R_REF)


def yaw_command(
    dna_l: float,
    dna_r: float,
    gf_l: float,
    gf_r: float,
    blue_l: float,
    blue_r: float,
    red_l: float,
    red_r: float,
) -> tuple[float, bool]:
    """Positive command is a right turn. Blue above threshold drops DNa02.

    With no red, a blue that is still above ``COUNT_FLOOR`` keeps the DNp01
    difference, even after it falls below ``BLUE_OVERRIDE``.
    """
    blue_l = present_count(blue_l)
    blue_r = present_count(blue_r)
    red_l = present_count(red_l)
    red_r = present_count(red_r)
    blue_hi = max(blue_l, blue_r)
    red_absent = max(red_l, red_r) == 0.0
    if blue_hi >= BLUE_OVERRIDE or (red_absent and blue_hi > 0.0):
        return gf_l - gf_r, True
    return dna_r - dna_l, False


def translation_mode(red_l: float, red_r: float, blue_l: float, blue_r: float) -> str:
    """stop, spin, or cruise. Yaw is chosen separately."""
    red_l = present_count(red_l)
    red_r = present_count(red_r)
    blue_l = present_count(blue_l)
    blue_r = present_count(blue_r)
    blue_hi = max(blue_l, blue_r)
    blue_lo = min(blue_l, blue_r)
    red_hi = max(red_l, red_r)
    red_lo = min(red_l, red_r)
    if blue_hi >= BLUE_OVERRIDE and blue_lo >= BLUE_OVERRIDE:
        return "stop"
    if blue_hi >= BLUE_OVERRIDE:
        if red_hi >= RED_PRESENT:
            return "cruise"
        return "spin"
    if red_lo >= RED_FILL:
        return "stop"
    if red_hi == 0.0 and blue_hi == 0.0:
        return "stop"
    return "cruise"


def wheels(omega: float, speed: float) -> tuple[float, float]:
    v_left = speed - omega * TRACK / 2
    v_right = speed + omega * TRACK / 2
    return v_left, v_right


@dataclass
class Step:
    mode: str
    override: bool
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
        command, override = yaw_command(
            self.dna_l.rate,
            self.dna_r.rate,
            self.gf_l.rate,
            self.gf_r.rate,
            blue_l,
            blue_r,
            red_l,
            red_r,
        )
        mode = translation_mode(red_l, red_r, blue_l, blue_r)
        if mode == "stop":
            speed = 0.0
            omega = 0.0
        else:
            steer = float(np.clip(command / RATE_SCALE, -1.0, 1.0))
            omega = -steer * OMEGA_MAX
            speed = 0.0 if mode == "spin" else V_CRUISE
        v_left, v_right = wheels(omega, speed)
        self.x += speed * float(np.cos(self.heading)) * DT
        self.y += speed * float(np.sin(self.heading)) * DT
        self.heading = float((self.heading + omega * DT + np.pi) % (2 * np.pi) - np.pi)
        return Step(
            mode=mode,
            override=override,
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
