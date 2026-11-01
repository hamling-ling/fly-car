#!/usr/bin/env python3
"""Map LC4 and LPLC2 onto the camera from MaleCNS optic-lobe columns.

Synapse coordinates come from syn-points. Each postsynapse already carries a
lobula or lobula-plate column label, ``LO_*_col_a_b``. The cell's image
position is the mean of those column indices, not a fit to its soma.

Column ``a`` increases toward the lateral eye. The left edge of the image is
the left eye's maximum ``a``, the center is both eyes' minimum ``a``, and the
right edge is the right eye's maximum ``a``. Column ``b`` increases downward.
The range is every column in that neuropil, including columns the cell type
never touches.

A postsynapse labeled on both sides of the brain is kept on the left. Column
centroid sums count every postsynapse in the column, not only LC4 or LPLC2.
The dictionary is taken from the first record batch, which is how the camera
notebooks built the caches.

The vertical band stretch drawn in those notebooks is not applied here. The
loom notebooks use this unstretched map.

Existing caches are reused. ``--rebuild`` scans the synapse table again.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
ANNOTATIONS = DATA / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
SYNAPSES = DATA / "syn-points-male-cns-v1.0-minconf-0.5.feather"
LC4_CACHE = DATA / "lc4-camera" / "lc4_lobula_posts.npz"
LPLC2_CACHE = DATA / "lplc2-camera" / "lplc2_lobula_posts.npz"
CELLS = DATA / "camera-map" / "cells.csv"

LOBULA = ("lobula_l_column", "lobula_r_column")
PLATE = ("lobula_plate_l_column", "lobula_plate_r_column")
COLUMN_FIELDS = LOBULA + PLATE
SIDE_NAME = {0: "L", 1: "R"}


def parse_column_labels(labels: list) -> np.ndarray:
    """Return ``(a, b)`` for each dictionary entry. Missing labels are ``-1``."""
    parsed = np.full((len(labels), 2), -1, dtype=np.int16)
    for index, text in enumerate(labels):
        if not text or text == "<unspecified>":
            continue
        first, second = str(text).split("_")[-2:]
        parsed[index, 0] = int(first)
        parsed[index, 1] = int(second)
    return parsed


def image_uv(ab, side, left_ab, right_ab):
    """Map column indices to image coordinates.

    ``u`` is 0 at the left edge and 1 at the right edge. ``v`` is 0 at the top.
    """
    u = np.empty(len(ab), dtype=np.float64)
    v = np.empty(len(ab), dtype=np.float64)
    for code, grid in ((0, left_ab), (1, right_ab)):
        valid = grid[:, 0] >= 0
        a0 = int(grid[valid, 0].min())
        a1 = int(grid[valid, 0].max())
        b0 = int(grid[valid, 1].min())
        b1 = int(grid[valid, 1].max())
        chosen = side == code
        lateral = (ab[chosen, 0] - a0) / (a1 - a0)
        if code == 0:
            u[chosen] = 0.5 * (1.0 - lateral)
        else:
            u[chosen] = 0.5 + 0.5 * lateral
        v[chosen] = (ab[chosen, 1] - b0) / (b1 - b0)
    return u, v


def _ids(cell_type: str) -> np.ndarray:
    table = feather.read_table(ANNOTATIONS, columns=["bodyId", "type"])
    body = table.column("bodyId").to_numpy()
    types = table.column("type").to_pylist()
    chosen = np.array([item == cell_type for item in types], dtype=bool)
    return np.sort(body[chosen].astype(np.int64, copy=False))


def _member(sorted_ids: np.ndarray, values: np.ndarray) -> np.ndarray:
    at = np.searchsorted(sorted_ids, values)
    at = np.clip(at, 0, len(sorted_ids) - 1)
    return sorted_ids[at] == values


def _append_side(store, body, x, y, z, hit, use_left, left_ab, right_ab, left_i, right_i) -> None:
    count = int(hit.sum())
    aa = np.empty(count, dtype=np.int16)
    bb = np.empty(count, dtype=np.int16)
    ss = np.empty(count, dtype=np.int8)
    left_hit = left_i[hit]
    right_hit = right_i[hit]
    aa[use_left] = left_ab[left_hit[use_left], 0]
    bb[use_left] = left_ab[left_hit[use_left], 1]
    ss[use_left] = 0
    aa[~use_left] = right_ab[right_hit[~use_left], 0]
    bb[~use_left] = right_ab[right_hit[~use_left], 1]
    ss[~use_left] = 1
    store["body"].append(body[hit])
    store["xyz"].append(np.column_stack([x[hit], y[hit], z[hit]]).astype(np.int32))
    store["ab"].append(np.column_stack([aa, bb]))
    store["side"].append(ss)


def scan_synapses() -> dict:
    if not ANNOTATIONS.exists() or not SYNAPSES.exists():
        raise SystemExit("Run scripts/download_malecns.py before building the camera map.")
    lc4_ids = _ids("LC4")
    lplc2_ids = _ids("LPLC2")
    source = pa.memory_map(str(SYNAPSES), "r")
    reader = pa.ipc.open_file(source)
    first = reader.get_batch(0)
    post = first.column("kind").dictionary.to_pylist().index("PostSyn")
    label_text = {name: first.column(name).dictionary.to_pylist() for name in COLUMN_FIELDS}
    grids = {name: parse_column_labels(text) for name, text in label_text.items()}
    sums = {name: np.zeros((len(grid), 3), dtype=np.float64) for name, grid in grids.items()}
    counts = {name: np.zeros(len(grid), dtype=np.int64) for name, grid in grids.items()}
    kept = {
        key: {"body": [], "xyz": [], "ab": [], "side": []}
        for key in ("lc4", "lo", "lop")
    }
    batches = reader.num_record_batches
    print(f"scanning {batches} synapse batches", flush=True)
    for index in range(batches):
        batch = reader.get_batch(index)
        kind = batch.column("kind").indices.to_numpy(zero_copy_only=False)
        keep = kind == post
        body = batch.column("body").to_numpy()
        x = batch.column("x").to_numpy()
        y = batch.column("y").to_numpy()
        z = batch.column("z").to_numpy()
        column_index = {
            name: batch.column(name).indices.to_numpy(zero_copy_only=False) for name in COLUMN_FIELDS
        }
        on = {name: keep & (grids[name][column_index[name], 0] >= 0) for name in COLUMN_FIELDS}
        for name in COLUMN_FIELDS:
            chosen = on[name]
            if not chosen.any():
                continue
            np.add.at(sums[name], column_index[name][chosen], np.column_stack([x[chosen], y[chosen], z[chosen]]))
            np.add.at(counts[name], column_index[name][chosen], 1)
        lc4_hit = _member(lc4_ids, body) & (on["lobula_l_column"] | on["lobula_r_column"])
        if lc4_hit.any():
            _append_side(
                kept["lc4"], body, x, y, z, lc4_hit,
                on["lobula_l_column"][lc4_hit],
                grids["lobula_l_column"], grids["lobula_r_column"],
                column_index["lobula_l_column"], column_index["lobula_r_column"],
            )
        lplc2_hit = _member(lplc2_ids, body) & keep
        for key, left_name, right_name in (
            ("lo", "lobula_l_column", "lobula_r_column"),
            ("lop", "lobula_plate_l_column", "lobula_plate_r_column"),
        ):
            hit = lplc2_hit & (on[left_name] | on[right_name])
            if not hit.any():
                continue
            _append_side(
                kept[key], body, x, y, z, hit,
                on[left_name][hit],
                grids[left_name], grids[right_name],
                column_index[left_name], column_index[right_name],
            )
        if batches > 1 and (index + 1) % 500 == 0:
            print(f"  batch {index + 1}/{batches}", flush=True)
    source.close()

    def cat(key: str, field: str, dtype):
        return np.concatenate(kept[key][field]).astype(dtype, copy=False)

    return {
        "labels": label_text,
        "grids": grids,
        "sums": sums,
        "counts": counts,
        "lc4_body": cat("lc4", "body", np.int64),
        "lc4_xyz": cat("lc4", "xyz", np.int32),
        "lc4_ab": cat("lc4", "ab", np.int16),
        "lc4_side": cat("lc4", "side", np.int8),
        "lo_body": cat("lo", "body", np.int64),
        "lo_xyz": cat("lo", "xyz", np.int32),
        "lo_ab": cat("lo", "ab", np.int16),
        "lo_side": cat("lo", "side", np.int8),
        "lop_body": cat("lop", "body", np.int64),
        "lop_xyz": cat("lop", "xyz", np.int32),
        "lop_ab": cat("lop", "ab", np.int16),
        "lop_side": cat("lop", "side", np.int8),
    }


def save_caches(scanned: dict) -> None:
    LC4_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LPLC2_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        LC4_CACHE,
        body=scanned["lc4_body"],
        xyz=scanned["lc4_xyz"],
        ab=scanned["lc4_ab"],
        side=scanned["lc4_side"],
        left_sum=scanned["sums"]["lobula_l_column"],
        left_count=scanned["counts"]["lobula_l_column"],
        right_sum=scanned["sums"]["lobula_r_column"],
        right_count=scanned["counts"]["lobula_r_column"],
        left_ab=scanned["grids"]["lobula_l_column"],
        right_ab=scanned["grids"]["lobula_r_column"],
        left_labels=np.array(scanned["labels"]["lobula_l_column"], dtype=object),
        right_labels=np.array(scanned["labels"]["lobula_r_column"], dtype=object),
    )
    grids = scanned["grids"]
    sums = scanned["sums"]
    counts = scanned["counts"]
    np.savez_compressed(
        LPLC2_CACHE,
        lo_body=scanned["lo_body"],
        lo_xyz=scanned["lo_xyz"],
        lo_ab=scanned["lo_ab"],
        lo_side=scanned["lo_side"],
        lop_body=scanned["lop_body"],
        lop_xyz=scanned["lop_xyz"],
        lop_ab=scanned["lop_ab"],
        lop_side=scanned["lop_side"],
        lo_left_ab=grids["lobula_l_column"],
        lo_right_ab=grids["lobula_r_column"],
        lop_left_ab=grids["lobula_plate_l_column"],
        lop_right_ab=grids["lobula_plate_r_column"],
        lo_left_sum=sums["lobula_l_column"],
        lo_left_count=counts["lobula_l_column"],
        lo_right_sum=sums["lobula_r_column"],
        lo_right_count=counts["lobula_r_column"],
        lop_left_sum=sums["lobula_plate_l_column"],
        lop_left_count=counts["lobula_plate_l_column"],
        lop_right_sum=sums["lobula_plate_r_column"],
        lop_right_count=counts["lobula_plate_r_column"],
    )


def cell_rows(body, ab, side, left_ab, right_ab, cell_type: str) -> list[dict]:
    u, v = image_uv(ab, side, left_ab, right_ab)
    order = np.argsort(body, kind="mergesort")
    body_s = body[order]
    u_s = u[order]
    v_s = v[order]
    side_s = side[order]
    cuts = np.r_[0, np.flatnonzero(np.diff(body_s)) + 1, len(body_s)]
    count = np.diff(cuts)
    side_max = np.maximum.reduceat(side_s, cuts[:-1])
    side_min = np.minimum.reduceat(side_s, cuts[:-1])
    mixed = body_s[cuts[:-1]][side_max != side_min]
    if len(mixed):
        raise RuntimeError(f"{cell_type} cells span both eyes: {mixed.tolist()}")
    rows = []
    u_mean = np.add.reduceat(u_s, cuts[:-1]) / count
    v_mean = np.add.reduceat(v_s, cuts[:-1]) / count
    for index, body_id in enumerate(body_s[cuts[:-1]]):
        rows.append(
            {
                "type": cell_type,
                "body": int(body_id),
                "side": SIDE_NAME[int(side_min[index])],
                "u": float(u_mean[index]),
                "v": float(v_mean[index]),
                "n": int(count[index]),
            }
        )
    return rows


def _load_posts(path: Path) -> dict:
    return dict(np.load(path, allow_pickle=True))


def rows_from_caches() -> tuple[list[dict], list[dict], dict, dict]:
    lc4 = _load_posts(LC4_CACHE)
    lplc2 = _load_posts(LPLC2_CACHE)
    lc4_rows = cell_rows(lc4["body"], lc4["ab"], lc4["side"], lc4["left_ab"], lc4["right_ab"], "LC4")
    plate_rows = cell_rows(
        lplc2["lop_body"], lplc2["lop_ab"], lplc2["lop_side"],
        lplc2["lop_left_ab"], lplc2["lop_right_ab"], "LPLC2",
    )
    return lc4_rows, plate_rows, lc4, lplc2


def high_low_x(ab, total, count) -> tuple[float, float]:
    valid = (ab[:, 0] >= 0) & (count > 0)
    column_a = ab[valid, 0].astype(np.float64)
    centroid_x = total[valid, 0] / count[valid]
    high = float(centroid_x[column_a >= np.quantile(column_a, 0.8)].mean())
    low = float(centroid_x[column_a <= np.quantile(column_a, 0.2)].mean())
    return high, low


def check_orientation(lc4: dict, lplc2: dict) -> None:
    checks = (
        ("LC4 lobula L", lc4["left_ab"], lc4["left_sum"], lc4["left_count"], True),
        ("LC4 lobula R", lc4["right_ab"], lc4["right_sum"], lc4["right_count"], False),
        ("LPLC2 plate L", lplc2["lop_left_ab"], lplc2["lop_left_sum"], lplc2["lop_left_count"], True),
        ("LPLC2 plate R", lplc2["lop_right_ab"], lplc2["lop_right_sum"], lplc2["lop_right_count"], False),
    )
    for label, ab, total, count, outer_larger in checks:
        high, low = high_low_x(ab, total, count)
        print(f"{label}  high-a x {high:.0f}  low-a x {low:.0f}")
        lateral_is_high_a = high > low
        if lateral_is_high_a != outer_larger:
            raise RuntimeError(f"{label}: lateral side is not the large-a side.")


def write_cells(rows: list[dict]) -> None:
    CELLS.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda row: (row["type"], row["side"], row["body"]))
    with CELLS.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["type", "body", "side", "u", "v", "n"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "type": row["type"],
                    "body": row["body"],
                    "side": row["side"],
                    "u": f"{row['u']:.10f}",
                    "v": f"{row['v']:.10f}",
                    "n": row["n"],
                }
            )


def report(lc4_rows: list[dict], plate_rows: list[dict], lplc2: dict) -> None:
    def counts(rows: list[dict]) -> str:
        left = sum(row["side"] == "L" for row in rows)
        right = sum(row["side"] == "R" for row in rows)
        return f"{len(rows)} cells  L {left}  R {right}"

    print(f"LC4 {counts(lc4_rows)}")
    print(f"LPLC2 {counts(plate_rows)}")
    lobe_rows = cell_rows(
        lplc2["lo_body"], lplc2["lo_ab"], lplc2["lo_side"],
        lplc2["lo_left_ab"], lplc2["lo_right_ab"], "LPLC2",
    )
    plate_by_id = {row["body"]: row for row in plate_rows}
    lobe_by_id = {row["body"]: row for row in lobe_rows}
    if plate_by_id.keys() != lobe_by_id.keys():
        raise RuntimeError("Lobula and lobula-plate LPLC2 cell sets differ.")
    du = [abs(plate_by_id[body]["u"] - lobe_by_id[body]["u"]) for body in plate_by_id]
    dv = [abs(plate_by_id[body]["v"] - lobe_by_id[body]["v"]) for body in plate_by_id]
    print(
        f"lobula plate minus lobula  |du| mean {np.mean(du):.3f} max {np.max(du):.3f}  "
        f"|dv| mean {np.mean(dv):.3f} max {np.max(dv):.3f}"
    )
    for cell_type, rows in (("LC4", lc4_rows), ("LPLC2", plate_rows)):
        for side in ("L", "R"):
            chosen = [row for row in rows if row["side"] == side]
            u = [row["u"] for row in chosen]
            v = [row["v"] for row in chosen]
            print(f"{cell_type} {side}  u {min(u):.2f}–{max(u):.2f}  v {min(v):.2f}–{max(v):.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="scan syn-points again and overwrite the caches",
    )
    args = parser.parse_args()
    if args.rebuild or not LC4_CACHE.exists() or not LPLC2_CACHE.exists():
        save_caches(scan_synapses())
        print(f"wrote {LC4_CACHE.relative_to(ROOT)}")
        print(f"wrote {LPLC2_CACHE.relative_to(ROOT)}")
    else:
        print("caches present; pass --rebuild to scan syn-points again")
    lc4_rows, plate_rows, lc4, lplc2 = rows_from_caches()
    check_orientation(lc4, lplc2)
    report(lc4_rows, plate_rows, lplc2)
    write_cells(lc4_rows + plate_rows)
    print(f"wrote {CELLS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
