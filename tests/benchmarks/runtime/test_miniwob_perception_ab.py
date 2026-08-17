from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus
from affordance_runtime.benchmarks.external_breadth.manifest import build_breadth_manifest
from affordance_runtime.benchmarks.external_breadth.perception_ab import (
    _adapter,
    _inconclusive_pairs,
    _write_progress,
    capability_covered_cases,
    readiness_cohorts,
    run_provider_cohort_arm,
)
from affordance_runtime.model.policy import model_policy_from_environment
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile


def test_perception_ab_selects_only_inventory_v2_capability_covered_cases() -> None:
    payload = json.loads(
        open(
            "docs/benchmarks/miniwob-60-seed7-v1-manifest.json",
            encoding="utf-8",
        ).read()
    )
    census = MiniWobRegistryCensus(
        payload["package_name"],
        payload["package_version"],
        payload.get("core_version", payload["package_version"]),
        payload["source_commit"],
        tuple(item["task_id"] for item in payload["cases"]),
        payload["registry_digest"],
    )
    selected = capability_covered_cases(build_breadth_manifest(census), census)
    task_ids = {item.task_id for item in selected}
    assert "browsergym/miniwob.click-link" in task_ids
    assert "browsergym/miniwob.click-tab-2" in task_ids
    assert "browsergym/miniwob.read-table-2" not in task_ids
    assert "browsergym/miniwob.copy-paste-2" not in task_ids


def test_perception_comparison_validity_is_separate_from_run_evidence() -> None:
    clean = SimpleNamespace(
        case_id="case:1",
        outcome=MiniWobTaskOutcome.SUCCESS,
        result=SimpleNamespace(harness_integrity_failures=()),
    )
    unavailable = SimpleNamespace(
        case_id="case:1",
        outcome=MiniWobTaskOutcome.PROVIDER_UNAVAILABLE,
        result=SimpleNamespace(harness_integrity_failures=()),
    )
    arms = (
        SimpleNamespace(records=(clean,)),
        SimpleNamespace(records=(unavailable,)),
    )

    assert _inconclusive_pairs(("case:1",), arms) == ("case:1",)


def test_readiness_cohorts_are_disjoint_and_exhaust_the_manifest() -> None:
    payload = json.loads(
        open(
            "docs/benchmarks/miniwob-60-seed7-v1-manifest.json",
            encoding="utf-8",
        ).read()
    )
    census = MiniWobRegistryCensus(
        payload["package_name"],
        payload["package_version"],
        payload.get("core_version", payload["package_version"]),
        payload["source_commit"],
        tuple(item["task_id"] for item in payload["cases"]),
        payload["registry_digest"],
    )
    manifest = build_breadth_manifest(census)

    cohorts = readiness_cohorts(manifest, census)

    assert set(cohorts) == {"capability_covered", "unassessed", "declared_gap"}
    case_ids = [case.case_id for values in cohorts.values() for case in values]
    assert len(case_ids) == len(manifest.cases)
    assert len(case_ids) == len(set(case_ids))


def test_provider_cohort_adapter_does_not_weaken_frozen_mistral_ab() -> None:
    environment = {
        "LLM_ACTIVE_PROFILE": "zhipu",
        "LLM_ZHIPU_BASE_URL": "https://example.invalid/v1",
        "LLM_ZHIPU_API_KEY": "fixture",
        "LLM_ZHIPU_MODEL": "glm-4.1v-thinking-flashx",
        "LLM_MODEL_ADAPTER": "compact-json",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    }
    policy = model_policy_from_environment(environment)

    with __import__("pytest").raises(ValueError, match="frozen Mistral"):
        _adapter(policy)
    assert _adapter(policy, require_frozen_mistral=False).provider_id == "zhipu"


def test_provider_cohort_accepts_native_tool_policy_without_weakening_frozen_ab() -> None:
    from affordance_runtime.model.policy import ModelBackedAgentPolicy
    from affordance_runtime.model.policy.pydantic_ai_bridge import PydanticAIGroundedDecisionPort

    native = PydanticAIGroundedDecisionPort(
        model=object(),
        provider_id="zhipu",
        model_id="glm-4.6",
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        transport_timeout_s=1,
    )
    policy = ModelBackedAgentPolicy(native, call_timeout_s=2)

    with __import__("pytest").raises(TypeError, match="frozen perception A/B"):
        _adapter(policy)
    assert _adapter(policy, require_frozen_mistral=False) is native


def test_provider_cohort_progress_is_atomically_persisted_per_case(tmp_path) -> None:
    _write_progress(
        tmp_path,
        profile="visual-gate",
        perception_profile=DecisionPerceptionProfile.SCREENSHOT_AX,
        case_ids=("01", "02"),
        completed_case_ids=("01",),
        complete=False,
    )

    payload = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    assert payload["completed_cases"] == 1
    assert payload["completed_case_ids"] == ["01"]
    assert payload["complete"] is False


def test_provider_cohort_forwards_goal_compiler_to_existing_target_composition(monkeypatch) -> None:
    from affordance_runtime.benchmarks.external_breadth import perception_ab

    captured = {}
    sentinel = object()

    async def fake_run_arm(*args, **kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(perception_ab, "_run_arm", fake_run_arm)
    result = asyncio.run(run_provider_cohort_arm(
        object(), object(), DecisionPerceptionProfile.STRUCTURE_FIRST,
        goal_compiler="compiler",
    ))

    assert result is sentinel
    assert captured["goal_compiler"] == "compiler"
    assert captured["require_frozen_mistral"] is False
