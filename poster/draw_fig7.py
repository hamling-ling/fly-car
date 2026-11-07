"""Poster figure: LC4 and LPLC2, both seen from behind, on one sheet.

Gray points are a thinned set of other cell bodies. Large points are the
cell's somas. Small points are its postsynapses. Color is the image
left-right coordinate of the column the postsynapse sits in. LC4 junctions
are in the lobula. LPLC2 junctions are in the lobula plate. The screen
mapping lives in draw_fig7_overlap.py.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyarrow.feather as feather
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GOTHIC = FontProperties(fname="/usr/share/fonts/truetype/fonts-japanese-gothic.ttf")
OUT = Path(__file__).with_name("fig7_lobula")
ANN = ROOT / "data" / "malecns" / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
CACHE = ROOT / "data" / "malecns" / "lc4-camera" / "lc4_lobula_posts.npz"

INK = "#1c1915"
MUTED = "#5e584f"
PAPER = "#fbfaf6"
SPINE = "#c9c1b4"
UM = 8.0 / 1000.0
BG_N = 25_000
SYN_N = 12_000

# Native MaleCNS axes: +x is the fly's left, +y is ventral, +z is posterior.
# The rear view is the x-y plane from +z, turned 180° on the page so dorsal
# is up and the fly's right eye is on the right. A downward arrow marks
# ventral. The other views stay from the positive missing axis.
VIEWS = (
    (0, 1, "x", "y", "後ろから", False),
    (0, 2, "x", "z", "上から", True),
    (1, 2, "y", "z", "左から", True),
)


def image_uv(ab, side, left_ab, right_ab):
    """Image position of each postsynapse. u is 0 at the left edge, v at the top."""
    u = np.empty(len(ab), dtype=np.float64)
    v = np.empty(len(ab), dtype=np.float64)
    for code, grid in ((0, left_ab), (1, right_ab)):
        valid = grid[:, 0] >= 0
        a0, a1 = grid[valid, 0].min(), grid[valid, 0].max()
        b0, b1 = grid[valid, 1].min(), grid[valid, 1].max()
        mask = side == code
        lateral = (ab[mask, 0] - a0) / (a1 - a0)
        if code == 0:
            u[mask] = 0.5 * (1.0 - lateral)
        else:
            u[mask] = 0.5 + 0.5 * lateral
        v[mask] = (ab[mask, 1] - b0) / (b1 - b0)
    return u, v


def load(spec: dict):
    """Somas, a thinned brain outline, and one cell type's postsynapses in micrometres."""
    rng = np.random.default_rng(0)
    ann = feather.read_table(ANN, columns=["bodyId", "type", "somaLocation"]).to_pandas()
    soma_rows = []
    for value in ann.somaLocation:
        if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3:
            soma_rows.append([float(value[0]), float(value[1]), float(value[2])])
        else:
            soma_rows.append([np.nan, np.nan, np.nan])
    soma = np.asarray(soma_rows, dtype=np.float64) * UM
    has_soma = np.isfinite(soma).all(axis=1)
    own = (ann.type == spec["cell_type"]).to_numpy() & has_soma
    bg_pool = np.flatnonzero(has_soma & ~own)
    bg = soma[rng.choice(bg_pool, size=BG_N, replace=False)]

    pack = np.load(spec["cache"])
    syn_um = pack[spec["xyz"]].astype(np.float64) * UM
    u, v = image_uv(pack[spec["ab"]], pack[spec["side"]], pack[spec["left"]], pack[spec["right"]])
    order = np.argsort(pack[spec["body"]], kind="mergesort")
    body_s = pack[spec["body"]][order]
    syn_s = syn_um[order]
    u_s, v_s = u[order], v[order]
    cuts = np.flatnonzero(np.diff(body_s)) + 1
    groups = np.split(np.arange(len(body_s)), cuts)
    cell_id = np.array([body_s[g[0]] for g in groups])
    cell_u = np.array([u_s[g].mean() for g in groups])
    cell_v = np.array([v_s[g].mean() for g in groups])
    cell_xyz = np.array([syn_s[g].mean(axis=0) for g in groups])
    id_to_soma = {
        int(body): soma[index]
        for index, body in enumerate(ann.bodyId.to_numpy())
        if own[index]
    }
    missing = [int(body) for body in cell_id if int(body) not in id_to_soma]
    if missing:
        raise RuntimeError(f"{len(missing)} {spec['cell_type']} cells have no soma")
    cell_soma = np.array([id_to_soma[int(body)] for body in cell_id])
    syn_take = rng.choice(len(syn_um), size=SYN_N, replace=False)
    return soma, bg, cell_soma, cell_u, cell_v, cell_xyz, syn_um, syn_um[syn_take], u[syn_take]


