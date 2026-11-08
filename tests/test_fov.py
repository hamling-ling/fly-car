"""Closed-loop check for the reference camera scene in research/notebooks/fov_sim.ipynb.

Run from the repository root:

    python3 -m pytest tests/test_fov.py

The notebook writes the same initial conditions out so they can be edited.
This test keeps the reference scene: a red sphere starts on the right, the
car turns right, and it crawls until both eye ranges fill. The blue sphere
stays outside the frame. The crawl reaches that fill after the 8 s default.
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


def test_reference_red_turns_right_then_crawls():
    """右の赤へ頭を向け、そのあと両輪で這う。8 秒では範囲が 0.75 に届かない。"""
    run = simulate(notebook_scene())
    first = run.samples[0]
    assert first.heading == pytest.approx(0.0)
    assert first.red.inside
    assert first.red.nx == pytest.approx(0.6479331048207451)
    assert first.red.nx > 0.4
    assert first.red.right > first.red.left
    assert not any(sample.blue.inside for sample in run.samples)
    assert min(sample.heading for sample in run.samples) < -0.15
    early = run.samples[5]
    assert early.v_left > early.v_right
    # The turn keeps bringing the blob toward center. Both wheels are
    # already forward, and the 0.75 fill is still ahead.
    crawling = [sample for sample in run.samples if sample.t > 1.0]
    assert crawling
    assert all(sample.v_left > 0.0 and sample.v_right > 0.0 for sample in crawling)
    assert all(sample.red.inside and sample.red.nx > -0.05 for sample in crawling)
    assert min(sample.red.nx for sample in crawling) < 0.20
    assert all(sample.mode != "stop" for sample in run.samples)
    assert "停止せず" in str(run)
    assert "青は画面の外のまま" in str(run)


def test_reference_red_stops_when_both_ranges_fill():
    """左右の範囲が 0.75 に届いて止まるのは 9.2 秒付近で、頭は右を向いている。"""
    scene = Scene(
        cam_h=0.15,
        pitch_deg=12.0,
        red=Blob((1.30, -0.40), 0.12),
        blue=Blob((0.25, 0.90), 0.10),
        run_s=32.0,
    )
    run = simulate(scene)
    stops = [sample for sample in run.samples if sample.mode == "stop"]
    assert stops
    stop = stops[0]
    assert stop.t == pytest.approx(9.18, abs=0.04)
    assert stop.red.left >= 0.75
    assert stop.red.right >= 0.75
    assert stop.heading < -0.15


def test_empty_view_stays_put():
    run = simulate(Scene(red=None, blue=None, run_s=1.0))
    assert all(sample.mode == "stop" for sample in run.samples)
    assert run.samples[-1].x == pytest.approx(0.0)
    assert run.samples[-1].y == pytest.approx(0.0)
    assert run.samples[-1].heading == pytest.approx(0.0)


def test_static_blue_on_the_right_does_not_move():
    """車が止まっていれば青球の拡大は 0 で、電流は閾値を超えない。"""
    run = simulate(Scene(red=None, blue=Blob((0.45, -0.08), 0.10), run_s=2.0))
    assert all(sample.mode == "stop" for sample in run.samples)
    assert run.samples[-1].x == pytest.approx(0.0)
    assert run.samples[-1].y == pytest.approx(0.0)
    assert run.samples[-1].heading == pytest.approx(0.0)
    assert all(sample.i_gf[0] < 1.0 and sample.i_gf[1] < 1.0 for sample in run.samples)


def test_a_side_blue_yaws_the_nose_then_the_crawl_continues():
    """横の青のそばを這うと視角が広がって頭が一度それ、球には触らず赤へ進む。"""
    red = Blob((1.30, 0.00), 0.12)
    blue = Blob((0.45, -0.08), 0.10)
    run = simulate(Scene(red=red, blue=blue, run_s=10.0))
    assert max(sample.heading for sample in run.samples) > 0.10
    assert min(sample.heading for sample in run.samples) > -0.10
    assert abs(run.samples[-1].heading) < 0.10
    assert run.samples[-1].x > 0.2
    assert any(sample.mode == "cruise" for sample in run.samples)
    assert run.samples[-1].mode == "stop"
    assert run.samples[-1].red.left >= 0.75
    assert run.samples[-1].red.right >= 0.75
    assert max(max(sample.i_gf) for sample in run.samples) > 1.0
    dist = [((s.x - 0.45) ** 2 + (s.y + 0.08) ** 2) ** 0.5 for s in run.samples]
    assert min(dist) > blue.radius


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
    run = simulate(
        Scene(
            cam_h=0.15,
            pitch_deg=12.0,
            red=Blob((1.30, -0.40), 0.12),
            blue=Blob((0.25, 0.90), 0.10),
            run_s=32.0,
        )
    )
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
