"""十字キーで車輪を動かし、マイコンへ渡す左右の指令を直接入れる。

カメラは使わない。setMotorSpeed の引数は右、左で、正が前進、負が後退。
左モーターの +/- は逆つなぎなので、スケッチが左右とも 1500 µs より長くして前進にする。
ブラウザからの指令が WATCHDOG_S 秒途切れたら止める。
"""

from __future__ import annotations

import threading
import time

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

from curve import clean_limit, direct_commands
from straight import BODY_MM, group_rows, make_trial

WATCHDOG_S = 0.45

ui = WebUI()
lock = threading.Lock()
state = {
    "right": 0,
    "left": 0,
    "sent_right": None,
    "sent_left": None,
    "last": time.monotonic(),
    "busy": False,
    "abort": False,
    "aborted": False,
    "trial_end": 0.0,
    "trial_right": 0,
    "trial_left": 0,
    "trial_ms": 0,
}
trials: list[dict] = []


def _int(value: int, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: float, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trials() -> dict:
    with lock:
        copied = list(trials)
    return {"trials": copied, "groups": group_rows(copied)}


def set_target(right: int, left: int, reason: str = "") -> dict:
    with lock:
        state["last"] = time.monotonic()
        state["right"] = right
        state["left"] = left
        same = (right, left) == (state["sent_right"], state["sent_left"])
        if same:
            return {"right": right, "left": left}
        try:
            Bridge.call("setMotorSpeed", right, left)
        except Exception as exc:
            print(f"setMotorSpeed failed: {exc}")
            return {"right": right, "left": left, "error": str(exc)}
        state["sent_right"] = right
        state["sent_left"] = left
    note = f" ({reason})" if reason else ""
    print(f"motors R:{right} L:{left}{note}")
    return {"right": right, "left": left}


def drive(
    up: int = 0,
    down: int = 0,
    left: int = 0,
    right: int = 0,
    forward_right: int = 150,
    forward_left: int = 149,
    back_right: int = 91,
    back_left: int = 77,
) -> dict:
    with lock:
        if state["busy"]:
            return {"right": state["right"], "left": state["left"], "busy": True}
    sent_right, sent_left = direct_commands(
        bool(up),
        bool(down),
        bool(left),
        bool(right),
        _int(forward_right, 150),
        _int(forward_left, 149),
        _int(back_right, 91),
        _int(back_left, 77),
    )
    return set_target(sent_right, sent_left)


def status() -> dict:
    with lock:
        return {
            "right": state["right"],
            "left": state["left"],
            "busy": state["busy"],
            "aborted": state["aborted"],
            "trial_right": state["trial_right"],
            "trial_left": state["trial_left"],
            "trial_ms": state["trial_ms"],
        }


def run_forward(right: int = 150, left: int = 149, ms: int = 800) -> dict:
    """前進の左右を、指定したミリ秒だけ送る。止めるのは loop。"""
    command_right = clean_limit(_int(right, 150))
    command_left = clean_limit(_int(left, 149))
    duration = _int(ms, 800)
    if duration < 200:
        duration = 200
    if duration > 3000:
        duration = 3000
    now = time.monotonic()
    with lock:
        if state["busy"]:
            busy = True
        else:
            busy = False
            state["busy"] = True
            state["abort"] = False
            state["aborted"] = False
            state["last"] = now
            state["trial_end"] = now + duration / 1000.0
            state["trial_right"] = command_right
            state["trial_left"] = command_left
            state["trial_ms"] = duration
    if busy:
        return {"busy": True, "started": False, **_trials()}
    sent = set_target(command_right, command_left, "trial")
    if "error" in sent:
        with lock:
            state["busy"] = False
        sent.update(_trials())
        return sent
    print(f"trial R:{command_right} L:{command_left} {duration} ms")
    return {
        "started": True,
        "right": command_right,
        "left": command_left,
        "ms": duration,
        "aborted": False,
        **_trials(),
    }


def abort() -> dict:
    with lock:
        state["abort"] = True
    return set_target(0, 0, "abort")


def record(
    right: int = 0,
    left: int = 0,
    ms: int = 800,
    front: float = 0.0,
    rear: float = 0.0,
    length: float = BODY_MM,
) -> dict:
    try:
        trial = make_trial(
            _int(right, 0),
            _int(left, 0),
            _int(ms, 800),
            _float(front, 0.0),
            _float(rear, 0.0),
            _float(length, BODY_MM),
        )
    except ValueError as exc:
        return {"error": str(exc), **_trials()}
    with lock:
        trials.append(trial)
    print(
        f"trial record R:{trial['right']} L:{trial['left']} "
        f"front:{trial['front_mm']} rear:{trial['rear_mm']} "
        f"heading:{trial['heading_deg']:.2f}"
    )
    return _trials()


def undo() -> dict:
    with lock:
        if trials:
            trials.pop()
    return _trials()


def clear_trials() -> dict:
    with lock:
        trials.clear()
    return _trials()


def loop() -> None:
    for _ in range(50):
        if "error" not in set_target(0, 0, "start"):
            break
        time.sleep(0.1)

    while True:
        time.sleep(0.05)
        now = time.monotonic()
        with lock:
            busy = state["busy"]
            aborting = state["abort"]
            ended = busy and now >= state["trial_end"]
            if busy and not aborting and not ended:
                state["last"] = now
            stale = (now - state["last"]) > WATCHDOG_S
            moving = (state["sent_right"], state["sent_left"]) != (0, 0)
        if busy and (aborting or ended):
            set_target(0, 0, "trial-end")
            with lock:
                state["aborted"] = aborting and not ended
                state["busy"] = False
                state["abort"] = False
            print(f"trial end aborted={aborting and not ended}")
        elif stale and moving:
            set_target(0, 0, "watchdog")


ui.expose_api("POST", "/drive", drive)
ui.expose_api("GET", "/status", status)
ui.expose_api("POST", "/run", run_forward)
ui.expose_api("POST", "/abort", abort)
ui.expose_api("POST", "/record", record)
ui.expose_api("POST", "/undo", undo)
ui.expose_api("POST", "/clear", clear_trials)
ui.expose_api("GET", "/trials", _trials)
App.run(user_loop=loop)
