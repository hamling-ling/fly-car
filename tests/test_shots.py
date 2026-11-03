"""JPEG named on the log line. Run from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

from shots import Shots  # noqa: E402


def test_one_capture_is_one_jpeg(tmp_path: Path) -> None:
    """同じ取り込みは 1 枚。次の取り込みは別のファイル。"""
    shots = Shots(tmp_path)
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    frame[0, 0] = (10, 20, 30)
    first = shots.save(frame, 4)
    assert first is not None
    assert (tmp_path / "frames" / f"{first}.jpg").is_file()
    assert shots.save(frame, 4) == first
    assert len(list((tmp_path / "frames").glob("*.jpg"))) == 1
    second = shots.save(frame, 5)
    assert second is not None and second != first
    assert shots.save(None, 6) is None


def test_a_new_run_drops_the_previous_jpegs(tmp_path: Path) -> None:
    """起動のたびに、前の走行の JPEG を消す。"""
    first = Shots(tmp_path)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    first.save(frame, 1)
    assert len(list((tmp_path / "frames").glob("*.jpg"))) == 1
    Shots(tmp_path)
    assert list((tmp_path / "frames").glob("*.jpg")) == []
