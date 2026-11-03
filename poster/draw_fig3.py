"""Poster figure: escape paths while a blue disk keeps expanding.

A static sphere does not expand, and one eye then stays under threshold, so
the side path is not a sphere sitting in the world. Both traces hold the
loom current the cells emit for that disk. The solid circle is that near
disk. One circle of the same radius, farther along the same ray, is the
earlier position, and the blue arrow points toward the car. The radii match
because the axes are a top view. Each panel also draws the camera field:
the start fan is a paler fill with a dashed edge, and the stop fan is the
darker fill with no edge. The radius is short enough that the arc stays
inside the axes. No distance is printed. Forward is up on the page and
right is to the right. World y is left-positive.

The centered disk is 30° at 0.4 rad/s for 1.2 s: both wheels reverse and
the heading stays put. The right-eye disk is 20° at 0.4 rad/s for the first
0.25 s: both wheels reverse, the left wheel faster, and the nose yaws left,
away from the blue. A longer hold keeps turning.
"""

import sys
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, Polygon
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flycar.behavior import DT, Plant
from flycar.loom import Disk, camera_tangents, cells

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT = Path(__file__).with_name("fig3_escape")

INK = "#1c1915"
MUTED = "#5e584f"
PAPER = "#fbfaf6"
WEDGE = "#e4ddd0"
WEDGE_START = "#efece3"
WEDGE_EDGE = "#8a8175"
BLUE = "#1d5f99"
BLUE_SOFT = "#d4e4f5"
EXPANSION = 0.4
BLUE_RADIUS = 0.12
MARKER = 0.16


def text(ax, x, y, s, size, color=INK, ha="center", va="center"):
    ax.text(x, y, s, fontproperties=GOTHIC, fontsize=size, color=color, ha=ha, va=va)


def disk(theta_deg: float, cu: float) -> Disk:
    """Equal-area disk of ``theta_deg`` centered at image ``cu``."""
    tan_h, tan_v = camera_tangents()
    theta = float(np.deg2rad(theta_deg))
    cx = (cu * 2.0 - 1.0) * tan_h
    rod = float(np.tan(theta / 2.0) * np.sqrt(1.0 + cx * cx))
    return Disk(cu, 0.5, rod / tan_h / 2.0, rod / tan_v / 2.0, theta)


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


def _ray_box(px: float, py: float, vx: float, vy: float, bounds) -> float:
    """Distance from ``(px, py)`` along ``(vx, vy)`` until the frame."""
    lo_x, hi_x, lo_y, hi_y = bounds
    limits = []
    if vx > 1e-9:
        limits.append((hi_x - px) / vx)
    elif vx < -1e-9:
        limits.append((lo_x - px) / vx)
    if vy > 1e-9:
        limits.append((hi_y - py) / vy)
    elif vy < -1e-9:
        limits.append((lo_y - py) / vy)
    positive = [t for t in limits if t > 1e-4]
    if not positive:
        raise RuntimeError("a fan ray does not meet the frame")
    return min(positive)


def fan_reach(poses, half: float, xlim, ylim, inset: float = 0.02) -> float:
    """Largest shared radius whose arc stays inside the axes."""
    bounds = (xlim[0] + inset, xlim[1] - inset, ylim[0] + inset, ylim[1] - inset)
    reach = np.inf
    for pose in poses:
        ox, oy = page(pose.x, pose.y)
        for angle in np.linspace(-half, half, 61):
            theta = pose.heading + float(angle)
            reach = min(reach, _ray_box(ox, oy, -np.sin(theta), np.cos(theta), bounds))
    return float(reach)


def draw_fields(ax, start, stop, half: float, reach: float) -> None:
    """Start fan pale with a dashed edge. Stop fan darker, with no edge."""
    start_fan = wedge(start.x, start.y, start.heading, reach, half)
    stop_fan = wedge(stop.x, stop.y, stop.heading, reach, half)
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


def triangle(x: float, y: float, heading: float, length: float = MARKER) -> np.ndarray:
    forward = np.array([np.cos(heading), np.sin(heading)])
    left = np.array([-np.sin(heading), np.cos(heading)])
    nose = np.array([x, y])
    tail = nose - forward * length
    half = length * 0.38
    pts = (nose, tail + left * half, tail - left * half)
    return np.array([page(float(px), float(py)) for px, py in pts])


def trace(loom: tuple[float, float], seconds: float):
    plant = Plant()
    n = int(round(seconds / DT))
    samples = []
    for i in range(n):
        step = plant.step(0.0, 0.0, 0.0, 0.0, loom=loom)
        if i % 20 == 0 or i == n - 1:
            samples.append(step)
    return samples


