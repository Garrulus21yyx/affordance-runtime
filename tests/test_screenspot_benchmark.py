import json
from pathlib import Path

import pytest
from PIL import Image

from affordance_runtime.benchmarks.screenspot import (
    load_screenspot_predictions,
    run_screenspot_offline_suite,
)


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    images = root / "images"
    images.mkdir()
    Image.new("RGB", (100, 80), "white").save(images / "one.png")
    Image.new("RGB", (100, 80), "white").save(images / "two.png")
    annotations = root / "annotations.json"
    annotations.write_text(
        json.dumps(
            [
                {"sample_id": "one", "img_filename": "one.png", "instruction": "click save", "bbox": [10, 20, 30, 10], "data_type": "text", "data_source": "web"},
                {"sample_id": "two", "img_filename": "two.png", "instruction": "click icon", "bbox": [40, 30, 10, 20], "data_type": "icon", "data_source": "mobile"},
            ]
        ),
        encoding="utf-8",
    )
    predictions = root / "predictions.json"
    predictions.write_text(
        json.dumps(
            [
                {"sample_id": "one", "point_xy": [0.2, 0.3], "normalized": True},
                {"sample_id": "two", "x": 45, "y": 35},
            ]
        ),
        encoding="utf-8",
    )
    return annotations, images, predictions


def test_screenspot_offline_suite_scores_point_in_official_xywh_box(tmp_path: Path) -> None:
    annotations, images, predictions = _write_fixture(tmp_path)

    report = run_screenspot_offline_suite(annotations, images, predictions, tmp_path / "output")

    assert report["official_protocol"] == "ScreenSpot point-in-ground-truth-bbox"
    assert report["complete_coverage"] is True
    assert report["point_accuracy"] == 1.0
    assert report["by_data_type"]["icon"]["point_accuracy"] == 1.0
    assert (tmp_path / "output" / "screenspot-report.json").exists()


def test_screenspot_reports_missing_and_unexpected_predictions(tmp_path: Path) -> None:
    annotations, images, predictions = _write_fixture(tmp_path)
    predictions.write_text(json.dumps([{"sample_id": "one", "point_xy": [20, 30]}, {"sample_id": "extra", "point_xy": [1, 1]}]))

    report = run_screenspot_offline_suite(annotations, images, predictions, tmp_path / "output")

    assert report["complete_coverage"] is False
    assert report["missing_prediction_ids"] == ["two"]
    assert report["unexpected_prediction_ids"] == ["extra"]
    assert report["acceptance_errors"] == ["missing predictions: 1", "unexpected predictions: 1"]


def test_screenspot_rejects_duplicate_prediction_ids(tmp_path: Path) -> None:
    _, _, predictions = _write_fixture(tmp_path)
    predictions.write_text(json.dumps([{"sample_id": "one", "point_xy": [20, 30]}, {"sample_id": "one", "point_xy": [20, 30]}]))

    with pytest.raises(ValueError, match="duplicate ScreenSpot prediction id"):
        load_screenspot_predictions(predictions)
