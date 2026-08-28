import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from affordance_runtime.benchmarks.screenspot import (
    load_screenspot_predictions,
    run_screenspot_grounder_suite,
    run_screenspot_offline_suite,
)
from affordance_runtime.model.policy.pydantic_ai_bridge import ConfiguredPydanticAIModel
from affordance_runtime.surfaces.visual.grounding import (
    PydanticAIVisualGrounder,
    PydanticAIVisualRegionProposer,
    VisualGroundingPoint,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
    configured_visual_region_proposer_from_environment,
    glm_visual_point_grounder_from_environment,
    point_grounded_visual_regions,
    visual_grounder_from_environment,
    visual_region_proposer_from_environment,
)
from affordance_runtime.surfaces.visual.pydantic_ai_inference import PydanticAIVisualInference


def _visual_inference(
    *outputs: str,
) -> tuple[PydanticAIVisualInference, list[list[object]]]:
    scripted = list(outputs)
    records: list[list[object]] = []

    async def respond(messages, info):  # type: ignore[no-untyped-def]
        del info
        records.append(messages)
        return ModelResponse(parts=[TextPart(scripted.pop(0))])

    configured = ConfiguredPydanticAIModel(
        FunctionModel(respond, model_name="visual-fixture"),
        "zhipu",
        "glm-4.6v-test",
        "fixture",
        True,
    )
    return PydanticAIVisualInference(configured, timeout_s=5), records


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


