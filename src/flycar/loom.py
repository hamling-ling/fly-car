"""DNp01 current from angular size and expansion.

LC4 follows expansion through a sigmoid. LPLC2 follows angular size through
a Gaussian peaked at 40°. A cell contributes its chemical synapse count onto
the ipsilateral DNp01, multiplied by the fraction of its columns inside the
blue disk, and the side is divided by that side's total LC4 + LPLC2 count.

The Gaussian peak 40° and width 20° are the hand-set values from
``research/notebooks/loom_sigmoid.ipynb``. That notebook scales the sum by
80/50. This car uses 100/50, so the leading factor is 2.0. A frontal card
that reached about 0.98 under 80/50 reaches about 1.22 here. The sigmoid
in the notebook is centered at 8 rad/s. This camera clips a blue card once
it fills the frame, so a hand can only produce about 1 rad/s. The center
here is 0.20 rad/s and the width is 0.10 rad/s. The LC4 term is then
multiplied by 5, so a frontal sheet of about 22° at 0.4 rad/s can cross
threshold even when it straddles the two eyes. A static disk is unchanged,
because that factor multiplies expansion only. None of these is a fit.
LPLC2 alone cannot fill the denominator.

The camera estimates one disk from the largest blue region. Angular size is
the equal-area circle of those pixels on the camera's tangent plane.
Expansion is the increase in that angle since the previous frame that also
saw a region. A region that appears, or one that shrinks, contributes no
expansion. Columns come from ``loom_cells.npz``, built by
``scripts/export_loom_cells.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

R_MAX = 100.0
R_REF = 50.0
SCALE = R_MAX / R_REF
SIZE_PEAK_DEG = 40.0
SIZE_SIGMA_DEG = 20.0
EARLY_MID = 0.20
EARLY_WIDTH = 0.10
# Hand-set. A frontal sheet near 22° at 0.4 rad/s covered too little of
# either eye for the sigmoid to reach threshold. Five times the LC4 term
# crosses it. The size term is not scaled, so a stopped disk is unchanged.
LC4_GAIN = 5.0
# Specks smaller than this fraction of the frame are not a disk.
BLUE_MIN_FRACTION = 0.002

CELLS_PATH = Path(__file__).with_name("loom_cells.npz")


def camera_tangents(dfov_deg: float = 58.0, aspect: float = 16 / 9) -> tuple[float, float]:
    """Tangent of the half-angles for a diagonal field on a 16:9 frame."""
    half = np.tan(np.deg2rad(dfov_deg) / 2.0)
    vertical = half / np.sqrt(aspect**2 + 1.0)
    horizontal = aspect * vertical
    return float(horizontal), float(vertical)


def anchored_sigmoid(theta_dot: float, mid: float = EARLY_MID, width: float = EARLY_WIDTH) -> float:
    """Zero at no expansion, one at high expansion."""
    raw = 1.0 / (1.0 + np.exp(-(theta_dot - mid) / width))
    raw0 = 1.0 / (1.0 + np.exp(mid / width))
    return float((raw - raw0) / (1.0 - raw0))


def size_gain(theta: float) -> float:
    """One at 40° full angle. ``theta`` is radians."""
    deg = float(np.rad2deg(theta))
    return float(np.exp(-0.5 * ((deg - SIZE_PEAK_DEG) / SIZE_SIGMA_DEG) ** 2))


@dataclass(frozen=True)
class Disk:
    """Blue disk in image coordinates, plus its full angular size in radians.

    ``u`` and ``v`` run from 0 to 1, left to right and top to bottom.
    ``ru`` and ``rv`` are the ellipse radii in those coordinates.
    """

    cu: float
    cv: float
    ru: float
    rv: float
    theta: float


class Population:
    """Columns of one cell type, and each cell's synapse count onto DNp01."""

    def __init__(self, pack: np.lib.npyio.NpzFile, prefix: str) -> None:
        self.u = pack[f"{prefix}_u"]
        self.v = pack[f"{prefix}_v"]
        self.n = pack[f"{prefix}_n"].astype(np.float64)
        self.starts = pack[f"{prefix}_starts"]
        self.side = pack[f"{prefix}_side"]
        self.w = pack[f"{prefix}_w"]
        self.cell_n = np.add.reduceat(self.n, self.starts)
        self.side_sum = np.array(
            [float(self.w[self.side == code].sum()) for code in (0, 1)],
            dtype=np.float64,
        )

    def covered(self, disk: Disk) -> np.ndarray:
        """Return ``sum f_i w_i`` for the left and the right eye."""
        if disk.ru <= 1e-8 or disk.rv <= 1e-8:
            return np.zeros(2, dtype=np.float64)
        du = (self.u - disk.cu) / disk.ru
        dv = (self.v - disk.cv) / disk.rv
        inside = ((du * du + dv * dv) <= 1.0).astype(np.float64)
        covered_n = np.add.reduceat(self.n * inside, self.starts)
        frac = covered_n / self.cell_n
        out = np.zeros(2, dtype=np.float64)
        for code in (0, 1):
            chosen = self.side == code
            out[code] = float(frac[chosen] @ self.w[chosen])
        return out


