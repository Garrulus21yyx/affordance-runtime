from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from affordance_runtime.benchmarks.visual_capability import (
    CONTENT_FILTER_PROFILE,
    resolved_visual_run_identity,
    validate_visual_live_configuration,
    visual_capability_manifest_digest,
    write_visual_capability_manifest,
)
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
    ObservationToolExposureProfile,
)
from affordance_runtime.model.policy.pydantic_ai_bridge import ConfiguredPydanticAIModel
from affordance_runtime.surfaces.visual.pydantic_ai_inference import PydanticAIVisualInference
from affordance_runtime.surfaces.visual.role_set import PydanticAIVisualRoleSet


def _roles() -> PydanticAIVisualRoleSet:
    async def respond(_messages, _info):  # type: ignore[no-untyped-def]
        return ModelResponse(parts=[TextPart("{}")])

    configured = ConfiguredPydanticAIModel(
        FunctionModel(respond, model_name="visual-fixture"),
        "deepseek",
        "deepseek-v4-flash-vision-exp",
        "deepseek.invalid",
        True,
    )
    return PydanticAIVisualRoleSet(PydanticAIVisualInference(configured, timeout_s=5))


def _adapter() -> SimpleNamespace:
    return SimpleNamespace(
        provider_id="deepseek",
        model_id="deepseek-v4-flash",
        endpoint_host="deepseek.invalid",
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        observation_tool_profile=ObservationToolExposureProfile.DYNAMIC_VISUAL,
    )


def test_visual_role_set_reuses_one_pydantic_ai_inference_for_every_role() -> None:
    roles = _roles()
    try:
        assert {
            id(roles.region_proposer.inference),
            id(roles.point_grounder.inference),
            id(roles.candidate_disambiguator.inference),
            id(roles.predicate_classifier.inference),
            id(roles.text_reader.inference),
            id(roles.spatial_classifier.inference),
            id(roles.change_classifier.inference),
        } == {id(roles.inference)}
        assert roles.provider == "deepseek"
        assert roles.model == "deepseek-v4-flash-vision-exp"
        assert {purpose for purpose, _version in roles.prompt_versions} == {
            "entity_discovery",
            "point_grounding",
            "candidate_disambiguation",
            "predicate_classification",
            "text_in_image",
            "spatial_relationship",
            "visual_change",
        }
    finally:
        roles.close()


def test_visual_manifest_is_filter_off_and_digest_bound(tmp_path) -> None:
    output = tmp_path / "visual.json"

    manifest = write_visual_capability_manifest(output)

    assert manifest["content_filter_profile"] == CONTENT_FILTER_PROFILE == "off"
    assert manifest["live_authorization_required"] is True
    assert manifest["manifest_digest"] == visual_capability_manifest_digest()
    assert [arm["observation_tool_profile"] for arm in manifest["arms"]] == [
        "compatibility.v1",
        "dynamic-visual.v1",
    ]
    assert output.exists()
    committed = json.loads(
        open(
            "docs/benchmarks/visual-capability-evaluation-v1.json",
            encoding="utf-8",
        ).read()
    )
    assert committed == manifest


def test_visual_run_identity_is_redacted_and_rejects_wrong_live_profile() -> None:
    roles = _roles()
    try:
        identity = resolved_visual_run_identity(_adapter(), roles)
        encoded = repr(identity)

        assert identity["visual_provider"]["model"] == "deepseek-v4-flash-vision-exp"
        assert identity["content_filter_profile"] == "off"
        assert identity["resolved_config_digest"].startswith("sha256:")
        assert "API_KEY" not in encoded and "secret" not in encoded
        assert validate_visual_live_configuration(
            {"LLM_VISUAL_PROFILE": "deepseek"}, _adapter(), roles
        ) == ()

        wrong = _adapter()
        wrong.observation_tool_profile = ObservationToolExposureProfile.COMPATIBILITY
        errors = validate_visual_live_configuration(
            {"LLM_VISUAL_PROFILE": "deepseek"}, wrong, roles
        )
        assert errors == ("visual evaluation requires dynamic-visual.v1 observation tools",)
    finally:
        roles.close()
