"""Poster figure: input, membrane, rate, and wheel time series.

The traces follow the poster equations, not the running plant. A red sphere
on the right becomes the red fraction on each eye's range. Those ranges
overlap: the left reads p from 0 to 0.65 and the right reads p from 0.35
to 1. The fraction saturates in the PN, and each DNa02 subtracts the other
side. Escape holds a 30° centered disk and a 20° right-eye disk, both
expanding at the same rate. A cell reads the vertical blue fraction of the
column at its stretched screen position. DNp01 adds the LC4 expansion term
to the LPLC2 size term. The size term is a Gaussian of angular size, and it
is zero when the disk is not expanding. Approach wheels follow
``wheel_speeds``: the mean DNa02 rate is forward, and the yaw from the
concentration difference stops at the cap, so one-sided red keeps both
wheels rolling forward. Escape still puts DNp01 on the opposite wheel.
Solid is the left side, dashed the right. The dotted line is the membrane
threshold. Current, rate, and wheels use the whole trial. The membrane row
is a short stretch once firing has started, because a spike lasts a few
milliseconds.

The poster leaves the sigmoid, the size curve, and the wheel scale as
symbols. The numbers below are only for this picture.

Each case is one figure: the path on the left, and current, membrane,
firing rate, and wheels on the right. The paths are the existing
schematics. The traces are these equations.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flycar.behavior import DT, Lif, MOVE_MPS, REFRAC_MS, TRACK, V_THRESHOLD, wheel_speeds
from flycar.fov import Blob, Scene, camera_tangents, project_blob
from flycar.loom import Disk, cells
from flycar.occupancy import red_place

from draw_fig2 import draw_approach
from draw_fig3 import draw_front, draw_side, prepare

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT_APPROACH = Path(__file__).with_name("fig_approach")
OUT_RETREAT = Path(__file__).with_name("fig_retreat")
OUT_AVOID = Path(__file__).with_name("fig_avoid")

INK = "#1c1915"
MUTED = "#5e584f"
PAPER = "#fbfaf6"
SPINE = "#c9c1b4"
RED = "#b4232c"
BLUE = "#1d5f99"

# Poster symbols, fixed here so the picture can be drawn.
# Equation (1): left range through 0.65, right range from 0.35.
LEFT_HI = 0.65
RIGHT_LO = 0.35
# Same stretch as the structure figure. The old midline lands at 0.65 and 0.35.
STRETCH = (0.5 + 0.15) / 0.5
N_ORN = 1.0
C0 = 0.05
ALPHA = 4.0
BETA = 0.70
K_S = 1.0
M_S = 0.20
W_S = 0.10
# g(θ) while the disk is expanding. The poster does not fix the peak.
SIZE_PEAK_DEG = 40.0
SIZE_SIGMA_DEG = 20.0
EXPANSION = 0.4
# ±1 on the wheel row is one cell firing about as fast as the refractory
# period allows. The approach currents sit lower, so those wheels are quieter.
FULL_RATE = 1.0 / 0.006
# Wheel command filter. Long enough that one spike does not reach the motor.
TAU_V = 0.10
# MOVE_MPS is one cell at the refractory rate, in meters per second.
# The wheel row divides by it, so that speed is 1 on the axis.
WIDTH, HEIGHT = 320, 180
HOLD = 20
APPROACH_S = 2.4


def expansion(theta_dot: float) -> float:
    return K_S / (1.0 + np.exp(-(theta_dot - M_S) / W_S))


def size_term(theta: float, theta_dot: float) -> float:
    """Angular-size weight. Zero when the region is not expanding."""
    if theta_dot <= 0.0:
        return 0.0
    deg = float(np.rad2deg(theta))
    return float(np.exp(-0.5 * ((deg - SIZE_PEAK_DEG) / SIZE_SIGMA_DEG) ** 2))


def pn(concentration: np.ndarray) -> np.ndarray:
    c = np.asarray(concentration, dtype=np.float64)
    return N_ORN * c / (N_ORN * c + C0)


def bilateral(concentration: np.ndarray) -> np.ndarray:
    """DNa02 current. Each side keeps its PN and subtracts the other."""
    u = pn(concentration)
    return ALPHA * np.array([u[0] - BETA * u[1], u[1] - BETA * u[0]])


def eye_mean(mask: np.ndarray) -> np.ndarray:
    """Red fraction on the left range and the right range. A red pixel is 1."""
    width = mask.shape[1]
    p = (np.arange(width) + 0.5) / width
    field = np.asarray(mask, dtype=np.float64)
    return np.array(
        [float(field[:, p <= LEFT_HI].mean()), float(field[:, p >= RIGHT_LO].mean())]
    )


def widen(u: np.ndarray) -> np.ndarray:
    """Stretch each eye from its lateral edge onto the overlapping ranges."""
    out = np.empty(u.shape, dtype=np.float64)
    left = u <= 0.5
    out[left] = u[left] * STRETCH
    out[~left] = 1.0 - (1.0 - u[~left]) * STRETCH
    return out


def cell_p(pop) -> np.ndarray:
    """Screen position of each cell: the synapse-weighted mean, then stretched."""
    total = np.add.reduceat(pop.n * pop.u, pop.starts)
    return widen(total / pop.cell_n)


PACK = cells()
LC4_P = cell_p(PACK.lc4)
LPLC_P = cell_p(PACK.lplc2)


def fraction(pop, p_i: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """F on the left and the right. f_i is the vertical blue fraction at p_i."""
    width = mask.shape[1]
    columns = np.asarray(mask, dtype=np.float64).mean(axis=0)
    ui = np.clip(np.rint(p_i * width - 0.5).astype(np.int64), 0, width - 1)
    covered = columns[ui]
    out = np.zeros(2)
    for side in (0, 1):
        chosen = pop.side == side
        out[side] = float(covered[chosen] @ pop.w[chosen] / pop.side_sum[side])
    return out


def ellipse(cu: float, cv: float, ru: float, rv: float) -> np.ndarray:
    mask = np.zeros((HEIGHT, WIDTH), dtype=bool)
    if ru <= 1e-8 or rv <= 1e-8:
        return mask
    u = (np.arange(WIDTH) + 0.5) / WIDTH
    v = (np.arange(HEIGHT) + 0.5) / HEIGHT
    uu, vv = np.meshgrid(u, v)
    mask[:] = ((uu - cu) / ru) ** 2 + ((vv - cv) / rv) ** 2 <= 1.0
    return mask


def disk(theta_deg: float, cu: float) -> Disk:
    """Equal-area disk of ``theta_deg`` centered at image ``cu``."""
    tan_h, tan_v = camera_tangents()
    theta = float(np.deg2rad(theta_deg))
    cx = (cu * 2.0 - 1.0) * tan_h
    rod = float(np.tan(theta / 2.0) * np.sqrt(1.0 + cx * cx))
    return Disk(cu, 0.5, rod / tan_h / 2.0, rod / tan_v / 2.0, theta)


def view_mask(view) -> np.ndarray:
    if not view.inside:
        return np.zeros((HEIGHT, WIDTH), dtype=bool)
    return ellipse((view.nx + 1.0) / 2.0, (1.0 - view.ny) / 2.0, view.nrx / 2.0, view.nry / 2.0)


def shown_voltage(neuron) -> float:
    """Voltage after the step. A spike is drawn at the threshold, then reset."""
    refrac = int(round(REFRAC_MS / (DT * 1000.0)))
    if neuron.v == 0.0 and neuron.silent_until == neuron.i + refrac:
        return V_THRESHOLD
    return neuron.v


def command(rate_dna: tuple[float, float], rate_dnp: tuple[float, float]) -> tuple[float, float]:
    """Left command reads the right cells. Right command reads the left cells.

    The value is the rate difference divided by one cell's steady rate,
    so a steady command runs from -1 to 1 instead of an uncalibrated m/s.
    """
    u_left = (rate_dna[1] - rate_dnp[1]) / FULL_RATE
    u_right = (rate_dna[0] - rate_dnp[0]) / FULL_RATE
    return u_left, u_right


def follow(speed: float, target: float) -> float:
    """One step of the wheel low-pass."""
    return speed + (DT / TAU_V) * (-speed + target)


def approach():
    """Right-hand red. Both wheels stay forward, and the left one is faster.

    The sphere is close enough that the right current starts above threshold
    and the left current starts below it. Bilateral subtraction keeps the
    weak side quiet until the red moves toward the middle. The wheels use
    the mean of the two rates as forward speed and cap the yaw, so the
    quiet side does not pivot.
    """
    scene = Scene(red=Blob((0.55, -0.18), 0.18), blue=None, run_s=APPROACH_S)
    x = y = heading = 0.0
    dna = [Lif(), Lif()]
    v_left = v_right = 0.0
    n = int(round(APPROACH_S / DT))
    rows = []
    volts = []
    for i in range(0, n, HOLD):
        view = project_blob(scene, x, y, heading, scene.red)
        mask = view_mask(view)
        fractions = eye_mean(mask)
        current = bilateral(fractions)
        place = red_place(mask)
        for _ in range(HOLD):
            dna[0].step(float(current[0]))
            dna[1].step(float(current[1]))
            volts.append((shown_voltage(dna[0]), shown_voltage(dna[1])))
            _speed, _omega, target_left, target_right = wheel_speeds(
                dna[0].rate,
                dna[1].rate,
                0.0,
                0.0,
                float(fractions[0]),
                float(fractions[1]),
                place,
            )
            v_left = follow(v_left, target_left)
            v_right = follow(v_right, target_right)
        speed = 0.5 * (v_left + v_right)
        omega = (v_right - v_left) / TRACK
        step = DT * HOLD
        x += speed * float(np.cos(heading)) * step
        y += speed * float(np.sin(heading)) * step
        heading = float((heading + omega * step + np.pi) % (2 * np.pi) - np.pi)
        rows.append(
            (
                i * DT,
                current[0],
                current[1],
                dna[0].rate,
                dna[1].rate,
                v_left / MOVE_MPS,
                v_right / MOVE_MPS,
                heading,
            )
        )
    arr = np.array(rows)
    t_v = np.arange(len(volts)) * DT
    return arr[:, 0], arr[:, 1:3], (t_v, np.array(volts)), arr[:, 3:5], arr[:, 5], arr[:, 6], arr[:, 7]


def escape(theta_deg: float, cu: float, seconds: float):
    """Hold one blue disk and one expansion. Red stays absent."""
    spot = disk(theta_deg, cu)
    mask = ellipse(spot.cu, spot.cv, spot.ru, spot.rv)
    weight = expansion(EXPANSION) * fraction(PACK.lc4, LC4_P, mask)
    weight = weight + size_term(spot.theta, EXPANSION) * fraction(PACK.lplc2, LPLC_P, mask)
    current = ALPHA * weight
    dnp = [Lif(), Lif()]
    v_left = v_right = 0.0
    n = int(round(seconds / DT))
    rows = []
    volts = []
    for i in range(n):
        dnp[0].step(float(current[0]))
        dnp[1].step(float(current[1]))
        volts.append((shown_voltage(dnp[0]), shown_voltage(dnp[1])))
        u_left, u_right = command((0.0, 0.0), (dnp[0].rate, dnp[1].rate))
        v_left = follow(v_left, u_left)
        v_right = follow(v_right, u_right)
        if i % HOLD == HOLD - 1 or i == n - 1:
            rows.append((i * DT, current[0], current[1], dnp[0].rate, dnp[1].rate, v_left, v_right))
    arr = np.array(rows)
    t_v = np.arange(n) * DT
    return arr[:, 0], arr[:, 1:3], (t_v, np.array(volts)), arr[:, 3:5], arr[:, 5], arr[:, 6]


def firing_window(t_v: np.ndarray, voltage: np.ndarray, width: float = 0.060):
    """A short stretch that includes the rise into the later side's first spike.

    Both sides of a frontal loom spike within a millisecond of each other, so
    the window opens at the start of the trial. Approach keeps the right
    membrane firing for half a second before the left current crosses
    threshold, and the window opens just before that first left spike.
    """
    onsets = []
    for side in (0, 1):
        hits = np.flatnonzero(voltage[:, side] >= V_THRESHOLD - 1e-9)
        if len(hits):
            onsets.append(float(t_v[hits[0]]))
    start = max(onsets) - 0.012 if onsets else float(t_v[0])
    start = max(float(t_v[0]), start)
    stop = start + width
    if stop > float(t_v[-1]):
        stop = float(t_v[-1])
        start = max(float(t_v[0]), stop - width)
    keep = (t_v >= start - 1e-9) & (t_v <= stop + 1e-9)
    return t_v[keep], voltage[keep]


def padded(values: np.ndarray, *, include_zero: bool) -> tuple[float, float]:
    lo = float(np.min(values))
    hi = float(np.max(values))
    if include_zero:
        lo = min(lo, 0.0)
        hi = max(hi, 0.0)
    if hi - lo < 1e-6:
        lo -= 0.5
        hi += 0.5
    pad = 0.08 * (hi - lo)
    return lo - pad, hi + pad


def style(ax) -> None:
    ax.set_facecolor(PAPER)
    ax.tick_params(colors=MUTED, labelsize=8, length=3, width=0.6)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(GOTHIC)
        label.set_color(MUTED)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(SPINE)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))


def draw(ax, t, left, right, color: str) -> None:
    ax.plot(t, left, color=color, lw=1.6, solid_capstyle="round")
    ax.plot(t, right, color=color, lw=1.6, ls=(0, (4, 2.2)), solid_capstyle="round")
    style(ax)


def save_case(title: str, color: str, series, draw_left, out: Path) -> None:
    """One case. The path fills the left. Four traces stack on the right."""
    fig = plt.figure(figsize=(12.8, 8.2))
    fig.patch.set_facecolor(PAPER)
    grid = fig.add_gridspec(
        4,
        2,
        width_ratios=(1.12, 1.0),
        wspace=0.34,
        hspace=0.46,
        left=0.055,
        right=0.985,
        top=0.90,
        bottom=0.07,
    )
    left = fig.add_subplot(grid[:, 0])
    draw_left(left)
    left.set_title(title, fontproperties=GOTHIC, fontsize=16, color=INK, pad=12)
    current_ax = fig.add_subplot(grid[0, 1])
    membrane_ax = fig.add_subplot(grid[1, 1])
    rate_ax = fig.add_subplot(grid[2, 1], sharex=current_ax)
    wheel_ax = fig.add_subplot(grid[3, 1], sharex=current_ax)

    t, current, membrane, rate, v_left, v_right = series
    t_v, voltage = firing_window(*membrane)
    rows = (
        (current_ax, t, current),
        (membrane_ax, t_v, voltage),
        (rate_ax, t, rate),
        (wheel_ax, t, np.column_stack((v_left, v_right))),
    )
    row_name = ("電流", "膜電位", "発火率", "車輪")
    for row, (ax, time, values) in enumerate(rows):
        draw(ax, time, values[:, 0], values[:, 1], color)
        ax.set_ylabel(row_name[row], fontproperties=GOTHIC, fontsize=11, color=INK, labelpad=6)
        if row == 0:
            ax.axhline(1.0, color=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=0)
            ax.set_ylim(*padded(np.vstack([values, [[1.0, 1.0]]]), include_zero=True))
            ax.tick_params(labelbottom=False)
        elif row == 1:
            ax.axhline(1.0, color=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=0)
            ax.set_ylim(*padded(np.vstack([values, [[0.0, 0.0], [1.0, 1.0]]]), include_zero=True))
            ax.set_yticks([0.0, 0.5, 1.0])
            ax.set_xlabel("時間(拡大)", fontproperties=GOTHIC, fontsize=11, color=INK, labelpad=2)
        elif row == 2:
            ax.set_ylim(*padded(values, include_zero=True))
            ax.tick_params(labelbottom=False)
        else:
            ax.axhline(0.0, color=SPINE, lw=0.6, zorder=0)
            ax.set_xlabel("時間(s)", fontproperties=GOTHIC, fontsize=11, color=INK, labelpad=2)
            ax.set_ylim(-1.4, 1.4)
            ax.set_yticks([-1.0, 0.0, 1.0])

    legend = [
        Line2D([0], [0], color=INK, lw=1.6, label="左"),
        Line2D([0], [0], color=INK, lw=1.6, ls=(0, (4, 2.2)), label="右"),
        Line2D([0], [0], color=MUTED, lw=0.8, ls=(0, (2, 2)), label="閾値"),
    ]
    current_ax.legend(
        handles=legend,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.08),
        ncol=3,
        frameon=False,
        prop=GOTHIC,
        fontsize=11,
        labelcolor=INK,
        borderaxespad=0.0,
        columnspacing=1.1,
        handlelength=2.4,
    )
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.18)
    fig.savefig(out.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)


def main() -> None:
    approach_run = approach()
    retreat = escape(30.0, 0.5, 1.2)
    avoid = escape(20.0, 0.75, 0.8)
    t0, i0, membrane0, _, vl0, vr0, heading0 = approach_run
    early = t0 < 0.25
    if not (i0[0, 1] > 1.0 > i0[0, 0]):
        raise RuntimeError("the approach did not start on the right eye only")
    if not (vl0[early][-1] > vr0[early][-1] > 0.0):
        raise RuntimeError("the approach did not roll both wheels forward")
    if float(np.min(vl0)) < -1e-6 or float(np.min(vr0)) < -1e-6:
        raise RuntimeError("a red wheel reversed")
    if not (vl0[-1] > 0.0 and vr0[-1] > 0.0):
        raise RuntimeError("the approach did not finish with both wheels forward")
    if float(heading0[-1]) >= 0.0:
        raise RuntimeError("the approach did not turn toward the right-hand red")
    if float(np.max(membrane0[1])) < 1.0:
        raise RuntimeError("the approach membrane never reached threshold")
    _, i1, membrane1, _, vl1, vr1 = retreat
    if abs(vl1[-1] - vr1[-1]) > 1e-4 or vl1[-1] >= 0.0:
        raise RuntimeError("the frontal series did not reverse both wheels")
    if float(np.max(membrane1[1][:, 0])) < 1.0 or float(np.max(membrane1[1][:, 1])) < 1.0:
        raise RuntimeError("the frontal membranes did not both spike")
    _, i2, membrane2, _, vl2, vr2 = avoid
    if i2[0, 0] >= 1.0 or i2[0, 1] <= 1.0 or not (vl2[-1] < -1e-4 and abs(vr2[-1]) < 1e-6):
        raise RuntimeError("the side series did not reverse only the far wheel")
    if float(np.max(membrane2[1][:, 0])) >= 1.0 or float(np.max(membrane2[1][:, 1])) < 1.0:
        raise RuntimeError("the side membrane did not spike on the near eye only")

    save_case("赤に向かう", RED, approach_run[:6], draw_approach, OUT_APPROACH)
    paths = prepare()
    save_case("正面の青から遠ざかる", BLUE, retreat, lambda ax: draw_front(ax, paths), OUT_RETREAT)
    save_case("横の青から回避する", BLUE, avoid, lambda ax: draw_side(ax, paths), OUT_AVOID)


if __name__ == "__main__":
    main()
