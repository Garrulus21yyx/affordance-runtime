from __future__ import annotations

import copy

from affordance_runtime.benchmarks.external_breadth.semantic_inventory_targeted import (
    CASE_MANIFEST,
    SEED,
    manifest_digest,
    privacy_scan,
    validate_campaign,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantic_profile import (
    BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
)

RUN_ID = "miniwob-inventory-17:" + "a" * 32
IMPLEMENTATION = "b" * 40


def _campaign() -> dict[str, object]:
    cases = []
    for case_id, slug in CASE_MANIFEST:
        cases.append({
            "case_id": case_id,
            "task_family_label": slug,
            "benchmark_task_id": f"browsergym/miniwob.{slug}",
            "seed": SEED,
            "run_id": RUN_ID,
            "implementation_sha": IMPLEMENTATION,
            "acquisition_complete": True,
            "projection_complete": True,
            "cleanup_complete": True,
            "projection_coverage": "complete",
            "inventory_profile_id": BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
            "inventory_status": "partial",
            "recognized_target_count": 1,
            "projected_target_count": 0,
            "actionable_target_count": 0,
            "non_executable_target_count": 0,
            "omitted_target_count": 1,
            "informational_target_count": 0,
            "world_target_count": 0,
            "unique_binding_target_count": 0,
            "backend_reset_calls": 1,
            "logical_reset_calls": 1,
            "independent_capture_calls": 0,
            "step_calls": 0,
            "currentness_probe_calls": 0,
            "model_enabled": False,
            "policy_calls": 0,
            "provider_attempts": 0,
            "tokens": 0,
            "diagnostic_error_code": "",
        })
    return {
        "run_id": RUN_ID,
        "implementation_sha": IMPLEMENTATION,
        "manifest_digest": manifest_digest(),
        "case_manifest": [
            {"case_id": case_id, "task_family_label": slug}
            for case_id, slug in CASE_MANIFEST
        ],
        "cases": cases,
    }


def test_targeted_manifest_is_exact_fixed_and_privacy_safe() -> None:
    assert tuple(case_id for case_id, _slug in CASE_MANIFEST) == (
        "miniwob-60-04", "miniwob-60-05", "miniwob-60-07", "miniwob-60-14",
        "miniwob-60-17", "miniwob-60-26", "miniwob-60-28", "miniwob-60-33",
        "miniwob-60-34", "miniwob-60-36", "miniwob-60-38", "miniwob-60-43",
        "miniwob-60-44", "miniwob-60-47", "miniwob-60-49", "miniwob-60-52",
        "miniwob-60-57",
    )
    campaign = _campaign()
    assert validate_campaign(campaign) == ()
    assert privacy_scan(campaign) == ()


def test_targeted_validator_rejects_control_activity_and_false_inventory_truth() -> None:
    campaign = _campaign()
    active = copy.deepcopy(campaign)
    active["cases"][0]["step_calls"] = 1  # type: ignore[index]
    assert "step_calls_nonzero" in validate_campaign(active)

    false_empty = copy.deepcopy(campaign)
    false_empty["cases"][0]["inventory_status"] = "empty"  # type: ignore[index]
    assert "inventory_contract_invalid" in validate_campaign(false_empty)

    false_actionable = copy.deepcopy(campaign)
    false_actionable["cases"][0]["actionable_target_count"] = 1  # type: ignore[index]
    assert "inventory_contract_invalid" in validate_campaign(false_actionable)

    private = copy.deepcopy(campaign)
    private["cases"][0]["selector"] = "#secret"  # type: ignore[index]
    assert privacy_scan(private)
