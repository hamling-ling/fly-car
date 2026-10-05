#!/usr/bin/env python3
"""Cut the walking-yaw steering pair out of the MaleCNS v1.0 chemical connectome.

This is the red sheet for the camera car. It is not part of the loom sheet.

  red   DNa02 left and right     data/malecns/steer-dna02/
  blue  LC4, LPLC2, DNp01        data/malecns/gf-loom/  (already cut)

Red and blue stay in separate graphs. Edges with one end in DNa02 and the
other in LC4, LPLC2, or DNp01 are counted in summary.json and then dropped.
Mushroom body, antennal lobe, T4, and T5 are not loaded. Red is an external
current into the two DNa02 cells, standing in for a left/right difference,
not a reconstructed odor circuit.

Body ids come from the local annotation feather. That is the same selection
as the male-cns:v1.0 query for type DNa02. No NeuPrint token is required.
Weights are chemical synapse counts at confidence >= 0.5. Gap junctions are
not in the table.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.feather as feather

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
OUT = DATA / "steer-dna02"
LOOM_DIR = DATA / "gf-loom"

ANNOTATIONS = DATA / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
TRANSMITTERS = DATA / "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = DATA / "connectome-weights-male-cns-v1.0-minconf-0.5.feather"

STEER_TYPE = "DNa02"
LOOM_TYPES = ("LC4", "LPLC2", "DNp01")
ROLE = "steer_dn"

EXCITATORY = {"acetylcholine"}
INHIBITORY = {"gaba", "glutamate"}


def side_of(instance: str) -> str | None:
    if instance.endswith("_L"):
        return "L"
    if instance.endswith("_R"):
        return "R"
    return None


def nt_sign(consensus: str | None) -> int | None:
    if consensus in EXCITATORY:
        return 1
    if consensus in INHIBITORY:
        return -1
    return None


def membership(sorted_ids: np.ndarray, values: np.ndarray) -> np.ndarray:
    n = len(sorted_ids)
    if n == 0:
        return np.zeros(len(values), dtype=bool)
    at = np.searchsorted(sorted_ids, values)
    return (at < n) & (sorted_ids[np.clip(at, 0, n - 1)] == values)


def load_annotations() -> pd.DataFrame:
    columns = [
        "bodyId",
        "type",
        "instance",
        "superclass",
        "hemibrainType",
        "mancType",
        "status",
        "statusLabel",
        "somaSide",
        "somaLocation",
    ]
    return feather.read_table(ANNOTATIONS, columns=columns).to_pandas()


def load_steer_neurons(ann: pd.DataFrame) -> pd.DataFrame:
    neurons = ann.loc[ann["type"] == STEER_TYPE].copy()
    if len(neurons) != 2:
        raise SystemExit(f"expected 2 {STEER_TYPE} neurons, found {len(neurons)}")

    nt = feather.read_table(
        TRANSMITTERS,
        columns=[
            "body",
            "consensus_nt",
            "predicted_nt",
            "predicted_nt_confidence",
            "celltype_predicted_nt",
            "celltype_predicted_nt_confidence",
        ],
    ).to_pandas()
    neurons = neurons.merge(nt, left_on="bodyId", right_on="body", how="left")
    neurons = neurons.drop(columns=["body"])

    coords = []
    for value in neurons["somaLocation"]:
        if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3:
            coords.append([int(value[0]), int(value[1]), int(value[2])])
        else:
            coords.append([None, None, None])
    xyz = pd.DataFrame(coords, columns=["soma_x", "soma_y", "soma_z"], index=neurons.index)
    neurons = pd.concat([neurons.drop(columns=["somaLocation"]), xyz], axis=1)

    neurons["side"] = neurons["instance"].map(lambda s: side_of(s or ""))
    neurons["role"] = ROLE
    neurons["nt_sign"] = neurons["consensus_nt"].map(nt_sign)
    neurons = neurons.sort_values(["side", "bodyId"]).reset_index(drop=True)

    counts = neurons.groupby("side", dropna=False).size()
    if counts.get("L") != 1 or counts.get("R") != 1:
        raise SystemExit(f"expected one {STEER_TYPE} on each side, got\n{counts.to_string()}")
    mismatched = neurons["somaSide"].notna() & (neurons["side"] != neurons["somaSide"])
    if mismatched.any():
        bad = neurons.loc[mismatched, ["bodyId", "instance", "side", "somaSide"]]
        raise SystemExit(f"instance side and somaSide disagree\n{bad.to_string(index=False)}")
    return neurons


def loom_ids(ann: pd.DataFrame) -> np.ndarray:
    ids = ann.loc[ann["type"].isin(LOOM_TYPES), "bodyId"].to_numpy(dtype=np.int64)
    if len(ids) == 0:
        raise SystemExit(f"no neurons of types {LOOM_TYPES} in the annotation table")
    return np.sort(ids)


def scan_weights(steer: np.ndarray, loom: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Return DNa02-DNa02 edges, dropped cross edges, and the DNa02 touch count."""
    table = feather.read_table(
        WEIGHTS,
        columns=["body_pre", "body_post", "weight"],
        memory_map=True,
    )
    internal_pre = []
    internal_post = []
    internal_w = []
    cross_pre = []
    cross_post = []
    cross_w = []
    touching = 0
    seen = 0
    for batch in table.to_batches(max_chunksize=4_000_000):
        pre = batch.column(0).to_numpy()
        post = batch.column(1).to_numpy()
        weight = batch.column(2).to_numpy()
        seen += len(pre)
        pre_steer = membership(steer, pre)
        post_steer = membership(steer, post)
        pre_loom = membership(loom, pre)
        post_loom = membership(loom, post)
        internal = pre_steer & post_steer
        cross = (pre_steer & post_loom) | (post_steer & pre_loom)
        touching += int((pre_steer | post_steer).sum())
        if internal.any():
            internal_pre.append(pre[internal])
            internal_post.append(post[internal])
            internal_w.append(weight[internal])
        if cross.any():
            cross_pre.append(pre[cross])
            cross_post.append(post[cross])
            cross_w.append(weight[cross])
        if seen % 20_000_000 < len(pre):
            print(f"  scanned {seen:,} edges", flush=True)

    def pack(pre_parts: list[np.ndarray], post_parts: list[np.ndarray], w_parts: list[np.ndarray]) -> pd.DataFrame:
        if not pre_parts:
            return pd.DataFrame(columns=["body_pre", "body_post", "weight"])
        return pd.DataFrame(
            {
                "body_pre": np.concatenate(pre_parts),
                "body_post": np.concatenate(post_parts),
                "weight": np.concatenate(w_parts),
            }
        )

    return pack(internal_pre, internal_post, internal_w), pack(cross_pre, cross_post, cross_w), touching


