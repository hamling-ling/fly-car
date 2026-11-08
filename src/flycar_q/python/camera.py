"""Brio 100 on the Uno Q. One thread keeps the newest frame.

Open MJPG before the frame size, and do not write a frame rate. A written
rate caps the shutter. The exposure controls then let a dim room lengthen
it. The membrane loop must not wait on capture: a long shutter would stall
that window.
"""

from __future__ import annotations

import os
import struct
import fcntl
import threading
import time
from pathlib import Path

from config import WARMUP_FRAMES

STREAM_SIZE = (1280, 720)
# Log 20261107-160814 ran near 30 fps, then cam stayed 0 and one JPEG
# repeated, so a later red sheet was never counted. A blocked dequeue
# returns after this, and that many failures reopen the device.
_READ_TIMEOUT_MS = 500
_READ_FAILS = 3

# VIDIOC_S_CTRL. Same three controls as research/camera_capture_q/capture.py.
_VIDIOC_S_CTRL = 0xC008561C
_EXPOSURE_CONTROLS = (
    ("auto_exposure", 0x009A0901, 3),
    ("exposure_dynamic_framerate", 0x009A0903, 1),
    ("white_balance_automatic", 0x0098090C, 1),
)

# Skip the Qualcomm Venus memory-to-memory nodes. Same test as capture.py.
_V4L2_CAP_VIDEO_CAPTURE = 0x00000001
_V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
_V4L2_CAP_VIDEO_M2M = 0x00004000
_V4L2_CAP_VIDEO_M2M_MPLANE = 0x00008000
_V4L2_CAP_DEVICE_CAPS = 0x80000000
_VIDIOC_QUERYCAP = (2 << 30) | (104 << 16) | (ord("V") << 8) | 0


def configure_capture(cap, width: int, height: int) -> None:
    """MJPG, then the size, then one buffer. A frame rate is not written."""
    import cv2

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)


# 64-bit linux/videodev2.h: struct v4l2_format is 208 bytes and the pix
# fields start at offset 8. VIDIOC_S_FMT carries that size.
_VIDIOC_S_FMT = 0xC0D05605
_V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
_V4L2_PIX_FMT_MJPEG = 0x47504A4D
_FORMAT_BYTES = 208
_PIX_OFFSET = 8


def mjpg_format(width: int, height: int) -> bytearray:
    """One MJPG request. Both dimensions travel in the same ioctl."""
    buf = bytearray(_FORMAT_BYTES)
    struct.pack_into("<I", buf, 0, _V4L2_BUF_TYPE_VIDEO_CAPTURE)
    struct.pack_into(
        "<III", buf, _PIX_OFFSET, int(width), int(height), _V4L2_PIX_FMT_MJPEG
    )
    return buf


def format_size(buf: bytes) -> tuple[int, int]:
    """Width and height the driver wrote back into a format ioctl."""
    width, height = struct.unpack_from("<II", buf, _PIX_OFFSET)
    return int(width), int(height)


def request_mjpg(device: str, width: int, height: int) -> tuple[int, int]:
    """Ask for MJPG at one size while nothing else is streaming the device.

    OpenCV sets the two axes through separate property calls. A driver that
    only has discrete modes can keep the old 4:3 frame instead of crossing
    to 1280x720. This asks for both axes at once and returns the size the
    driver kept.
    """
    buf = mjpg_format(width, height)
    fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, _VIDIOC_S_FMT, buf, True)
    finally:
        os.close(fd)
    return format_size(buf)


# _IO('U', 20). Resets one USB device, not the hub.
_USBDEVFS_RESET = 0x5514
# None until the first reset. A zero here would skip the reset for the
# first 15 s after boot, because time.monotonic() starts at power-on.
_reset_at: float | None = None


