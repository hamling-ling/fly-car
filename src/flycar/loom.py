"""DNp01 current from the blue columns on each eye.

Each cell reads the vertical blue fraction of the image column at its
stretched screen position. The stretch keeps the outer edge fixed and lands
the old midline at the far side of the overlap, the same rule as the poster.
LC4 multiplies that fraction by the expansion sigmoid. LPLC2 multiplies it
by 1 while the angle is expanding and by 0 otherwise. Expansion below
0.10 rad/s counts as not expanding. Each side is divided by that cell type's own ipsilateral synapse
sum, then scaled by ``ALPHA``.

The sigmoid center 0.20 rad/s and width 0.10 rad/s, ``K_S``, and ``ALPHA``
are the numbers that produced the three poster figures. A logistic centered
at 8 rad/s leaves 0–1 rad/s, which is what this camera can show, on the
tail, so an expanding sheet would not cross threshold. These are a starting
point. ``1/w`` is the reciprocal of the width inside the exponential.
``K_S`` and ``ALPHA`` are coefficients.

The camera estimates one disk from the largest blue region. Angular size is
the equal-area circle of those pixels. Expansion is the increase in that
angle since the previous frame that also saw a region. A region that
appears, or one that shrinks, contributes no expansion. With a mask, the
column fractions come from that mask. Without one, the disk is drawn as an
ellipse on a small raster and read the same way. Columns come from
``loom_cells.npz``, built by ``scripts/export_loom_cells.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Eye ranges on p, the poster horizontal coordinate. 0 is the left edge.
LEFT_HI = 0.65
RIGHT_LO = 0.35
# Lateral edge stays fixed. The anatomical midline lands at LEFT_HI.
STRETCH = LEFT_HI / 0.5
# Poster-figure starting point. See the module docstring.
K_S = 1.0
SIGMOID_MID = 0.20
SIGMOID_WIDTH = 0.10
# Angle noise on a still sheet is a few hundredths of a rad/s. Below this
# the size term stays off. A hand pushing the sheet at 0.2 rad/s still
# passes. Kept separate from SIGMOID_WIDTH so retuning the logistic does
# not move the noise floor.
EXPANSION_FLOOR = 0.10
ALPHA = 4.0
# Raster used when a caller has a disk and no camera mask.
RASTER_H = 180
RASTER_W = 320
# Specks smaller than this fraction of the frame are not a disk.
BLUE_MIN_FRACTION = 0.002

CELLS_PATH = Path(__file__).with_name("loom_cells.npz")


def camera_tangents(dfov_deg: float = 58.0, aspect: float = 16 / 9) -> tuple[float, float]:
    """Tangent of the half-angles for a diagonal field on a 16:9 frame."""
    half = np.tan(np.deg2rad(dfov_deg) / 2.0)
    vertical = half / np.sqrt(aspect**2 + 1.0)
    horizontal = aspect * vertical
    return float(horizontal), float(vertical)


def expansion(theta_dot: float) -> float:
    """Sigmoid of expansion. About 0.12 at rest, near 1 once ``theta_dot`` is large."""
    return K_S / (1.0 + np.exp(-(float(theta_dot) - SIGMOID_MID) / SIGMOID_WIDTH))


def size_term(theta: float, theta_dot: float) -> float:
    """Size weight g(θ). 1 while the angle is expanding, otherwise 0.

    The poster does not give g(θ) a peak. ``theta`` stays in the signature
    because the weight is g(θ), and the value does not depend on the angle.
    """
    del theta
    if float(theta_dot) < EXPANSION_FLOOR:
        return 0.0
    return 1.0


def widen(u: np.ndarray) -> np.ndarray:
    """Stretch each eye from its lateral edge onto the overlapping ranges."""
    anatomical = np.asarray(u, dtype=np.float64)
    out = np.empty(anatomical.shape, dtype=np.float64)
    left = anatomical <= 0.5
    out[left] = anatomical[left] * STRETCH
    out[~left] = 1.0 - (1.0 - anatomical[~left]) * STRETCH
    return out


def raster(disk: "Disk", height: int = RASTER_H, width: int = RASTER_W) -> np.ndarray:
    """Boolean ellipse of ``disk`` on a small image. An empty disk stays empty."""
    mask = np.zeros((height, width), dtype=bool)
    if disk.ru <= 1e-8 or disk.rv <= 1e-8:
        return mask
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height
    uu, vv = np.meshgrid(u, v)
    mask[:] = ((uu - disk.cu) / disk.ru) ** 2 + ((vv - disk.cv) / disk.rv) ** 2 <= 1.0
    return mask


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
        # Synapse-weighted mean of anatomical u, then the poster stretch.
        total = np.add.reduceat(self.n * self.u, self.starts)
        self.p = widen(total / self.cell_n)

    def column_drive(self, mask: np.ndarray) -> np.ndarray:
        """Return F for the left and the right eye.

        ``f_i`` is the vertical mean of ``mask`` at the cell's screen column.
        The side sum of ``w_i f_i`` is divided by that side's synapse total.
        """
        image = np.asarray(mask)
        if image.ndim != 2:
            raise ValueError("blue mask must be a 2D image")
        height, width = image.shape
        if height == 0 or width == 0 or not np.any(image):
            return np.zeros(2, dtype=np.float64)
        columns = np.asarray(image, dtype=np.float64).mean(axis=0)
        ui = np.clip(np.rint(self.p * width - 0.5).astype(np.int64), 0, width - 1)
        covered = columns[ui]
        out = np.zeros(2, dtype=np.float64)
        for code in (0, 1):
            chosen = self.side == code
            total = float(self.side_sum[code])
            if total <= 0.0:
                continue
            out[code] = float(covered[chosen] @ self.w[chosen] / total)
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

    def current(
        self,
        disk: Disk,
        theta_dot: float,
        mask: np.ndarray | None = None,
    ) -> tuple[float, float]:
        """DNp01 current on the left and the right.

        ``mask`` supplies the blue pixels. Without it, the disk's ellipse is
        rasterized and read the same way. Angle and expansion still come from
        ``disk`` and ``theta_dot``.
        """
        speed = expansion(theta_dot)
        gain = size_term(disk.theta, theta_dot)
        image = raster(disk) if mask is None else mask
        lc4 = self.lc4.column_drive(image)
        lplc = self.lplc2.column_drive(image)
        drive = ALPHA * (speed * lc4 + gain * lplc)
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


def _largest_component(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, int] | None:
    """Row and column indices of the largest region, and the image width.

    Regions smaller than ``BLUE_MIN_FRACTION`` of the frame, and an empty
    frame, return None.
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
    return ys, xs, int(image.shape[1])


def measure_blue(mask: np.ndarray) -> Disk | None:
    """Fit one disk to the largest blue region in a boolean image.

    The region has to cover at least ``BLUE_MIN_FRACTION`` of the frame.
    Smaller regions, and a frame with no blue, return None.
    """
    found = _largest_component(mask)
    if found is None:
        return None
    ys, xs, width = found
    image = np.asarray(mask)
    height = int(image.shape[0])
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

    def update(
        self,
        disk: Disk | None,
        now: float,
        mask: np.ndarray | None = None,
    ) -> tuple[float, float]:
        """Return the DNp01 currents for this disk at time ``now`` in seconds.

        ``mask`` selects the blue columns. Angle and expansion still come
        from ``disk``.
        """
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
        self.current = cells().current(disk, theta_dot, mask)
        return self.current
