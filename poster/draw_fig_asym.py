"""Left-right asymmetry of the LC4 / LPLC2 weights, for the poster.

Writes fig_lplc2_asym (each eye's F plotted against distance from its own
edge; mirror-symmetric eyes would overlap) and fig_lplc2_ratio (the mirror
ratio F_left(x) / F_right(1 - x); 1 is mirror-symmetric).

A blue disk of fixed angular size is swept across the frame and read with
the same column drive as the car (flycar.loom). D is the distance of a
0.15 m radius disk: D = 0.6 is theta = 0.49 rad, D = 1.0 is theta = 0.30 rad.

Run from the repository root:

    python3 poster/draw_fig_asym.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import flycar.loom as loom  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
DISK_RADIUS = 0.15
DISTANCES = (0.6, 1.0)


def sweep(population, distance: float):
    """F on each side for a disk swept across the frame at one size."""
    tan_h, tan_v = loom.camera_tangents()
    theta = 2.0 * math.atan(DISK_RADIUS / distance)
    ru = DISK_RADIUS / distance / tan_h / 2.0
    rv = DISK_RADIUS / distance / tan_v / 2.0
    cus = np.arange(0.03, 0.971, 0.01)
    left = np.empty(len(cus))
    right = np.empty(len(cus))
    for i, cu in enumerate(cus):
        disk = loom.Disk(cu=float(cu), cv=0.5, ru=ru, rv=rv, theta=theta)
        f = population.column_drive(loom.raster(disk))
        left[i], right[i] = f[0], f[1]
    return cus, left, right


def save(fig, stem: str) -> None:
    out = OUT_DIR / stem
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.18)
    fig.savefig(out.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    print(f"wrote {stem}.pdf / .png")


def mirror_plot(cells) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, population, name in (
        (axes[0], cells.lplc2, "LPLC2"),
        (axes[1], cells.lc4, "LC4"),
    ):
        for distance, style, alpha in ((0.6, "-", 1.0), (1.0, "--", 0.65)):
            cus, left, right = sweep(population, distance)
            ax.plot(cus, left, style, color="#c0392b", alpha=alpha,
                    label=f"left eye (from left), D={distance}")
            ax.plot(1.0 - cus, right, style, color="#2471a3", alpha=alpha,
                    label=f"right eye (from right), D={distance}")
        ax.axvline(0.5, color="gray", lw=0.7, ls=":")
        ax.set_xlabel("distance from own edge (disk centre position)")
        ax.set_title(name)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7.5)
    axes[0].set_ylabel("F (share of side's synapse weight covered)")
    fig.suptitle("Each eye plotted from its own edge — mirror-symmetric eyes would overlap")
    fig.tight_layout()
    save(fig, "fig_lplc2_asym")


def ratio_plot(cells) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, population, name in (
        (axes[0], cells.lplc2, "LPLC2"),
        (axes[1], cells.lc4, "LC4"),
    ):
        for distance, style in ((0.6, "-"), (1.0, "--")):
            cus, left, right = sweep(population, distance)
            mirrored = right[::-1]  # right eye at the mirror position 1 - x
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(mirrored > 0.02, left / np.maximum(mirrored, 1e-9), np.nan)
            ax.plot(cus, ratio, style, color="#7d3c98",
                    label=f"L/R mirror ratio, D={distance}")
        ax.axhline(1.0, color="gray", lw=0.8)
        ax.axvline(0.5, color="gray", lw=0.7, ls=":")
        ax.set_ylim(0.7, 1.35)
        ax.set_xlabel("distance from left edge (disk centre position)")
        ax.set_title(name)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("F_left(x) / F_right(1 - x)")
    axes[0].annotate("1.09 at centre (D=0.6)", xy=(0.5, 1.09), xytext=(0.52, 1.2),
                     arrowprops=dict(arrowstyle="->", lw=0.8), fontsize=9)
    fig.suptitle("Mirror ratio: 1.00 = perfectly mirror-symmetric")
    fig.tight_layout()
    save(fig, "fig_lplc2_ratio")


def main() -> None:
    cells = loom.cells()
    mirror_plot(cells)
    ratio_plot(cells)


if __name__ == "__main__":
    main()
