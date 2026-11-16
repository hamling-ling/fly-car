"""膜を実時間ぶん進め、10 Hz で占有と青の loom を取り直す。

間隔が 0.02 秒なら 20 ms 分である。遅れた更新は開いた時間ぶん、
ただし 0.70 秒まで進める。パルスの引数はスケッチと同じく右、左。
カメラの読み出しは別スレッドで、ここは最新の 1 枚だけを見る。
顔の送信も別スレッドで、最新の 1 枚だけを送る。
"""

from __future__ import annotations

import threading
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
from shots import Shots, jpeg_enabled
from trace import trace_line, trace_mark

_face_error: str | None = None


class _Span:
    """Mean wall time of one loop section, read and reset like Plant.mean_ms."""

    def __init__(self) -> None:
        self._s = 0.0
        self._n = 0

    def add(self, span_s: float) -> None:
        self._s += span_s
        self._n += 1

    def mean_ms(self) -> float:
        if self._n == 0:
            return 0.0
        mean = self._s / self._n * 1000.0
        self._s = 0.0
        self._n = 0
        return mean


_count_span = _Span()
_face_span = _Span()


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
    _call(
        "showFaceAndLamps",
        frame(red_l, red_r, blue_l, blue_r, right, left, mode),
        *lamps(red_l, red_r, blue_l, blue_r, right, left),
    )


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


class FacePublisher:
    """Send face frames from its own thread, newest only.

    The Bridge round trip is slow and the display can lag, so the loop only
    leaves the newest frame here. A frame still waiting when a newer one
    arrives is dropped, never queued.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending: tuple[float, float, float, float, tuple[int, int], str] | None = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def offer(
        self,
        red_l: float,
        red_r: float,
        blue_l: float,
        blue_r: float,
        sent: tuple[int, int],
        mode: str,
    ) -> None:
        with self._condition:
            self._pending = (red_l, red_r, blue_l, blue_r, sent, mode)
            self._condition.notify()

    def close(self) -> None:
        """Publish the last offered frame, then stop the thread."""
        with self._condition:
            self._closed = True
            self._condition.notify()
        self._thread.join()

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                pending = self._pending
                self._pending = None
                if pending is None:
                    return
            began = time.monotonic()
            publish_face(*pending)
            _face_span.add(time.monotonic() - began)


def loop() -> None:
    if not wait_until_bridge():
        raise SystemExit("マイコンに届かない")
    eye = Eye()
    plant = Plant()
    counts = Counts()
    face_publisher = FacePublisher()
    shots = Shots(enabled=jpeg_enabled())
    try:
        eye.start()
        if not eye.wait_ready():
            print("camera: フレームが来てから走り始める")
        held, held_seen = eye.shot()
        if shots.enabled:
            opened = shots.save(held, held_seen)
            if opened:
                print(f"camera: frame {opened}")
        else:
            print("camera: JPEG は書かない")
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
                began = time.monotonic()
                counted_ok = counts.update(held, mirror=MIRROR, now=now)
                _count_span.add(time.monotonic() - began)
                if not counted_ok:
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
                                f"steps {plant.mean_ms():.2f} ms  n {n}  "
                                f"cnt {_count_span.mean_ms():.1f} ms  "
                                f"face {_face_span.mean_ms():.1f} ms"
                            )
                        if active or max(counts.values) >= 0.002:
                            name = shots.save(held, held_seen)
                            if name:
                                line += f"  img {name}"
                        print(line)
            if counted:
                red_l, red_r, blue_l, blue_r = counts.values
                face_publisher.offer(red_l, red_r, blue_l, blue_r, last_sent, last_mode)
            time.sleep(0.002)
    finally:
        send(0, 0)
        face_publisher.offer(0.0, 0.0, 0.0, 0.0, (0, 0), "stop")
        face_publisher.close()
        eye.close()


App.run(user_loop=loop)
