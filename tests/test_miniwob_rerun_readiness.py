from __future__ import annotations

from dataclasses import replace

from affordance_runtime.benchmarks.external_breadth.rerun_readiness import (
    BreadthRerunEvidence,
    evaluate_rerun_readiness,
)


def test_rerun_readiness_requires_every_hard_gate() -> None:
    evidence = _evidence()
    assert evaluate_rerun_readiness(evidence).admitted is True
    blocked = evaluate_rerun_readiness(replace(evidence, provider_capacity_sufficient=False))
    assert blocked.admitted is False
    assert "provider capacity is not sufficient" in blocked.errors


def test_unclassified_failure_and_incomplete_inventory_block() -> None:
    evidence = replace(
        _evidence(),
        unclassified_outcome_count=27,
        capability_inventory_v2_complete=False,
        full_local_validation_passed=False,
    )
    result = evaluate_rerun_readiness(evidence)
    assert result.admitted is False
    assert len(result.errors) == 3


def _evidence() -> BreadthRerunEvidence:
    return BreadthRerunEvidence(
        new_report_schema_typed=True,
        unclassified_outcome_count=0,
        failure_origins_complete=True,
        capability_inventory_v2_complete=True,
        capability_inventory_digest="sha256:digest",
        representative_diagnostics_complete=True,
        unresolved_diagnostic_count=0,
        provider_capacity_declared=True,
        provider_capacity_sufficient=True,
        privacy_passed=True,
        full_local_validation_passed=True,
    )
