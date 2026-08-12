from __future__ import annotations

import json
from types import SimpleNamespace

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus
from affordance_runtime.benchmarks.external_breadth.manifest import build_breadth_manifest
from affordance_runtime.benchmarks.external_breadth.perception_ab import (
    _adapter,
    _inconclusive_pairs,
    capability_covered_cases,
    readiness_cohorts,
)
from affordance_runtime.model_policy import model_policy_from_environment


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
        "LLM_ZHIPU_MODEL": "glm-4.7-flash",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    }
    policy = model_policy_from_environment(environment)

    with __import__("pytest").raises(ValueError, match="frozen Mistral"):
        _adapter(policy)
    assert _adapter(policy, require_frozen_mistral=False).provider_id == "zhipu"