def draw_path(ax, samples) -> None:
    """Arrow beside the bodies, as long as the reverse itself.

    The marker is longer than this short move, so a shaft drawn on the
    path sits inside the triangles.
    """
    points = np.array([page(sample.x, sample.y) for sample in samples])
    direction = points[-1] - points[0]
    direction = direction / np.linalg.norm(direction)
    side = np.array([direction[1], -direction[0]])
    offset = side * (MARKER * 0.38 + 0.05)
    start = points[0] + offset
    end = points[-1] + offset
    ax.add_patch(
        FancyArrowPatch(
            tuple(start),
            tuple(end),
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=2.2,
            color=INK,
            shrinkA=0,
            shrinkB=0,
            zorder=5,
        )
    )


def _lower_chain(points: np.ndarray) -> np.ndarray:
    """Lower edge of the convex hull, left to right."""
    ordered = sorted((tuple(point) for point in points), key=lambda p: (p[0], p[1]))

    def cross(origin, a, b) -> float:
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    chain = []
    for point in ordered:
        while len(chain) >= 2 and cross(chain[-2], chain[-1], point) <= 0:
            chain.pop()
        chain.append(point)
    return np.array(chain)


def _smooth(points: np.ndarray, steps: int = 8) -> np.ndarray:
    """Catmull-Rom samples through ``points``, including both ends."""
    knots = np.vstack([points[0], points, points[-1]])
    samples = []
    for i in range(1, len(knots) - 2):
        p0, p1, p2, p3 = knots[i - 1], knots[i], knots[i + 1], knots[i + 2]
        for t in np.linspace(0.0, 1.0, steps, endpoint=False):
            t2 = t * t
            t3 = t2 * t
            samples.append(
                0.5
                * (
                    2 * p1
                    + (-p0 + p2) * t
                    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
                )
            )
    samples.append(points[-1])
    return np.array(samples)


def yaw_arrow(ax, samples) -> None:
    """Arc around the outside of the turning triangles.

    The noses barely move, so a straight arrow hides the turn. The bases
    swing out, and this curve follows that outer edge. It stops short of
    the rightmost corner so the head stays outside the black triangle.
    """
    bodies = [triangle(sample.x, sample.y, sample.heading) for sample in samples]
    pivot = np.mean([body[0] for body in bodies], axis=0)
    chain = _lower_chain(np.vstack([body[1:] for body in bodies]))
    outward = chain - pivot
    outward /= np.linalg.norm(outward, axis=1)[:, None]
    offset = chain + outward * 0.03
    edge = offset[-1] - offset[-2]
    length = float(np.linalg.norm(edge))
    stop = offset[-2] + edge * max(length - 0.06, length * 0.45) / length
    points = _smooth(np.vstack([offset[:-1], stop]))
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1)
    ax.add_patch(
        FancyArrowPatch(
            path=MplPath(points, codes),
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=2.2,
            color=INK,
            zorder=5,
        )
    )


def blue_circle(ax, center) -> None:
    ax.add_patch(
        Circle(
            center,
            BLUE_RADIUS,
            facecolor=BLUE_SOFT,
            edgecolor=BLUE,
            linewidth=1.8,
            zorder=2,
        )
    )


def approach(ax, center) -> None:
    """Draw the same blue farther out, at the same radius, coming toward the nose.

    The solid disk stays put. The earlier disk is the same size because this
    is a top view. The arrow sits beside the two disks.
    """
    here = np.asarray(center, dtype=float)
    dist = float(np.linalg.norm(here))
    away = here / dist
    side = np.array([away[1], -away[0]])
    extra = 0.14
    ax.add_patch(
        Circle(
            tuple(away * (dist + extra)),
            BLUE_RADIUS,
            facecolor="#e7f1f8",
            edgecolor=BLUE,
            linewidth=1.8,
            zorder=1,
        )
    )
    offset = side * (BLUE_RADIUS + 0.035)
    start = away * (dist + extra) + offset
    end = away * dist + offset
    ax.add_patch(
        FancyArrowPatch(
            tuple(start),
            tuple(end),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.6,
            color=BLUE,
            zorder=3,
            shrinkA=0,
            shrinkB=0,
        )
    )


def draw_body(ax, sample, face) -> None:
    ax.add_patch(
        Polygon(
            triangle(sample.x, sample.y, sample.heading),
            closed=True,
            facecolor=face,
            edgecolor=INK,
            lw=1.3,
            zorder=4,
        )
    )


