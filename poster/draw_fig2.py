"""Poster figure: overhead path of a one-sided red approach.

The sphere sits to the right. Both wheels stay forward, the heading turns
toward the red, and the car stops once both halves reach the red fill.
Blue is absent, so the escape cells stay quiet. Coordinates on the page
put forward up and right to the right. World y is left-positive.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, Polygon
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flycar.behavior import RED_FILL
from flycar.fov import Blob, Scene, simulate

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT = Path(__file__).with_name("fig2_approach")

INK = "#1c1915"
MUTED = "#5e584f"
PAPER = "#fbfaf6"
WEDGE = "#e4ddd0"
WEDGE_START = "#efece3"
WEDGE_EDGE = "#8a8175"
RED = "#b4232c"
RED_SOFT = "#f0d2d0"
# The simulated approach is about a meter. On the page the start and the
# stop sit half that far apart, and the fans and the red move with them.
DRAW = 0.5


def text(ax, x, y, s, size, color=INK, ha="center", va="center"):
    ax.text(x, y, s, fontproperties=GOTHIC, fontsize=size, color=color, ha=ha, va=va)


def page(x: float, y: float) -> tuple[float, float]:
    """World (forward, left) to page (right, forward)."""
    return -y, x


def wedge(x: float, y: float, heading: float, reach: float, half: float) -> np.ndarray:
    """Camera field on the page. ``half`` is the horizontal half-angle."""
    angles = np.linspace(-half, half, 40)
    points = [page(x, y)]
    points += [
        page(x + reach * np.cos(heading + angle), y + reach * np.sin(heading + angle))
        for angle in angles
    ]
    return np.array(points)


def shorten(points: list[tuple[float, float]], back: float) -> list[tuple[float, float]]:
    """Drop the last ``back`` meters so an arrowhead can sit before the stop."""
    pts = [np.array(point, dtype=float) for point in points]
    remain = back
    for index in range(len(pts) - 1, 0, -1):
        step = float(np.linalg.norm(pts[index] - pts[index - 1]))
        if step >= remain:
            direction = pts[index] - pts[index - 1]
            direction /= np.linalg.norm(direction)
            end = pts[index] - direction * remain
            return [tuple(point) for point in pts[:index]] + [tuple(end)]
        remain -= step
    return [tuple(point) for point in pts]


def triangle(x: float, y: float, heading: float, length: float = 0.16) -> np.ndarray:
    forward = np.array([np.cos(heading), np.sin(heading)])
    left = np.array([-np.sin(heading), np.cos(heading)])
    nose = np.array([x, y])
    tail = nose - forward * length
    half = length * 0.38
    pts = (nose, tail + left * half, tail - left * half)
    return np.array([page(px, py) for px, py in pts])


def main() -> None:
    red = Blob((1.30, -0.40), 0.12)
    scene = Scene(red=red, blue=None, run_s=12.0)
    run = simulate(scene)
    moving = [sample for sample in run.samples if sample.mode != "stop"]
    stops = [sample for sample in run.samples if sample.mode == "stop"]
    if not moving or not stops:
        raise RuntimeError("the approach did not cruise and then stop")
    stop = stops[0]
    if not all(sample.v_left > 0.0 and sample.v_right > 0.0 for sample in moving):
        raise RuntimeError("a wheel reversed during the approach")
    if stop.red.left < RED_FILL or stop.red.right < RED_FILL:
        raise RuntimeError("the stop was not both red halves")
    if stop.heading >= 0.0 or stop.y >= 0.0:
        raise RuntimeError("the path did not turn toward the right-hand red")

    fig, ax = plt.subplots(figsize=(6.6, 7.8))
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)

    horizontal, _ = scene.fovs()
    half = horizontal / 2.0
    reach = 1.45 * DRAW
    start = run.samples[0]
    start_fan = wedge(start.x * DRAW, start.y * DRAW, start.heading, reach, half)
    stop_fan = wedge(stop.x * DRAW, stop.y * DRAW, stop.heading, reach, half)
    ax.add_patch(Polygon(start_fan, closed=True, facecolor=WEDGE_START, edgecolor="none", zorder=0))
    ax.add_patch(Polygon(stop_fan, closed=True, facecolor=WEDGE, edgecolor="none", zorder=0))
    ax.add_patch(
        Polygon(
            start_fan,
            closed=True,
            facecolor="none",
            edgecolor=WEDGE_EDGE,
            linewidth=1.1,
            linestyle=(0, (4, 2.5)),
            joinstyle="round",
            zorder=1,
        )
    )

    path = [page(sample.x * DRAW, sample.y * DRAW) for sample in run.samples[: len(moving) + 1]]
    shaft = shorten(path, 0.20)
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(shaft) - 1)
    ax.add_patch(
        FancyArrowPatch(
            path=MplPath(shaft, codes),
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=2.2,
            color=INK,
            shrinkA=0,
            shrinkB=0,
            capstyle="round",
            zorder=3,
        )
    )

    cx, cy = page(red.xy[0] * DRAW, red.xy[1] * DRAW)
    ax.add_patch(Circle((cx, cy), red.radius, facecolor=RED_SOFT, edgecolor=RED, lw=1.8, zorder=2))
    text(ax, cx, cy + red.radius + 0.08, "赤", 14, RED)

    for sample, face in ((start, PAPER), (stop, INK)):
        ax.add_patch(
            Polygon(
                triangle(sample.x * DRAW, sample.y * DRAW, sample.heading),
                closed=True,
                facecolor=face,
                edgecolor=INK,
                lw=1.3,
                zorder=4,
            )
        )

    start_body = triangle(start.x * DRAW, start.y * DRAW, start.heading)
    start_right = start_body[int(np.argmax(start_body[:, 0]))]
    text(ax, start_right[0] + 0.04, start_right[1], "開始", 13, INK, ha="left", va="center")
    body = triangle(stop.x * DRAW, stop.y * DRAW, stop.heading)
    rightmost = body[int(np.argmax(body[:, 0]))]
    text(ax, rightmost[0] + 0.04, rightmost[1], "停止", 13, INK, ha="left", va="center")
    text(ax, -0.20 * DRAW, 0.70 * DRAW, "開始時の\n画角", 11, MUTED, ha="center", va="center")
    # Left of the stop fan's centerline, past the 赤 caption. The disc kept
    # its radius, so a uniformly scaled offset would sit on that caption.
    inward = float(np.arctan2(0.10, 0.85))
    reach_label = 0.58
    direction = stop.heading + inward
    sx, sy = page(
        stop.x * DRAW + reach_label * np.cos(direction),
        stop.y * DRAW + reach_label * np.sin(direction),
    )
    text(ax, sx, sy, "停止時の\n画角", 11, MUTED, ha="center", va="center")

    span = np.vstack([start_fan, stop_fan])
    pad = 0.12
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(span[:, 0].min() - pad, span[:, 0].max() + pad)
    ax.set_ylim(min(span[:, 1].min(), -0.28) - 0.04, span[:, 1].max() + pad)
    ax.set_xlabel("x", fontproperties=GOTHIC, fontsize=13, color=INK, labelpad=8)
    ax.set_ylabel("y", fontproperties=GOTHIC, fontsize=13, color=INK, labelpad=8)
    ax.tick_params(bottom=False, left=False, labelbottom=False, labelleft=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c9c1b4")
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(GOTHIC)
        label.set_color(MUTED)

    fig.tight_layout()
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.25)
    fig.savefig(OUT.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    main()
