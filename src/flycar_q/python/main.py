"""20 ms ごとに膜を進め、10 Hz で占有を取り直す。

パルスの引数はスケッチと同じく右、左。カメラの読み出しは別スレッドで、
ここは最新の 1 枚だけを見る。
"""

from __future__ import annotations

import time

import bootstrap

bootstrap.install()

from arduino.app_utils import App, Bridge

from flycar.behavior import Plant
from flycar.occupancy import Counts
from flycar.pulse import wheel_pulses

from camera import Eye
from config import COUNT_S, LOG_S, MIRROR, TICK_S
from face import frame, lamps
from motors import send, wait_until_bridge
from schedule import Next

_face_error: str | None = None


def publish_face(
    red_l: float,
    red_r: float,
    blue_l: float,
    blue_r: float,
    sent: tuple[int, int],
    mode: str,
) -> None:
    """Push one frame. A Bridge failure leaves the wheels on their last command."""
    right, left = sent
    see_red, see_blue, go_forward, go_back = lamps(
        red_l, red_r, blue_l, blue_r, right, left
    )
    _call("showFace", frame(red_l, red_r, blue_l, blue_r, right, left, mode))
    _call("showLamps", see_red, see_blue, go_forward, go_back)


def _call(name: str, *args: object) -> None:
    global _face_error
    try:
        Bridge.call(name, *args)
    except Exception as exc:
        text = f"{name} failed: {exc}"
        if text != _face_error:
            print(text)
            _face_error = text
        return
    if _face_error is not None and _face_error.startswith(name):
        _face_error = None


def loop() -> None:
    if not wait_until_bridge():
        raise SystemExit("マイコンに届かない")
    eye = Eye()
    plant = Plant()
    counts = Counts()
    try:
        eye.start()
        if not eye.wait_ready():
            print("camera: フレームが来てから走り始める")
        next_count = Next(COUNT_S)
        next_tick = Next(TICK_S)
        next_log = Next(LOG_S)
        last_sent = (0, 0)
        last_mode = "stop"
        while True:
            now = time.monotonic()
            counted = False
            if next_count.tick(now):
                counted = True
                if not counts.update(eye.latest(), mirror=MIRROR):
                    stopped = send(0, 0)
                    if stopped is not None:
                        last_sent = stopped
                        last_mode = "stop"
            if next_tick.tick(now):
                step = plant.steps(*counts.values)
                sent = send(*wheel_pulses(step.v_left, step.v_right))
                if sent is not None:
                    last_sent = sent
                    last_mode = step.mode
                    if next_log.tick(now):
                        right, left = sent
                        red_l, red_r, blue_l, blue_r = counts.values
                        print(
                            f"red {red_l:.2f} {red_r:.2f}  "
                            f"blue {blue_l:.2f} {blue_r:.2f}  "
                            f"pulse R:{right} L:{left}  {step.mode}  "
                            f"cam {eye.fps():.1f} fps  steps {plant.mean_ms():.2f} ms"
                        )
            if counted:
                red_l, red_r, blue_l, blue_r = counts.values
                publish_face(red_l, red_r, blue_l, blue_r, last_sent, last_mode)
            time.sleep(0.002)
    finally:
        send(0, 0)
        publish_face(0.0, 0.0, 0.0, 0.0, (0, 0), "stop")
        eye.close()


App.run(user_loop=loop)
