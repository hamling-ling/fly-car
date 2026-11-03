"""Poster figure: three camera frames and the wheel signs they produced.

No speeds are printed. Forward is an upward arrow and reverse is a downward
arrow. A longer arrow is only the harder command, not a floor distance.

Frames, with people out of view:
- approach.jpg: red on the right, both wheels forward, left harder
  so the car arcs toward that red
  (flycar_q-20261103-091626, img 20261103-001634-155-287)
- frontal.jpg: blue across the frame, both wheels reverse together
  (flycar_q-20261103-103108, img 20261103-013120-722-391)
- side.jpg: blue on the left, the right wheel reverses harder
  (flycar_q-20261103-103108, img 20261103-013125-589-416)
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch
from PIL import Image

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT = Path(__file__).with_name("fig4_wheels")
FRAMES = Path(__file__).with_name("frames")

INK = "#1c1915"
PAPER = "#fbfaf6"

# sign is +1 forward or -1 reverse. strength is only relative.
PANELS = (
    ("接近", "approach.jpg", (("左", 1, 1.0), ("右", 1, 0.62))),
    ("正面からの後退", "frontal.jpg", (("左", -1, 1.0), ("右", -1, 1.0))),
    ("横からの後退", "side.jpg", (("左", -1, 0.62), ("右", -1, 1.0))),
)


def text(ax, x, y, s, size, ha="center", va="center"):
    ax.text(x, y, s, fontproperties=GOTHIC, fontsize=size, color=INK, ha=ha, va=va)


def wheels(ax, sides) -> None:
    ax.set_xlim(0, 2)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.set_facecolor(PAPER)
    # Tails of reverse arrows and heads of forward arrows share one line
    # just under the photo. Equal strengths then occupy the same span.
    top = 0.92
    full = 0.56
    for index, (label, sign, strength) in enumerate(sides):
        x = 0.55 + index * 0.9
        length = full * strength
        if sign > 0:
            start, end = (x, top - length), (x, top)
        else:
            start, end = (x, top), (x, top - length)
        ax.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=11,
                linewidth=1.8,
                color=INK,
                shrinkA=0,
                shrinkB=0,
                clip_on=True,
            )
        )
        text(ax, x, 0.14, label, 13)


def main() -> None:
    fig = plt.figure(figsize=(12.6, 4.55), facecolor=PAPER)
    grid = fig.add_gridspec(2, 3, height_ratios=(3.15, 1.25), hspace=0.02, wspace=0.18)
    for column, (title, name, sides) in enumerate(PANELS):
        image_ax = fig.add_subplot(grid[0, column])
        wheel_ax = fig.add_subplot(grid[1, column])
        image = np.asarray(Image.open(FRAMES / name))
        image_ax.imshow(image)
        image_ax.set_xticks([])
        image_ax.set_yticks([])
        image_ax.set_anchor("S")
        image_ax.set_title(title, fontproperties=GOTHIC, fontsize=15, color=INK, pad=6)
        for spine in image_ax.spines.values():
            spine.set_color("#c9c1b4")
            spine.set_linewidth(0.8)
        wheels(wheel_ax, sides)

    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.22)
    fig.savefig(OUT.with_suffix(".png"), dpi=140, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)


if __name__ == "__main__":
    main()
