"""JPEG of the frame a log line counted.

The file stem is printed on that line as ``img``. The same capture is not
written twice. Idle heartbeats do not call this. Starting the app removes
the previous run's files.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

JPEG_QUALITY = 85


class Shots:
    """Write frames next to the app, under ``frames/``."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(__file__).resolve().parents[1]
        self.dir = Path(root) / "frames"
        self.dir.mkdir(parents=True, exist_ok=True)
        for old in self.dir.glob("*.jpg"):
            old.unlink()
        self._seen = -1
        self._name: str | None = None

    def save(self, frame: np.ndarray | None, seen: int) -> str | None:
        """Return the file stem, or None when ``frame`` is missing.

        ``seen`` is the camera's capture count. A repeat returns the stem
        already written for that capture.
        """
        if seen == self._seen and self._name is not None:
            return self._name
        if frame is None:
            return None
        stamp = datetime.now()
        name = stamp.strftime("%Y%m%d-%H%M%S-") + f"{stamp.microsecond // 1000:03d}-{int(seen)}"
        path = self.dir / f"{name}.jpg"
        if not cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]):
            print(f"frame: write failed {path.name}")
            return None
        self._seen = int(seen)
        self._name = name
        return name
