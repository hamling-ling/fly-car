#!/usr/bin/env python3
"""Grab one frame from a USB camera on the Arduino Uno Q.

The Qualcomm Venus codec nodes are memory-to-memory and are skipped.
The default frame is 1280x720. The camera's auto exposure is allowed to
lengthen the shutter in a dim room, and the script waits until that exposure
settles before saving. A fixed gamma then lifts shadows the same way in
sunlight and in an evening room. Pitch black still has nothing to lift.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
from pathlib import Path

V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
V4L2_CAP_VIDEO_M2M = 0x00004000
V4L2_CAP_VIDEO_M2M_MPLANE = 0x00008000
V4L2_CAP_DEVICE_CAPS = 0x80000000
VIDIOC_QUERYCAP = (2 << 30) | (104 << 16) | (ord("V") << 8) | 0


def query_cap(path: str) -> dict:
    """Return driver, card, bus, and whether this node can capture frames."""
    info = {"path": path, "error": "", "driver": "", "card": "", "bus": "", "capture": False}
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError as exc:
        info["error"] = f"open: {exc}"
        return info
    buf = bytearray(104)
    try:
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf)
    except OSError as exc:
        info["error"] = f"VIDIOC_QUERYCAP: {exc}"
        return info
    finally:
        os.close(fd)

    def text(start: int, length: int) -> str:
        return bytes(buf[start : start + length]).split(b"\0", 1)[0].decode(errors="replace")

    caps = int.from_bytes(buf[84:88], "little")
    device_caps = int.from_bytes(buf[88:92], "little")
    use = device_caps if caps & V4L2_CAP_DEVICE_CAPS else caps
    m2m = bool(use & (V4L2_CAP_VIDEO_M2M | V4L2_CAP_VIDEO_M2M_MPLANE))
    capture = bool(use & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE))
    info.update(
        driver=text(0, 16),
        card=text(16, 32),
        bus=text(48, 32),
        capture=capture and not m2m,
    )
    return info


def video_nodes() -> list[str]:
    sysfs = Path("/sys/class/video4linux")
    if sysfs.is_dir():
        names = sorted(p.name for p in sysfs.iterdir() if p.name.startswith("video"))
        return [f"/dev/{name}" for name in names]
    return sorted(str(p) for p in Path("/dev").glob("video*"))


def capture_nodes() -> tuple[list[dict], list[dict]]:
    usable: list[dict] = []
    others: list[dict] = []
    for path in video_nodes():
        info = query_cap(path)
        (usable if info["capture"] else others).append(info)
    return usable, others


def read_exposure(device: str) -> tuple[int, int]:
    """Return (exposure_time_absolute, gain). Exposure is in units of 100 us."""
    import subprocess

    out = subprocess.check_output(
        ["v4l2-ctl", "-d", device, "--get-ctrl=exposure_time_absolute,gain"],
        text=True,
    )
    vals: dict[str, int] = {}
    for line in out.splitlines():
        key, value = line.split(":", 1)
        vals[key.strip()] = int(value.strip().split()[0])
    return vals["exposure_time_absolute"], vals["gain"]


def enable_auto_exposure(device: str) -> None:
    """Let the shutter run past one 30 fps frame when the room is dim."""
    import subprocess

    subprocess.run(
        [
            "v4l2-ctl",
            "-d",
            device,
            "-c",
            "auto_exposure=3,exposure_dynamic_framerate=1,white_balance_automatic=1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def grab(device: str, width: int, height: int, warmup: int):
    import cv2

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"cv2 could not open {device}")
    # MJPG carries 1280x720 and 1920x1080. Do not pin FPS: a 30 fps cap holds
    # the shutter at 33 ms, which leaves an evening room underexposed.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    enable_auto_exposure(device)

    frame = None
    exposure, gain = 0, 0
    prev: tuple[int, float] | None = None
    stable = 0
    min_frames = max(warmup, 1)
    try:
        for i in range(max(min_frames, 90)):
            ok, frame = cap.read()
            if not ok:
                frame = None
                continue
            if i + 1 < min_frames or (i + 1) % 5 != 0:
                continue
            exposure, gain = read_exposure(device)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            level = float(gray.mean())
            if prev is not None and abs(exposure - prev[0]) <= 30 and abs(level - prev[1]) < 3:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev = (exposure, level)
    finally:
        cap.release()
    if frame is None:
        raise RuntimeError(f"no frame from {device}")
    return frame, exposure, gain


def lift_shadows(frame, gamma: float):
    """Same curve in sunlight and in a dim room. Values near white stay put."""
    import cv2
    import numpy as np

    if gamma == 1:
        return frame
    table = np.array([min(255, round(((i / 255.0) ** gamma) * 255.0)) for i in range(256)], dtype=np.uint8)
    return cv2.LUT(frame, table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Save one frame from a USB camera on the Uno Q.")
    parser.add_argument("--device", help="V4L2 node, for example /dev/video2. Default: first capture node.")
    parser.add_argument("--output", type=Path, default=Path("capture.jpg"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--warmup", type=int, default=15, help="Minimum frames before exposure is allowed to settle.")
    parser.add_argument("--gamma", type=float, default=0.8, help="Shadow lift. 1 keeps the camera image unchanged.")
    parser.add_argument("--list", action="store_true", help="List video nodes and exit.")
    args = parser.parse_args()

    usable, others = capture_nodes()
    print("capture nodes:")
    if not usable:
        print("  (none)")
    for info in usable:
        print(f"  {info['path']}  {info['card']}  driver={info['driver']}  bus={info['bus']}")
    print("other video nodes:")
    if not others:
        print("  (none)")
    for info in others:
        detail = info["error"] or f"{info['card']}  driver={info['driver']}"
        print(f"  {info['path']}  {detail}")
    if args.list:
        return 0 if usable else 1

    if args.device:
        device = args.device
    elif usable:
        device = usable[0]["path"]
    else:
        print(
            "No USB camera capture node. /dev/video0 and /dev/video1 on the Uno Q are the Venus codec. "
            "A UVC camera appears only when the USB-C port is in host mode, usually through a powered PD hub.",
            file=sys.stderr,
        )
        return 1

    raw, exposure, gain = grab(device, args.width, args.height, args.warmup)
    import cv2

    frame = lift_shadows(raw, args.gamma)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), frame):
        print(f"failed to write {args.output}", file=sys.stderr)
        return 2
    raw_gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    out_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    print(
        f"saved {args.output}  device={device}  shape={tuple(frame.shape)}  "
        f"exposure_ms={exposure / 10:.1f}  gain={gain}  gamma={args.gamma}  "
        f"raw_mean={raw_gray.mean():.1f}  out_mean={out_gray.mean():.1f}  "
        f"bytes={args.output.stat().st_size}"
    )
    if float(out_gray.std()) < 1.0:
        print("frame is flat; the camera opened but the image has no detail", file=sys.stderr)
        return 3
    # 2500 is this camera's longest shutter. Gain tops out at 255.
    if exposure >= 2400 or (gain >= 250 and float(raw_gray.mean()) < 40):
        print(
            "exposure is at the limit and the frame is still dark; "
            "sunlight and this scene will not match",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