def style_view(ax) -> None:
    ax.set_facecolor(PAPER)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(colors=MUTED, labelsize=8, length=2, width=0.6)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(GOTHIC)
        label.set_color(MUTED)
    for spine in ax.spines.values():
        spine.set_color(SPINE)
    ax.xaxis.label.set_fontproperties(GOTHIC)
    ax.yaxis.label.set_fontproperties(GOTHIC)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def draw_views(axes, soma, bg, cell_soma, cell_u, syn, syn_u, norm, title: str) -> None:
    limits = []
    for i, j, _, _, _, _ in VIEWS:
        pad_i = 0.02 * (np.nanmax(soma[:, i]) - np.nanmin(soma[:, i]))
        pad_j = 0.02 * (np.nanmax(soma[:, j]) - np.nanmin(soma[:, j]))
        limits.append(
            (
                (np.nanmin(soma[:, i]) - pad_i, np.nanmax(soma[:, i]) + pad_i),
                (np.nanmin(soma[:, j]) - pad_j, np.nanmax(soma[:, j]) + pad_j),
            )
        )
    for ax, (i, j, xl, yl, view, anterior_down), (xlim, ylim) in zip(axes, VIEWS, limits):
        ax.scatter(bg[:, i], bg[:, j], s=1, c="0.78", linewidths=0, rasterized=True, zorder=1)
        ax.scatter(
            syn[:, i],
            syn[:, j],
            s=7,
            c=syn_u,
            cmap="coolwarm",
            norm=norm,
            alpha=0.75,
            linewidths=0,
            rasterized=True,
            zorder=2,
        )
        ax.scatter(
            cell_soma[:, i],
            cell_soma[:, j],
            s=28,
            c=cell_u,
            cmap="coolwarm",
            norm=norm,
            linewidths=0.35,
            edgecolors=INK,
            zorder=3,
        )
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        if view == "後ろから":
            ax.invert_xaxis()
            ax.invert_yaxis()
        ax.set_xlabel(f"{xl} (μm)", fontsize=10, labelpad=2)
        ax.set_ylabel(f"{yl} (μm)", fontsize=10, labelpad=2)
        style_view(ax)
        ax.text(
            0.98,
            0.98,
            view,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontproperties=GOTHIC,
            fontsize=12,
            color=INK,
            zorder=5,
            bbox={"facecolor": PAPER, "edgecolor": "none", "pad": 1.2, "alpha": 0.9},
        )
        if anterior_down:
            ax.annotate(
                "",
                xy=(0.07, 0.58),
                xytext=(0.07, 0.80),
                xycoords=ax.transAxes,
                arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 1.1, "mutation_scale": 9},
                zorder=5,
            )
            ax.text(
                0.10,
                0.66,
                "前",
                transform=ax.transAxes,
                ha="left",
                va="center",
                fontproperties=GOTHIC,
                fontsize=12,
                color=INK,
                zorder=5,
            )
        else:
            ax.annotate(
                "",
                xy=(0.08, 0.08),
                xytext=(0.08, 0.28),
                xycoords=ax.transAxes,
                arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 1.1, "mutation_scale": 9},
                zorder=5,
            )
            ax.text(
                0.11,
                0.18,
                "下",
                transform=ax.transAxes,
                ha="left",
                va="center",
                fontproperties=GOTHIC,
                fontsize=12,
                color=INK,
                zorder=5,
            )
        if view == "左から":
            ax.annotate(
                "",
                xy=(0.92, 0.10),
                xytext=(0.72, 0.10),
                xycoords=ax.transAxes,
                arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 1.1, "mutation_scale": 9},
                zorder=5,
            )
            ax.text(
                0.68,
                0.10,
                "下",
                transform=ax.transAxes,
                ha="right",
                va="center",
                fontproperties=GOTHIC,
                fontsize=12,
                color=INK,
                zorder=5,
            )
    axes[0].set_title(
        title,
        fontproperties=GOTHIC,
        fontsize=13,
        color=INK,
        loc="left",
        pad=6,
    )


