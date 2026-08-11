from __future__ import annotations

import json

from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus
from affordance_runtime.benchmarks.external_breadth.manifest import build_breadth_manifest
from affordance_runtime.benchmarks.external_breadth.perception_ab import declared_supported_cases


def test_perception_ab_selects_only_inventory_v2_declared_supported_cases() -> None:
    payload = json.loads(open(
        "docs/benchmarks/miniwob-60-seed7-v1-manifest.json", encoding="utf-8",
    ).read())
    census = MiniWobRegistryCensus(
        payload["package_name"],
        payload["package_version"],
        payload.get("core_version", payload["package_version"]),
        payload["source_commit"],
        tuple(item["task_id"] for item in payload["cases"]),
        payload["registry_digest"],
    )
    selected = declared_supported_cases(build_breadth_manifest(census), census)
    task_ids = {item.task_id for item in selected}
    assert "browsergym/miniwob.click-link" in task_ids
    assert "browsergym/miniwob.click-tab-2" in task_ids
    assert "browsergym/miniwob.read-table-2" not in task_ids
    assert "browsergym/miniwob.copy-paste-2" not in task_ids
