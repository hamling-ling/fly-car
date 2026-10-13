"""samples/marked を、見た目で決めた色相・彩度・明度で赤と青に分ける。

この数字は矩形から一意に計算したものではない。人間が見て赤か、水色か、
壁か、木かで切った値である。OpenCV の色相は 0 から 179 なので、度は 2 倍する。

明るい赤: 彩度 120 以上、明度 190 以上、色相 30 度以下または 350 度以上。
暗い赤:   彩度 150 以上、明度 130 以上、色相 20 度以下または 350 度以上。
青:       彩度 100 以上、明度 230 以上、色相 180 度以上 240 度以下。
薄い水色: 彩度 30 以上、明度 230 以上、色相 170 度以上 190 度以下。

肌は色相が赤でも彩度は 80 から 100 にとどまる。暗い赤のスマホは彩度 155 以上。
薄い水色の画面は色相が 180 度付近に寄る。彩度の下限を青全体で下げると、
同じ彩度の壁まで青になる。
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
MARKED = ROOT / "samples" / "marked"
OUT = ROOT / "samples" / "check_hsv"

RED_S_BRIGHT = 120
RED_S_DARK = 150
BLUE_S = 100
PALE_S = 30
RED_V_BRIGHT = 190
RED_V_DARK = 130
BLUE_V = 230
RED_H_BRIGHT = 30
RED_H_DARK = 20
RED_H_WRAP = 350
BLUE_H_LOW = 180
BLUE_H_HIGH = 240
PALE_H_LOW = 170
PALE_H_HIGH = 190
HALF_FLOOR = 0.04


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
                "rect": rect,
                "image": image,
            }
        )
    return shots


def classify(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """画素ごとの赤と青。色相の範囲は重ならない。"""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16) * 2
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    bright = (saturation >= RED_S_BRIGHT) & (value >= RED_V_BRIGHT) & ((hue <= RED_H_BRIGHT) | (hue >= RED_H_WRAP))
    dark = (saturation >= RED_S_DARK) & (value >= RED_V_DARK) & ((hue <= RED_H_DARK) | (hue >= RED_H_WRAP))
    red = bright | dark
    blue = (hue >= BLUE_H_LOW) & (hue <= BLUE_H_HIGH) & (saturation >= BLUE_S) & (value >= BLUE_V)
    pale = (hue >= PALE_H_LOW) & (hue <= PALE_H_HIGH) & (saturation >= PALE_S) & (value >= BLUE_V)
    return red, blue | pale


def fraction(mask: np.ndarray, rect: dict) -> float:
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    region = mask[y : y + h, x : x + w]
    return float(region.mean()) if region.size else 0.0


def overlay(image: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    view = image.copy()
    tint = np.zeros_like(view)
    tint[red] = (0, 0, 255)
    tint[blue] = (255, 80, 0)
    blended = cv2.addWeighted(view, 0.45, tint, 0.55, 0)
    view[red | blue] = blended[red | blue]
    return view


def main() -> None:
    shots = load_shots()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for shot in shots:
        image = cv2.imread(str(shot["image"]))
        if image is None:
            raise SystemExit(f"読めない: {shot['image']}")
        red, blue = classify(image)
        mid = red.shape[1] // 2
        record = {
            "stamp": shot["stamp"],
            "kind": shot["kind"],
            "red_frame": float(red.mean()),
            "blue_frame": float(blue.mean()),
            "red_left": float(red[:, :mid].mean()),
            "red_right": float(red[:, mid:].mean()),
            "blue_left": float(blue[:, :mid].mean()),
            "blue_right": float(blue[:, mid:].mean()),
        }
        if shot["rect"] is not None:
            record["recall"] = fraction(red if shot["kind"] == "red" else blue, shot["rect"])
        else:
            record["recall"] = None
        rows.append(record)
        view = overlay(image, red, blue)
        text = f"{shot['kind']} R{record['red_frame'] * 100:.1f}% B{record['blue_frame'] * 100:.1f}%"
        if record["recall"] is not None:
            text += f" rect{record['recall'] * 100:.0f}%"
        cv2.putText(view, text, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        small = cv2.resize(view, (960, 540), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(OUT / f"{shot['stamp']}.jpg"), small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])

    (OUT / "summary.json").write_text(
        json.dumps({"rule": "appearance", "shots": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    report(rows)


def half(row: dict) -> float:
    return max(row["red_left"], row["red_right"], row["blue_left"], row["blue_right"])


def report(rows: list[dict]) -> None:
    for kind in ("red", "blue"):
        subset = [row for row in rows if row["kind"] == kind]
        recall = np.array([row["recall"] for row in subset])
        print(
            f"{kind} n={len(subset)} rect>=0.5 {int((recall >= 0.5).sum())}"
            f" median {np.median(recall):.2f}"
        )
        for row in subset:
            if row["recall"] < 0.5:
                print(f"  {row['stamp'][9:]} rect {row['recall'] * 100:.0f}% frame {row['red_frame'] * 100:.1f}%/{row['blue_frame'] * 100:.1f}%")
    neither = [row for row in rows if row["kind"] == "neither" and half(row) >= HALF_FLOOR]
    print(f"neither half>={HALF_FLOOR:.2f} {len(neither)}")
    for row in sorted(neither, key=half, reverse=True):
        print(
            f"  {row['stamp'][9:]} R{row['red_frame'] * 100:.1f}% B{row['blue_frame'] * 100:.1f}%"
            f" half {half(row) * 100:.1f}%"
        )


if __name__ == "__main__":
    main()
