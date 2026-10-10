"""Figures for a :class:`flycar.fov.Run`.

Importing this module selects IPAexGothic through ``japanize_matplotlib``,
so Japanese axis labels render in a notebook or in a plain script.

``animate`` returns the matplotlib figure and animation. ``show_world`` turns
that into an HTML player for a notebook. ``neuron_figure`` returns the
DNa02 / DNp01 figure and does not show it. A notebook displays that return
value when it is the cell result. A script saves it with ``savefig``.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import japanize_matplotlib  # IPAexGothic for the labels in this module
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse, Polygon

from flycar.behavior import DT, V_THRESHOLD
from flycar.fov import Blob, Run, View

MODE_JA = {"cruise": "前進", "stop": "停止", "spin": "その場旋回"}
IMG_W, IMG_H = 16.0, 9.0
_COLORS = {"red": "C3", "blue": "C0"}
_LABELS = {"red": "赤", "blue": "青"}


def animate(run: Run, stride: int = 5) -> tuple[plt.Figure, FuncAnimation]:
    """Top-down view beside the camera. Playback stays at real time.

    ``stride`` is how many hold windows one displayed frame skips. The default
    shows a frame every 100 ms when the hold is 20 ms.
    """
    if stride < 1:
        raise ValueError("stride must be at least 1")
    indices = list(range(0, len(run.samples), stride))
    fig, (ax_w, ax_c) = plt.subplots(1, 2, figsize=(11.2, 5.0), layout="constrained")
    ax_w.set_aspect("equal")
    (x_lim, y_lim) = _world_limits(run)
    ax_w.set_xlim(*x_lim)
    ax_w.set_ylim(*y_lim)
    ax_w.set_xlabel("x (m)")
    ax_w.set_ylabel("y (m)、左が正")
    ax_w.set_title("俯瞰")
    for name in ("red", "blue"):
        blob: Blob | None = getattr(run.scene, name)
        if blob is None:
            continue
        color = _COLORS[name]
        ax_w.add_patch(plt.Circle(blob.xy, blob.radius, color=color, alpha=0.85, zorder=2))
        ax_w.text(
            blob.xy[0],
            blob.xy[1] + blob.radius + 0.04,
            _LABELS[name],
            color=color,
            ha="center",
        )
    (path_line,) = ax_w.plot([], [], color="0.35", lw=1.2, zorder=3)
    fov_patch = Polygon([[0, 0]], closed=True, color="0.75", alpha=0.45, zorder=1)
    robot_patch = Polygon([[0, 0]], closed=True, color="0.15", zorder=4)
    ax_w.add_patch(fov_patch)
    ax_w.add_patch(robot_patch)

    ax_c.set_xlim(0, IMG_W)
    ax_c.set_ylim(0, IMG_H)
    ax_c.set_aspect("equal")
    ax_c.set_facecolor("#141414")
    ax_c.set_title("カメラ")
    ax_c.set_xticks([0, IMG_W / 2, IMG_W], ["左", "中央", "右"])
    ax_c.set_yticks([])
    ax_c.axvline(IMG_W / 2, color="white", lw=0.8, alpha=0.7)
    for spine in ax_c.spines.values():
        spine.set_color("0.6")
    image = {
        name: Ellipse((0, 0), 0, 0, color=color, alpha=0.9, visible=False)
        for name, color in _COLORS.items()
    }
    for patch in image.values():
        ax_c.add_patch(patch)

    def draw(frame_i: int) -> list[object]:
        index = indices[frame_i]
        sample = run.samples[index]
        walked = run.samples[: index + 1]
        path_line.set_data([item.x for item in walked], [item.y for item in walked])
        fov_patch.set_xy(_fov_wedge(sample.x, sample.y, sample.heading, run))
        robot_patch.set_xy(_robot_triangle(sample.x, sample.y, sample.heading))
        for name, patch in image.items():
            view: View = getattr(sample, name)
            if view.inside:
                cx, cy, width, height = _img_ellipse(view)
                patch.set_center((cx, cy))
                patch.width = width
                patch.height = height
                patch.set_visible(True)
            else:
                patch.set_visible(False)
        fig.suptitle(f"t = {sample.t:.1f} s   {MODE_JA[sample.mode]}")
        return []

    draw(0)
    interval_ms = stride * run.scene.hold_steps * DT * 1000.0
    anim = FuncAnimation(fig, draw, frames=len(indices), interval=interval_ms, blit=False)
    return fig, anim


def show_world(run: Run, stride: int = 5):
    """HTML player for a notebook. The static figure is closed."""
    from IPython.display import HTML

    fig, anim = animate(run, stride)
    player = HTML(anim.to_jshtml())
    plt.close(fig)
    return player


def neuron_figure(run: Run) -> Figure:
    """Screen position, membrane current, and the rates sent to the wheels.

    Solid lines are the left cell, dashed lines the right cell. Current 1 is
    the spike threshold. Gray bands are stop. The figure is not registered
    with pyplot, so calling this does not open a window.
    """
    time_s = np.array([sample.t for sample in run.samples])
    modes = [sample.mode for sample in run.samples]
    red_nx = np.array(
        [sample.red.nx if sample.red.inside else np.nan for sample in run.samples]
    )
    i_dna = np.array([sample.i_dna for sample in run.samples])
    i_gf = np.array([sample.i_gf for sample in run.samples])
    rate_dna = np.array([sample.rate_dna for sample in run.samples])
    rate_gf = np.array([sample.rate_gf for sample in run.samples])

    fig = Figure(figsize=(9.0, 7.2), layout="constrained")
    axes = fig.subplots(3, 1, sharex=True)

    def shade(ax) -> None:
        for start, end in _stop_spans(time_s, modes):
            ax.axvspan(start, end, color="0.85", zorder=0)

    shade(axes[0])
    axes[0].plot(time_s, red_nx, color="C3", label="赤の中心")
    axes[0].axhline(0.0, color="black", lw=0.8)
    axes[0].set_ylabel("画面の横位置")
    axes[0].set_ylim(-1.05, 1.05)
    axes[0].legend(loc="upper right", frameon=False)
    axes[0].set_title("右が正。0 が水平中央")

    shade(axes[1])
    axes[1].plot(time_s, i_dna[:, 0], color="C3", label="DNa02 左")
    axes[1].plot(time_s, i_dna[:, 1], color="C3", ls="--", label="DNa02 右")
    axes[1].plot(time_s, i_gf[:, 0], color="C0", label="DNp01 左")
    axes[1].plot(time_s, i_gf[:, 1], color="C0", ls="--", label="DNp01 右")
    axes[1].axhline(V_THRESHOLD, color="black", lw=0.8, ls=":", label="閾値")
    axes[1].set_ylabel("電流")
    axes[1].legend(loc="upper right", frameon=False, ncol=3)
    axes[1].set_title("ニューロンへの入力")

    shade(axes[2])
    axes[2].plot(time_s, rate_dna[:, 0], color="C3", label="DNa02 左")
    axes[2].plot(time_s, rate_dna[:, 1], color="C3", ls="--", label="DNa02 右")
    axes[2].plot(time_s, rate_gf[:, 0], color="C0", label="DNp01 左")
    axes[2].plot(time_s, rate_gf[:, 1], color="C0", ls="--", label="DNp01 右")
    axes[2].set_ylabel("発火率 (Hz)")
    axes[2].set_xlabel("時間 (s)")
    axes[2].legend(loc="upper right", frameon=False, ncol=2)
    axes[2].set_title("ニューロンの出力")
    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    return fig


def _stop_spans(time_s: np.ndarray, modes: list[str]) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    start = None
    for index, mode in enumerate(modes):
        if mode == "stop" and start is None:
            start = float(time_s[index])
        if start is None:
            continue
        last = index == len(modes) - 1
        if mode != "stop":
            spans.append((start, float(time_s[index])))
            start = None
        elif last:
            spans.append((start, float(time_s[index])))
    return spans


def _world_limits(run: Run) -> tuple[tuple[float, float], tuple[float, float]]:
    xs = [sample.x for sample in run.samples]
    ys = [sample.y for sample in run.samples]
    for blob in (run.scene.red, run.scene.blue):
        if blob is None:
            continue
        xs.extend((blob.xy[0] - blob.radius, blob.xy[0] + blob.radius))
        ys.extend((blob.xy[1] - blob.radius, blob.xy[1] + blob.radius))
    return _padded(xs), _padded(ys)


def _padded(values: list[float], pad: float = 0.3, min_span: float = 1.0) -> tuple[float, float]:
    lo, hi = min(values), max(values)
    if hi - lo < min_span:
        mid = (lo + hi) / 2.0
        lo, hi = mid - min_span / 2.0, mid + min_span / 2.0
    return lo - pad, hi + pad


def _img_ellipse(view: View) -> tuple[float, float, float, float]:
    width = 2 * view.nrx * (IMG_W / 2)
    height = 2 * view.nry * (IMG_H / 2)
    cx = (view.nx + 1) / 2 * IMG_W
    cy = (view.ny + 1) / 2 * IMG_H
    return cx, cy, width, height


def _robot_triangle(x: float, y: float, heading: float) -> np.ndarray:
    forward = np.array([np.cos(heading), np.sin(heading)])
    left = np.array([-np.sin(heading), np.cos(heading)])
    nose = np.array([x, y])
    tail = nose - forward * 0.18
    return np.vstack([nose, tail + left * 0.07, tail - left * 0.07])


def _fov_wedge(x: float, y: float, heading: float, run: Run) -> np.ndarray:
    horizontal, _ = run.scene.fovs()
    angles = np.linspace(-horizontal / 2.0, horizontal / 2.0, 24)
    reach = 1.7
    pts = [(x, y)]
    for angle in angles:
        pts.append(
            (
                x + reach * np.cos(heading + angle),
                y + reach * np.sin(heading + angle),
            )
        )
    return np.array(pts)
