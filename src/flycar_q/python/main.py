"""20 ms ごとに膜を進め、10 Hz で占有を取り直す。

パルスの引数はスケッチと同じく右、左。カメラの読み出しは別スレッドで、
ここは最新の 1 枚だけを見る。
"""

from __future__ import annotations

import time

import bootstrap

bootstrap.install()

from arduino.app_utils import App

from flycar.behavior import Plant
from flycar.occupancy import Counts
from flycar.pulse import wheel_pulses

from camera import Eye
from config import COUNT_S, LOG_S, MIRROR, TICK_S
from motors import send, wait_until_bridge
from schedule import Next


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
        while True:
            now = time.monotonic()
            if next_count.tick(now):
                if not counts.update(eye.latest(), mirror=MIRROR):
                    send(0, 0)
            if next_tick.tick(now):
                step = plant.steps(*counts.values)
                sent = send(*wheel_pulses(step.v_left, step.v_right))
                if sent is not None and next_log.tick(now):
                    right, left = sent
                    red_l, red_r, blue_l, blue_r = counts.values
                    print(
                        f"red {red_l:.2f} {red_r:.2f}  "
                        f"blue {blue_l:.2f} {blue_r:.2f}  "
                        f"pulse R:{right} L:{left}  {step.mode}  "
                        f"cam {eye.fps():.1f} fps  steps {plant.mean_ms():.2f} ms"
                    )
            time.sleep(0.002)
    finally:
        send(0, 0)
        eye.close()


App.run(user_loop=loop)