def label_edges(edges: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    if len(edges) == 0:
        return edges.copy()
    named = edges.join(meta.add_prefix("pre_"), on="body_pre").join(meta.add_prefix("post_"), on="body_post")
    return named.sort_values(["body_pre", "body_post"]).reset_index(drop=True)


def jsonable(value: object) -> object:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return None
        return float(value)
    return value


def records(frame: pd.DataFrame) -> list[dict]:
    return [{key: jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def pair_records(named: pd.DataFrame) -> list[dict]:
    if len(named) == 0:
        return []
    rows = []
    grouped = named.groupby(["pre_type", "pre_side", "post_type", "post_side"], dropna=False)
    for (pre_type, pre_side, post_type, post_side), part in grouped:
        same = pre_side == post_side
        rows.append(
            {
                "type_pre": pre_type,
                "side_pre": pre_side,
                "type_post": post_type,
                "side_post": post_side,
                "laterality": "ipsi" if same else "contra",
                "edges": int(len(part)),
                "synapses": int(part.weight.sum()),
            }
        )
    rows.sort(key=lambda row: (-row["synapses"], row["type_pre"], row["side_pre"] or "", row["type_post"], row["side_post"] or ""))
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("loading neurons")
    ann = load_annotations()
    neurons = load_steer_neurons(ann)
    steer = np.sort(neurons["bodyId"].to_numpy(dtype=np.int64))
    loom = loom_ids(ann)
    print(neurons[["bodyId", "type", "instance", "side", "status", "consensus_nt", "nt_sign"]].to_string(index=False))
    print(f"loom ids held aside for the cross-edge check: {len(loom)}")

    print("scanning weights")
    internal, cross, touching = scan_weights(steer, loom)
    sign_by_body = neurons.set_index("bodyId")["nt_sign"]
    nt_by_body = neurons.set_index("bodyId")["consensus_nt"]
    internal = internal.sort_values(["body_pre", "body_post"]).reset_index(drop=True)
    internal["consensus_nt"] = internal["body_pre"].map(nt_by_body)
    internal["nt_sign"] = internal["body_pre"].map(sign_by_body)

    meta = pd.concat(
        [
            neurons.assign(type=STEER_TYPE)[["bodyId", "type", "side"]],
            ann.loc[ann["type"].isin(LOOM_TYPES), ["bodyId", "type", "instance"]].assign(
                side=lambda frame: frame["instance"].map(lambda s: side_of(s or ""))
            )[["bodyId", "type", "side"]],
        ],
        ignore_index=True,
    ).drop_duplicates("bodyId").set_index("bodyId")
    internal_named = label_edges(internal, meta)
    cross_named = label_edges(cross, meta)

    kept_ids = set(steer.tolist())
    if len(internal) and not (internal.body_pre.isin(kept_ids) & internal.body_post.isin(kept_ids)).all():
        raise SystemExit("internal edges include a body id outside DNa02")

    type_edges = pd.DataFrame(pair_records(internal_named))
    if len(type_edges) == 0:
        type_edges = pd.DataFrame(
            columns=["type_pre", "side_pre", "type_post", "side_post", "laterality", "edges", "synapses"]
        )

    feather.write_feather(neurons, OUT / "neurons.feather")
    feather.write_feather(internal, OUT / "edges.feather")
    type_edges.to_csv(OUT / "type_edges.csv", index=False)

    def counts_at(threshold: int) -> int:
        return int((internal["weight"] >= threshold).sum()) if len(internal) else 0

    summary = {
        "dataset": "male-cns:v1.0",
        "sheet": "steer",
        "color": "red",
        "companion_sheet": "data/malecns/gf-loom",
        "companion_types": list(LOOM_TYPES),
        "do_not_merge_with_companion": True,
        "synapse_confidence": ">= 0.5",
        "weight_meaning": "chemical synapse count; gap junctions are not included",
        "neuron_count": int(len(neurons)),
        "internal_edge_count": int(len(internal)),
        "internal_synapse_count": int(internal["weight"].sum()) if len(internal) else 0,
        "edges_weight_ge_3": counts_at(3),
        "edges_weight_ge_5": counts_at(5),
        "edges_weight_ge_10": counts_at(10),
        "touching_edge_count": int(touching),
        "neurons_by_type_side": {
            f"{t}|{s}": int(n)
            for (t, s), n in neurons.groupby(["type", "side"], dropna=False).size().items()
        },
        "neurons": records(neurons[
            ["bodyId", "type", "instance", "side", "status", "consensus_nt", "nt_sign", "soma_x", "soma_y", "soma_z"]
        ]),
        "roles": {STEER_TYPE: ROLE},
        "stimulus": (
            "External current difference from left and right red counts, "
            "injected into the two DNa02 cells. Not synapses from olfactory neurons."
        ),
        "internal_pairs": pair_records(internal_named),
        "dropped_cross_with_loom": {
            "edge_count": int(len(cross)),
            "synapse_count": int(cross["weight"].sum()) if len(cross) else 0,
            "pairs": pair_records(cross_named),
            "kept_in_edges": False,
        },
        "notes": [
            "DNa02 is the steering descending neuron used for the red sheet. MaleCNS has one traced cell on each side.",
            "Both DNa02 cells have consensus transmitter acetylcholine, so nt_sign is +1.",
            "The red camera half is an external current into that side's DNa02. The mushroom body and the antennal lobe are not in this cut.",
            "LC4, LPLC2, and DNp01 stay in data/malecns/gf-loom. Do not concatenate the two edge tables.",
            "For the car, filter gf-loom to LC4, LPLC2, and DNp01. TTMn, PSI, and DLMn are the jump and flight path and are not the yaw command.",
            "Blue pixel counts drive LC4 and LPLC2. The yaw override is the left/right difference of DNp01 firing.",
            "On a frame where blue is above threshold, ignore DNa02 output and use only the DNp01 difference. This table does not apply that rule.",
            "T4 and T5 are not included. The camera's color counts replace the visual expansion measurement.",
            "Edges between DNa02 and the loom trio are listed under dropped_cross_with_loom and are absent from edges.feather.",
            "Chemical synapses only. Gap junctions are not in the source table.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({
        "neuron_count": summary["neuron_count"],
        "internal_edge_count": summary["internal_edge_count"],
        "internal_synapse_count": summary["internal_synapse_count"],
        "touching_edge_count": summary["touching_edge_count"],
        "dropped_cross_edges": summary["dropped_cross_with_loom"]["edge_count"],
        "dropped_cross_synapses": summary["dropped_cross_with_loom"]["synapse_count"],
        "loom_extract_present": (LOOM_DIR / "neurons.feather").exists(),
    }, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
