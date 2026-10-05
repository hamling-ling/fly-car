#!/usr/bin/env python3
"""Cut the giant-fiber loom circuit out of the MaleCNS v1.0 chemical connectome.

Reads the flat feather tables already in data/malecns/ and writes a neuron
table, the synapses among those neurons, and a type-to-type summary to
data/malecns/gf-loom/.

Included cells
  LC4, LPLC2     looming visual projection neurons (the stimulus layer)
  DNp01          giant fiber (hemibrain name: Giant Fiber)
  TTMn           tergotrochanteral motor neuron (jump)
  PSI            peripherally synapsing interneuron
  DLMn a, b      dorsal longitudinal motor neuron for fibers a and b
  DLMn c-f       dorsal longitudinal motor neurons for fibers c-f

Weights are synapse counts at confidence >= 0.5. Gap junctions are not in
this table, so the electrical GF-GF and GF-TTMn couplings are absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.feather as feather

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
OUT = DATA / "gf-loom"

ANNOTATIONS = DATA / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
TRANSMITTERS = DATA / "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = DATA / "connectome-weights-male-cns-v1.0-minconf-0.5.feather"

# Types kept whole. DLMn names contain spaces and commas, so they are matched
# by prefix below rather than listed here.
CORE_TYPES = ("LC4", "LPLC2", "DNp01", "TTMn", "PSI")
DLM_PREFIX = "DLMn"

ROLES = {
    "LC4": "loom_vpn",
    "LPLC2": "loom_vpn",
    "DNp01": "giant_fiber",
    "TTMn": "jump_motor",
    "PSI": "flight_trigger",
    "DLMn a, b": "flight_motor",
    "DLMn c-f": "flight_motor",
}

# Sign is only assigned where the consensus transmitter is reliable enough to
# use as a synapse sign. Motor-neuron calls in this table are low-confidence
# and are left unsigned.
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


def load_neurons() -> pd.DataFrame:
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
    ann = feather.read_table(ANNOTATIONS, columns=columns).to_pandas()
    type_name = ann["type"].fillna("")
    keep = ann["type"].isin(CORE_TYPES) | type_name.str.startswith(DLM_PREFIX)
    neurons = ann.loc[keep].copy()

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

    soma = neurons["somaLocation"]
    coords = []
    for value in soma:
        if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3:
            coords.append([int(value[0]), int(value[1]), int(value[2])])
        else:
            coords.append([None, None, None])
    xyz = pd.DataFrame(coords, columns=["soma_x", "soma_y", "soma_z"], index=neurons.index)
    neurons = pd.concat([neurons.drop(columns=["somaLocation"]), xyz], axis=1)

    neurons["side"] = neurons["instance"].map(lambda s: side_of(s or ""))
    neurons["role"] = neurons["type"].map(ROLES)
    neurons["nt_sign"] = neurons["consensus_nt"].map(nt_sign)
    neurons = neurons.sort_values(["role", "type", "side", "bodyId"]).reset_index(drop=True)
    return neurons


def edges_touching(core_ids: np.ndarray) -> pd.DataFrame:
    """Stream the full weight table and keep edges with an end in core_ids."""
    table = feather.read_table(
        WEIGHTS,
        columns=["body_pre", "body_post", "weight"],
        memory_map=True,
    )
    n = len(core_ids)
    parts_pre = []
    parts_post = []
    parts_w = []
    seen = 0
    for batch in table.to_batches(max_chunksize=4_000_000):
        pre = batch.column(0).to_numpy()
        post = batch.column(1).to_numpy()
        weight = batch.column(2).to_numpy()
        seen += len(pre)
        pre_at = np.searchsorted(core_ids, pre)
        post_at = np.searchsorted(core_ids, post)
        pre_hit = (pre_at < n) & (core_ids[np.clip(pre_at, 0, n - 1)] == pre)
        post_hit = (post_at < n) & (core_ids[np.clip(post_at, 0, n - 1)] == post)
        mask = pre_hit | post_hit
        if mask.any():
            parts_pre.append(pre[mask])
            parts_post.append(post[mask])
            parts_w.append(weight[mask])
        if seen % 20_000_000 < len(pre):
            print(f"  scanned {seen:,} edges", flush=True)

    if not parts_pre:
        return pd.DataFrame(columns=["body_pre", "body_post", "weight"])
    return pd.DataFrame(
        {
            "body_pre": np.concatenate(parts_pre),
            "body_post": np.concatenate(parts_post),
            "weight": np.concatenate(parts_w),
        }
    )


def type_lookup(body_ids: np.ndarray) -> pd.DataFrame:
    wanted = pd.DataFrame({"bodyId": np.unique(body_ids)})
    ann = feather.read_table(
        ANNOTATIONS,
        columns=["bodyId", "type", "instance", "superclass"],
    ).to_pandas()
    found = wanted.merge(ann, on="bodyId", how="left")
    found["type"] = found["type"].fillna("untyped")
    found["superclass"] = found["superclass"].fillna("untyped")
    return found


def aggregate_types(edges: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    named = edges.merge(
        labels.rename(columns={"bodyId": "body_pre", "type": "type_pre", "superclass": "class_pre"}),
        on="body_pre",
        how="left",
    ).merge(
        labels.rename(columns={"bodyId": "body_post", "type": "type_post", "superclass": "class_post"}),
        on="body_post",
        how="left",
    )
    grouped = (
        named.groupby(["type_pre", "class_pre", "type_post", "class_post"], dropna=False)
        .agg(synapses=("weight", "sum"), edges=("weight", "size"), neurons_pre=("body_pre", "nunique"), neurons_post=("body_post", "nunique"))
        .reset_index()
        .sort_values("synapses", ascending=False)
    )
    return grouped


def top_partners(grouped: pd.DataFrame, focus_type: str, direction: str, n: int = 15) -> list[dict]:
    if direction == "in":
        rows = grouped[(grouped.type_post == focus_type) & (grouped.type_pre != focus_type)]
        partner = "type_pre"
    else:
        rows = grouped[(grouped.type_pre == focus_type) & (grouped.type_post != focus_type)]
        partner = "type_post"
    # A type can appear once per superclass pair; collapse just in case.
    collapsed = (
        rows.groupby(partner, as_index=False)
        .agg(synapses=("synapses", "sum"), edges=("edges", "sum"))
        .sort_values("synapses", ascending=False)
        .head(n)
    )
    return collapsed.to_dict(orient="records")


def pathway_table(edges: pd.DataFrame, neurons: pd.DataFrame) -> list[dict]:
    """Ipsilateral vs contralateral synapse totals for the escape path."""
    meta = neurons.set_index("bodyId")[["type", "instance", "side"]]
    named = edges.join(meta.add_prefix("pre_"), on="body_pre").join(meta.add_prefix("post_"), on="body_post")
    pairs = [
        ("LC4", "DNp01"),
        ("LPLC2", "DNp01"),
        ("LPLC2", "LC4"),
        ("DNp01", "TTMn"),
        ("DNp01", "PSI"),
        ("DNp01", "DNp01"),
        ("PSI", "DLMn c-f"),
        ("PSI", "DLMn a, b"),
        ("PSI", "DNp01"),
    ]
    rows = []
    for pre_type, post_type in pairs:
        sub = named[(named.pre_type == pre_type) & (named.post_type == post_type)]
        for (pre_side, post_side), part in sub.groupby(["pre_side", "post_side"], dropna=False):
            same = pre_side == post_side
            rows.append(
                {
                    "type_pre": pre_type,
                    "type_post": post_type,
                    "side_pre": pre_side,
                    "side_post": post_side,
                    "laterality": "ipsi" if same else "contra",
                    "edges": int(len(part)),
                    "synapses": int(part.weight.sum()),
                    "neurons_pre": int(part.body_pre.nunique()),
                }
            )
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("loading core neurons")
    neurons = load_neurons()
    core_ids = np.sort(neurons["bodyId"].to_numpy(dtype=np.int64))
    print(f"core neurons: {len(neurons)}")
    print(neurons.groupby(["type", "side"], dropna=False).size().to_string())

    print("scanning weights")
    touching = edges_touching(core_ids)
    internal_mask = touching.body_pre.isin(core_ids) & touching.body_post.isin(core_ids)
    internal = touching.loc[internal_mask].copy()
    # Attach presynaptic transmitter sign so a simulator does not have to rejoin.
    sign_by_body = neurons.set_index("bodyId")["nt_sign"]
    nt_by_body = neurons.set_index("bodyId")["consensus_nt"]
    internal["consensus_nt"] = internal["body_pre"].map(nt_by_body)
    internal["nt_sign"] = internal["body_pre"].map(sign_by_body)
    internal = internal.sort_values(["body_pre", "body_post"]).reset_index(drop=True)

    partner_ids = np.unique(
        np.concatenate([touching.body_pre.to_numpy(), touching.body_post.to_numpy()])
    )
    labels = type_lookup(partner_ids)
    by_type = aggregate_types(touching, labels)
    core_type_names = set(neurons["type"].unique())
    within = by_type[
        by_type.type_pre.isin(core_type_names) & by_type.type_post.isin(core_type_names)
    ].reset_index(drop=True)

    feather.write_feather(neurons, OUT / "neurons.feather")
    feather.write_feather(internal, OUT / "edges.feather")
    within.to_csv(OUT / "type_edges.csv", index=False)

    def counts_at(threshold: int) -> int:
        return int((internal["weight"] >= threshold).sum())

    summary = {
        "dataset": "male-cns:v1.0",
        "synapse_confidence": ">= 0.5",
        "weight_meaning": "chemical synapse count; gap junctions are not included",
        "neuron_count": int(len(neurons)),
        "internal_edge_count": int(len(internal)),
        "internal_synapse_count": int(internal["weight"].sum()) if len(internal) else 0,
        "edges_weight_ge_3": counts_at(3),
        "edges_weight_ge_5": counts_at(5),
        "edges_weight_ge_10": counts_at(10),
        "touching_edge_count": int(len(touching)),
        "neurons_by_type_side": {
            f"{t}|{s}": int(n)
            for (t, s), n in neurons.groupby(["type", "side"], dropna=False).size().items()
        },
        "roles": ROLES,
        "dnp01_top_inputs": top_partners(by_type, "DNp01", "in"),
        "dnp01_top_outputs": top_partners(by_type, "DNp01", "out"),
        "lc4_top_inputs": top_partners(by_type, "LC4", "in"),
        "lplc2_top_inputs": top_partners(by_type, "LPLC2", "in"),
        "psi_top_outputs": top_partners(by_type, "PSI", "out"),
        "pathways": pathway_table(internal, neurons),
        "notes": [
            "LC4 and LPLC2 are the direct looming visual inputs onto the giant fiber.",
            "Every LC4 and every LPLC2 connects only to the ipsilateral DNp01.",
            "DNp01 is the giant fiber. Both cells are labeled Roughly traced.",
            "LC4 counts are unequal (71 left, 55 right); many VPN cells are only preliminarily traced.",
            "TTMn is the jump motor neuron. Chemical DNp01->TTMn is ipsilateral but small (20 and 70 synapses).",
            "Chemical DNp01->PSI is only 16 synapses. The behaviorally strong GF-TTMn and GF-PSI links are electrical and are not in this table.",
            "Chemical DNp01<->DNp01 is 1 synapse each way. The two giant fibers are coupled electrically, which this cut does not contain.",
            "PSI->DLMn c-f is strictly contralateral (about 200 synapses per PSI). PSI->DLMn a,b is ipsilateral and weaker.",
            "There are 5 DLMns per side: one for fibers a+b and four for c-f.",
            "GFC2/GFC3/GFC4 are dye-coupled GF partners and the largest typed chemical outputs of DNp01, but they are omitted because that coupling is electrical.",
            "assignedOlHex is empty for these cells. Somas separate into left and right clusters only, with no column index.",
            "PSI and DLMn consensus transmitters are 'unclear'; do not treat nt_sign as known there.",
            "Glutamate on TTMn is the neuromuscular prediction, not evidence that TTMn inhibits its CNS targets.",
            "Untyped partners of DNp01 are a long tail of ~1-2 synapse edges, not a missing cell type.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in (
        "neuron_count", "internal_edge_count", "internal_synapse_count",
        "edges_weight_ge_3", "edges_weight_ge_5", "edges_weight_ge_10",
        "touching_edge_count",
    )}, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
