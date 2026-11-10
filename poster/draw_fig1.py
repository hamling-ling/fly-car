"""Poster figure: the motion model from camera to wheels.

The camera and the motors are the physical layers. Red halves become ORN
and PN concentrations, and the ipsilateral PN minus the contralateral PN
is the DNa02 current. LC4 carries expansion, and LPLC2 carries angular
size, into the ipsilateral DNp01 current. Red firing drives both wheels
forward, and the yaw from the concentration difference stops at a cap.
Blue firing drives the opposite wheel backward. No numbers.
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
    text(ax, 1.42, 4.15, "カメラ", 20, weight="medium")
    text(ax, 1.42, 3.35, "赤と青の画素", 13)

    box(ax, 13.85, 1.85, 2.15, 3.7, PHYSICAL, LINE, lw=1.8)
    text(ax, 14.92, 6.15, "物理", 15, MUTED)
    text(ax, 14.92, 4.15, "モーター", 20, weight="medium")
    text(ax, 14.92, 3.35, "左輪と右輪", 13)

    # Two lanes: approach on top, escape below.
    box(ax, 3.85, 4.05, 2.7, 1.85, WHITE, RED, lw=1.8)
    text(ax, 5.2, 5.52, "接近の電流", 15, RED, weight="medium")
    text(ax, 5.2, 4.98, "左右の濃度を ORN へ", 12)
    text(ax, 5.2, 4.58, "同側の PN から", 12)
    text(ax, 5.2, 4.22, "反対側の PN を引く", 12)

    box(ax, 3.85, 1.55, 2.7, 1.85, WHITE, BLUE, lw=1.8)
    text(ax, 5.2, 3.02, "逃避の電流", 15, BLUE, weight="medium")
    text(ax, 5.2, 2.48, "LC4 は拡大", 12)
    text(ax, 5.2, 2.08, "LPLC2 は視角の大きさ", 12)
    text(ax, 5.2, 1.72, "同側の DNp01 へ", 12)

    box(ax, 7.35, 4.05, 2.35, 1.85, WHITE, RED, lw=1.8)
    text(ax, 8.52, 5.4, "DNa02", 18, weight="medium")
    text(ax, 8.52, 4.85, "左と右", 13)
    text(ax, 8.52, 4.4, "接近", 13, RED)

    box(ax, 7.35, 1.55, 2.35, 1.85, WHITE, BLUE, lw=1.8)
    text(ax, 8.52, 2.9, "DNp01", 18, weight="medium")
    text(ax, 8.52, 2.35, "左と右", 13)
    text(ax, 8.52, 1.9, "逃避", 13, BLUE)

    box(ax, 10.4, 1.55, 2.05, 4.35, WHITE, LINE, lw=1.8)
    text(ax, 11.42, 5.35, "車輪速度", 15, weight="medium")
    text(ax, 11.42, 4.55, "赤は両輪が前へ", 12)
    text(ax, 11.42, 4.00, "差は回頭の上限まで", 12)
    text(ax, 11.42, 3.45, "青は反対の輪が後へ", 12)
    text(ax, 11.42, 2.90, "頭は赤へ向く", 12)

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
