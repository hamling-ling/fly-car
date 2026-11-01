"""Column labels and the camera map, without the synapse table.

Run from the repository root:

    python3 -m pytest tests/test_camera_map.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_camera_map.py"
_SPEC = importlib.util.spec_from_file_location("build_camera_map", _PATH)
build = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build)

_DOWNLOAD = Path(__file__).resolve().parents[1] / "scripts" / "download_malecns.py"
_DOWNLOAD_SPEC = importlib.util.spec_from_file_location("download_malecns", _DOWNLOAD)
download = importlib.util.module_from_spec(_DOWNLOAD_SPEC)
_DOWNLOAD_SPEC.loader.exec_module(download)


def test_column_label_keeps_the_last_two_numbers() -> None:
    parsed = build.parse_column_labels(["<unspecified>", "", "LO_L_col_01_08", "LOP_R_col_36_39"])
    assert parsed[0].tolist() == [-1, -1]
    assert parsed[1].tolist() == [-1, -1]
    assert parsed[2].tolist() == [1, 8]
    assert parsed[3].tolist() == [36, 39]


def test_large_column_a_is_the_outer_edge() -> None:
    left = np.array([[1, 1], [10, 20]], dtype=np.int16)
    right = np.array([[1, 1], [10, 20]], dtype=np.int16)
    ab = np.array([[10, 1], [1, 20], [1, 1], [10, 20]], dtype=np.int16)
    side = np.array([0, 0, 1, 1], dtype=np.int8)
    u, v = build.image_uv(ab, side, left, right)
    assert u.tolist() == [0.0, 0.5, 0.5, 1.0]
    assert v.tolist() == [0.0, 1.0, 0.0, 1.0]


def test_download_plan_resumes_a_short_file() -> None:
    assert download.plan(None, 10) == "download"
    assert download.plan(10, 10) == "skip"
    assert download.plan(4, 10) == "resume"
    assert download.plan(12, 10) == "larger"
    assert download.plan(4, None) == "skip"
