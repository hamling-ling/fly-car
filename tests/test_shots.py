"""JPEG named on the log line. Run from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

from shots import Shots, jpeg_enabled  # noqa: E402


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


def test_no_jpeg_file_turns_saving_off(tmp_path: Path) -> None:
    """隣の no-jpeg がある走行は、ファイルを書かない。"""
    assert jpeg_enabled(tmp_path) is True
    (tmp_path / "no-jpeg").write_text("")
    assert jpeg_enabled(tmp_path) is False


def test_disabled_shots_leave_the_old_jpegs(tmp_path: Path) -> None:
    """保存を止めた走行は frames を作らず、前の JPEG も消さない。"""
    frames = tmp_path / "frames"
    frames.mkdir()
    old = frames / "old.jpg"
    old.write_bytes(b"jpeg")
    shots = Shots(tmp_path, enabled=False)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    assert shots.save(frame, 1) is None
    assert shots.save(frame, 1) is None
    assert old.read_bytes() == b"jpeg"
    assert list(frames.glob("*.jpg")) == [old]

    bare = tmp_path / "bare"
    bare.mkdir()
    quiet = Shots(bare, enabled=False)
    assert quiet.save(frame, 2) is None
    assert not (bare / "frames").exists()


def test_a_new_run_drops_the_previous_jpegs(tmp_path: Path) -> None:
    """起動のたびに、前の走行の JPEG を消す。"""
    first = Shots(tmp_path)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    first.save(frame, 1)
    assert len(list((tmp_path / "frames").glob("*.jpg"))) == 1
    Shots(tmp_path)
    assert list((tmp_path / "frames").glob("*.jpg")) == []
