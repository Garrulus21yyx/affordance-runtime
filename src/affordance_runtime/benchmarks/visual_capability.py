"""Frozen evaluation matrix and redacted identity for general visual evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from affordance_runtime.model.policy.perception import (
    ObservationToolExposureProfile,
)
from affordance_runtime.surfaces.visual.role_set import PydanticAIVisualRoleSet

SCHEMA_VERSION = "visual-capability-evaluation.v1"
PROFILE_ID = "deepseek-v4-flash-vision-exp-general-visual.v1"
CONTENT_FILTER_PROFILE = "off"


def visual_capability_manifest() -> dict[str, Any]:
    """Return the ordered matrix without reading credentials or activating a provider."""

    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": PROFILE_ID,
        "visual_provider": "deepseek",
        "visual_model": "deepseek-v4-flash-vision-exp",
        "content_filter_profile": CONTENT_FILTER_PROFILE,
        "content_filter_ruleset_digest": None,
        "live_authorization_required": True,
        "arms": [
            {
                "arm_id": "compatibility",
                "observation_tool_profile": ObservationToolExposureProfile.COMPATIBILITY.value,
                "visual_provider_calls_expected": 0,
            },
            {
                "arm_id": "dynamic_visual",
                "observation_tool_profile": ObservationToolExposureProfile.DYNAMIC_VISUAL.value,
                "visual_provider_calls_expected": "only_after_admitted_request_evidence",
            },
        ],
        "stages": [
            {
                "stage_id": "provider_free_contract",
                "kind": "provider_free",
                "required_properties": [
                    "dynamic_offer_only_from_fresh_surface_capability",
                    "one_shared_capture_frame_per_acquisition",
                    "stale_request_zero_visual_provider_calls",
                    "typed_observed_unknown_failed_outcomes",
                ],
            },
            {
                "stage_id": "screenspot_point_grounding",
                "kind": "live_visual_provider",
                "metric": "point_in_ground_truth_box_accuracy",
            },
            {
                "stage_id": "miniwob_adaptive_vision",
                "kind": "live_action_policy_and_visual_provider",
                "metric": "native_task_success_by_paired_arm",
            },
            {
                "stage_id": "controlled_visual_semantics",
                "kind": "live_visual_provider",
                "capabilities": [
                    "text_in_image",
                    "svg_target",
                    "same_name_controls",
                    "visual_selected_state",
                    "stale_coordinate_rejection",
                    "unknown_ambiguous_calibration",
                ],
            },
        ],
    }


def visual_capability_manifest_digest() -> str:
    encoded = _canonical_json(visual_capability_manifest())
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def write_visual_capability_manifest(path: Path) -> dict[str, Any]:
    payload = {
        **visual_capability_manifest(),
        "manifest_digest": visual_capability_manifest_digest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def resolved_visual_run_identity(
    action_adapter: object,
    visual_roles: PydanticAIVisualRoleSet,
) -> dict[str, Any]:
    """Build a secret-free identity for one explicitly selected live arm."""

    action_port = getattr(action_adapter, "port", None)
    action_provider = str(
        getattr(action_port, "provider", "") or getattr(action_adapter, "provider_id", "")
    )
    action_model = str(
        getattr(action_port, "model", "") or getattr(action_adapter, "model_id", "")
    )
    action_endpoint = str(getattr(action_adapter, "endpoint_host", ""))
    perception = getattr(action_adapter, "perception_profile", "")
    observation_tools = getattr(action_adapter, "observation_tool_profile", "")
    configured = visual_roles.inference.configured
    payload = {
        "manifest_digest": visual_capability_manifest_digest(),
        "content_filter_profile": CONTENT_FILTER_PROFILE,
        "content_filter_ruleset_digest": None,
        "action_policy": {
            "provider": action_provider,
            "model": action_model,
            "endpoint_host": action_endpoint,
            "perception_profile": getattr(perception, "value", str(perception)),
            "observation_tool_profile": getattr(observation_tools, "value", str(observation_tools)),
        },
        "visual_provider": {
            "provider": visual_roles.provider,
            "model": visual_roles.model,
            "endpoint_host": configured.endpoint_host,
            "timeout_s": visual_roles.inference.timeout_s,
            "prompt_versions": dict(visual_roles.prompt_versions),
        },
    }
    return {
        **payload,
        "resolved_config_digest": "sha256:" + hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }


def validate_visual_live_configuration(
    environment: Mapping[str, str],
    action_adapter: object,
    visual_roles: PydanticAIVisualRoleSet,
) -> tuple[str, ...]:
    """Fail closed before a live call when the frozen arm is not selected."""

    errors: list[str] = []
    if environment.get("LLM_VISUAL_PROFILE", "").strip().casefold() != "deepseek":
        errors.append("visual evaluation requires LLM_VISUAL_PROFILE=deepseek")
    if visual_roles.model.casefold() != "deepseek-v4-flash-vision-exp":
        errors.append("visual evaluation requires deepseek-v4-flash-vision-exp")
    profile = getattr(action_adapter, "observation_tool_profile", None)
    if profile is not ObservationToolExposureProfile.DYNAMIC_VISUAL:
        errors.append("visual evaluation requires dynamic-visual.v1 observation tools")
    return tuple(errors)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


__all__ = [
    "CONTENT_FILTER_PROFILE",
    "PROFILE_ID",
    "SCHEMA_VERSION",
    "resolved_visual_run_identity",
    "validate_visual_live_configuration",
    "visual_capability_manifest",
    "visual_capability_manifest_digest",
    "write_visual_capability_manifest",
]
