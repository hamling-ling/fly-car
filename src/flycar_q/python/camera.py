"""Brio 100 on the Uno Q. One thread keeps the newest frame.

The membrane loop must not wait on capture. In a dark room the shutter can
stretch to 250 ms, and a blocking read would stall the 20 ms window.
"""

from __future__ import annotations

import os
import struct
import fcntl
import threading

from arduino.app_peripherals.camera import Camera

from config import WARMUP_FRAMES

STREAM_SIZE = (1280, 720)
# Camera rejects 0. The real interval follows the shutter after the ioctl below.
STREAM_FPS = 10

# VIDIOC_S_CTRL. Same three controls as research/camera_capture_q/capture.py.
_VIDIOC_S_CTRL = 0xC008561C
_EXPOSURE_CONTROLS = (
    ("auto_exposure", 0x009A0901, 3),
    ("exposure_dynamic_framerate", 0x009A0903, 1),
    ("white_balance_automatic", 0x0098090C, 1),
)


def enable_auto_exposure(device: str) -> None:
    """Let the shutter outrun one frame. A failure still leaves the camera open."""
    failed = []
    try:
        fd = os.open(device, os.O_RDWR)
    except OSError as exc:
        print(f"camera controls failed: open {device}: {exc}")
        return
    try:
        for name, cid, value in _EXPOSURE_CONTROLS:
            try:
                fcntl.ioctl(fd, _VIDIOC_S_CTRL, bytearray(struct.pack("<Ii", cid, value)))
            except OSError as exc:
                failed.append(f"{name}: {exc}")
    finally:
        os.close(fd)
    if failed:
        print("camera controls failed: " + "; ".join(failed))
    else:
        print(f"camera controls set on {device}")


class Eye:
    """Latest BGR frame. ``capture`` runs off the membrane loop."""

    def __init__(self) -> None:
        self._camera = Camera(resolution=STREAM_SIZE, fps=STREAM_FPS, codec="MJPG")
        self._lock = threading.Lock()
        self._frame = None
        self._seen = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._camera.start()
        device = getattr(self._camera, "v4l_path", "")
        if device:
            enable_auto_exposure(device)
        else:
            print("camera: no v4l_path, exposure controls skipped")
        self._thread = threading.Thread(target=self._read, name="camera", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        while not self._stop.is_set():
            frame = self._camera.capture()
            if frame is None:
                continue
            with self._lock:
                self._frame = frame
                self._seen += 1

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def wait_ready(self, timeout_s: float = 20.0) -> bool:
        deadline = timeout_s
        waited = 0.0
        while waited < deadline:
            with self._lock:
                seen = self._seen
            if seen >= WARMUP_FRAMES:
                print(f"camera: warmup {seen} frames")
                return True
            self._stop.wait(0.05)
            waited += 0.05
        print(f"camera: warmup saw {self.seen} frames")
        return False

    @property
    def seen(self) -> int:
        with self._lock:
            return self._seen

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
