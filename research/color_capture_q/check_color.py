"""ゲインとシャッターから、矩形の平均色とゆらぎ幅を予測する。

赤と青は別々の直線である。目的変数は BGR の平均 3 つと、各成分の標準偏差 3 つ。
画素は、予測した平均から予測した標準偏差以内にあるとき、その色になる。
赤も青も無い絵は学習に使わない。ラベル付きの絵は、その絵を除いて予測する。
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parent
MARKED = ROOT / "samples" / "marked"
OUT = ROOT / "samples" / "check"


def load_shots() -> list[dict]:
    shots = []
    for path in sorted(MARKED.glob("*.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        image = path.with_suffix(".jpg")
        if meta.get("neither"):
            kind = "neither"
            rect = None
        elif meta.get("red") and not meta.get("blue"):
            kind = "red"
            rect = meta["red"]
        elif meta.get("blue") and not meta.get("red"):
            kind = "blue"
            rect = meta["blue"]
        else:
            raise SystemExit(f"矩形が両方ある: {path.name}")
        shots.append(
            {
                "stamp": path.stem,
                "kind": kind,
                "gain": float(meta["gain"]),
                "exposure": float(meta["exposure_time_absolute"]),
                "rect": rect,
                "image": image,
                "meta": meta,
            }
        )
    return shots


def rect_stats(image: np.ndarray, rect: dict) -> tuple[np.ndarray, np.ndarray]:
    """矩形の中の BGR 平均と、成分ごとの標準偏差。"""
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    patch = image[y : y + h, x : x + w].reshape(-1, 3).astype(np.float64)
    return patch.mean(axis=0), patch.std(axis=0)


def design(shots: list[dict]) -> np.ndarray:
    return np.array([[shot["gain"], shot["exposure"]] for shot in shots], dtype=np.float64)


def leave_one_out_indices(n: int):
    index = np.arange(n)
    for i in range(n):
        yield index[index != i], index[i : i + 1]


def fit_predict_loo(shots: list[dict], targets: np.ndarray) -> np.ndarray:
    """各枚の目的変数を、その枚を除いた直線で予測する。"""
    features = design(shots)
    predicted = np.zeros_like(targets)
    for train, test in leave_one_out_indices(len(shots)):
        model = LinearRegression()
        model.fit(features[train], targets[train])
        predicted[test] = model.predict(features[test])
    return predicted


def fit_all(shots: list[dict], targets: np.ndarray) -> LinearRegression:
    model = LinearRegression()
    model.fit(design(shots), targets)
    return model


def match(image: np.ndarray, mean: np.ndarray, width: np.ndarray) -> np.ndarray:
    """3 成分とも、予測平均から予測したゆらぎ幅以内なら真。"""
    delta = np.abs(image.astype(np.float64) - mean.reshape(1, 1, 3))
    limit = np.maximum(width, 0.0)
    return np.all(delta <= limit.reshape(1, 1, 3), axis=2)


def fraction(mask: np.ndarray, rect: dict | None = None, inside: bool = True) -> float:
    if rect is None:
        return float(mask.mean())
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    region = mask[y : y + h, x : x + w]
    outside = mask.copy()
    outside[y : y + h, x : x + w] = False
    if inside:
        return float(region.mean()) if region.size else 0.0
    return float(outside.mean())


def overlay(image: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    view = image.copy()
    tint = np.zeros_like(view)
    tint[red] = (0, 0, 255)
    tint[blue] = (255, 80, 0)
    both = red & blue
    tint[both] = (255, 0, 255)
    blended = cv2.addWeighted(view, 0.45, tint, 0.55, 0)
    view[red | blue] = blended[red | blue]
    return view


def predict_pair(kind: str, shot: dict, models: dict[str, LinearRegression], loo: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    if shot["kind"] == kind:
        row = loo[shot["stamp"]]
        return row[:3], row[3:]
    features = np.array([[shot["gain"], shot["exposure"]]])
    row = models[kind].predict(features)[0]
    return row[:3], row[3:]


def main() -> None:
    shots = load_shots()
    labeled = [shot for shot in shots if shot["kind"] in ("red", "blue")]
    by_kind = {kind: [shot for shot in labeled if shot["kind"] == kind] for kind in ("red", "blue")}
    cache: dict[str, np.ndarray] = {}
    observed: dict[str, np.ndarray] = {}
    for shot in labeled:
        image = cv2.imread(str(shot["image"]))
        cache[shot["stamp"]] = image
        mean, width = rect_stats(image, shot["rect"])
        observed[shot["stamp"]] = np.concatenate([mean, width])

    loo: dict[str, np.ndarray] = {}
    models: dict[str, LinearRegression] = {}
    for kind in ("red", "blue"):
        group = by_kind[kind]
        targets = np.stack([observed[shot["stamp"]] for shot in group])
        predicted = fit_predict_loo(group, targets)
        for shot, row in zip(group, predicted):
            loo[shot["stamp"]] = row
        models[kind] = fit_all(group, targets)
        mean_mae = np.abs(predicted[:, :3] - targets[:, :3]).mean()
        width_mae = np.abs(predicted[:, 3:] - targets[:, 3:]).mean()
        print(f"{kind} n={len(group)} mean MAE {mean_mae:.1f} width MAE {width_mae:.1f}")

    out_dir = OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for shot in shots:
        image = cache[shot["stamp"]] if shot["kind"] != "neither" else cv2.imread(str(shot["image"]))
        pred = {}
        width = {}
        for kind in ("red", "blue"):
            pred[kind], width[kind] = predict_pair(kind, shot, models, loo)
        masks = {kind: match(image, pred[kind], width[kind]) for kind in ("red", "blue")}
        both = masks["red"] & masks["blue"]
        if both.any():
            red_distance = np.linalg.norm(image.astype(np.float64) - pred["red"], axis=2)
            blue_distance = np.linalg.norm(image.astype(np.float64) - pred["blue"], axis=2)
            masks["red"] = masks["red"] & ~(both & (blue_distance < red_distance))
            masks["blue"] = masks["blue"] & ~(both & (red_distance <= blue_distance))
        rect = shot["rect"]
        width_px = masks["red"].shape[1]
        mid = width_px // 2
        record = {
            "stamp": shot["stamp"],
            "kind": shot["kind"],
            "gain": shot["gain"],
            "exposure": shot["exposure"],
            "red_frame": float(masks["red"].mean()),
            "blue_frame": float(masks["blue"].mean()),
            "red_left": float(masks["red"][:, :mid].mean()),
            "red_right": float(masks["red"][:, mid:].mean()),
            "blue_left": float(masks["blue"][:, :mid].mean()),
            "blue_right": float(masks["blue"][:, mid:].mean()),
            "red_width": np.maximum(width["red"], 0).round(2).tolist(),
            "blue_width": np.maximum(width["blue"], 0).round(2).tolist(),
            "red_mean": pred["red"].round(1).tolist(),
            "blue_mean": pred["blue"].round(1).tolist(),
        }
        if rect is not None:
            record["recall"] = fraction(masks[shot["kind"]], rect, inside=True)
            record["outside"] = fraction(masks[shot["kind"]], rect, inside=False)
            record["other"] = fraction(masks["blue" if shot["kind"] == "red" else "red"], rect, inside=False)
        else:
            record["recall"] = None
            record["outside"] = None
            record["other"] = None
        rows.append(record)
        wrong = False
        if shot["kind"] == "neither" and (record["red_frame"] > 0.002 or record["blue_frame"] > 0.002):
            wrong = True
        if shot["kind"] != "neither" and (
            record["recall"] < 0.5 or record["outside"] > 0.01 or record["other"] > 0.002
        ):
            wrong = True
        if wrong:
            view = overlay(image, masks["red"], masks["blue"])
            text = (
                f"{shot['kind']} g{int(shot['gain'])} e{int(shot['exposure'])} "
                f"R{record['red_frame'] * 100:.1f}% B{record['blue_frame'] * 100:.1f}%"
            )
            if record["recall"] is not None:
                text += f" rect{record['recall'] * 100:.0f}%"
            cv2.putText(view, text, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            small = cv2.resize(view, (960, 540), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out_dir / f"{shot['stamp']}.jpg"), small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])

    summary = {"shots": rows}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print_report(rows)
    pure = next(row for row in rows if row["stamp"].endswith("095912_415"))
    print(
        "095912 recall",
        round(pure["recall"], 3),
        "blue_frame",
        round(pure["blue_frame"], 3),
        "left",
        round(pure["blue_left"], 3),
        "right",
        round(pure["blue_right"], 3),
        "pred mean",
        pure["blue_mean"],
        "pred width",
        pure["blue_width"],
    )
    floor = 0.04
    for title, subset in (
        ("labeled half>=0.04", [row for row in rows if row["kind"] != "neither"]),
        ("neither half>=0.04", [row for row in rows if row["kind"] == "neither"]),
    ):
        hit = [
            row
            for row in subset
            if max(row["red_left"], row["red_right"], row["blue_left"], row["blue_right"]) >= floor
        ]
        print(f"{title} {len(hit)}/{len(subset)}")


def print_report(rows: list[dict]) -> None:
    def show(title: str, subset: list[dict]) -> None:
        print(f"\n{title} n={len(subset)}")
        if subset and subset[0]["recall"] is not None:
            recall = np.array([row["recall"] for row in subset])
            outside = np.array([row["outside"] for row in subset])
            print(f"  rect recall min/median {recall.min():.2f} {np.median(recall):.2f}")
            print(f"  outside median/max {np.median(outside):.4f} {outside.max():.4f}")
        flagged = [
            row
            for row in subset
            if row["kind"] == "neither" and (row["red_frame"] > 0.002 or row["blue_frame"] > 0.002)
            or row["kind"] != "neither"
            and (row["recall"] < 0.5 or row["outside"] > 0.01 or row["other"] > 0.002)
        ]
        flagged.sort(key=lambda row: max(row["red_frame"], row["blue_frame"]), reverse=True)
        for row in flagged:
            extra = ""
            if row["recall"] is not None:
                extra = f" recall {row['recall']:.2f} outside {row['outside']:.3f} other {row['other']:.3f}"
            print(
                f"  {row['stamp'][9:]} {row['kind']:7} g{int(row['gain']):3} e{int(row['exposure']):3}"
                f" red {row['red_frame'] * 100:5.1f}% blue {row['blue_frame'] * 100:5.1f}%{extra}"
            )

    show("red", [row for row in rows if row["kind"] == "red"])
    show("blue", [row for row in rows if row["kind"] == "blue"])
    show("neither", [row for row in rows if row["kind"] == "neither"])


if __name__ == "__main__":
    main()
