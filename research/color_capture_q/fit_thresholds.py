"""samples/marked の四角形から、色紙の色相・彩度・明度の下限を求める。

赤と青の囲いだけを使う。赤でも青でもない絵は下限に入れず、求めた範囲で
半画面が ``COUNT_FLOOR`` 以上になるものだけを最後に出す。

色相は OpenCV の値を 2 倍した度 (0, 2, ..., 358) で、``flycar.occupancy`` と同じである。

1. 囲いごとに色相の 10% 点と 90% 点を取る。
2. 赤は 0 度をまたぐ。180 度未満には 360 度を足し、10% 点の最小を 2 度で
   切り下げ、さらに 2 度広げる。足したあとの 99% 点が 360 度以上のときだけ
   0 度側を開き、その超過分の最大を 2 度で切り上げ、さらに 2 度広げる。
   四角の 1% に届かない画素は、0 度側を開かない。
3. 青はまたがない。10% 点の最小を 10 度で切り下げ、90% 点の最大を 10 度で
   切り上げる。追加の 1 段は付けない。
4. その色相の中で、彩度と明度を 10 刻みに上げる。どの四角形も画素の 80% 以上が
   残る組のうち、彩度が最も高いものを採り、同じ彩度なら明度が最も高いものを採る。

結果は ``src/flycar/color_thresholds.json`` に書く。``occupancy.py`` は起動時にそのファイルを読む。
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
MARKED = ROOT / "samples" / "marked"
SRC = ROOT.parents[1] / "src"
OUTPUT = SRC / "flycar" / "color_thresholds.json"
PY = ROOT / "python"
for path in (SRC, PY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flycar.behavior import COUNT_FLOOR  # noqa: E402
from flycar.occupancy import _large_regions  # noqa: E402
from rects import region_mask  # noqa: E402

RECALL_FLOOR = 0.80
SV_STEP = 10
RED_HUE_STEP = 2
BLUE_HUE_STEP = 10
HUE_SPLIT = 180
SV_BINS = 255 // SV_STEP + 1


def snap_red_wrap(min_shifted_p10: float) -> int:
    """2 度で切り下げ、さらに 2 度広げる。

    入力は、180 度未満に 360 度を足した色相の、画像ごとの 10% 点の最小。
    """
    step = RED_HUE_STEP
    return math.floor(min_shifted_p10 / step) * step - step


def snap_red_low(max_tail_p99: float | None) -> int:
    """0 度側の尾を 2 度で切り上げ、さらに 2 度広げる。尾が無ければ -1。"""
    if max_tail_p99 is None:
        return -1
    step = RED_HUE_STEP
    return math.ceil(max_tail_p99 / step) * step + step


def snap_blue(min_p10: float, max_p90: float) -> tuple[int, int]:
    """10 度で外側へ切る。赤のような追加の 1 段は付けない。"""
    step = BLUE_HUE_STEP
    low = math.floor(min_p10 / step) * step
    high = math.ceil(max_p90 / step) * step
    return low, high


@dataclass(frozen=True)
class PaperSample:
    stamp: str
    kind: str
    hue: np.ndarray
    saturation: np.ndarray
    value: np.ndarray


@dataclass(frozen=True)
class ColorCut:
    saturation: int
    value: int
    hue_low: int
    hue_high: int
    wraps: bool
    worst: float
    worst_stamp: str
    median: float
    n: int


@dataclass(frozen=True)
class Fit:
    red: ColorCut
    blue: ColorCut
    red_seen_as_blue: float
    red_seen_as_blue_stamp: str
    blue_seen_as_red: float
    blue_seen_as_red_stamp: str


def _as_pixels(sample: PaperSample) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if sample.kind not in ("red", "blue"):
        raise ValueError(f"色が赤でも青でもない: {sample.stamp}")
    hue = np.asarray(sample.hue)
    saturation = np.asarray(sample.saturation)
    value = np.asarray(sample.value)
    if hue.size == 0 or saturation.shape != hue.shape or value.shape != hue.shape:
        raise ValueError(f"画素数が揃っていない: {sample.stamp}")
    if saturation.min() < 0 or saturation.max() > 255 or value.min() < 0 or value.max() > 255:
        raise ValueError(f"彩度か明度が 0..255 の外: {sample.stamp}")
    return hue, saturation, value


def red_hue_bounds(hues: list[np.ndarray]) -> tuple[int, int]:
    """赤の ``(low, wrap)``。判定は ``hue <= low`` または ``hue >= wrap``。

    0 度側は、360 度を足した色相の 99% 点が 360 度以上のときだけ開く。
    四角の 1% に届かない画素は、その 99% 点に入らない。
    """
    shifted_p10: list[float] = []
    crossed: list[float] = []
    for hue in hues:
        if hue.size == 0:
            raise ValueError("空の四角形")
        shifted = np.where(hue < HUE_SPLIT, hue.astype(np.float64) + 360, hue)
        shifted_p10.append(float(np.percentile(shifted, 10)))
        high = float(np.percentile(shifted, 99))
        if high >= 360:
            crossed.append(high - 360)
    low = snap_red_low(max(crossed) if crossed else None)
    wrap = snap_red_wrap(min(shifted_p10))
    return low, wrap


def blue_hue_bounds(hues: list[np.ndarray]) -> tuple[int, int]:
    """青の ``(low, high)``。判定は ``low <= hue <= high``。"""
    if any(hue.size == 0 for hue in hues):
        raise ValueError("空の四角形")
    p10 = min(float(np.percentile(hue, 10)) for hue in hues)
    p90 = max(float(np.percentile(hue, 90)) for hue in hues)
    return snap_blue(p10, p90)


def hue_matches(hue: np.ndarray, cut: ColorCut) -> np.ndarray:
    if cut.wraps:
        return (hue <= cut.hue_low) | (hue >= cut.hue_high)
    return (hue >= cut.hue_low) & (hue <= cut.hue_high)


def _suffix(saturation: np.ndarray, value: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """``suffix[s][v]`` は色相を通った画素のうち、彩度と明度が各下限以上の数。"""
    hist = np.zeros((SV_BINS, SV_BINS), dtype=np.int64)
    if np.any(keep):
        s_bin = saturation[keep].astype(np.int16) // SV_STEP
        v_bin = value[keep].astype(np.int16) // SV_STEP
        np.add.at(hist, (s_bin, v_bin), 1)
    flipped = hist[::-1, ::-1].cumsum(0).cumsum(1)
    return flipped[::-1, ::-1]


def strictest_sv(
    samples: list[PaperSample],
    keep: list[np.ndarray],
) -> tuple[int, int, float, str, float]:
    """再現率を満たす組のうち、彩度を先に、明度を次に、最も高いものを返す。"""
    if not samples:
        raise ValueError("四角形が無い")
    rows = []
    for sample, mask in zip(samples, keep, strict=True):
        hue, saturation, value = _as_pixels(sample)
        if mask.shape != hue.shape:
            raise ValueError(f"色相のマスクが画素と違う: {sample.stamp}")
        rows.append((sample.stamp, _suffix(saturation, value, mask), hue.size))
    best: tuple[int, int, float, str, float] | None = None
    for s_i in range(SV_BINS):
        for v_i in range(SV_BINS):
            scores: list[float] = []
            worst = 1.0
            worst_stamp = rows[0][0]
            feasible = True
            for stamp, suffix, total in rows:
                score = float(suffix[s_i, v_i]) / float(total)
                scores.append(score)
                if score < worst:
                    worst = score
                    worst_stamp = stamp
                if score < RECALL_FLOOR:
                    feasible = False
                    break
            if not feasible:
                continue
            candidate = (s_i * SV_STEP, v_i * SV_STEP, worst, worst_stamp, float(np.median(scores)))
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1] > best[1]):
                best = candidate
    if best is None:
        raise RuntimeError(f"再現率 {RECALL_FLOOR:.2f} を満たす彩度と明度が無い")
    return best


def _cut(samples: list[PaperSample], *, wraps: bool, hue_low: int, hue_high: int) -> ColorCut:
    provisional = ColorCut(0, 0, hue_low, hue_high, wraps, 0.0, samples[0].stamp, 0.0, len(samples))
    keep = [hue_matches(sample.hue, provisional) for sample in samples]
    saturation, value, worst, stamp, median = strictest_sv(samples, keep)
    return ColorCut(saturation, value, hue_low, hue_high, wraps, worst, stamp, median, len(samples))


def _covered(sample: PaperSample, cut: ColorCut) -> float:
    hue, saturation, value = _as_pixels(sample)
    mask = hue_matches(hue, cut) & (saturation >= cut.saturation) & (value >= cut.value)
    return float(mask.mean())


def fit_thresholds(samples: list[PaperSample]) -> Fit:
    """赤と青の画素から下限を決める。入力の順で、同点の最悪画像は先のものを出す。"""
    reds = [sample for sample in samples if sample.kind == "red"]
    blues = [sample for sample in samples if sample.kind == "blue"]
    if not reds or not blues:
        raise ValueError("赤と青の四角形が両方要る")
    red_low, red_wrap = red_hue_bounds([sample.hue for sample in reds])
    blue_low, blue_high = blue_hue_bounds([sample.hue for sample in blues])
    red = _cut(reds, wraps=True, hue_low=red_low, hue_high=red_wrap)
    blue = _cut(blues, wraps=False, hue_low=blue_low, hue_high=blue_high)
    red_as_blue = max((_covered(sample, blue), sample.stamp) for sample in reds)
    blue_as_red = max((_covered(sample, red), sample.stamp) for sample in blues)
    return Fit(red, blue, red_as_blue[0], red_as_blue[1], blue_as_red[0], blue_as_red[1])


def masks(image: np.ndarray, fit: Fit) -> tuple[np.ndarray, np.ndarray]:
    """BGR の uint8 画像を、求めた下限で赤と青に分ける。

    画面の ``BLUE_MIN_FRACTION`` 未満の塊は、車と同じく残さない。
    """
    frame = np.asarray(image)
    if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        raise ValueError("frame must be a uint8 BGR image")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16) * 2
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    red = hue_matches(hue, fit.red) & (saturation >= fit.red.saturation) & (value >= fit.red.value)
    blue = hue_matches(hue, fit.blue) & (saturation >= fit.blue.saturation) & (value >= fit.blue.value)
    return _large_regions(red), _large_regions(blue)


def frame_halves(image: np.ndarray, fit: Fit) -> tuple[float, float, float, float]:
    """``(red_left, red_right, blue_left, blue_right)``。列 0 が左。"""
    red, blue = masks(image, fit)
    mid = red.shape[1] // 2
    parts = (
        red[:, :mid],
        red[:, mid:],
        blue[:, :mid],
        blue[:, mid:],
    )
    return tuple(float(part.mean()) if part.size else 0.0 for part in parts)


def _fit_block(cut: ColorCut) -> dict:
    return {
        "n": cut.n,
        "worst": round(float(cut.worst), 6),
        "worst_stamp": cut.worst_stamp,
        "median": round(float(cut.median), 6),
    }


def threshold_document(fit: Fit) -> dict:
    """``occupancy.load_cuts`` が読むオブジェクト。``fit`` は記録だけで、判定には使わない。"""
    return {
        "red": {
            "saturation": fit.red.saturation,
            "value": fit.red.value,
            "hue_low": fit.red.hue_low,
            "hue_wrap": fit.red.hue_high,
        },
        "blue": {
            "saturation": fit.blue.saturation,
            "value": fit.blue.value,
            "hue_low": fit.blue.hue_low,
            "hue_high": fit.blue.hue_high,
        },
        "fit": {
            "recall_floor": RECALL_FLOOR,
            "red": _fit_block(fit.red),
            "blue": _fit_block(fit.blue),
        },
    }


def write_thresholds(fit: Fit, path: Path) -> None:
    """設定を一時ファイルへ書いてから置き換える。"""
    text = json.dumps(threshold_document(fit), indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _describe(name: str, cut: ColorCut) -> str:
    if cut.wraps and cut.hue_low < 0:
        hue = f"色相>={cut.hue_high}"
    elif cut.wraps:
        hue = f"色相<={cut.hue_low} または >={cut.hue_high}"
    else:
        hue = f"色相>={cut.hue_low} かつ <={cut.hue_high}"
    return (
        f"{name} n={cut.n} 彩度>={cut.saturation} 明度>={cut.value} {hue}\n"
        f"  最悪 {cut.worst:.3f} {cut.worst_stamp} 中央値 {cut.median:.3f}"
    )


def _quad_pixels(image: np.ndarray, mark: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    region = region_mask(image.shape[0], image.shape[1], mark)
    return (
        hsv[:, :, 0][region].astype(np.int16) * 2,
        hsv[:, :, 1][region],
        hsv[:, :, 2][region],
    )


def load_marked(marked: Path) -> tuple[list[PaperSample], list[tuple[str, Path]]]:
    samples: list[PaperSample] = []
    neither: list[tuple[str, Path]] = []
    paths = sorted(marked.glob("*.json"))
    if not paths:
        raise SystemExit(f"JSON が無い: {marked}")
    for path in paths:
        meta = json.loads(path.read_text(encoding="utf-8"))
        image_path = path.with_suffix(".jpg")
        if meta.get("neither"):
            neither.append((path.stem, image_path))
            continue
        if meta.get("red") and not meta.get("blue"):
            kind, mark = "red", meta["red"]
        elif meta.get("blue") and not meta.get("red"):
            kind, mark = "blue", meta["blue"]
        else:
            raise SystemExit(f"赤と青のどちらを使うか決まらない: {path.name}")
        image = cv2.imread(str(image_path))
        if image is None:
            raise SystemExit(f"読めない: {image_path}")
        hue, saturation, value = _quad_pixels(image, mark)
        samples.append(PaperSample(path.stem, kind, hue, saturation, value))
    return samples, neither


def _percent(part: int, whole: int) -> str:
    if whole == 0:
        return "なし"
    return f"{100.0 * part / whole:.1f}%"


@dataclass
class Recognition:
    """四角の中の正解と、色紙の無い絵の誤検出。車と同じく小さい塊は除く。"""

    red_in: int = 0
    red_hit: int = 0
    red_as_blue: int = 0
    blue_in: int = 0
    blue_hit: int = 0
    blue_as_red: int = 0
    empty: int = 0
    empty_red: int = 0
    empty_blue: int = 0
    empty_either: int = 0
    empty_lines: list[str] = field(default_factory=list)

    def add_quad(self, kind: str, region: np.ndarray, red: np.ndarray, blue: np.ndarray) -> None:
        inside = np.asarray(region, dtype=bool)
        own = red if kind == "red" else blue
        other = blue if kind == "red" else red
        count = int(inside.sum())
        hit = int(np.asarray(own, dtype=bool)[inside].sum())
        cross = int(np.asarray(other, dtype=bool)[inside].sum())
        if kind == "red":
            self.red_in += count
            self.red_hit += hit
            self.red_as_blue += cross
        else:
            self.blue_in += count
            self.blue_hit += hit
            self.blue_as_red += cross

    def add_empty(self, stamp: str, red: np.ndarray, blue: np.ndarray) -> None:
        red_mask = np.asarray(red, dtype=bool)
        blue_mask = np.asarray(blue, dtype=bool)
        self.empty += red_mask.size
        red_count = int(red_mask.sum())
        blue_count = int(blue_mask.sum())
        either = int(np.logical_or(red_mask, blue_mask).sum())
        self.empty_red += red_count
        self.empty_blue += blue_count
        self.empty_either += either
        if red_count or blue_count:
            self.empty_lines.append(
                f"  {stamp} 赤 {_percent(red_count, red_mask.size)}"
                f" 青 {_percent(blue_count, blue_mask.size)}"
            )

    def format(self) -> str:
        paper_in = self.red_in + self.blue_in
        paper_hit = self.red_hit + self.blue_hit
        lines = [
            "認識 四角の中"
            f" 正解 {_percent(paper_hit, paper_in)}"
            f" 取りこぼし {_percent(paper_in - paper_hit, paper_in)}",
            "  赤"
            f" 正解 {_percent(self.red_hit, self.red_in)}"
            f" 取りこぼし {_percent(self.red_in - self.red_hit, self.red_in)}"
            f" 青へ {_percent(self.red_as_blue, self.red_in)}",
            "  青"
            f" 正解 {_percent(self.blue_hit, self.blue_in)}"
            f" 取りこぼし {_percent(self.blue_in - self.blue_hit, self.blue_in)}"
            f" 赤へ {_percent(self.blue_as_red, self.blue_in)}",
            "色紙の無い絵"
            f" 赤 {_percent(self.empty_red, self.empty)}"
            f" 青 {_percent(self.empty_blue, self.empty)}"
            f" どちらか {_percent(self.empty_either, self.empty)}",
        ]
        lines.extend(self.empty_lines)
        return "\n".join(lines)


def report_recognition(marked: Path, fit: Fit) -> str:
    """車が塗る範囲で、四角の中と色紙の無い絵を集計する。"""
    rates = Recognition()
    for path in sorted(marked.glob("*.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        image_path = path.with_suffix(".jpg")
        image = cv2.imread(str(image_path))
        if image is None:
            raise SystemExit(f"読めない: {image_path}")
        red, blue = masks(image, fit)
        if meta.get("neither"):
            rates.add_empty(path.stem, red, blue)
            continue
        if meta.get("red") and not meta.get("blue"):
            kind, mark = "red", meta["red"]
        elif meta.get("blue") and not meta.get("red"):
            kind, mark = "blue", meta["blue"]
        else:
            raise SystemExit(f"赤と青のどちらを使うか決まらない: {path.name}")
        region = region_mask(image.shape[0], image.shape[1], mark)
        rates.add_quad(kind, region, red, blue)
    return rates.format()


def main() -> None:
    samples, neither = load_marked(MARKED)
    fit = fit_thresholds(samples)
    print(_describe("赤", fit.red))
    print(_describe("青", fit.blue))
    print(
        f"四角の中で逆の色 赤→青 {fit.red_seen_as_blue:.3f} {fit.red_seen_as_blue_stamp}"
        f" 青→赤 {fit.blue_seen_as_red:.3f} {fit.blue_seen_as_red_stamp}"
    )
    print(report_recognition(MARKED, fit))
    hits: list[tuple[str, tuple[float, float, float, float], float]] = []
    for stamp, image_path in neither:
        image = cv2.imread(str(image_path))
        if image is None:
            raise SystemExit(f"読めない: {image_path}")
        halves = frame_halves(image, fit)
        peak = max(halves)
        if peak >= COUNT_FLOOR:
            hits.append((stamp, halves, peak))
    hits.sort(key=lambda item: item[2], reverse=True)
    print(f"neither 半画面>={COUNT_FLOOR:.2f} {len(hits)}")
    for stamp, halves, peak in hits:
        red_l, red_r, blue_l, blue_r = halves
        print(
            f"  {stamp} 左赤 {red_l * 100:.1f}% 右赤 {red_r * 100:.1f}%"
            f" 左青 {blue_l * 100:.1f}% 右青 {blue_r * 100:.1f}% 半画面 {peak * 100:.1f}%"
        )
    write_thresholds(fit, OUTPUT)
    print(f"書いた: {OUTPUT}")


if __name__ == "__main__":
    main()
