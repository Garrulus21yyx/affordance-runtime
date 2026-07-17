"""Initial benchmark matrix."""

from __future__ import annotations

from affordance_runtime.benchmarks.spec import BenchmarkTask


def mvp_benchmark_tasks() -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            suite="local_saas_ops",
            task_id="read_only_evidence_chain",
            start_url="http://localhost:3000/pricing",
            goal="Extract plan limits with screenshots and source URLs as evidence.",
            tags=["read_only", "evidence", "web"],
            oracle={"requires_evidence": True, "no_write": True},
        ),
        BenchmarkTask(
            suite="local_saas_ops",
            task_id="reversible_settings_update",
            start_url="http://localhost:3000/settings",
            goal="Change a reversible notification setting and verify persisted state.",
            tags=["write", "reversible", "modal", "async"],
            oracle={"setting_value": "enabled", "requires_receipt": True},
            perturbations=["selector_drift", "blocking_modal", "async_button_state"],
        ),
        BenchmarkTask(
            suite="local_saas_ops",
            task_id="export_with_approval",
            start_url="http://localhost:3000/reports",
            goal="Export a report only after approval and return the downloaded receipt.",
            tags=["approval", "external_side_effect", "download"],
            oracle={"approval_required": True, "download_receipt": True},
            perturbations=["navigation_delay", "stale_snapshot"],
        ),
    ]

