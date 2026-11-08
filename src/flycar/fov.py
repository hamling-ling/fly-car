"""Closed-loop drive through one camera's field of view.

A sphere counts only when its projection overlaps the image rectangle.
``View.left`` and ``View.right`` are how much of each eye's range the sphere
covers horizontally, divided by that range's width. The left range runs from
the left edge to ``LEFT_HI``, and the right range runs from ``RIGHT_LO`` to
the right edge. Vertical clipping does not shrink the width. Counts are held
for ``Scene.hold_steps`` membrane steps.

Heading 0 faces +x and left is +y. Image ``nx`` is -1 to +1, right positive,
``ny`` is -1 to +1, up positive.

Other notebooks and scripts use the same types::

    scene = Scene(red=Blob((1.30, -0.40), 0.12))
    run = simulate(scene)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from flycar.behavior import DT, Plant, dna_current
from flycar.loom import LEFT_HI, RIGHT_LO, LoomTrack, camera_tangents, project_rel


@dataclass(frozen=True)
class Blob:
    """Sphere on the ground. Its center height is the radius."""

    xy: tuple[float, float]
    radius: float

    def __post_init__(self) -> None:
        if self.radius < 0.0:
            raise ValueError("radius must be non-negative")
        object.__setattr__(self, "xy", (float(self.xy[0]), float(self.xy[1])))

    def center(self) -> np.ndarray:
        return np.array([self.xy[0], self.xy[1], self.radius])


def _reference_red() -> Blob:
    return Blob((1.30, -0.40), 0.12)


def _reference_blue() -> Blob:
    return Blob((0.25, 0.90), 0.10)


@dataclass(frozen=True)
class View:
    """One sphere in the image. Counts are 0 when it misses the rectangle."""

    nx: float
    ny: float
    nrx: float
    nry: float
    inside: bool
    left: float
    right: float


def _miss() -> View:
    return View(
        nx=float(np.nan),
        ny=float(np.nan),
        nrx=0.0,
        nry=0.0,
        inside=False,
        left=0.0,
        right=0.0,
    )


@dataclass(frozen=True)
class Scene:
    """Initial conditions for one closed-loop run.

    The car starts at ``(x, y)`` with ``heading`` in radians. Pitch is degrees
    down from the horizontal. The diagonal field is the Brio 100's 58°.
    """

    red: Blob | None = field(default_factory=_reference_red)
    blue: Blob | None = field(default_factory=_reference_blue)
    cam_h: float = 0.15
    pitch_deg: float = 12.0
    dfov_deg: float = 58.0
    aspect: float = 16 / 9
    run_s: float = 8.0
    hold_steps: int = 20
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0

    def __post_init__(self) -> None:
        if self.aspect <= 0.0:
            raise ValueError("aspect must be positive")
        if not 0.0 < self.dfov_deg < 180.0:
            raise ValueError("dfov_deg must be between 0 and 180")
        if self.hold_steps < 1:
            raise ValueError("hold_steps must be at least 1")
        if self.run_s <= 0.0:
            raise ValueError("run_s must be positive")

    def fovs(self) -> tuple[float, float]:
        """Horizontal and vertical fields of view, in radians.

        The diagonal is split so the squared tangents of the half-angles add
        up across the 16:9 frame.
        """
        horizontal, vertical = camera_tangents(self.dfov_deg, self.aspect)
        return float(2 * np.arctan(horizontal)), float(2 * np.arctan(vertical))

    def __str__(self) -> str:
        horizontal, vertical = self.fovs()
        lines = [
            (
                f"対角 {self.dfov_deg:.1f}°  "
                f"水平 {np.rad2deg(horizontal):.1f}°  "
                f"垂直 {np.rad2deg(vertical):.1f}°"
            ),
            f"カメラ高さ {self.cam_h:.2f} m  俯角 {self.pitch_deg:.0f}°",
            f"赤 {_blob_text(self.red)}",
            f"青 {_blob_text(self.blue)}",
            f"走行 {self.run_s:.1f} s",
        ]
        if self.x != 0.0 or self.y != 0.0 or self.heading != 0.0:
            lines.append(
                f"車の開始 ({self.x:.2f}, {self.y:.2f}) m  "
                f"向き {np.rad2deg(self.heading):.0f}°"
            )
        return "\n".join(lines)


def _blob_text(blob: Blob | None) -> str:
    if blob is None:
        return "なし"
    return f"({blob.xy[0]:.2f}, {blob.xy[1]:.2f}) m、半径 {blob.radius:.2f} m"


@dataclass(frozen=True)
class Sample:
    """Picture at the start of a hold window, and the wheels after that window."""

    t: float
    x: float
    y: float
    heading: float
    red: View
    blue: View
    i_dna: tuple[float, float]
    i_gf: tuple[float, float]
    rate_dna: tuple[float, float]
    rate_gf: tuple[float, float]
    mode: str
    omega: float
    v_left: float
    v_right: float


@dataclass(frozen=True)
class Run:
    scene: Scene
    samples: tuple[Sample, ...]

    def __str__(self) -> str:
        first = self.samples[0]
        lines = [_view_text("赤", first.red), _view_text("青", first.blue)]
        centered = [
            sample
            for sample in self.samples
            if sample.red.inside and abs(sample.red.nx) < 0.05
        ]
        if centered:
            lines.append(f"赤が水平中央 |nx|<0.05 に入った時刻 {centered[0].t:.2f} s")
        stops = [sample for sample in self.samples if sample.mode == "stop"]
        if stops:
            stop = stops[0]
            lines.append(
                f"停止 {stop.t:.2f} s、"
                f"赤 {stop.red.left:.2f} / {stop.red.right:.2f}、"
                f"青 {stop.blue.left:.2f} / {stop.blue.right:.2f}"
                + _nx_text(stop.red)
            )
        else:
            last = self.samples[-1]
            lines.append(f"停止せず、終了 {last.t:.2f} s は{last.mode}")
        if any(sample.blue.inside for sample in self.samples):
            lines.append("青は走行中に画面へ入った")
        else:
            lines.append("青は画面の外のまま")
        return "\n".join(lines)


def _view_text(name: str, view: View) -> str:
    if not view.inside or not np.isfinite(view.nx):
        return f"開始時の{name}は画面の外"
    return f"開始時の{name} nx={view.nx:+.2f} ny={view.ny:+.2f}"


def _nx_text(view: View) -> str:
    if not np.isfinite(view.nx):
        return ""
    return f"、nx={view.nx:+.2f} ny={view.ny:+.2f}"


def _camera_basis(heading: float, pitch: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # Pitch drops the optical axis below the horizontal.
    # Image right points opposite world left.
    forward = np.array([np.cos(heading), np.sin(heading), 0.0])
    left = np.array([-np.sin(heading), np.cos(heading), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    optical = forward * np.cos(pitch) - up * np.sin(pitch)
    cam_up = forward * np.sin(pitch) + up * np.cos(pitch)
    cam_right = -left
    return optical, cam_up, cam_right


def project_blob(scene: Scene, x: float, y: float, heading: float, blob: Blob | None) -> View:
    """Project one sphere. A missing sphere contributes no counts."""
    if blob is None:
        return _miss()
    pitch = float(np.deg2rad(scene.pitch_deg))
    horizontal, vertical = scene.fovs()
    rel = blob.center() - np.array([x, y, scene.cam_h])
    optical, cam_up, cam_right = _camera_basis(heading, pitch)
    depth = float(np.dot(rel, optical))
    if depth <= 1e-4:
        return _miss()
    right = float(np.dot(rel, cam_right))
    up = float(np.dot(rel, cam_up))
    nx = (right / depth) / np.tan(horizontal / 2.0)
    ny = (up / depth) / np.tan(vertical / 2.0)
    nrx = (blob.radius / depth) / np.tan(horizontal / 2.0)
    nry = (blob.radius / depth) / np.tan(vertical / 2.0)
    x_overlap = min(nx + nrx, 1.0) - max(nx - nrx, -1.0)
    y_overlap = min(ny + nry, 1.0) - max(ny - nry, -1.0)
    if x_overlap <= 0.0 or y_overlap <= 0.0:
        return View(nx, ny, nrx, nry, False, 0.0, 0.0)
    a0, a1 = nx - nrx, nx + nrx

    def overlap(b0: float, b1: float) -> float:
        return max(0.0, min(a1, b1) - max(a0, b0))

    # p = (nx + 1) / 2. Each eye's range is 0.65 wide in p, so 1.30 in nx.
    left_hi = 2.0 * LEFT_HI - 1.0
    right_lo = 2.0 * RIGHT_LO - 1.0
    span = left_hi - (-1.0)
    left = float(np.clip(overlap(-1.0, left_hi) / span, 0.0, 1.0))
    right = float(np.clip(overlap(right_lo, 1.0) / span, 0.0, 1.0))
    return View(nx, ny, nrx, nry, True, left, right)


def simulate(scene: Scene) -> Run:
    """Drive ``scene`` and return one sample per hold window.

    The picture is taken at the start of the window. Red counts and the blue
    sphere's loom current are held for ``hold_steps`` membrane steps of 1 ms.
    Expansion is the increase in angular size since the previous picture.
    The recorded pose is the pose at the picture, and the recorded rates are
    the rates at the end of the window.
    """
    n = int(round(scene.run_s / DT))
    if n < scene.hold_steps:
        raise ValueError("run_s is shorter than one hold window")
    plant = Plant()
    plant.x = scene.x
    plant.y = scene.y
    plant.heading = float((scene.heading + np.pi) % (2 * np.pi) - np.pi)
    tan_h, tan_v = camera_tangents(scene.dfov_deg, scene.aspect)
    track = LoomTrack()
    samples: list[Sample] = []
    for i in range(0, n, scene.hold_steps):
        red = project_blob(scene, plant.x, plant.y, plant.heading, scene.red)
        blue = project_blob(scene, plant.x, plant.y, plant.heading, scene.blue)
        disk = _blue_disk(scene, plant.x, plant.y, plant.heading, tan_h, tan_v)
        track.update(disk, i * DT)
        photo = (plant.x, plant.y, plant.heading)
        place = float(np.clip(red.nx, -1.0, 1.0)) if red.inside else 0.0
        step = plant.step(
            red.left, red.right, blue.left, blue.right, loom=track.current, place=place
        )
        for _ in range(scene.hold_steps - 1):
            step = plant.step(
                red.left, red.right, blue.left, blue.right, loom=track.current, place=place
            )
        samples.append(
            Sample(
                t=i * DT,
                x=photo[0],
                y=photo[1],
                heading=photo[2],
                red=red,
                blue=blue,
                i_dna=dna_current(red.left, red.right, place),
                i_gf=track.current,
                rate_dna=(plant.dna_l.rate, plant.dna_r.rate),
                rate_gf=(plant.gf_l.rate, plant.gf_r.rate),
                mode=step.mode,
                omega=step.omega,
                v_left=step.v_left,
                v_right=step.v_right,
            )
        )
    return Run(scene, tuple(samples))


def _blue_disk(scene: Scene, x: float, y: float, heading: float, tan_h: float, tan_v: float):
    """Angular size of the blue sphere. None when it is missing or behind the camera."""
    blob = scene.blue
    if blob is None:
        return None
    pitch = float(np.deg2rad(scene.pitch_deg))
    optical, cam_up, cam_right = _camera_basis(heading, pitch)
    rel = blob.center() - np.array([x, y, scene.cam_h])
    return project_rel(rel, blob.radius, optical, cam_up, cam_right, tan_h, tan_v)