class Cells:
    """LC4, LPLC2, and the per-side synapse totals."""

    def __init__(self, path: Path = CELLS_PATH) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"loom cell table is missing: {path}")
        pack = np.load(path)
        self.lc4 = Population(pack, "lc4")
        self.lplc2 = Population(pack, "lplc2")
        self.side_ref = self.lc4.side_sum + self.lplc2.side_sum

    def current(self, disk: Disk, theta_dot: float) -> tuple[float, float]:
        """DNp01 current on the left and the right. Expansion below zero is ignored."""
        speed = anchored_sigmoid(max(float(theta_dot), 0.0))
        gain = size_gain(disk.theta)
        lc4 = self.lc4.covered(disk)
        lplc = self.lplc2.covered(disk)
        drive = SCALE * (LC4_GAIN * speed * lc4 + gain * lplc) / self.side_ref
        return float(drive[0]), float(drive[1])


_CELLS: Cells | None = None


def cells() -> Cells:
    global _CELLS
    if _CELLS is None:
        _CELLS = Cells()
    return _CELLS


def project_rel(
    rel: np.ndarray,
    radius: float,
    optical: np.ndarray,
    cam_up: np.ndarray,
    cam_right: np.ndarray,
    tan_h: float,
    tan_v: float,
) -> Disk | None:
    """Project a sphere. ``rel`` is the center minus the camera, in meters.

    The angular size uses the 3D distance. The ellipse uses depth along the
    optical axis, matching the loom notebooks. A center behind the camera
    returns None.
    """
    depth = float(np.dot(rel, optical))
    if depth <= 1e-4 or radius <= 0.0:
        return None
    dist = float(np.linalg.norm(rel))
    theta = float(2.0 * np.arctan(radius / dist))
    nx = float(np.dot(rel, cam_right)) / depth / tan_h
    ny = float(np.dot(rel, cam_up)) / depth / tan_v
    radius_over_depth = radius / depth
    return Disk(
        cu=(nx + 1.0) / 2.0,
        cv=(1.0 - ny) / 2.0,
        ru=radius_over_depth / tan_h / 2.0,
        rv=radius_over_depth / tan_v / 2.0,
        theta=theta,
    )


def measure_blue(mask: np.ndarray) -> Disk | None:
    """Fit one disk to the largest blue region in a boolean image.

    The region has to cover at least ``BLUE_MIN_FRACTION`` of the frame.
    Smaller regions, and a frame with no blue, return None.
    """
    image = np.ascontiguousarray(np.asarray(mask))
    if image.ndim != 2:
        raise ValueError("blue mask must be a 2D image")
    if image.size == 0 or not np.any(image):
        return None
    _count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        image.astype(np.uint8), connectivity=8
    )
    areas = stats[1:, cv2.CC_STAT_AREA]
    if areas.size == 0:
        return None
    chosen = 1 + int(np.argmax(areas))
    if int(areas.max()) < BLUE_MIN_FRACTION * image.size:
        return None
    ys, xs = np.nonzero(labels == chosen)
    height, width = image.shape
    tan_h, tan_v = camera_tangents()
    u = (xs.astype(np.float64) + 0.5) / width
    v = (ys.astype(np.float64) + 0.5) / height
    nx = (2.0 * u - 1.0) * tan_h
    ny = (1.0 - 2.0 * v) * tan_v
    center_x = float(nx.mean())
    center_y = float(ny.mean())
    pixel_area = (2.0 * tan_h / width) * (2.0 * tan_v / height)
    radius_over_depth = float(np.sqrt(nx.size * pixel_area / np.pi))
    dist_factor = float(np.sqrt(1.0 + center_x * center_x + center_y * center_y))
    theta = float(2.0 * np.arctan(radius_over_depth / dist_factor))
    return Disk(
        cu=(center_x / tan_h + 1.0) / 2.0,
        cv=(1.0 - center_y / tan_v) / 2.0,
        ru=radius_over_depth / tan_h / 2.0,
        rv=radius_over_depth / tan_v / 2.0,
        theta=theta,
    )


class LoomTrack:
    """Hold the last angular size so the next frame can report expansion."""

    def __init__(self) -> None:
        self.theta = 0.0
        self.theta_dot = 0.0
        self.current = (0.0, 0.0)
        self._theta: float | None = None
        self._time: float | None = None

    def update(self, disk: Disk | None, now: float) -> tuple[float, float]:
        """Return the DNp01 currents for this disk at time ``now`` in seconds."""
        if disk is None:
            self.theta = 0.0
            self.theta_dot = 0.0
            self.current = (0.0, 0.0)
            self._theta = None
            self._time = None
            return self.current
        theta_dot = 0.0
        if self._theta is not None and self._time is not None:
            dt = float(now) - self._time
            if dt > 0.0:
                theta_dot = max(0.0, (disk.theta - self._theta) / dt)
        self._theta = disk.theta
        self._time = float(now)
        self.theta = disk.theta
        self.theta_dot = theta_dot
        self.current = cells().current(disk, theta_dot)
        return self.current
