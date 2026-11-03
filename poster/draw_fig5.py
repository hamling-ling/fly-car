"""Poster figure: input, membrane, rate, and wheel time series.

The traces are the same plant as fig2 and fig3. Approach is the red sphere
on the right. Escape holds the loom current of a 30° centered disk and of a
20° right-eye disk, both expanding at 0.4 rad/s. Solid is the left side,
dashed the right. The dotted line is the membrane threshold. Current, rate,
and wheels use the whole trial. The membrane row is a short stretch once
firing has started, because a spike lasts a few milliseconds.
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

from flycar.behavior import DT, Plant, REFRAC_MS, V_THRESHOLD
from flycar.fov import Blob, Scene, _blue_disk, camera_tangents, project_blob, simulate
from flycar.loom import Disk, LoomTrack, cells

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT = Path(__file__).with_name("fig5_series")

INK = "#1c1915"
MUTED = "#5e584f"
PAPER = "#fbfaf6"
SPINE = "#c9c1b4"
RED = "#b4232c"
BLUE = "#1d5f99"
EXPANSION = 0.4


def disk(theta_deg: float, cu: float) -> Disk:
    """Equal-area disk of ``theta_deg`` centered at image ``cu``."""
    tan_h, tan_v = camera_tangents()
    theta = float(np.deg2rad(theta_deg))
    cx = (cu * 2.0 - 1.0) * tan_h
    rod = float(np.tan(theta / 2.0) * np.sqrt(1.0 + cx * cx))
    return Disk(cu, 0.5, rod / tan_h / 2.0, rod / tan_v / 2.0, theta)


def shown_voltage(neuron) -> float:
    """Voltage after the step. A spike is drawn at the threshold, then reset."""
    refrac = int(round(REFRAC_MS / (DT * 1000.0)))
    if neuron.v == 0.0 and neuron.silent_until == neuron.i + refrac:
        return V_THRESHOLD
    return neuron.v


def approach():
    """Red on the right, until the wheels have been stopped for a short while."""
    scene = Scene(red=Blob((1.30, -0.40), 0.12), blue=None, run_s=12.0)
    run = simulate(scene)
    stop = next(sample.t for sample in run.samples if sample.mode == "stop")
    kept = [sample for sample in run.samples if sample.t <= stop + 0.34]
    t = np.array([sample.t for sample in kept])
    current = np.array([sample.i_dna for sample in kept])
    rate = np.array([sample.rate_dna for sample in kept])
    left = np.array([sample.v_left for sample in kept])
    right = np.array([sample.v_right for sample in kept])
    t_end = float(t[-1])
    membrane = _approach_voltage(scene, t_end)
    return t, current, membrane, rate, left, right


def _approach_voltage(scene: Scene, t_end: float) -> tuple[np.ndarray, np.ndarray]:
    """DNa02 voltage at every millisecond, on the same run as ``simulate``."""
    n = int(round(scene.run_s / DT))
    plant = Plant()
    plant.x = scene.x
    plant.y = scene.y
    plant.heading = float((scene.heading + np.pi) % (2 * np.pi) - np.pi)
    tan_h, tan_v = camera_tangents(scene.dfov_deg, scene.aspect)
    track = LoomTrack()
    volts: list[tuple[float, float]] = []
    step_i = 0
    for i in range(0, n, scene.hold_steps):
        red = project_blob(scene, plant.x, plant.y, plant.heading, scene.red)
        blue = project_blob(scene, plant.x, plant.y, plant.heading, scene.blue)
        disk_now = _blue_disk(scene, plant.x, plant.y, plant.heading, tan_h, tan_v)
        track.update(disk_now, i * DT)
        for _ in range(scene.hold_steps):
            plant.step(red.left, red.right, blue.left, blue.right, loom=track.current)
            volts.append((shown_voltage(plant.dna_l), shown_voltage(plant.dna_r)))
            step_i += 1
            if step_i * DT > t_end:
                break
        if step_i * DT > t_end:
            break
    t_v = np.arange(len(volts)) * DT
    return t_v, np.array(volts)


def escape(theta_deg: float, cu: float, seconds: float):
    """Hold one loom current. Blue occupancy stays 0, as in fig3."""
    loom = cells().current(disk(theta_deg, cu), EXPANSION)
    plant = Plant()
    n = int(round(seconds / DT))
    rows = []
    volts = []
    for i in range(n):
        step = plant.step(0.0, 0.0, 0.0, 0.0, loom=loom)
        volts.append((shown_voltage(plant.gf_l), shown_voltage(plant.gf_r)))
        if i % 20 == 0 or i == n - 1:
            rows.append(
                (
                    i * DT,
                    loom[0],
                    loom[1],
                    plant.gf_l.rate,
                    plant.gf_r.rate,
                    step.v_left,
                    step.v_right,
                )
            )
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


def main() -> None:
    cases = (
        ("赤に向かう", RED, approach()),
        ("正面の青から遠ざかる", BLUE, escape(30.0, 0.5, 1.2)),
        ("横の青から回避する", BLUE, escape(20.0, 0.75, 0.25)),
    )
    # Approach turns toward the right-hand red, then both wheels stop.
    # Frontal blue reverses both wheels together. Side blue reverses the
    # far (left) wheel harder.
    t0, i0, membrane0, r0, vl0, vr0 = cases[0][2]
    if not (vl0[0] > vr0[0] > 0.0 and vl0[-1] == 0.0 and vr0[-1] == 0.0):
        raise RuntimeError("the approach series is not a right turn that stops")
    if float(np.max(i0[:, 0])) < 1.0 or float(np.max(i0[:, 1])) < 1.0:
        raise RuntimeError("the approach current stayed under threshold")
    if float(np.max(membrane0[1])) < 1.0:
        raise RuntimeError("the approach membrane never reached threshold")
    _, i1, membrane1, _, vl1, vr1 = cases[1][2]
    if abs(vl1[-1] - vr1[-1]) > 1e-6 or vl1[-1] >= 0.0:
        raise RuntimeError("the frontal series did not reverse both wheels")
    if float(np.max(membrane1[1][:, 0])) < 1.0 or float(np.max(membrane1[1][:, 1])) < 1.0:
        raise RuntimeError("the frontal membranes did not both spike")
    _, i2, membrane2, _, vl2, vr2 = cases[2][2]
    if i2[0, 0] != 0.0 or not (vl2[-1] < vr2[-1] < 0.0):
        raise RuntimeError("the side series did not reverse the far wheel harder")
    if float(np.max(membrane2[1][:, 0])) > 0.0 or float(np.max(membrane2[1][:, 1])) < 1.0:
        raise RuntimeError("the side membrane did not spike on the near eye only")
    del t0, r0

    fig, axes = plt.subplots(4, 3, figsize=(12.6, 9.6), sharex=False)
    fig.patch.set_facecolor(PAPER)
    row_name = ("電流", "膜電位", "発火率", "車輪")
    for col in range(3):
        axes[2, col].sharex(axes[0, col])
        axes[3, col].sharex(axes[0, col])

    for col, (title, color, (t, current, membrane, rate, v_left, v_right)) in enumerate(cases):
        t_v, voltage = firing_window(*membrane)
        rows = (
            (t, current),
            (t_v, voltage),
            (t, rate),
            (t, np.column_stack((v_left, v_right))),
        )
        for row, (time, values) in enumerate(rows):
            ax = axes[row, col]
            draw(ax, time, values[:, 0], values[:, 1], color)
            if row == 0:
                ax.axhline(1.0, color=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=0)
                ax.set_title(title, fontproperties=GOTHIC, fontsize=13, color=INK, pad=8)
                ax.set_ylim(*padded(np.vstack([values, [[1.0, 1.0]]]), include_zero=True))
            elif row == 1:
                ax.axhline(1.0, color=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=0)
                ax.set_ylim(*padded(np.vstack([values, [[0.0, 0.0], [1.0, 1.0]]]), include_zero=True))
                ax.set_yticks([0.0, 0.5, 1.0])
                ax.set_xlabel("時間(拡大)", fontproperties=GOTHIC, fontsize=11, color=INK, labelpad=4)
            elif row == 3:
                ax.axhline(0.0, color=SPINE, lw=0.6, zorder=0)
                ax.set_xlabel("時間(s)", fontproperties=GOTHIC, fontsize=11, color=INK, labelpad=4)
                ax.set_ylim(*padded(values, include_zero=True))
            else:
                ax.set_ylim(*padded(values, include_zero=True))
            if col == 0:
                ax.set_ylabel(row_name[row], fontproperties=GOTHIC, fontsize=11, color=INK, labelpad=6)

    legend = [
        Line2D([0], [0], color=INK, lw=1.6, label="左"),
        Line2D([0], [0], color=INK, lw=1.6, ls=(0, (4, 2.2)), label="右"),
        Line2D([0], [0], color=MUTED, lw=0.8, ls=(0, (2, 2)), label="閾値"),
    ]
    fig.legend(
        handles=legend,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 1.02),
        prop=GOTHIC,
        fontsize=11,
        labelcolor=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.25)
    fig.savefig(OUT.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    main()
