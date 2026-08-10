"""Pure hard-gate evaluation for a future MiniWoB-60 breadth rerun."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreadthRerunEvidence:
    new_report_schema_typed: bool
    unclassified_outcome_count: int
    failure_origins_complete: bool
    capability_inventory_v2_complete: bool
    capability_inventory_digest: str
    representative_diagnostics_complete: bool
    unresolved_diagnostic_count: int
    provider_capacity_declared: bool
    provider_capacity_sufficient: bool
    privacy_passed: bool
    full_local_validation_passed: bool


@dataclass(frozen=True)
class BreadthRerunReadiness:
    admitted: bool
    errors: tuple[str, ...]


def evaluate_rerun_readiness(evidence: BreadthRerunEvidence) -> BreadthRerunReadiness:
    errors = []
    if not evidence.new_report_schema_typed:
        errors.append("new report schema is not fully typed")
    if evidence.unclassified_outcome_count:
        errors.append("unclassified historical evidence remains")
    if not evidence.failure_origins_complete:
        errors.append("component failure origins are incomplete")
    if not evidence.capability_inventory_v2_complete or not evidence.capability_inventory_digest:
        errors.append("capability inventory v2 is incomplete")
    if not evidence.representative_diagnostics_complete:
        errors.append("representative local diagnostics are incomplete")
    if evidence.unresolved_diagnostic_count:
        errors.append("local diagnostics remain unresolved")
    if not evidence.provider_capacity_declared:
        errors.append("provider capacity is not declared")
    if not evidence.provider_capacity_sufficient:
        errors.append("provider capacity is not sufficient")
    if not evidence.privacy_passed:
        errors.append("diagnostic privacy validation did not pass")
    if not evidence.full_local_validation_passed:
        errors.append("full local validation is not attested")
    return BreadthRerunReadiness(not errors, tuple(errors))
