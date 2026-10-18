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
from flycar.occupancy import half_counts
from flycar.pulse import wheel_pulses

from camera import Eye
from config import COUNT_S, LOG_S, MIRROR, TICK_S
from motors import send, wait_until_bridge


def loop() -> None:
    if not wait_until_bridge():
        raise SystemExit("マイコンに届かない")
    eye = Eye()
    plant = Plant()
    counts = (0.0, 0.0, 0.0, 0.0)
    try:
        eye.start()
        if not eye.wait_ready():
            print("camera: フレームが来てから走り始める")
        next_count = time.monotonic()
        next_tick = next_count
        next_log = next_count
        while True:
            now = time.monotonic()
            if now >= next_count:
                frame = eye.latest()
                if frame is not None:
                    try:
                        counts = half_counts(frame, mirror=MIRROR)
                    except ValueError as exc:
                        print(f"counts: {exc}")
                        counts = (0.0, 0.0, 0.0, 0.0)
                        send(0, 0)
                next_count += COUNT_S
                if next_count < now:
                    next_count = now + COUNT_S
            if now >= next_tick:
                step = plant.steps(*counts)
                sent = send(*wheel_pulses(step.v_left, step.v_right))
                if sent is not None and now >= next_log:
                    right, left = sent
                    print(
                        f"red {counts[0]:.2f} {counts[1]:.2f}  "
                        f"blue {counts[2]:.2f} {counts[3]:.2f}  "
                        f"pulse R:{right} L:{left}  {step.mode}"
                    )
                    next_log += LOG_S
                    if next_log < now:
                        next_log = now + LOG_S
                next_tick += TICK_S
                if next_tick < now:
                    next_tick = now + TICK_S
            time.sleep(0.002)
    finally:
        send(0, 0)
        eye.close()


App.run(user_loop=loop)
