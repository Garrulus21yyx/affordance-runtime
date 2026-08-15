"""Offline ScreenSpot-compatible point-grounding evaluation.

The evaluator intentionally consumes model predictions rather than embedding a
benchmark-specific solver.  This keeps ScreenSpot an offline visual-grounding
gate while allowing a Generalist planner or any multimodal model to supply
bounded click-point predictions through the same reproducible artifact format.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from affordance_runtime.surfaces.visual.grounding import (
    VisualGrounderPort,
    VisualGroundingPoint,
    VisualGroundingRequest,
)


@dataclass(frozen=True)
class ScreenSpotSample:
    sample_id: str
    image_path: Path
    instruction: str
    bbox_xywh: tuple[float, float, float, float]
    data_type: str
    data_source: str


@dataclass(frozen=True)
class ScreenSpotPrediction:
    sample_id: str
    point_xy: tuple[float, float]
    normalized: bool = False


@dataclass(frozen=True)
class ScreenSpotResult:
    sample_id: str
    correct: bool
    prediction_present: bool
    prediction_valid: bool
    point_xy: tuple[float, float] | None
    bbox_xywh: tuple[float, float, float, float]
    data_type: str
    data_source: str
    image_size: tuple[int, int] | None
    error: str = ""


def load_screenspot_samples(annotations_path: Path, images_root: Path) -> list[ScreenSpotSample]:
    """Load the public ScreenSpot JSON layout without changing its annotations."""

    payload = _load_list(annotations_path, "annotations")
    samples: list[ScreenSpotSample] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"annotations[{index}] must be an object")
        filename = _required_text(item, "img_filename", index)
        instruction = _required_text(item, "instruction", index)
        sample_id = str(item.get("sample_id") or item.get("id") or filename)
        if sample_id in seen:
            raise ValueError(f"duplicate ScreenSpot sample id: {sample_id}")
        seen.add(sample_id)
        bbox = _bbox_xywh(item.get("bbox"), index)
        samples.append(
            ScreenSpotSample(
                sample_id=sample_id,
                image_path=_bounded_image_path(images_root, filename, index),
                instruction=instruction,
                bbox_xywh=bbox,
                data_type=str(item.get("data_type") or "unknown"),
                data_source=str(item.get("data_source") or "unknown"),
            )
        )
    return samples


def load_screenspot_predictions(predictions_path: Path) -> dict[str, ScreenSpotPrediction]:
    """Load a strict point-prediction artifact keyed by ``sample_id``.

    Each entry must contain ``sample_id`` and either ``point_xy: [x, y]`` or
    ``x`` / ``y``. Set ``normalized: true`` for values in the [0, 1] image
    coordinate system; pixel coordinates are the default.
    """

    payload = _load_list(predictions_path, "predictions")
    predictions: dict[str, ScreenSpotPrediction] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"predictions[{index}] must be an object")
        sample_id = _required_text(item, "sample_id", index)
        if sample_id in predictions:
            raise ValueError(f"duplicate ScreenSpot prediction id: {sample_id}")
        point = item.get("point_xy")
        if point is None:
            point = [item.get("x"), item.get("y")]
        if not isinstance(point, list) or len(point) != 2 or any(not isinstance(value, (int, float)) for value in point):
            raise ValueError(f"predictions[{index}].point_xy must contain two numbers")
        predictions[sample_id] = ScreenSpotPrediction(
            sample_id=sample_id,
            point_xy=(float(point[0]), float(point[1])),
            normalized=bool(item.get("normalized", False)),
        )
    return predictions


def evaluate_screenspot(
    samples: Iterable[ScreenSpotSample], predictions: dict[str, ScreenSpotPrediction]
) -> dict[str, Any]:
    """Evaluate exact point-in-box accuracy with complete prediction coverage."""

    sample_list = list(samples)
    sample_ids = {sample.sample_id for sample in sample_list}
    unexpected = sorted(set(predictions) - sample_ids)
    results = [_evaluate_sample(sample, predictions.get(sample.sample_id)) for sample in sample_list]
    by_type = _breakdown(results, "data_type")
    by_source = _breakdown(results, "data_source")
    missing = sorted(sample.sample_id for sample in sample_list if sample.sample_id not in predictions)
    errors = [result.error for result in results if result.error]
    acceptance_errors: list[str] = []
    if missing:
        acceptance_errors.append(f"missing predictions: {len(missing)}")
    if unexpected:
        acceptance_errors.append(f"unexpected predictions: {len(unexpected)}")
    if errors:
        acceptance_errors.append(f"invalid or unreadable samples: {len(errors)}")
    correct = sum(result.correct for result in results)
    report = {
        "schema_version": "screenspot-offline-v1",
        "official_protocol": "ScreenSpot point-in-ground-truth-bbox",
        "sample_count": len(sample_list),
        "prediction_count": len(predictions),
        "complete_coverage": not missing and not unexpected,
        "point_accuracy": correct / len(sample_list) if sample_list else 0.0,
        "correct_count": correct,
        "missing_prediction_ids": missing,
        "unexpected_prediction_ids": unexpected,
        "by_data_type": by_type,
        "by_data_source": by_source,
        "results": [asdict(result) for result in results],
        "acceptance_errors": acceptance_errors,
    }
    return report


def run_screenspot_offline_suite(
    annotations_path: Path,
    images_root: Path,
    predictions_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    samples = load_screenspot_samples(annotations_path, images_root)
    report = evaluate_screenspot(samples, load_screenspot_predictions(predictions_path))
    _attach_source_manifest(report, annotations_path, images_root, samples)
    report["prediction_artifact_sha256"] = _sha256_file(predictions_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "screenspot-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def run_screenspot_grounder_suite(
    annotations_path: Path,
    images_root: Path,
    grounder: VisualGrounderPort,
    output_dir: Path,
) -> dict[str, Any]:
    """Run a screenshot-only grounder and score its emitted predictions.

    The runner is not an action executor. It writes the exact points supplied
    by the port and delegates scoring to the strict offline evaluator, keeping
    missing or failed predictions visible.
    """

    samples = load_screenspot_samples(annotations_path, images_root)
    predictions: dict[str, ScreenSpotPrediction] = {}
    grounder_errors: dict[str, str] = {}
    for sample in samples:
        try:
            image_size = _image_size(sample.image_path)
            point = grounder.ground(
                VisualGroundingRequest(
                    sample_id=sample.sample_id,
                    image_path=sample.image_path,
                    image_bytes=sample.image_path.read_bytes(),
                    image_size=image_size,
                    instruction=sample.instruction,
                )
            )
            _validate_grounder_point(point, image_size)
            predictions[sample.sample_id] = ScreenSpotPrediction(
                sample_id=sample.sample_id,
                point_xy=point.point_xy,
                normalized=point.normalized,
            )
        except Exception as exc:
            grounder_errors[sample.sample_id] = f"{type(exc).__name__}: {exc}"

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "screenspot-predictions.json"
    predictions_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": prediction.sample_id,
                    "point_xy": list(prediction.point_xy),
                    "normalized": prediction.normalized,
                }
                for prediction in predictions.values()
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    report = evaluate_screenspot(samples, predictions)
    _attach_source_manifest(report, annotations_path, images_root, samples)
    report["grounder"] = {
        "provider": str(grounder.provider),
        "model": str(grounder.model),
        "prompt_version": str(grounder.prompt_version),
        "input": "screenshot_bytes_and_instruction_only",
        "prediction_artifact": str(predictions_path),
    }
    report["grounder_errors"] = grounder_errors
    report["prediction_artifact_sha256"] = _sha256_file(predictions_path)
    if grounder_errors:
        report["acceptance_errors"].append(f"grounder failures: {len(grounder_errors)}")
    (output_dir / "screenspot-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def _evaluate_sample(sample: ScreenSpotSample, prediction: ScreenSpotPrediction | None) -> ScreenSpotResult:
    if prediction is None:
        return ScreenSpotResult(sample.sample_id, False, False, False, None, sample.bbox_xywh, sample.data_type, sample.data_source, None)
    try:
        from PIL import Image  # type: ignore[import-not-found]

        with Image.open(sample.image_path) as image:
            width, height = image.size
    except Exception as exc:
        return ScreenSpotResult(
            sample.sample_id, False, True, False, prediction.point_xy, sample.bbox_xywh,
            sample.data_type, sample.data_source, None, f"image unreadable: {type(exc).__name__}"
        )
    x, y = prediction.point_xy
    if prediction.normalized:
        x *= width
        y *= height
    left, top, box_width, box_height = sample.bbox_xywh
    valid = 0 <= x <= width and 0 <= y <= height
    correct = valid and left <= x <= left + box_width and top <= y <= top + box_height
    return ScreenSpotResult(
        sample.sample_id, correct, True, valid, (x, y), sample.bbox_xywh,
        sample.data_type, sample.data_source, (width, height), "" if valid else "prediction outside image"
    )


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image  # type: ignore[import-not-found]

    with Image.open(path) as image:
        return image.size


def _validate_grounder_point(point: VisualGroundingPoint, image_size: tuple[int, int]) -> None:
    if not isinstance(point, VisualGroundingPoint):
        raise TypeError("VisualGrounderPort must return VisualGroundingPoint")
    point.pixel_coordinates(image_size)


def _attach_source_manifest(
    report: dict[str, Any],
    annotations_path: Path,
    images_root: Path,
    samples: Iterable[ScreenSpotSample],
) -> None:
    """Bind an offline score to exact annotations and image bytes."""

    resolved_root = images_root.resolve()
    image_entries: list[dict[str, str]] = []
    image_errors: dict[str, str] = {}
    for sample in sorted(samples, key=lambda item: item.sample_id):
        try:
            digest = _sha256_file(sample.image_path)
            error = ""
        except OSError as exc:
            digest = ""
            error = type(exc).__name__
            image_errors[sample.sample_id] = error
        image_entries.append(
            {
                "sample_id": sample.sample_id,
                "image_path": sample.image_path.relative_to(resolved_root).as_posix(),
                "sha256": digest,
                "error": error,
            }
        )
    encoded = json.dumps(image_entries, separators=(",", ":"), sort_keys=True).encode()
    report["source_annotations_sha256"] = _sha256_file(annotations_path)
    report["source_image_manifest_sha256"] = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    report["source_image_errors"] = image_errors
    if image_errors:
        report["acceptance_errors"].append(f"source image failures: {len(image_errors)}")
    report["official_score_claimed"] = False


def _bounded_image_path(images_root: Path, filename: str, index: int) -> Path:
    """Resolve one annotation image without allowing escape from its asset root."""

    root = images_root.resolve()
    candidate = (root / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"annotations[{index}].img_filename escapes the images root") from exc
    return candidate


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _breakdown(results: list[ScreenSpotResult], field: str) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[ScreenSpotResult]] = defaultdict(list)
    for result in results:
        grouped[str(getattr(result, field))].append(result)
    return {
        key: {"samples": len(items), "correct": sum(item.correct for item in items), "point_accuracy": sum(item.correct for item in items) / len(items)}
        for key, items in sorted(grouped.items())
    }


def _load_list(path: Path, label: str) -> list[Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{label} must be a JSON array")
    return payload


def _required_text(item: dict[str, Any], key: str, index: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"annotations[{index}].{key} must be non-empty text")
    return value


def _bbox_xywh(value: Any, index: int) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4 or any(not isinstance(item, (int, float)) for item in value):
        raise ValueError(f"annotations[{index}].bbox must contain four numbers")
    bbox = tuple(float(item) for item in value)
    if bbox[2] < 0 or bbox[3] < 0:
        raise ValueError(f"annotations[{index}].bbox width and height must be non-negative")
    return bbox  # type: ignore[return-value]
