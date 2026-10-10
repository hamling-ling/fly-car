"""Closed-loop check for the reference camera scene in notebooks/fov_sim.ipynb.

Run from the repository root:

    python3 -m pytest tests/test_fov.py

The notebook writes the same initial conditions out so they can be edited.
This test keeps the reference scene: a red sphere starts on the right, the
car turns right, and it stops near the horizontal center while the blue
sphere stays outside the frame.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from flycar.fov import Blob, Scene, project_blob, simulate
from flycar.view import animate, neuron_figure


def _finish(anim) -> None:
    # The still frame is what this test checks. Mark it so matplotlib does
    # not warn that the player was discarded.
    anim._draw_was_started = True


def notebook_scene() -> Scene:
    return Scene(
        cam_h=0.15,
        pitch_deg=12.0,
        red=Blob((1.30, -0.40), 0.12),
        blue=Blob((0.25, 0.90), 0.10),
        run_s=8.0,
    )


def test_notebook_scene_matches_the_default():
    assert notebook_scene() == Scene()


def test_reference_red_starts_on_the_right_and_stops_centered():
    run = simulate(notebook_scene())
    first = run.samples[0]
    assert first.heading == pytest.approx(0.0)
    assert first.red.inside
    assert first.red.nx == pytest.approx(0.6479331048207451)
    assert first.red.nx > 0.4
    assert not any(sample.blue.inside for sample in run.samples)

    centered = [
        sample
        for sample in run.samples
        if sample.red.inside and abs(sample.red.nx) < 0.05
    ]
    assert centered
    stops = [sample for sample in run.samples if sample.mode == "stop"]
    assert stops
    assert stops[0].t == pytest.approx(6.86)
    assert stops[0].red.left >= 0.75
    assert stops[0].red.right >= 0.75
    assert abs(stops[0].red.nx) < 0.1
    assert min(sample.heading for sample in run.samples) < -0.15
    cruise = [sample for sample in run.samples if sample.mode == "cruise"]
    assert cruise
    assert all(sample.v_left > 0.0 and sample.v_right > 0.0 for sample in cruise)
    assert "停止" in str(run)
    assert "青は画面の外のまま" in str(run)


def test_empty_view_stays_put():
    run = simulate(Scene(red=None, blue=None, run_s=1.0))
    assert all(sample.mode == "stop" for sample in run.samples)
    assert run.samples[-1].x == pytest.approx(0.0)
    assert run.samples[-1].y == pytest.approx(0.0)
    assert run.samples[-1].heading == pytest.approx(0.0)


def test_right_blue_only_keeps_turning_after_the_spin():
    run = simulate(Scene(red=None, blue=Blob((0.45, -0.08), 0.10)))
    cruise = [sample for sample in run.samples if sample.mode == "cruise"]
    stops = [sample for sample in run.samples if sample.mode == "stop"]
    assert cruise[0].t == pytest.approx(0.22)
    assert cruise[0].blue.right == pytest.approx(0.66, abs=0.01)
    assert cruise[0].omega > 0.2
    assert stops[0].t == pytest.approx(0.82)
    assert stops[0].x == pytest.approx(0.09, abs=0.02)


def test_left_red_turns_left_without_a_blue_sphere():
    scene = Scene(red=Blob((1.30, 0.40), 0.12), blue=None, run_s=1.0)
    run = simulate(scene)
    assert run.samples[0].red.nx < -0.4
    assert max(sample.heading for sample in run.samples) > 0.05
    assert all(sample.blue.left == 0.0 and sample.blue.right == 0.0 for sample in run.samples)
    fig, anim = animate(run)
    _finish(anim)
    plt.close(fig)


def test_steep_pitch_puts_the_reference_red_outside_the_frame():
    scene = Scene(pitch_deg=28.0, run_s=0.02)
    view = project_blob(scene, 0.0, 0.0, 0.0, scene.red)
    assert view.inside is False
    assert simulate(scene).samples[0].red.left == 0.0


def test_figures_cover_the_reference_scene():
    run = simulate(notebook_scene())
    fig, anim = animate(run)
    _finish(anim)
    fig.canvas.draw()
    ax = fig.axes[0]
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    assert x0 < 1.30 < x1
    assert y0 < -0.40 < y1
    assert y0 < 0.90 < y1
    plt.close(fig)

    open_figures = plt.get_fignums()
    neurons = neuron_figure(run)
    assert plt.get_fignums() == open_figures
    assert len(neurons.axes) == 3
    assert neurons.axes[0].get_ylabel() == "画面の横位置"
    assert neurons.axes[0].get_legend().get_texts()[0].get_text() == "赤の中心"
    spans = neurons.axes[0].patches
    assert len(spans) == 1
    stop = next(sample for sample in run.samples if sample.mode == "stop")
    assert spans[0].get_x() == pytest.approx(stop.t)
    assert spans[0].get_width() == pytest.approx(run.samples[-1].t - stop.t)
    plt.close(neurons)