def usb_reset(device: str) -> None:
    """Reset the USB device behind a V4L node so a stuck mode can be set again."""
    current = Path("/sys/class/video4linux") / Path(device).resolve().name / "device"
    current = current.resolve()
    for _ in range(6):
        bus = current / "busnum"
        dev = current / "devnum"
        if bus.is_file() and dev.is_file():
            path = f"/dev/bus/usb/{int(bus.read_text()):03d}/{int(dev.read_text()):03d}"
            fd = os.open(path, os.O_WRONLY)
            try:
                fcntl.ioctl(fd, _USBDEVFS_RESET)
            finally:
                os.close(fd)
            return
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise OSError(f"camera: no usb device for {device}")


def _ask_format(device: str, width: int, height: int) -> tuple[int, int]:
    """Request the stream size. A stuck 4:3 mode gets one USB reset."""
    global _reset_at
    kept = request_mjpg(device, width, height)
    if kept == (width, height):
        return kept
    print(f"camera: format ioctl kept {kept[0]}x{kept[1]}")
    now = time.monotonic()
    if _reset_at is not None and now - _reset_at < 15.0:
        return kept
    _reset_at = now
    try:
        usb_reset(device)
    except OSError as exc:
        print(f"camera: usb reset failed: {exc}")
        return kept
    print(f"camera: usb reset {device}")
    time.sleep(1.0)
    try:
        kept = request_mjpg(device, width, height)
    except OSError as exc:
        print(f"camera: format request failed: {exc}")
        return (0, 0)
    print(f"camera: format ioctl kept {kept[0]}x{kept[1]}")
    return kept


def _fourcc_name(code: float) -> str:
    number = int(code)
    raw = bytes((number >> (8 * i)) & 0xFF for i in range(4))
    return raw.decode("ascii", errors="replace")


