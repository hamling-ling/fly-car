"""止まった車体の横ずれから、直進かどうかを平均と 95% 区間で出す。

走っている姿は見ない。出発線から、前と後ろの横ずれを mm で読む。右が正。
前後が同じだけずれていれば向きは 0 で、前だけ右なら向きは正、左輪が速い。
"""

from __future__ import annotations

import math

# 自由度 1..30 の両側 95%。それより多いときは区間を少し広く 2.0 にする。
_T95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}

BODY_MM = 170.0
MIN_LENGTH_MM = 50.0
MAX_LENGTH_MM = 500.0
MAX_OFFSET_MM = 2000.0


def t95(df: int) -> float:
    if df < 1:
        raise ValueError("自由度が足りない")
    if df > 30:
        return 2.0
    return _T95[df]


def heading_deg(front_mm: float, rear_mm: float, length_mm: float) -> float:
    """前と後ろの横ずれから、右を正にした向きを度で返す。"""
    length = float(length_mm)
    if length <= 0.0:
        raise ValueError("前後の間隔が 0 以下")
    return math.degrees(math.atan2(float(front_mm) - float(rear_mm), length))


def summarize(values: list[float]) -> dict:
    """平均、標本標準偏差、標準誤差、95% 区間。1 回では区間を出さない。"""
    n = len(values)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "sd": None,
            "sem": None,
            "ci_low": None,
            "ci_high": None,
            "includes_zero": None,
        }
    mean = sum(values) / n
    if n == 1:
        return {
            "n": 1,
            "mean": mean,
            "sd": None,
            "sem": None,
            "ci_low": None,
            "ci_high": None,
            "includes_zero": None,
        }
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    sd = math.sqrt(var)
    sem = sd / math.sqrt(n)
    half = t95(n - 1) * sem
    low = mean - half
    high = mean + half
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "sem": sem,
        "ci_low": low,
        "ci_high": high,
        "includes_zero": low <= 0.0 <= high,
    }


def reading(summary: dict) -> str:
    """区間が 0 を含むか、どちらの輪が速いか。"""
    if summary["n"] < 2:
        return "回数不足"
    if summary["includes_zero"]:
        return "区別できない"
    if summary["mean"] > 0.0:
        return "左が速い"
    return "右が速い"


def make_trial(
    right: int,
    left: int,
    ms: int,
    front_mm: float,
    rear_mm: float,
    length_mm: float,
) -> dict:
    if ms < 1:
        raise ValueError("走行時間が 0 以下")
    length = float(length_mm)
    front = float(front_mm)
    rear = float(rear_mm)
    if length < MIN_LENGTH_MM or length > MAX_LENGTH_MM:
        raise ValueError("前後の間隔が範囲外")
    if abs(front) > MAX_OFFSET_MM or abs(rear) > MAX_OFFSET_MM:
        raise ValueError("横ずれが範囲外")
    return {
        "right": int(right),
        "left": int(left),
        "ms": int(ms),
        "front_mm": front,
        "rear_mm": rear,
        "length_mm": length,
        "heading_deg": heading_deg(front, rear, length),
    }


def group_rows(trials: list[dict]) -> list[dict]:
    """同じ右・左・走行時間の向きをまとめる。"""
    buckets: dict[tuple[int, int, int], list[dict]] = {}
    for trial in trials:
        key = (int(trial["right"]), int(trial["left"]), int(trial["ms"]))
        buckets.setdefault(key, []).append(trial)
    rows = []
    for right, left, ms in sorted(buckets):
        group = buckets[(right, left, ms)]
        summary = summarize([t["heading_deg"] for t in group])
        fronts = [t["front_mm"] for t in group]
        rows.append(
            {
                "right": right,
                "left": left,
                "ms": ms,
                "front_mean": sum(fronts) / len(fronts),
                "reading": reading(summary),
                **summary,
            }
        )
    return rows
