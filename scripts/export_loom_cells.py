#!/usr/bin/env python3
"""Write the LC4 and LPLC2 table the car loads.

The robot does not read the synapse feather. This script turns the camera
caches and the loom-circuit edges into ``src/flycar/loom_cells.npz``.

Each row is one optic-lobe column of one cell. Posts that share a column
share an image position, so they are stored as a count. The cell weight is
the chemical synapse count onto the ipsilateral DNp01.

Run from the repository root, after ``build_camera_map.py`` and
``extract_gf_loom.py``:

    python3 scripts/export_loom_cells.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.feather as feather

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
OUT = ROOT / "src" / "flycar" / "loom_cells.npz"

_SPEC = importlib.util.spec_from_file_location(
    "build_camera_map", ROOT / "scripts" / "build_camera_map.py"
)
_BUILD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BUILD)
image_uv = _BUILD.image_uv


def _weights(type_name: str, neurons: pd.DataFrame, edges: pd.DataFrame) -> dict[int, float]:
    pre = neurons.loc[neurons.type == type_name, ["bodyId", "side"]].rename(
        columns={"bodyId": "body_pre", "side": "side_pre"}
    )
    post = neurons.loc[neurons.type == "DNp01", ["bodyId", "side"]].rename(
        columns={"bodyId": "body_post", "side": "side_post"}
    )
    part = edges.merge(pre, on="body_pre").merge(post, on="body_post")
    if not (part.side_pre == part.side_post).all():
        raise SystemExit(f"{type_name} has a contralateral edge onto DNp01.")
    if not part.nt_sign.eq(1).all():
        raise SystemExit(f"{type_name} onto DNp01 is not all excitatory.")
    totals = part.groupby("body_pre")["weight"].sum()
    return {int(body): float(weight) for body, weight in totals.items()}


def _group(body, ab, side, u, v) -> dict[str, np.ndarray]:
    order = np.lexsort((ab[:, 1], ab[:, 0], side, body))
    body = body[order]
    ab = ab[order]
    side = side[order]
    u = u[order]
    v = v[order]
    break_at = np.empty(len(body), dtype=bool)
    break_at[0] = True
    break_at[1:] = (
        (body[1:] != body[:-1])
        | (side[1:] != side[:-1])
        | (ab[1:, 0] != ab[:-1, 0])
        | (ab[1:, 1] != ab[:-1, 1])
    )
    index = np.flatnonzero(break_at)
    count = np.diff(np.r_[index, len(body)]).astype(np.int32)
    grouped_body = body[index]
    cell_break = np.empty(len(grouped_body), dtype=bool)
    cell_break[0] = True
    cell_break[1:] = grouped_body[1:] != grouped_body[:-1]
    starts = np.flatnonzero(cell_break).astype(np.int64)
    cell_side = side[index][starts]
    if np.any(np.maximum.reduceat(side[index], starts) != np.minimum.reduceat(side[index], starts)):
        raise SystemExit("a cell spans both eyes.")
    return {
        "u": np.ascontiguousarray(u[index], dtype=np.float64),
        "v": np.ascontiguousarray(v[index], dtype=np.float64),
        "n": count,
        "starts": starts,
        "side": cell_side.astype(np.int8),
        "body": grouped_body[starts].astype(np.int64),
    }


def _attach(group: dict[str, np.ndarray], weight_of: dict[int, float], label: str) -> None:
    missing = [int(body) for body in group["body"] if int(body) not in weight_of]
    if missing:
        raise SystemExit(f"{label} cells with no DNp01 edge, first {missing[:5]}.")
    group["w"] = np.array([weight_of[int(body)] for body in group["body"]], dtype=np.float64)


def _pack(cache: np.lib.npyio.NpzFile, keys: tuple[str, ...], weight_of: dict[int, float], label: str):
    body = cache[keys[0]]
    ab = cache[keys[1]]
    side = cache[keys[2]]
    u, v = image_uv(ab, side, cache[keys[3]], cache[keys[4]])
    group = _group(body, ab, side, u, v)
    _attach(group, weight_of, label)
    return group, u, v, body, side


def _covered(group: dict[str, np.ndarray], cu: float, cv: float, ru: float, rv: float) -> np.ndarray:
    du = (group["u"] - cu) / ru
    dv = (group["v"] - cv) / rv
    inside = ((du * du + dv * dv) <= 1.0).astype(np.float64)
    covered_n = np.add.reduceat(group["n"] * inside, group["starts"])
    cell_n = np.add.reduceat(group["n"].astype(np.float64), group["starts"])
    frac = covered_n / cell_n
    out = np.zeros(2, dtype=np.float64)
    for code in (0, 1):
        chosen = group["side"] == code
        out[code] = float(frac[chosen] @ group["w"][chosen])
    return out


def _covered_posts(u, v, body, side, weights, cu, cv, ru, rv) -> np.ndarray:
    order = np.argsort(body, kind="mergesort")
    body = body[order]
    u = u[order]
    v = v[order]
    side = side[order]
    cuts = np.r_[0, np.flatnonzero(np.diff(body)) + 1]
    cell_n = np.diff(np.r_[cuts, len(body)]).astype(np.float64)
    du = (u - cu) / ru
    dv = (v - cv) / rv
    inside = ((du * du + dv * dv) <= 1.0).astype(np.float64)
    frac = np.add.reduceat(inside, cuts) / cell_n
    cell_side = side[cuts]
    cell_w = np.array([weights[int(item)] for item in body[cuts]], dtype=np.float64)
    out = np.zeros(2, dtype=np.float64)
    for code in (0, 1):
        chosen = cell_side == code
        out[code] = float(frac[chosen] @ cell_w[chosen])
    return out


def main() -> None:
    neurons_path = DATA / "gf-loom" / "neurons.feather"
    edges_path = DATA / "gf-loom" / "edges.feather"
    lc4_path = DATA / "lc4-camera" / "lc4_lobula_posts.npz"
    lplc2_path = DATA / "lplc2-camera" / "lplc2_lobula_posts.npz"
    for path in (neurons_path, edges_path, lc4_path, lplc2_path):
        if not path.is_file():
            raise SystemExit(f"missing {path}. Build the camera map and the loom cut first.")
    neurons = feather.read_table(neurons_path).to_pandas()
    edges = feather.read_table(edges_path).to_pandas()
    lc4_w = _weights("LC4", neurons, edges)
    lplc_w = _weights("LPLC2", neurons, edges)
    lc4_cache = np.load(lc4_path)
    lplc_cache = np.load(lplc2_path)
    lc4, lc4_u, lc4_v, lc4_body, lc4_side = _pack(
        lc4_cache, ("body", "ab", "side", "left_ab", "right_ab"), lc4_w, "LC4"
    )
    lplc, lplc_u, lplc_v, lplc_body, lplc_side = _pack(
        lplc_cache,
        ("lop_body", "lop_ab", "lop_side", "lop_left_ab", "lop_right_ab"),
        lplc_w,
        "LPLC2",
    )
    disk = (0.25, 0.50, 0.20, 0.30)
    lc4_group = _covered(lc4, *disk)
    lc4_posts = _covered_posts(lc4_u, lc4_v, lc4_body, lc4_side, lc4_w, *disk)
    lplc_group = _covered(lplc, *disk)
    lplc_posts = _covered_posts(lplc_u, lplc_v, lplc_body, lplc_side, lplc_w, *disk)
    if not np.allclose(lc4_group, lc4_posts) or not np.allclose(lplc_group, lplc_posts):
        raise SystemExit(
            f"grouped columns disagree with posts: LC4 {lc4_group} {lc4_posts}, "
            f"LPLC2 {lplc_group} {lplc_posts}"
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT,
        lc4_u=lc4["u"],
        lc4_v=lc4["v"],
        lc4_n=lc4["n"],
        lc4_starts=lc4["starts"],
        lc4_side=lc4["side"],
        lc4_body=lc4["body"],
        lc4_w=lc4["w"],
        lplc2_u=lplc["u"],
        lplc2_v=lplc["v"],
        lplc2_n=lplc["n"],
        lplc2_starts=lplc["starts"],
        lplc2_side=lplc["side"],
        lplc2_body=lplc["body"],
        lplc2_w=lplc["w"],
    )
    left = float(lc4["w"][lc4["side"] == 0].sum() + lplc["w"][lplc["side"] == 0].sum())
    right = float(lc4["w"][lc4["side"] == 1].sum() + lplc["w"][lplc["side"] == 1].sum())
    print(
        f"wrote {OUT.relative_to(ROOT)}  "
        f"LC4 {len(lc4['body'])} cells, {len(lc4['u'])} columns  "
        f"LPLC2 {len(lplc['body'])} cells, {len(lplc['u'])} columns  "
        f"W_side L {left:.0f} R {right:.0f}"
    )


if __name__ == "__main__":
    main()
