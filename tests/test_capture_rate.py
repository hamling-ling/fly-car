"""Capture rate reported by the Uno Q camera thread."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "flycar_q" / "python"))

import cv2

from camera import CaptureRate, configure_capture  # noqa: E402


def test_read_is_frames_over_the_window() -> None:
    rate = CaptureRate(10.0, 100)
    assert rate.read(11.0, 115) == pytest.approx(15.0)
    assert rate.read(12.0, 125) == pytest.approx(10.0)


def test_configure_sets_mjpg_then_the_size_and_skips_fps() -> None:
    calls: list[int] = []

    class Cap:
        def set(self, prop: int, value: int) -> bool:
            calls.append(prop)
            return True

    configure_capture(Cap(), 1280, 720)
    assert calls == [
        cv2.CAP_PROP_FOURCC,
        cv2.CAP_PROP_FRAME_WIDTH,
        cv2.CAP_PROP_FRAME_HEIGHT,
        cv2.CAP_PROP_BUFFERSIZE,
    ]
    assert cv2.CAP_PROP_FPS not in calls


def test_mjpg_format_sets_both_dimensions() -> None:
    from camera import (  # noqa: E402
        _FORMAT_BYTES,
        _PIX_OFFSET,
        _VIDIOC_S_FMT,
        _V4L2_PIX_FMT_MJPEG,
        format_size,
        mjpg_format,
    )

    buf = mjpg_format(1280, 720)
    assert len(buf) == _FORMAT_BYTES
    assert _VIDIOC_S_FMT == 0xC0D05605
    assert format_size(buf) == (1280, 720)
    pixelformat = int.from_bytes(buf[_PIX_OFFSET + 8 : _PIX_OFFSET + 12], "little")
    assert pixelformat == _V4L2_PIX_FMT_MJPEG


def _fake_open(monkeypatch, sizes: list[tuple[int, int]]):
    made: list[object] = []

    class Cap:
        def __init__(self, size: tuple[int, int]) -> None:
            self.size = size
            self.released = False
            self.sets: list[int] = []

        def isOpened(self) -> bool:
            return True

        def release(self) -> None:
            self.released = True

        def set(self, prop: int, value: int) -> bool:
            self.sets.append(prop)
            return True

        def get(self, prop: int) -> float:
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return self.size[0]
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return self.size[1]
            if prop == cv2.CAP_PROP_FOURCC:
                return cv2.VideoWriter_fourcc(*"MJPG")
            return 0

    def factory(device: str, api: int) -> Cap:
        cap = Cap(sizes[len(made)])
        made.append(cap)
        return cap

    monkeypatch.setattr(cv2, "VideoCapture", factory)
    monkeypatch.setattr("camera.enable_auto_exposure", lambda device: None)
    return made


def test_open_keeps_a_1280x720_capture(monkeypatch) -> None:
    from camera import open_capture  # noqa: E402

    made = _fake_open(monkeypatch, [(1280, 720)])
    asked: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "camera.request_mjpg",
        lambda device, width, height: asked.append((width, height)) or (width, height),
    )
    cap = open_capture("/dev/video0")
    assert cap is made[0]
    assert made[0].released is False
    assert asked == [(1280, 720)]


def test_open_raises_when_the_driver_keeps_4_by_3(monkeypatch) -> None:
    from camera import open_capture  # noqa: E402

    made = _fake_open(monkeypatch, [(800, 600)])
    resets: list[str] = []
    monkeypatch.setattr("camera.request_mjpg", lambda device, width, height: (800, 600))
    monkeypatch.setattr("camera.usb_reset", lambda device: resets.append(device))
    monkeypatch.setattr("camera._reset_at", None)
    monkeypatch.setattr("camera.time.sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="ioctl kept 800x600"):
        open_capture("/dev/video0")
    assert made[0].released is True
    assert resets == ["/dev/video0"]


def test_a_zero_span_reports_zero_and_moves_the_mark() -> None:
    rate = CaptureRate(10.0, 100)
    assert rate.read(10.0, 104) == 0.0
    assert rate.read(11.0, 114) == pytest.approx(10.0)