def test_pydantic_ai_visual_grounder_sends_only_screenshot_and_instruction(tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    Image.new("RGB", (20, 10), "white").save(image)
    inference, records = _visual_inference('{"x":0.5,"y":0.4,"normalized":true}')

    point = PydanticAIVisualGrounder(inference).ground(
        VisualGroundingRequest("sample", image, image.read_bytes(), (20, 10), "click the target")
    )

    assert point == VisualGroundingPoint((0.5, 0.4), normalized=True)
    user = next(part for part in records[0][-1].parts if isinstance(part, UserPromptPart))
    assert any(isinstance(item, BinaryContent) and item.data == image.read_bytes() for item in user.content)
    assert any(isinstance(item, str) and "click the target" in item for item in user.content)


def test_visual_region_converts_normalized_bbox_and_rejects_invalid_extent() -> None:
    region = VisualRegion((0.1, 0.2, 0.25, 0.5), label="target", confidence=0.9)

    assert region.pixel_bbox((200, 100)) == (20.0, 20.0, 50.0, 50.0)
    with pytest.raises(ValueError, match="dimensions"):
        VisualRegion((0.1, 0.2, 0.0, 0.5)).pixel_bbox((200, 100))


def test_visual_region_proposer_uses_named_corners_and_converts_to_xywh(tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    Image.new("RGB", (200, 100), "white").save(image)

    inference, _ = _visual_inference(
        '{"regions":[{"left":0.1,"top":0.2,"right":0.35,"bottom":0.7,"label":"target","confidence":0.9,"role":"detected target","actionable":false,"color":"blue","shape":"circle","row":2,"column":3,"selected":false},{"left":0.8,"top":0.8,"right":1.2,"bottom":0.9,"label":"invalid sibling","confidence":0.9,"role":"option","actionable":true}]}'
    )
    regions = PydanticAIVisualRegionProposer(inference).propose(
        VisualRegionProposalRequest("sample", image, image.read_bytes(), (200, 100), "click target")
    )

    assert len(regions) == 1
    assert regions[0].pixel_bbox((200, 100)) == pytest.approx((20.0, 20.0, 50.0, 50.0))
    assert regions[0].label == "target"
    assert regions[0].role == "option"
    assert regions[0].primitive_action == "observe_only"
    assert regions[0].state == {
        "color": "blue", "shape": "circle", "row": 2, "column": 3, "selected": False,
    }


def test_visual_region_proposer_accepts_first_valid_region_without_point_retry(
    tmp_path: Path,
) -> None:
    image = tmp_path / "sample.png"
    Image.new("RGB", (200, 100), "white").save(image)
    inference, records = _visual_inference(
        '{"regions":[{"left":0.0,"top":0.0,"right":1.0,"bottom":1.0,'
        '"label":"low confidence target","confidence":0.2,"role":"option","actionable":true}]}'
    )
    regions = PydanticAIVisualRegionProposer(inference).propose(
        VisualRegionProposalRequest("sample", image, image.read_bytes(), (200, 100), "click target")
    )

    assert len(records) == 1
    assert len(regions) == 1
    assert regions[0].pixel_bbox((200, 100)) == pytest.approx((0.0, 0.0, 200.0, 100.0))
    assert regions[0].label == "low confidence target"
    assert regions[0].role == "option"
    assert regions[0].primitive_action == "observe_only"


def test_visual_region_proposer_never_owns_point_fallback(
    tmp_path: Path,
) -> None:
    image = tmp_path / "sample.png"
    Image.new("RGB", (200, 100), "white").save(image)
    inference, records = _visual_inference(
        '{"regions":[{"left":0.0,"top":0.0,"right":1.0,"bottom":1.0,'
        '"label":"context","confidence":0.9,"role":"region","actionable":false}]}'
    )
    regions = PydanticAIVisualRegionProposer(inference).propose(
        VisualRegionProposalRequest("sample", image, image.read_bytes(), (200, 100), "click target")
    )

    assert len(records) == 1
    assert regions[0].primitive_action == "observe_only"


def test_glm_point_attaches_to_smallest_visual_entity_without_replacing_identity() -> None:
    regions = [
        VisualRegion((0.1, 0.1, 0.8, 0.8), "panel", 0.9, primitive_action="observe_only"),
        VisualRegion((0.3, 0.4, 0.2, 0.2), "target", 0.9, primitive_action="observe_only"),
    ]

    grounded = point_grounded_visual_regions(
        regions,
        VisualGroundingPoint((0.4, 0.5), normalized=True),
        (200, 100),
    )

    assert [item.primitive_action for item in grounded] == ["observe_only", "point_activate"]
    assert grounded[1].label == "target"
    assert grounded[1].action_point_xy == (0.4, 0.5)
    assert grounded[1].confidence == 0.5


def test_visual_grounder_environment_factory_uses_zhipu_vision_model_without_exposing_key() -> None:
    grounder = visual_grounder_from_environment(
        {
            "LLM_VISUAL_PROFILE": "zhipu",
            "LLM_ZHIPU_BASE_URL": "https://zhipu.invalid/v4/",
            "LLM_ZHIPU_API_KEY": "zhipu-secret",
            "LLM_ZHIPU_VISION_MODEL": "glm-4.6v-test",
        }
    )

    assert isinstance(grounder, PydanticAIVisualGrounder)
    assert grounder.model == "glm-4.6v-test"
    assert "zhipu-secret" not in repr(grounder)


def test_dedicated_visual_only_point_factory_is_always_glm() -> None:
    grounder = glm_visual_point_grounder_from_environment({
        "LLM_VISUAL_PROFILE": "gemini",
        "LLM_ZHIPU_BASE_URL": "https://zhipu.invalid/v4/",
        "LLM_ZHIPU_API_KEY": "zhipu-secret",
        "LLM_ZHIPU_VISION_MODEL": "glm-4.1v-thinking-flashx",
    })

    assert grounder.provider == "zhipu"
    assert grounder.model == "glm-4.1v-thinking-flashx"
    with pytest.raises(ValueError, match="multimodal GLM"):
        glm_visual_point_grounder_from_environment({
            "LLM_ZHIPU_BASE_URL": "https://zhipu.invalid/v4/",
            "LLM_ZHIPU_API_KEY": "zhipu-secret",
            "LLM_ZHIPU_VISION_MODEL": "qwen-vl",
        })


def test_region_proposer_is_disabled_without_explicit_role_configuration() -> None:
    assert configured_visual_region_proposer_from_environment({
        "LLM_VISUAL_PROFILE": "zhipu",
        "LLM_ZHIPU_BASE_URL": "https://zhipu.invalid/v4/",
        "LLM_ZHIPU_API_KEY": "zhipu-secret",
        "LLM_ZHIPU_VISION_MODEL": "glm-4.1v-thinking-flashx",
    }) is None


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


def test_visual_factories_support_deepseek_vision_profile_without_exposing_key() -> None:
    environment = {
        "LLM_VISUAL_PROFILE": "deepseek",
        "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "LLM_DEEPSEEK_API_KEY": "deepseek-secret",
        "LLM_DEEPSEEK_VISION_MODEL": "deepseek-v4-flash-vision-exp",
    }

    grounder = visual_grounder_from_environment(environment)
    proposer = visual_region_proposer_from_environment(environment)

    assert grounder.provider == proposer.provider == "deepseek"
    assert grounder.model == proposer.model == "deepseek-v4-flash-vision-exp"
    assert "deepseek-secret" not in repr(grounder)
    assert "deepseek-secret" not in repr(proposer)