def style(ax, xlim=(-1.0, 1.0), ylim=(-1.0, 1.0)) -> None:
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xlabel("x", fontproperties=GOTHIC, fontsize=12, color=INK, labelpad=6)
    ax.set_ylabel("y", fontproperties=GOTHIC, fontsize=12, color=INK, labelpad=6)
    ax.tick_params(bottom=False, left=False, labelbottom=False, labelleft=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c9c1b4")
    ax.set_facecolor(PAPER)


def main() -> None:
    center = cells().current(disk(30.0, 0.5), EXPANSION)
    side = cells().current(disk(20.0, 0.75), EXPANSION)
    straight = trace(center, 1.2)
    turned = trace(side, 0.25)

    if min(center) <= 1.0 or abs(straight[-1].heading) > 1e-3:
        raise RuntimeError("the frontal loom did not back straight")
    if not all(sample.v_left < 0.0 and sample.v_right < 0.0 for sample in straight[2:]):
        raise RuntimeError("a frontal wheel was not reversing")
    if side[0] != 0.0 or side[1] <= 1.0:
        raise RuntimeError("the right-hand loom did not stay on one eye")
    if not all(sample.v_left < sample.v_right < 0.0 for sample in turned[2:]):
        raise RuntimeError("the far wheel was not the one reversing harder")
    if turned[-1].heading < np.deg2rad(30.0):
        raise RuntimeError("the nose did not yaw away from the right-hand blue")

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 7.2))
    fig.patch.set_facecolor(PAPER)

    # Same reach on both panels, so the blue sits the same distance from
    # the nose. The side disk stays on the right edge of the field.
    half = float(np.arctan(camera_tangents()[0]))
    reach = 0.32
    side_blue = (reach * np.sin(half), reach * np.cos(half))
    frame = dict(xlim=(-0.5, 0.5), ylim=(-0.40, 0.60))

    # Draw the reverse twice as long as the trace. No distance is printed.
    start = straight[0]
    end = straight[-1]
    backed = replace(
        end,
        x=start.x + 2.0 * (end.x - start.x),
        y=start.y + 2.0 * (end.y - start.y),
    )
    fan = fan_reach(
        (turned[0], turned[-1], start, backed),
        half,
        frame["xlim"],
        frame["ylim"],
    )

    front, lateral = axes
    draw_fields(front, start, backed, half, fan)
    approach(front, (0.0, 0.32))
    blue_circle(front, (0.0, 0.32))
    draw_path(front, (start, backed))
    draw_body(front, start, PAPER)
    draw_body(front, backed, INK)
    front.set_title("正面から青を近づける", fontproperties=GOTHIC, fontsize=15, color=INK, pad=10)
    start_body = triangle(straight[0].x, straight[0].y, straight[0].heading)
    start_edge = start_body[int(np.argmax(start_body[:, 0]))]
    text(front, start_edge[0] + 0.04, start_edge[1], "開始", 13, ha="left", va="center")
    end_edge = triangle(backed.x, backed.y, backed.heading)
    end_edge_pt = end_edge[int(np.argmax(end_edge[:, 0]))]
    text(front, end_edge_pt[0] + 0.04, end_edge_pt[1], "停止", 13, ha="left", va="center")

    draw_fields(lateral, turned[0], turned[-1], half, fan)
    approach(lateral, side_blue)
    blue_circle(lateral, side_blue)
    shown = (turned[0], turned[len(turned) // 2], turned[-1])
    yaw_arrow(lateral, shown)
    for sample in shown[:2]:
        draw_body(lateral, sample, PAPER)
    draw_body(lateral, shown[-1], INK)
    lateral.set_title("横から青を近づける", fontproperties=GOTHIC, fontsize=15, color=INK, pad=10)
    turn_start = triangle(turned[0].x, turned[0].y, turned[0].heading)
    turn_left = turn_start[int(np.argmin(turn_start[:, 0]))]
    text(lateral, turn_left[0] - 0.04, turn_left[1], "開始", 13, ha="right", va="center")
    turn_end = triangle(turned[-1].x, turned[-1].y, turned[-1].heading)
    turn_right = turn_end[int(np.argmax(turn_end[:, 0]))]
    text(lateral, turn_right[0] + 0.04, turn_right[1], "停止", 13, ha="left", va="center")

    style(front, **frame)
    style(lateral, **frame)

    fig.tight_layout()
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.22)
    fig.savefig(OUT.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)


if __name__ == "__main__":
    main()
