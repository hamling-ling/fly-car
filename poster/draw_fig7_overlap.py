"""Trial plot: landing points moved onto the overlapping eye fields.

The brain position of each cell stays. On the plane, each eye is stretched
from its lateral edge so that the old midline maps to 1/2+δ past center.
Left landings use u' = u (1/2+δ)/(1/2). Right landings use the mirror.
δ is only for this picture.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

import draw_fig7 as fig7

# Each eye extends this far past the center, in units of image width.
# The shared band is 2δ wide. δ = 0.15 makes that band 0.3 of the image,
# about 15° of the 52° horizontal field.
DELTA = 0.15
# Columns in the voxel picture only. Not a bin width of the model.
N_VOXEL = 20
OUT = Path(__file__).with_name("fig_overlap")

LEFT = (0.27, 0.46, 0.68)
RIGHT = (0.72, 0.27, 0.29)
BAND = (0.45, 0.32, 0.55)
LEFT_DOT = "#1a3f66"
RIGHT_DOT = "#7a2428"


def widen(u: np.ndarray) -> np.ndarray:
    """Stretch each eye from its lateral edge onto an interval wider than half."""
    scale = (0.5 + DELTA) / 0.5
    out = np.empty_like(u, dtype=np.float64)
    left = u <= 0.5
    out[left] = u[left] * scale
    out[~left] = 1.0 - (1.0 - u[~left]) * scale
    return out


def _xy(u, v, xmin, xmax, ymin, ymax):
    x = xmax - np.asarray(u, dtype=np.float64) * (xmax - xmin)
    y = ymax - np.asarray(v, dtype=np.float64) * (ymax - ymin)
    return x, y


def _sheet(ax, u0, u1, z, xmin, xmax, ymin, ymax, color, alpha):
    uu = np.linspace(u0, u1, 30)
    vv = np.linspace(0.0, 1.0, 20)
    ug, vg = np.meshgrid(uu, vv)
    xx, yy = _xy(ug, vg, xmin, xmax, ymin, ymax)
    zz = np.full_like(xx, z)
    face = np.zeros(ug.shape + (4,))
    face[..., 0] = color[0]
    face[..., 1] = color[1]
    face[..., 2] = color[2]
    face[..., 3] = alpha
    ax.plot_surface(
        xx, yy, zz, facecolors=face, shade=False, linewidth=0, antialiased=False, zorder=1
    )


def _loop(ax, u_edge, v_edge, z, xmin, xmax, ymin, ymax, color, lw):
    x, y = _xy(u_edge, v_edge, xmin, xmax, ymin, ymax)
    ax.plot(x, y, np.full(len(x), z), color=color, lw=lw, zorder=3)


def draw(ax, cell_xyz, cell_u, cell_v, syn, title: str) -> None:
    ax.computed_zorder = False
    xmin, xmax = float(syn[:, 0].min()), float(syn[:, 0].max())
    ymin, ymax = float(syn[:, 1].min()), float(syn[:, 1].max())
    z_lo = float(syn[:, 2].min()) - 120.0
    span = xmax - xmin
    landed = widen(cell_u)

    _sheet(ax, 0.0, 0.5 - DELTA, z_lo, xmin, xmax, ymin, ymax, LEFT, 0.72)
    _sheet(ax, 0.5 + DELTA, 1.0, z_lo, xmin, xmax, ymin, ymax, RIGHT, 0.72)
    _sheet(ax, 0.5 - DELTA, 0.5 + DELTA, z_lo, xmin, xmax, ymin, ymax, BAND, 0.78)

    land_x, land_y = _xy(landed, cell_v, xmin, xmax, ymin, ymax)
    for point, px, py, cu in zip(cell_xyz, land_x, land_y, cell_u):
        ax.plot(
            [point[0], px],
            [point[1], py],
            [point[2], z_lo],
            color=plt.cm.coolwarm(float(cu)),
            lw=0.6,
            alpha=0.55,
            zorder=2,
        )
    ax.scatter(
        cell_xyz[:, 0],
        cell_xyz[:, 1],
        cell_xyz[:, 2],
        s=18,
        c=cell_u,
        cmap="coolwarm",
        vmin=0.0,
        vmax=1.0,
        edgecolors=fig7.INK,
        linewidths=0.25,
        depthshade=False,
        zorder=4,
    )
    left = cell_u <= 0.5
    for mask, color in ((left, LEFT_DOT), (~left, RIGHT_DOT)):
        ax.scatter(
            land_x[mask],
            land_y[mask],
            np.full(int(mask.sum()), z_lo),
            s=22,
            c=color,
            depthshade=False,
            linewidths=0.3,
            edgecolors=fig7.INK,
            zorder=5,
        )

    _loop(
        ax,
        [0.0, 1.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0, 0.0],
        z_lo,
        xmin, xmax, ymin, ymax,
        fig7.INK,
        0.7,
    )
    _loop(
        ax,
        [0.0, 0.5 + DELTA, 0.5 + DELTA, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0, 0.0],
        z_lo,
        xmin, xmax, ymin, ymax,
        LEFT,
        1.4,
    )
    _loop(
        ax,
        [0.5 - DELTA, 1.0, 1.0, 0.5 - DELTA, 0.5 - DELTA],
        [0.0, 0.0, 1.0, 1.0, 0.0],
        z_lo,
        xmin, xmax, ymin, ymax,
        RIGHT,
        1.4,
    )
    for edge in (0.5 - DELTA, 0.5 + DELTA):
        x, y = _xy([edge, edge], [0.0, 1.0], xmin, xmax, ymin, ymax)
        ax.plot(x, y, [z_lo, z_lo], color=fig7.INK, lw=0.8, zorder=3)
    x, y = _xy([0.5, 0.5], [0.0, 1.0], xmin, xmax, ymin, ymax)
    ax.plot(x, y, [z_lo, z_lo], color=fig7.INK, lw=0.7, ls="--", zorder=3)

    tx, ty = _xy(0.5, 1.08, xmin, xmax, ymin, ymax)
    ax.text(
        float(tx),
        float(ty),
        z_lo,
        "重なり",
        fontproperties=fig7.GOTHIC,
        fontsize=12,
        color=fig7.INK,
        ha="center",
        va="bottom",
        zorder=6,
        bbox={"facecolor": fig7.PAPER, "edgecolor": "none", "alpha": 0.92, "pad": 0.6},
    )

    # Same 180° turn as the rear view: the fly's left eye is on the left.
    ax.view_init(elev=18, azim=110)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_major_locator(fig7.MaxNLocator(nbins=4))
    box = np.array([span, ymax - ymin, float(syn[:, 2].max()) - z_lo])
    ax.set_box_aspect(box / box.max())
    ax.set_xlabel("x (μm)", fontsize=10, labelpad=8)
    ax.set_ylabel("y (μm)", fontsize=10, labelpad=4)
    ax.set_zlabel("z (μm)", fontsize=10, labelpad=8)
    ax.set_title(
        title,
        fontproperties=fig7.GOTHIC,
        fontsize=13,
        color=fig7.INK,
        pad=6,
    )
    ax.set_facecolor(fig7.PAPER)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.label.set_fontproperties(fig7.GOTHIC)
        axis.label.set_color(fig7.INK)
        axis.pane.set_facecolor((0.985, 0.98, 0.965, 0.95))
        axis.pane.set_edgecolor(fig7.SPINE)
        for label in axis.get_ticklabels():
            label.set_fontproperties(fig7.GOTHIC)
            label.set_color(fig7.MUTED)
            label.set_fontsize(8)


def _bands(ax) -> None:
    ax.axvspan(0.0, 0.5 - DELTA, color=LEFT, alpha=0.22, lw=0, zorder=0)
    ax.axvspan(0.5 + DELTA, 1.0, color=RIGHT, alpha=0.22, lw=0, zorder=0)
    ax.axvspan(0.5 - DELTA, 0.5 + DELTA, color=BAND, alpha=0.38, lw=0, zorder=0)
    ax.axvline(0.5, color=fig7.INK, lw=0.7, ls="--", zorder=1)
    ax.axvline(0.5 - DELTA, color=fig7.INK, lw=0.6, zorder=1)
    ax.axvline(0.5 + DELTA, color=fig7.INK, lw=0.6, zorder=1)


def _style_plane(ax) -> None:
    ax.set_facecolor(fig7.PAPER)
    for spine in ax.spines.values():
        spine.set_color(fig7.SPINE)
    ax.tick_params(colors=fig7.MUTED, labelsize=9, length=2, width=0.6)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(fig7.GOTHIC)
        label.set_color(fig7.MUTED)


def draw_voxels(ax, cell_u, show_ylabel: bool) -> None:
    """Bar per column. Height is the cell count. Overlap stacks both eyes."""
    landed = widen(cell_u)
    left = cell_u <= 0.5
    edges = np.linspace(0.0, 1.0, N_VOXEL + 1)
    n_left = np.empty(N_VOXEL, dtype=np.float64)
    n_right = np.empty(N_VOXEL, dtype=np.float64)
    for index, (start, stop) in enumerate(zip(edges[:-1], edges[1:])):
        take = (landed >= start) & (landed < stop if stop < 1.0 else landed <= stop)
        n_left[index] = (take & left).sum()
        n_right[index] = (take & ~left).sum()
    mids = (edges[:-1] + edges[1:]) / 2.0
    width = float(edges[1] - edges[0]) * 0.82
    _bands(ax)
    ax.bar(
        mids, n_left, width=width, color=LEFT_DOT, edgecolor=fig7.INK, linewidth=0.35, zorder=2
    )
    ax.bar(
        mids,
        n_right,
        width=width,
        bottom=n_left,
        color=RIGHT_DOT,
        edgecolor=fig7.INK,
        linewidth=0.35,
        zorder=2,
    )
    peak = float(np.max(n_left + n_right))
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, peak + 1.5)
    ax.set_xticks([0.0, 0.5, 1.0], ["左端", "中央", "右端"])
    ax.yaxis.set_major_locator(fig7.MaxNLocator(nbins=4, integer=True))
    if show_ylabel:
        ax.set_ylabel("細胞の数", fontproperties=fig7.GOTHIC, fontsize=11, color=fig7.INK, labelpad=8)
    else:
        ax.set_ylabel("")
    _style_plane(ax)


def _panel(spec, title: str):
    _soma, _bg, _cell_soma, cell_u, cell_v, cell_xyz, syn_all, _syn, _syn_u = fig7.load(spec)
    landed = widen(cell_u)
    left = cell_u <= 0.5
    band = (landed >= 0.5 - DELTA) & (landed <= 0.5 + DELTA)
    print(
        f"{title}  left u' [{landed[left].min():.3f}, {landed[left].max():.3f}]  "
        f"right u' [{landed[~left].min():.3f}, {landed[~left].max():.3f}]  "
        f"in band L {int((band & left).sum())} R {int((band & ~left).sum())}"
    )
    return cell_u, cell_v, cell_xyz, syn_all


def main() -> None:
    panels = (
        (fig7.LC4, "LC4"),
        (fig7.LPLC2, "LPLC2"),
    )
    loaded = [(name, *_panel(spec, name)) for spec, name in panels]
    fig = plt.figure(figsize=(12.6, 9.6))
    fig.patch.set_facecolor(fig7.PAPER)
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=(1.0, 1.0),
        height_ratios=(1.65, 0.72),
        wspace=0.24,
        hspace=0.18,
    )
    for column, (name, cell_u, cell_v, cell_xyz, syn_all) in enumerate(loaded):
        ax_map = fig.add_subplot(grid[0, column], projection="3d")
        ax_bars = fig.add_subplot(grid[1, column])
        draw(ax_map, cell_xyz, cell_u, cell_v, syn_all, name)
        draw_voxels(ax_bars, cell_u, show_ylabel=(column == 0))
    handles = [
        Line2D([0], [0], color=LEFT, lw=6, alpha=0.85, label="左の視野"),
        Line2D([0], [0], color=RIGHT, lw=6, alpha=0.85, label="右の視野"),
        Line2D([0], [0], color=BAND, lw=6, alpha=0.9, label="重なり"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=LEFT_DOT, markeredgecolor=fig7.INK, markersize=7, label="左の細胞"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=RIGHT_DOT, markeredgecolor=fig7.INK, markersize=7, label="右の細胞"),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        frameon=False,
        prop=fig7.GOTHIC,
        fontsize=11,
        labelcolor=fig7.INK,
        ncol=5,
    )
    fig.text(
        0.5,
        0.02,
        "上は接合部の平均から平面への対応、下は各列の細胞数。重なる列は左右を積み上げている。重なりの全幅は 0.3",
        ha="center",
        fontproperties=fig7.GOTHIC,
        fontsize=11,
        color=fig7.MUTED,
    )
    fig.subplots_adjust(left=0.05, right=0.98, top=0.91, bottom=0.07)
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.25)
    fig.savefig(OUT.with_suffix(".png"), dpi=140, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    main()
