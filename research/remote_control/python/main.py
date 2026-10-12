"""カメラ映像を見ながら、ブラウザの十字キーで左右の車輪を動かす。

車輪の符号は research/motor_test と同じ。setMotorSpeed の引数は右、左で、
正が前進、負が後退。右旋回は左の車輪を進め、右の車輪を戻す。
ブラウザからの指令が WATCHDOG_S 秒途切れたら止める。
"""

from __future__ import annotations

import time
import threading

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera

# capture.py で映った Brio 100 の MJPG。640x480 は露出が上がる前だとほぼ黒だった。
STREAM_SIZE = (1280, 720)
# Camera は 0 以下を拒否し、開くときにこの値をカメラへ書く。
# そのあとシャッターを伸ばすので、実際の間隔はこれより長くなる。
STREAM_FPS = 10
JPEG_QUALITY = 60
# capture.py と同じ影の持ち上げ。真っ黒なフレームはこれでは絵にならない。
SHADOW_GAMMA = 0.8
# 露出が落ち着くまでのフレーム数。capture.py の夕方は 20 枚あたりで安定した。
EXPOSURE_WARMUP = 20

# VIDIOC_S_CTRL。capture.py が v4l2-ctl に渡している 3 つ。
_VIDIOC_S_CTRL = 0xC008561C
_EXPOSURE_CONTROLS = (
    ("auto_exposure", 0x009A0901, 3),
    ("exposure_dynamic_framerate", 0x009A0903, 1),
    ("white_balance_automatic", 0x0098090C, 1),
)

# キーを押しているあいだページは 0.2 秒ごとに再送する。
# 1 回落ちても止まらないよう、途切れの判定はそれより長くする。
WATCHDOG_S = 0.45
PULSE_LIMIT = 255

ui = WebUI()
lock = threading.Lock()
state = {
    "right": 0,
    "left": 0,
    "sent_right": None,
    "sent_left": None,
    "last": time.monotonic(),
}
camera_error = ""


def clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def mix(up: bool, down: bool, left: bool, right: bool, speed: int) -> tuple[int, int]:
    """押されているキーから、右と左の指令 -255..255 を作る。"""
    forward = (1 if up else 0) - (1 if down else 0)
    # 右旋回は左輪が外側。yaw が正のとき左を進め、右を戻す。
    yaw = (1 if right else 0) - (1 if left else 0)
    right_cmd = forward - yaw
    left_cmd = forward + yaw
    peak = max(abs(right_cmd), abs(left_cmd), 1)
    scale = clamp(speed, 0, PULSE_LIMIT) / peak
    return (
        int(round(right_cmd * scale)),
        int(round(left_cmd * scale)),
    )


def set_target(right: int, left: int, reason: str = "") -> dict:
    right = clamp(int(right), -PULSE_LIMIT, PULSE_LIMIT)
    left = clamp(int(left), -PULSE_LIMIT, PULSE_LIMIT)
    with lock:
        state["last"] = time.monotonic()
        state["right"] = right
        state["left"] = left
        if (right, left) == (state["sent_right"], state["sent_left"]):
            return {"right": right, "left": left}
        try:
            # 引数の順はスケッチと同じく右、左。
            Bridge.call("setMotorSpeed", right, left)
        except Exception as exc:
            print(f"setMotorSpeed failed: {exc}")
            return {"right": right, "left": left, "error": str(exc)}
        state["sent_right"] = right
        state["sent_left"] = left
    note = f" ({reason})" if reason else ""
    print(f"motors R:{right} L:{left}{note}")
    return {"right": right, "left": left}


def drive(up: int = 0, down: int = 0, left: int = 0, right: int = 0, speed: int = 160) -> dict:
    right_pulse, left_pulse = mix(bool(up), bool(down), bool(left), bool(right), speed)
    return set_target(right_pulse, left_pulse)


def lift_shadows(frame):
    import cv2

    return cv2.LUT(frame, lift_shadows.table)


lift_shadows.table = None


def enable_auto_exposure(device: str) -> None:
    """シャッターを 1 フレームより長くする。失敗しても配信は続ける。"""
    import fcntl
    import os
    import struct

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


def exposure_mean(camera, frames: int) -> float | None:
    last = None
    for _ in range(frames):
        frame = camera.capture()
        if frame is None:
            continue
        last = float(frame.mean())
    return last


def status() -> dict:
    with lock:
        return {
            "right": state["right"],
            "left": state["left"],
            "camera": camera_error == "",
            "camera_error": camera_error,
        }


def loop() -> None:
    # スケッチの setup でも止める。Bridge が上がるまでここでは繰り返す。
    for _ in range(50):
        if "error" not in set_target(0, 0, "start"):
            break
        time.sleep(0.1)

    while True:
        time.sleep(0.05)
        with lock:
            stale = (time.monotonic() - state["last"]) > WATCHDOG_S
            moving = (state["sent_right"], state["sent_left"]) != (0, 0)
        if stale and moving:
            set_target(0, 0, "watchdog")


try:
    import numpy as np

    lift_shadows.table = np.array(
        [min(255, round(((i / 255.0) ** SHADOW_GAMMA) * 255.0)) for i in range(256)],
        dtype=np.uint8,
    )
    camera = Camera(
        resolution=STREAM_SIZE,
        fps=STREAM_FPS,
        codec="MJPG",
        adjustments=lift_shadows,
    )
    # start の中で fps をカメラへ書く。そのあとでないと露出設定が戻る。
    camera.start()
    device = getattr(camera, "v4l_path", "")
    if device:
        enable_auto_exposure(device)
    else:
        print("camera: no v4l_path, exposure controls skipped")
    width, height = camera.resolution
    try:
        mean = exposure_mean(camera, EXPOSURE_WARMUP)
    except Exception as exc:
        print(f"camera warmup: {exc}")
        mean = None
    if mean is None:
        print(f"camera: {device} {width}x{height} no frame")
    else:
        print(f"camera: {device} {width}x{height} mean={mean:.1f}")
    ui.expose_camera("/stream", camera, jpeg_quality=JPEG_QUALITY)
except Exception as exc:
    camera_error = str(exc)
    print(f"camera: {exc}")

ui.expose_api("POST", "/drive", drive)
ui.expose_api("GET", "/status", status)
App.run(user_loop=loop)
