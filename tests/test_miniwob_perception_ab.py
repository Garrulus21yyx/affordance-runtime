from __future__ import annotations

import json
from types import SimpleNamespace

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus
from affordance_runtime.benchmarks.external_breadth.manifest import build_breadth_manifest
from affordance_runtime.benchmarks.external_breadth.perception_ab import (
    _inconclusive_pairs,
    capability_covered_cases,
)


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