def draw_plane(ax, cell_xyz, cell_u, cell_v, syn, norm) -> None:
    ax.computed_zorder = False
    xmin, xmax = float(syn[:, 0].min()), float(syn[:, 0].max())
    ymin, ymax = float(syn[:, 1].min()), float(syn[:, 1].max())
    z_plane = float(syn[:, 2].min()) - 120.0
    uu = np.linspace(0.0, 1.0, 80)
    vv = np.linspace(0.0, 1.0, 40)
    uu_grid, vv_grid = np.meshgrid(uu, vv)
    xx = xmax - uu_grid * (xmax - xmin)
    yy = ymax - vv_grid * (ymax - ymin)
    zz = np.full_like(xx, z_plane)
    face = plt.cm.coolwarm(norm(uu_grid))
    face[..., 3] = 0.92
    land_x = xmax - cell_u * (xmax - xmin)
    land_y = ymax - cell_v * (ymax - ymin)
    for point, px, py, cu in zip(cell_xyz, land_x, land_y, cell_u):
        ax.plot(
            [point[0], px],
            [point[1], py],
            [point[2], z_plane],
            color=plt.cm.coolwarm(norm(float(cu))),
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
        norm=norm,
        edgecolors=INK,
        linewidths=0.25,
        depthshade=False,
        zorder=4,
    )
    ax.plot_surface(
        xx, yy, zz, facecolors=face, shade=False, linewidth=0, antialiased=False, zorder=1
    )
    ax.scatter(
        land_x,
        land_y,
        np.full(len(land_x), z_plane),
        s=18,
        c=INK,
        depthshade=False,
        linewidths=0,
        zorder=3,
    )
    border_u = np.array([0.0, 1.0, 1.0, 0.0, 0.0])
    border_v = np.array([0.0, 0.0, 1.0, 1.0, 0.0])
    ax.plot(
        xmax - border_u * (xmax - xmin),
        ymax - border_v * (ymax - ymin),
        np.full(5, z_plane),
        color=INK,
        lw=0.7,
        zorder=2,
    )
    ax.plot(
        [xmax - 0.5 * (xmax - xmin), xmax - 0.5 * (xmax - xmin)],
        [ymax, ymin],
        [z_plane, z_plane],
        color=INK,
        lw=0.6,
        zorder=2,
    )
    ax.view_init(elev=18, azim=-70)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_major_locator(MaxNLocator(nbins=4))
    span = np.array([xmax - xmin, ymax - ymin, float(syn[:, 2].max()) - z_plane])
    ax.set_box_aspect(span / span.max())
    ax.set_xlabel("x (μm)", fontsize=10, labelpad=8)
    ax.set_ylabel("y (μm)", fontsize=10, labelpad=16)
    ax.set_zlabel("z (μm)", fontsize=10, labelpad=8)
    ax.set_title(
        "接合部の平均位置から平面へのマッピング",
        fontproperties=GOTHIC,
        fontsize=13,
        color=INK,
        pad=6,
    )
    ax.set_facecolor(PAPER)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.label.set_fontproperties(GOTHIC)
        axis.label.set_color(INK)
        axis.pane.set_facecolor((0.985, 0.98, 0.965, 0.95))
        axis.pane.set_edgecolor(SPINE)
        for label in axis.get_ticklabels():
            label.set_fontproperties(GOTHIC)
            label.set_color(MUTED)
            label.set_fontsize(8)


LC4 = {
    "cache": CACHE,
    "out": OUT,
    "cell_type": "LC4",
    "body": "body",
    "xyz": "xyz",
    "ab": "ab",
    "side": "side",
    "left": "left_ab",
    "right": "right_ab",
    "title": "LC4 の細胞体と小葉後シナプス",
    "legend_soma": "LC4 の細胞体",
    "legend_syn": "LC4 の小葉後シナプス",
}

LPLC2 = {
    "cache": ROOT / "data" / "malecns" / "lplc2-camera" / "lplc2_lobula_posts.npz",
    "out": Path(__file__).with_name("fig8_plate"),
    "cell_type": "LPLC2",
    "body": "lop_body",
    "xyz": "lop_xyz",
    "ab": "lop_ab",
    "side": "lop_side",
    "left": "lop_left_ab",
    "right": "lop_right_ab",
    "title": "LPLC2 の細胞体と小葉板後シナプス",
    "legend_soma": "LPLC2 の細胞体",
    "legend_syn": "LPLC2 の小葉板後シナプス",
}


def render_pair() -> None:
    """LC4 and LPLC2, both from behind, on one sheet."""
    norm = Normalize(vmin=0.0, vmax=1.0)
    fig = plt.figure(figsize=(14.4, 6.1))
    fig.patch.set_facecolor(PAPER)
    grid = fig.add_gridspec(
        1,
        3,
        width_ratios=(1.0, 1.0, 0.035),
        wspace=0.22,
        left=0.04,
        right=0.97,
        top=0.84,
        bottom=0.10,
    )
    legend = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="0.78", markersize=5, label="脳の外形"),
    ]
    for column, spec in enumerate((LC4, LPLC2)):
        soma, bg, cell_soma, cell_u, _v, _xyz, _all, syn, syn_u = load(spec)
        view = fig.add_subplot(grid[0, column])
        draw_views([view], soma, bg, cell_soma, cell_u, syn, syn_u, norm, spec["title"])
        legend.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#4c72b0",
                markeredgecolor=INK,
                markeredgewidth=0.6,
                markersize=8,
                label=spec["legend_soma"],
            )
        )
        legend.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#c44e52",
                markersize=4,
                label=spec["legend_syn"],
            )
        )
    fig.legend(
        handles=legend,
        loc="upper center",
        bbox_to_anchor=(0.48, 0.98),
        frameon=False,
        prop=GOTHIC,
        fontsize=11,
        labelcolor=INK,
        ncol=5,
    )
    scale = fig.add_subplot(grid[0, 2])
    colorbar = fig.colorbar(
        ScalarMappable(norm=norm, cmap="coolwarm"),
        cax=scale,
    )
    colorbar.set_label("画面の左右", fontproperties=GOTHIC, fontsize=11, color=INK)
    colorbar.set_ticks([0, 0.5, 1], labels=["左端", "中央", "右端"])
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(GOTHIC)
        label.set_color(MUTED)
        label.set_fontsize(10)
    colorbar.outline.set_color(SPINE)
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.25)
    fig.savefig(OUT.with_suffix(".png"), dpi=140, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def main() -> None:
    render_pair()


if __name__ == "__main__":
    main()
