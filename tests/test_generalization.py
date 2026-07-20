import io

from PIL import Image, ImageDraw

from affordance_runtime.benchmarks.miniwob import CURATED_TASKS, MINIWOB_COMMIT
from affordance_runtime.benchmarks.visual import detect_magenta_region
from affordance_runtime.fixtures import pricing_html, reports_html, visual_html


def test_seeded_fixture_variants_change_layout_and_control_identity() -> None:
    seed_zero = pricing_html(0, "train")
    seed_one = pricing_html(1, "train")
    heldout = pricing_html(101, "heldout")

    assert seed_zero != seed_one != heldout
    assert 'id="show-pro"' in seed_zero
    assert 'id="show-pro-train-1"' in seed_one
    assert "Contact sales" in heldout
    assert 'id="export-report-heldout-101"' in reports_html(101, "heldout")
    assert visual_html(0, "train") != visual_html(101, "heldout")


def test_visual_detector_derives_real_pixel_bbox() -> None:
    image = Image.new("RGB", (160, 120), "white")
    ImageDraw.Draw(image).rectangle((23, 31, 82, 69), fill=(212, 20, 232))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    assert detect_magenta_region(buffer.getvalue()) == [23, 31, 60, 39]


def test_official_miniwob_subset_is_pinned_and_covers_required_families() -> None:
    assert len(MINIWOB_COMMIT) == 40
    assert {task.family for task in CURATED_TASKS} == {"click", "type", "select", "dialog", "sequence", "form"}
