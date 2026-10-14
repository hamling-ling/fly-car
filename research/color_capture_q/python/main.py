"""止めたカメラ画像に、赤と青の4点を付けて保存する。

車輪は動かさない。画素はカメラのバッファのまま。ガンマは掛けない。
シャッターとゲインは、絵を止めた瞬間のカメラの値を記録する。
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from fastapi import HTTPException
from fastapi.responses import Response

from rects import quads_for_save, relabel_single

# capture.py で映った Brio 100 の MJPG。640x480 は露出が上がる前だとほぼ黒だった。
STREAM_SIZE = (1280, 720)
# Camera は 0 以下を拒否し、開くときにこの値をカメラへ書く。
# そのあとシャッターを伸ばすので、実際の間隔はこれより長くなる。
STREAM_FPS = 10
# 画面のプレビューだけ。保存ファイルは SAVE_JPEG_QUALITY。
PREVIEW_JPEG_QUALITY = 60
SAVE_JPEG_QUALITY = 95

# VIDIOC_S_CTRL / VIDIOC_G_CTRL。capture.py が v4l2-ctl に渡している 3 つ。
# コンテナには v4l2-ctl が無いので、露出とゲインも同じ ioctl で読む。
_VIDIOC_S_CTRL = 0xC008561C
_VIDIOC_G_CTRL = 0xC008561B
_EXPOSURE_CONTROLS = (
    ("auto_exposure", 0x009A0901, 3),
    ("exposure_dynamic_framerate", 0x009A0903, 1),
    ("white_balance_automatic", 0x0098090C, 1),
)
_EXPOSURE_TIME = 0x009A0902
_GAIN = 0x00980913

NOTE_LIMIT = 80
_STAMP = re.compile(r"^\d{8}T\d{6}_\d{3}$")

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
MARKED = SAMPLES / "marked"

ui = WebUI()
camera_error = ""
device = ""
eye = None
save_lock = threading.Lock()
frozen_lock = threading.Lock()
frozen_frame = None
frozen_jpeg: bytes | None = None
frozen_exposure: tuple[int | None, int | None] = (None, None)
_exposure_at = 0.0
_exposure: tuple[int | None, int | None] = (None, None)


def enable_auto_exposure(path: str) -> None:
    """シャッターを 1 フレームより長くする。失敗しても配信は続ける。"""
    import fcntl
    import os
    import struct

    failed = []
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError as exc:
        print(f"camera controls failed: open {path}: {exc}")
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
        print(f"camera controls set on {path}")


def _get_ctrl(fd: int, cid: int) -> int | None:
    import fcntl
    import struct

    try:
        buf = fcntl.ioctl(fd, _VIDIOC_G_CTRL, struct.pack("<Ii", cid, 0))
    except OSError as exc:
        print(f"exposure: get {cid:#x}: {exc}")
        return None
    _cid, value = struct.unpack("<Ii", buf)
    return int(value)


def read_exposure(path: str) -> tuple[int | None, int | None]:
    """Return (exposure_time_absolute, gain). Exposure is in units of 100 us."""
    import os

    if not path:
        return None, None
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError as exc:
        print(f"exposure: open {path}: {exc}")
        return None, None
    try:
        return _get_ctrl(fd, _EXPOSURE_TIME), _get_ctrl(fd, _GAIN)
    finally:
        os.close(fd)


def cached_exposure() -> tuple[int | None, int | None]:
    global _exposure_at, _exposure
    now = time.monotonic()
    if now - _exposure_at < 1.0:
        return _exposure
    _exposure = read_exposure(device)
    _exposure_at = now
    return _exposure


class SharedEye:
    """1 本の読み出しが最新フレームを保つ。プレビューと保存はそれを見る。"""

    def __init__(self, camera) -> None:
        self._camera = camera
        self._lock = threading.Lock()
        self._frame = None
        self._seen = 0
        self._stop = threading.Event()

    def start(self) -> None:
        self._camera.start()
        threading.Thread(target=self._read, name="camera", daemon=True).start()

    def _read(self) -> None:
        while not self._stop.is_set():
            frame = self._camera.capture()
            if frame is None:
                continue
            with self._lock:
                self._frame = frame.copy()
                self._seen += 1

    def snapshot(self):
        with self._lock:
            if self._frame is None:
                return None, 0
            return self._frame.copy(), self._seen


def stream():
    """プレビュー用の MJPEG。保存ファイルとは品質だけが違う。"""
    import cv2
    from fastapi.responses import StreamingResponse

    def generate():
        last = 0
        while True:
            frame, seen = (None, 0) if eye is None else eye.snapshot()
            if frame is None or seen == last:
                time.sleep(0.05)
                continue
            last = seen
            ok, buf = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), PREVIEW_JPEG_QUALITY],
            )
            if not ok:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


def clean_note(note: str) -> str:
    return " ".join(str(note).split())[:NOTE_LIMIT]


def marked_count() -> int:
    if not MARKED.is_dir():
        return 0
    return sum(1 for path in MARKED.glob("*.jpg"))


def _held() -> tuple[object, bytes | None, int | None, int | None]:
    with frozen_lock:
        return frozen_frame, frozen_jpeg, frozen_exposure[0], frozen_exposure[1]


def status() -> dict:
    frame, seen = (None, 0) if eye is None else eye.snapshot()
    held, _jpeg, held_exposure, held_gain = _held()
    if held is None:
        exposure, gain = cached_exposure()
        mean = None if frame is None else round(float(frame.mean()), 1)
        width = height = None
    else:
        exposure, gain = held_exposure, held_gain
        mean = round(float(held.mean()), 1)
        height, width = int(held.shape[0]), int(held.shape[1])
    return {
        "camera": camera_error == "" and frame is not None,
        "camera_error": camera_error,
        "frames": seen,
        "frozen": held is not None,
        "mean": mean,
        "width": width,
        "height": height,
        "exposure_time_absolute": exposure,
        "gain": gain,
        "marked": marked_count(),
    }


def freeze() -> dict:
    """Keep one frame. Rectangles are drawn on this, not on the live stream."""
    global frozen_frame, frozen_jpeg, frozen_exposure, _exposure, _exposure_at
    import cv2

    if eye is None:
        raise HTTPException(status_code=503, detail=camera_error or "camera is not open")
    frame, _seen = eye.snapshot()
    if frame is None:
        raise HTTPException(status_code=503, detail="フレームがまだ無い")
    exposure, gain = read_exposure(device)
    ok, buf = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), SAVE_JPEG_QUALITY],
    )
    if not ok:
        raise HTTPException(status_code=500, detail="静止画にできなかった")
    with frozen_lock:
        frozen_frame = frame
        frozen_jpeg = buf.tobytes()
        frozen_exposure = (exposure, gain)
    _exposure = (exposure, gain)
    _exposure_at = time.monotonic()
    print(f"froze {frame.shape[1]}x{frame.shape[0]} exposure={exposure} gain={gain}")
    return {
        "frozen": True,
        "width": int(frame.shape[1]),
        "height": int(frame.shape[0]),
        "mean": round(float(frame.mean()), 1),
        "exposure_time_absolute": exposure,
        "gain": gain,
    }


def discard() -> dict:
    """Drop the held frame and return to the live stream."""
    global frozen_frame, frozen_jpeg, frozen_exposure
    with frozen_lock:
        frozen_frame = None
        frozen_jpeg = None
        frozen_exposure = (None, None)
    return {"frozen": False}


def still():
    """The held JPEG. It is the file that will be saved."""
    _frame, jpeg, _exposure_time, _gain = _held()
    if jpeg is None:
        raise HTTPException(status_code=404, detail="止まっている絵が無い")
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def save(
    note: str = "",
    red_points: str = "",
    blue_points: str = "",
    neither: str = "",
) -> dict:
    """Write the held JPEG and the quadrilaterals from that same moment."""
    text = clean_note(note)
    empty = str(neither).strip() in ("1", "true")
    with save_lock:
        frame, jpeg, exposure, gain = _held()
        if frame is None or jpeg is None:
            raise HTTPException(status_code=400, detail="先に絵を止める")
        height, width = int(frame.shape[0]), int(frame.shape[1])
        try:
            red, blue = quads_for_save(red_points, blue_points, width, height, empty)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        now = datetime.now().astimezone()
        stamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond // 1000:03d}"
        MARKED.mkdir(parents=True, exist_ok=True)
        image_path = MARKED / f"{stamp}.jpg"
        meta_path = MARKED / f"{stamp}.json"
        image_path.write_bytes(jpeg)
        meta = {
            "note": text,
            "saved_at": now.isoformat(timespec="seconds"),
            "file": f"samples/marked/{stamp}.jpg",
            "width": width,
            "height": height,
            "mean": round(float(frame.mean()), 1),
            "exposure_time_absolute": exposure,
            "gain": gain,
            "jpeg_quality": SAVE_JPEG_QUALITY,
            "gamma": 1.0,
            "neither": empty,
            "red": red,
            "blue": blue,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    count = marked_count()
    print(
        f"saved {meta['file']} mean={meta['mean']} exposure={exposure} gain={gain} "
        f"neither={empty} red={red} blue={blue} note={text!r}"
    )
    return {**meta, "count": count}


def _stamp_paths(stamp: str) -> tuple[Path, Path]:
    if not _STAMP.fullmatch(stamp):
        raise HTTPException(status_code=400, detail="その枚は無い")
    image = MARKED / f"{stamp}.jpg"
    meta_path = MARKED / f"{stamp}.json"
    if not image.is_file() or not meta_path.is_file():
        raise HTTPException(status_code=404, detail="その枚は無い")
    return image, meta_path


def marks() -> dict:
    """Saved shots, oldest first."""
    items = []
    if MARKED.is_dir():
        for path in sorted(MARKED.glob("*.json")):
            if not _STAMP.fullmatch(path.stem):
                continue
            if not (MARKED / f"{path.stem}.jpg").is_file():
                continue
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["stamp"] = path.stem
            items.append(meta)
    return {"marks": items}


def mark(stamp: str = ""):
    """One saved JPEG."""
    image, _meta = _stamp_paths(stamp)
    return Response(content=image.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def delete_mark(stamp: str = "") -> dict:
    """Remove one saved JPEG and its JSON."""
    image, meta_path = _stamp_paths(stamp)
    with save_lock:
        image.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    count = marked_count()
    print(f"deleted samples/marked/{stamp}.jpg ({count} left)")
    return {"deleted": stamp, "marked": count}


def relabel(stamp: str = "", color: str = "") -> dict:
    """Move a shot's only rectangle to red or blue."""
    _image, meta_path = _stamp_paths(stamp)
    with save_lock:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        try:
            red, blue = relabel_single(meta.get("red"), meta.get("blue"), color)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        meta["red"] = red
        meta["blue"] = blue
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"relabel samples/marked/{stamp}.jpg {color}")
    meta["stamp"] = stamp
    return meta


try:
    camera = Camera(resolution=STREAM_SIZE, fps=STREAM_FPS, codec="MJPG")
    eye = SharedEye(camera)
    eye.start()
    device = getattr(camera, "v4l_path", "") or ""
    if device:
        enable_auto_exposure(device)
    else:
        print("camera: no v4l_path, exposure controls skipped")
    width, height = camera.resolution
    print(f"camera: {device} {width}x{height}")
except Exception as exc:
    camera_error = str(exc)
    eye = None
    print(f"camera: {exc}")

ui.expose_api("GET", "/stream", stream)
ui.expose_api("GET", "/status", status)
ui.expose_api("GET", "/still", still)
ui.expose_api("POST", "/freeze", freeze)
ui.expose_api("POST", "/discard", discard)
ui.expose_api("POST", "/save", save)
ui.expose_api("GET", "/marks", marks)
ui.expose_api("GET", "/mark", mark)
ui.expose_api("POST", "/delete", delete_mark)
ui.expose_api("POST", "/relabel", relabel)
MARKED.mkdir(parents=True, exist_ok=True)
App.run()
