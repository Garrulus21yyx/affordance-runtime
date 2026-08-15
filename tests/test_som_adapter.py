import io
from dataclasses import replace

import pytest

from affordance_runtime.contracts import Observation
from affordance_runtime.surfaces.visual.som import BoundingBox, SomAdapter, VisualMark, annotate_screenshot


def _affordances(*, snapshot_id: str = "snap-1"):
    return SomAdapter().parse(
        [
            {"bbox": [10, 20, 40, 20], "label": "Save", "confidence": 0.95},
            {"bbox": [100, 120, 50, 30], "label": "Name", "confidence": 0.8, "action": "type"},
        ],
        environment_revision="rev-1",
        page_revision="page-1",
        snapshot_id=snapshot_id,
        screenshot_ref="screen.png",
    )


def test_som_overlay_retains_observation_bound_mark_identity() -> None:
    overlay = SomAdapter().render_overlay_svg(_affordances(), width=800, height=600)

    assert overlay.screenshot_ref == "screen.png"
    assert overlay.snapshot_id == "snap-1"
    assert [mark.mark_id for mark in overlay.marks] == ["M0", "M1"]
    assert overlay.marks[0].bbox.center == (30, 30)
    assert ">M0<" in overlay.svg and ">M1<" in overlay.svg


def test_som_overlay_rejects_marks_from_different_observations() -> None:
    first = _affordances(snapshot_id="snap-1")[0]
    second = _affordances(snapshot_id="snap-2")[1]

    with pytest.raises(ValueError, match="one screenshot observation"):
        SomAdapter().render_overlay_svg([first, second], width=800, height=600)


def test_select_current_rejects_stale_mark() -> None:
    affordances = _affordances()
    current = Observation(
        environment_revision="rev-1",
        page_revision="page-1",
        snapshot_id="snap-1",
    )
    stale = replace(current, snapshot_id="snap-2")

    assert SomAdapter().select_current(affordances, "M0", current).label == "Save"
    with pytest.raises(ValueError, match="stale"):
        SomAdapter().select_current(affordances, "M0", stale)


def test_som_rejects_non_positive_bbox() -> None:
    with pytest.raises(ValueError, match="positive size"):
        SomAdapter().parse(
            [{"bbox": [10, 20, 0, 20], "label": "bad"}],
            environment_revision="rev-1",
        )


def test_raster_som_label_is_drawn_outside_a_tiny_target() -> None:
    Image = pytest.importorskip("PIL.Image")
    source = Image.new("RGB", (80, 80), "white")
    encoded = io.BytesIO()
    source.save(encoded, format="PNG")
    mark = VisualMark(
        "E25",
        "E25",
        BoundingBox(30, 40, 14, 14),
        1.0,
        "screen",
        "snapshot",
        "page",
        "target",
    )

    rendered = Image.open(io.BytesIO(annotate_screenshot(encoded.getvalue(), (mark,))))

    assert rendered.getpixel((31, 30)) == (0, 200, 0)
    assert rendered.getpixel((37, 47)) == (255, 255, 255)