def _captures(path: str) -> bool:
    """True when ``path`` is a capture node and not a codec device."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return False
    buf = bytearray(104)
    try:
        fcntl.ioctl(fd, _VIDIOC_QUERYCAP, buf)
    except OSError:
        return False
    finally:
        os.close(fd)
    caps = int.from_bytes(buf[84:88], "little")
    device_caps = int.from_bytes(buf[88:92], "little")
    use = device_caps if caps & _V4L2_CAP_DEVICE_CAPS else caps
    m2m = bool(use & (_V4L2_CAP_VIDEO_M2M | _V4L2_CAP_VIDEO_M2M_MPLANE))
    capture = bool(use & (_V4L2_CAP_VIDEO_CAPTURE | _V4L2_CAP_VIDEO_CAPTURE_MPLANE))
    return capture and not m2m


def camera_device() -> str:
    """The Brio capture node, or the first real capture node."""
    by_id = Path("/dev/v4l/by-id")
    if by_id.is_dir():
        brios = sorted(by_id.glob("usb-046d_Brio_100_*-video-index0"))
        if brios:
            return str(brios[0])
    sysfs = Path("/sys/class/video4linux")
    if sysfs.is_dir():
        names = sorted(p.name for p in sysfs.iterdir() if p.name.startswith("video"))
        nodes = [f"/dev/{name}" for name in names]
    else:
        nodes = sorted(str(p) for p in Path("/dev").glob("video*"))
    for node in nodes:
        if _captures(node):
            return node
    raise RuntimeError("camera: no capture node")


def _capture_size(cap) -> tuple[int, int]:
    import cv2

    return (
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    )


def _open_configured(device: str):
    """Open MJPG and ask OpenCV for ``STREAM_SIZE``. The rate stays unset."""
    import cv2

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"camera: could not open {device}")
    width, height = STREAM_SIZE
    configure_capture(cap, width, height)
    timeout = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
    if timeout is not None:
        cap.set(timeout, _READ_TIMEOUT_MS)
    return cap


def open_capture(device: str):
    """Open ``device`` as MJPG at ``STREAM_SIZE`` and leave the rate unset.

    The capture is released when the driver stays at another size. ``Eye.start``
    tries again, so this raise does not end the app by itself.
    """
    import cv2

    width, height = STREAM_SIZE
    try:
        kept_w, kept_h = _ask_format(device, width, height)
    except OSError as exc:
        print(f"camera: format request failed: {exc}")
        kept_w, kept_h = 0, 0
    cap = _open_configured(device)
    got_w, got_h = _capture_size(cap)
    if (got_w, got_h) != (width, height):
        cap.release()
        raise RuntimeError(
            f"camera: {device} stayed {got_w}x{got_h}, "
            f"ioctl kept {kept_w}x{kept_h}, wanted {width}x{height}"
        )
    enable_auto_exposure(device)
    name = _fourcc_name(cap.get(cv2.CAP_PROP_FOURCC))
    print(f"camera: {device}  {name}  {got_w}x{got_h}")
    return cap


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


class CaptureRate:
    """Successful captures per second since the previous read."""

    def __init__(self, now: float, seen: int) -> None:
        self.at = float(now)
        self.seen = int(seen)

    def read(self, now: float, seen: int) -> float:
        span = float(now) - self.at
        frames = int(seen) - self.seen
        self.at = float(now)
        self.seen = int(seen)
        if span <= 0.0:
            return 0.0
        return frames / span


class Eye:
    """Latest BGR frame. Capture runs off the membrane loop."""

    def __init__(self) -> None:
        self._device = ""
        self._cap = None
        self._lock = threading.Lock()
        self._frame = None
        self._seen = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rate = CaptureRate(time.monotonic(), 0)

    def start(self) -> None:
        while not self._stop.is_set():
            try:
                self._device = camera_device()
                self._cap = open_capture(self._device)
                break
            except (RuntimeError, OSError) as exc:
                print(f"camera: open failed: {exc}")
                self._stop.wait(1.0)
        if self._cap is None or self._stop.is_set():
            return
        self._thread = threading.Thread(target=self._read, name="camera", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        cap = self._cap
        misses = 0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                misses += 1
                if misses >= _READ_FAILS:
                    print(f"camera: {misses} reads failed")
                    cap = self._reopen(cap)
                    misses = 0
                else:
                    self._stop.wait(0.2)
                continue
            misses = 0
            with self._lock:
                self._frame = frame
                self._seen += 1

    def _reopen(self, cap):
        import cv2

        print("camera: reopening")
        try:
            cap.release()
        except cv2.error as exc:
            print(f"camera: release failed: {exc}")
        while not self._stop.is_set():
            self._stop.wait(0.3)
            try:
                fresh = open_capture(self._device)
            except (RuntimeError, OSError, cv2.error) as exc:
                print(f"camera: reopen failed: {exc}")
                continue
            self._cap = fresh
            return fresh
        return cap

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def shot(self) -> tuple[object, int]:
        """Copy of the newest frame and how many captures have arrived."""
        with self._lock:
            seen = self._seen
            if self._frame is None:
                return None, seen
            return self._frame.copy(), seen

    def wait_ready(self, timeout_s: float = 20.0) -> bool:
        deadline = timeout_s
        waited = 0.0
        ready = False
        seen = 0
        while waited < deadline:
            with self._lock:
                seen = self._seen
            if seen >= WARMUP_FRAMES:
                ready = True
                break
            self._stop.wait(0.05)
            waited += 0.05
        self._rate = CaptureRate(time.monotonic(), self.seen)
        if ready:
            print(f"camera: warmup {seen} frames")
            return True
        print(f"camera: warmup saw {self.seen} frames")
        return False

    def fps(self) -> float:
        """Captures per second since the previous call. Warmup is not included."""
        return self._rate.read(time.monotonic(), self.seen)

    @property
    def seen(self) -> int:
        with self._lock:
            return self._seen

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        cap = self._cap
        self._cap = None
        if cap is not None and (self._thread is None or not self._thread.is_alive()):
            cap.release()
