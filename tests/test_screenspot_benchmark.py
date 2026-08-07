import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from affordance_runtime.benchmarks.screenspot import (
    load_screenspot_predictions,
    run_screenspot_grounder_suite,
    run_screenspot_offline_suite,
)
from affordance_runtime.visual_grounding import (
    OpenAICompatibleVisualGrounder,
    OpenAICompatibleVisualRegionProposer,
    VisualGroundingPoint,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
    visual_grounder_from_environment,
    visual_region_proposer_from_environment,
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
                {
                    "sample_id": "one",
                    "img_filename": "one.png",
                    "instruction": "click save",
                    "bbox": [10, 20, 30, 10],
                    "data_type": "text",
                    "data_source": "web",
                },
                {
                    "sample_id": "two",
                    "img_filename": "two.png",
                    "instruction": "click icon",
                    "bbox": [40, 30, 10, 20],
                    "data_type": "icon",
                    "data_source": "mobile",
                },
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
    assert report["source_annotations_sha256"].startswith("sha256:")
    assert report["source_image_manifest_sha256"].startswith("sha256:")
    assert report["prediction_artifact_sha256"].startswith("sha256:")
    assert report["official_score_claimed"] is False
    assert (tmp_path / "output" / "screenspot-report.json").exists()


def test_screenspot_reports_missing_and_unexpected_predictions(tmp_path: Path) -> None:
    annotations, images, predictions = _write_fixture(tmp_path)
    predictions.write_text(
        json.dumps([{"sample_id": "one", "point_xy": [20, 30]}, {"sample_id": "extra", "point_xy": [1, 1]}])
    )

    report = run_screenspot_offline_suite(annotations, images, predictions, tmp_path / "output")

    assert report["complete_coverage"] is False
    assert report["missing_prediction_ids"] == ["two"]
    assert report["unexpected_prediction_ids"] == ["extra"]
    assert report["acceptance_errors"] == ["missing predictions: 1", "unexpected predictions: 1"]


def test_screenspot_rejects_duplicate_prediction_ids(tmp_path: Path) -> None:
    _, _, predictions = _write_fixture(tmp_path)
    predictions.write_text(
        json.dumps([{"sample_id": "one", "point_xy": [20, 30]}, {"sample_id": "one", "point_xy": [20, 30]}])
    )

    with pytest.raises(ValueError, match="duplicate ScreenSpot prediction id"):
        load_screenspot_predictions(predictions)


def test_screenspot_rejects_annotation_image_path_outside_asset_root(tmp_path: Path) -> None:
    annotations, images, predictions = _write_fixture(tmp_path)
    annotations.write_text(
        json.dumps(
            [
                {
                    "sample_id": "escape",
                    "img_filename": "../secret.png",
                    "instruction": "click target",
                    "bbox": [0, 0, 1, 1],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes the images root"):
        run_screenspot_offline_suite(annotations, images, predictions, tmp_path / "output")


def test_screenspot_missing_image_produces_fail_closed_report_not_manifest_crash(tmp_path: Path) -> None:
    annotations, images, predictions = _write_fixture(tmp_path)
    (images / "two.png").unlink()

    report = run_screenspot_offline_suite(annotations, images, predictions, tmp_path / "output")

    assert report["official_score_claimed"] is False
    assert report["source_image_errors"] == {"two": "FileNotFoundError"}
    assert report["acceptance_errors"] == [
        "invalid or unreadable samples: 1",
        "source image failures: 1",
    ]
    assert (tmp_path / "output" / "screenspot-report.json").exists()


def test_screenspot_grounder_runner_uses_screenshot_request_and_writes_predictions(tmp_path: Path) -> None:
    annotations, images, _ = _write_fixture(tmp_path)

    class ScreenshotOnlyGrounder:
        provider = "test-visual"
        model = "point-model"
        prompt_version = "visual-grounder-v1"
        requests: list[VisualGroundingRequest] = []

        def ground(self, request: VisualGroundingRequest) -> VisualGroundingPoint:
            self.requests.append(request)
            assert request.image_bytes
            assert request.image_size == (100, 80)
            assert request.instruction in {"click save", "click icon"}
            if request.sample_id == "one":
                return VisualGroundingPoint((0.2, 0.3), normalized=True)
            return VisualGroundingPoint((45, 35))

    grounder = ScreenshotOnlyGrounder()
    report = run_screenspot_grounder_suite(annotations, images, grounder, tmp_path / "output")

    assert report["point_accuracy"] == 1.0
    assert report["grounder"]["input"] == "screenshot_bytes_and_instruction_only"
    assert report["prediction_artifact_sha256"].startswith("sha256:")
    assert len(grounder.requests) == 2
    assert (tmp_path / "output" / "screenspot-predictions.json").exists()


def test_screenspot_grounder_runner_fails_closed_for_invalid_normalized_point(tmp_path: Path) -> None:
    annotations, images, _ = _write_fixture(tmp_path)

    class InvalidGrounder:
        provider = "test-visual"
        model = "point-model"
        prompt_version = "visual-grounder-v1"

        def ground(self, request: VisualGroundingRequest) -> VisualGroundingPoint:
            del request
            return VisualGroundingPoint((2.0, 0.5), normalized=True)

    report = run_screenspot_grounder_suite(annotations, images, InvalidGrounder(), tmp_path / "output")

    assert report["prediction_count"] == 0
    assert report["complete_coverage"] is False
    assert report["acceptance_errors"] == ["missing predictions: 2", "grounder failures: 2"]


def test_openai_compatible_visual_grounder_sends_only_screenshot_and_instruction(tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    Image.new("RGB", (20, 10), "white").save(image)
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
            response = json.dumps(
                {"choices": [{"message": {"content": '{"x":0.5,"y":0.4,"normalized":true}\n</think>trailing prose'}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        point = OpenAICompatibleVisualGrounder(
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="vision-test"
        ).ground(VisualGroundingRequest("sample", image, image.read_bytes(), (20, 10), "click the target"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert point == VisualGroundingPoint((0.5, 0.4), normalized=True)
    content = requests[0]["messages"][1]["content"]  # type: ignore[index]
    encoded = content[0]["image_url"]["url"]  # type: ignore[index]
    assert encoded.startswith("data:image/png;base64,")
    assert base64.b64decode(encoded.split(",", 1)[1]) == image.read_bytes()
    assert "click the target" in content[1]["text"]  # type: ignore[index]
    assert requests[0]["model"] == "vision-test"
    assert requests[0]["thinking"] == {"type": "disabled"}


def test_visual_region_converts_normalized_bbox_and_rejects_invalid_extent() -> None:
    region = VisualRegion((0.1, 0.2, 0.25, 0.5), label="target", confidence=0.9)

    assert region.pixel_bbox((200, 100)) == (20.0, 20.0, 50.0, 50.0)
    with pytest.raises(ValueError, match="dimensions"):
        VisualRegion((0.1, 0.2, 0.0, 0.5)).pixel_bbox((200, 100))


def test_visual_region_proposer_uses_named_corners_and_converts_to_xywh(tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    Image.new("RGB", (200, 100), "white").save(image)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            response = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"regions":[{"left":0.1,"top":0.2,"right":0.35,"bottom":0.7,"label":"target","confidence":0.9}]}'
                            }
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        regions = OpenAICompatibleVisualRegionProposer(
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="vision-test"
        ).propose(VisualRegionProposalRequest("sample", image, image.read_bytes(), (200, 100), "click target"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(regions) == 1
    assert regions[0].pixel_bbox((200, 100)) == pytest.approx((20.0, 20.0, 50.0, 50.0))
    assert regions[0].label == "target"


def test_visual_grounder_environment_factory_uses_zhipu_vision_model_without_exposing_key() -> None:
    grounder = visual_grounder_from_environment(
        {
            "LLM_VISUAL_PROFILE": "zhipu",
            "LLM_ZHIPU_BASE_URL": "https://zhipu.invalid/v4/",
            "LLM_ZHIPU_API_KEY": "zhipu-secret",
            "LLM_ZHIPU_VISION_MODEL": "glm-vision-test",
        }
    )

    assert isinstance(grounder, OpenAICompatibleVisualGrounder)
    assert grounder.model == "glm-vision-test"
    assert "zhipu-secret" not in repr(grounder)


def test_visual_factories_support_gemini_profile_without_exposing_key() -> None:
    environment = {
        "LLM_VISUAL_PROFILE": "gemini",
        "LLM_GEMINI_BASE_URL": "https://gemini.invalid/v1beta/openai",
        "LLM_GEMINI_API_KEY": "gemini-secret",
        "LLM_GEMINI_MODEL": "gemini-vision-test",
    }

    grounder = visual_grounder_from_environment(environment)
    proposer = visual_region_proposer_from_environment(environment)

    assert grounder.provider == proposer.provider == "gemini"
    assert grounder.model == proposer.model == "gemini-vision-test"
    assert "gemini-secret" not in repr(grounder)
    assert "gemini-secret" not in repr(proposer)
