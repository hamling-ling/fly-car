"""膜を実時間ぶん進め、10 Hz で占有と青の loom を取り直す。

間隔が 0.02 秒なら 20 ms 分である。遅れた更新は開いた時間ぶん、
ただし 0.70 秒まで進める。パルスの引数はスケッチと同じく右、左。
カメラの読み出しは別スレッドで、ここは最新の 1 枚だけを見る。
"""

from __future__ import annotations

import time

import bootstrap

bootstrap.install()

from arduino.app_utils import App, Bridge

from flycar.behavior import Plant, blue_yaw_scale, catch_up_steps
from flycar.occupancy import Counts
from flycar.pulse import wheel_pulses

from camera import Eye
from config import COUNT_S, DETAIL_S, LOG_S, MIRROR, TICK_S
from face import frame, lamps
from motors import send, wait_until_bridge
from schedule import Next
from shots import Shots
from trace import trace_line, trace_mark

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
    _call("showFace", frame(red_l, red_r, blue_l, blue_r, right, left, mode))
    _call("showLamps", *lamps(red_l, red_r, blue_l, blue_r, right, left))


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
    shots = Shots()
    try:
        eye.start()
        if not eye.wait_ready():
            print("camera: フレームが来てから走り始める")
        held, held_seen = eye.shot()
        opened = shots.save(held, held_seen)
        if opened:
            print(f"camera: frame {opened}")
        next_count = Next(COUNT_S)
        next_tick = Next(TICK_S)
        next_log = Next(LOG_S)
        next_detail = Next(DETAIL_S)
        last_sent = (0, 0)
        last_mode = "stop"
        last_mark: tuple[object, ...] | None = None
        last_step = time.monotonic()
        while True:
            now = time.monotonic()
            counted = False
            if next_count.tick(now):
                counted = True
                held, held_seen = eye.shot()
                if not counts.update(held, mirror=MIRROR, now=now):
                    stopped = send(0, 0)
                    if stopped is not None:
                        last_sent = stopped
                        last_mode = "stop"
            if next_tick.tick(now):
                n = catch_up_steps(now - last_step)
                last_step = now
                step = plant.steps(*counts.values, loom=counts.loom, n=n, place=counts.place)
                sent = send(*wheel_pulses(step.v_left, step.v_right))
                if sent is not None:
                    last_sent = sent
                    last_mode = step.mode
                    heartbeat = next_log.tick(now)
                    detail = next_detail.tick(now)
                    scale = blue_yaw_scale(*counts.loom, counts.values[2:])
                    raw = wheel_pulses(step.v_left, step.v_right)
                    dnp = (plant.gf_l.rate, plant.gf_r.rate)
                    mark = trace_mark(
                        scale,
                        counts.loom,
                        counts.theta,
                        counts.theta_dot,
                        dnp,
                        raw,
                        sent,
                        step.mode,
                    )
                    active = (
                        max(counts.loom) >= 0.05
                        or max(dnp) >= 1.0
                        or step.mode != "stop"
                        or sent != (0, 0)
                    )
                    if heartbeat or mark != last_mark or (detail and active):
                        last_mark = mark
                        red_l, red_r, blue_l, blue_r = counts.values
                        line = trace_line(
                            (red_l, red_r),
                            (blue_l, blue_r),
                            counts.loom,
                            scale,
                            counts.theta,
                            counts.theta_dot,
                            dnp,
                            (plant.dna_l.rate, plant.dna_r.rate),
                            step.speed,
                            step.omega,
                            (step.v_right, step.v_left),
                            raw,
                            sent,
                            step.mode,
                        )
                        if heartbeat:
                            line += (
                                f"  cam {eye.fps():.1f} fps  "
                                f"steps {plant.mean_ms():.2f} ms  n {n}"
                            )
                        if active or max(counts.values) >= 0.002:
                            name = shots.save(held, held_seen)
                            if name:
                                line += f"  img {name}"
                        print(line)
            if counted:
                red_l, red_r, blue_l, blue_r = counts.values
                publish_face(red_l, red_r, blue_l, blue_r, last_sent, last_mode)
            time.sleep(0.002)
    finally:
        send(0, 0)
        publish_face(0.0, 0.0, 0.0, 0.0, (0, 0), "stop")
        eye.close()


App.run(user_loop=loop)
