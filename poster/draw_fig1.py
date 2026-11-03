"""Poster figure: the motion model from camera to wheels.

The camera and the motors are the physical layers. Everything between them
is the model: pixel to current, the four cells, and firing rate to wheel speed.
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT = Path(__file__).with_name("fig1_model")

INK = "#1c1915"
MUTED = "#5e584f"
PAPER = "#fbfaf6"
MODEL = "#f3efe4"
PHYSICAL = "#e6e1d6"
WHITE = "#fffcf7"
RED = "#b4232c"
BLUE = "#1d5f99"
LINE = "#2a2622"


def text(ax, x, y, s, size, color=INK, ha="center", va="center", weight="regular"):
    ax.text(
        x,
        y,
        s,
        fontproperties=GOTHIC,
        fontsize=size,
        color=color,
        ha=ha,
        va=va,
        fontweight=weight,
        linespacing=1.35,
    )


def box(ax, x, y, w, h, face, edge, lw=1.6, radius=0.12):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        facecolor=face,
        edgecolor=edge,
        linewidth=lw,
        mutation_aspect=0.72,
    )
    ax.add_patch(patch)


def arrow(ax, x0, x1, y, color=LINE):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y),
            (x1, y),
            arrowstyle="-|>",
            mutation_scale=16,
            linewidth=1.6,
            color=color,
            shrinkA=0,
            shrinkB=0,
            clip_on=False,
        )
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(16.4, 7.4))
    ax.set_xlim(0, 16.4)
    ax.set_ylim(0, 7.4)
    ax.set_axis_off()
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)

    # The middle span is the motion model. The ends are the physical layers.
    box(ax, 3.55, 0.95, 9.15, 5.55, MODEL, "#d9d0c0", lw=1.2, radius=0.16)
    text(ax, 8.12, 6.15, "動作モデル", 18, INK, weight="medium")

    box(ax, 0.35, 1.85, 2.15, 3.7, PHYSICAL, LINE, lw=1.8)
    text(ax, 1.42, 6.15, "物理", 15, MUTED)
    text(ax, 1.42, 4.55, "カメラ", 20, weight="medium")
    text(ax, 1.42, 3.85, "赤と青の画素", 13)
    text(ax, 1.42, 2.55, "0.10 秒ごと", 12, MUTED)

    box(ax, 13.85, 1.85, 2.15, 3.7, PHYSICAL, LINE, lw=1.8)
    text(ax, 14.92, 6.15, "物理", 15, MUTED)
    text(ax, 14.92, 4.55, "モーター", 20, weight="medium")
    text(ax, 14.92, 3.85, "左輪と右輪", 13)
    text(ax, 14.92, 2.55, "0.02 秒ごと", 12, MUTED)

    # Two lanes: approach on top, escape below.
    box(ax, 3.85, 4.05, 2.7, 1.85, WHITE, RED, lw=1.8)
    text(ax, 5.2, 5.45, "接近の電流", 15, RED, weight="medium")
    text(ax, 5.2, 4.85, "左右の占有", 13)
    text(ax, 5.2, 4.4, r"$I = \tilde{c}\,/\,c_{\mathrm{ref}}$", 14)

    box(ax, 3.85, 1.55, 2.7, 1.85, WHITE, BLUE, lw=1.8)
    text(ax, 5.2, 2.95, "逃避の電流", 15, BLUE, weight="medium")
    text(ax, 5.2, 2.35, r"視角 $\theta$ と拡大 $\dot\theta$", 13)
    text(ax, 5.2, 1.9, "LC4 と LPLC2 の重み", 12, MUTED)

    box(ax, 7.35, 4.05, 2.35, 1.85, WHITE, RED, lw=1.8)
    text(ax, 8.52, 5.4, "DNa02", 18, weight="medium")
    text(ax, 8.52, 4.85, "左と右", 13)
    text(ax, 8.52, 4.4, "接近", 13, RED)

    box(ax, 7.35, 1.55, 2.35, 1.85, WHITE, BLUE, lw=1.8)
    text(ax, 8.52, 2.9, "DNp01", 18, weight="medium")
    text(ax, 8.52, 2.35, "左と右", 13)
    text(ax, 8.52, 1.9, "逃避", 13, BLUE)

    box(ax, 10.4, 1.55, 2.05, 4.35, WHITE, LINE, lw=1.8)
    text(ax, 11.42, 5.4, "車輪速度", 15, weight="medium")
    text(ax, 11.42, 4.75, "赤の和は前進", 13)
    text(ax, 11.42, 4.25, "青の和は後退", 13)
    text(ax, 11.42, 3.7, "赤の差は旋回", 13)
    text(ax, 11.42, 3.15, "青の差は反対の\n輪を後退", 12.5)
    text(ax, 11.42, 2.15, "赤が左右を\n埋めたら停止", 12, MUTED)

    arrow(ax, 2.5, 3.85, 4.95, RED)
    arrow(ax, 2.5, 3.85, 2.5, BLUE)
    text(ax, 3.15, 5.25, "画素", 11, RED)
    text(ax, 3.15, 2.2, "画素", 11, BLUE)

    arrow(ax, 6.55, 7.35, 4.95, RED)
    arrow(ax, 6.55, 7.35, 2.5, BLUE)
    text(ax, 6.95, 5.25, "電流", 11, RED)
    text(ax, 6.95, 2.2, "電流", 11, BLUE)

    arrow(ax, 9.7, 10.4, 4.95, RED)
    arrow(ax, 9.7, 10.4, 2.5, BLUE)
    text(ax, 10.05, 5.28, "発火率", 10, RED)
    text(ax, 10.05, 2.18, "発火率", 10, BLUE)

    arrow(ax, 12.45, 13.85, 3.7, LINE)
    text(ax, 13.15, 4.05, "左右の速度", 11, INK)

    text(ax, 8.12, 1.15, "膜は 1 ms。発火率は 50 ms で平滑する。", 12, MUTED)

    text(
        ax,
        8.2,
        0.42,
        "カメラの画素は DNa02 と DNp01 の電流になり、その発火率は左右の車輪の速度になる。",
        13,
        INK,
    )

    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.25)
    fig.savefig(OUT.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    main()
