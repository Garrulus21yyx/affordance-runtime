"""One-way admission from current provider reports into typed criterion results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from affordance_runtime.contracts import Observation
from affordance_runtime.verification.contracts import CriterionEvaluation, CriterionStatus
from affordance_runtime.verification.mechanical import VerificationReport


def admit_completion_evidence(
    *,
    observation: Observation,
    report: VerificationReport | None = None,
) -> tuple[CriterionEvaluation, ...]:
    admitted: dict[str, CriterionEvaluation] = {}
    declared = observation.metadata.get("criterion_evaluations")
    if isinstance(declared, Mapping):
        for criterion_id, raw_status in declared.items():
            provider = "current_observation_provider"
            evidence_refs: tuple[str, ...] = ()
            authoritative_final_recheck = False
            if isinstance(raw_status, Mapping):
                provider = str(raw_status.get("provider") or provider)
                evidence_refs = tuple(
                    str(item)
                    for item in raw_status.get("evidence_refs", ())
                    if str(item)
                )
                authoritative_final_recheck = provider in {
                    "external_evaluator",
                    "independent_http_json",
                    "api_state",
                }
                raw_status = raw_status.get("status", CriterionStatus.ERROR.value)
            try:
                status = CriterionStatus(str(raw_status))
            except ValueError:
                status = CriterionStatus.ERROR
            admitted[str(criterion_id)] = CriterionEvaluation(
                str(criterion_id),
                status,
                evidence_refs=evidence_refs,
                evaluated_at_observation_ref=observation.snapshot_id,
                reason_code=provider,
                authoritative_final_recheck=authoritative_final_recheck,
            )

    if report is None:
        return tuple(admitted.values())
    by_criterion: dict[str, list[Any]] = {}
    for evidence in report.evidence:
        for criterion_id in evidence.criterion_ids:
            by_criterion.setdefault(criterion_id, []).append(evidence)
    for criterion_id, evidence_items in by_criterion.items():
        current = tuple(
            item
            for item in evidence_items
            if item.snapshot_id == observation.snapshot_id
            and item.environment_revision == observation.environment_revision
        )
        if not current:
            admitted[criterion_id] = CriterionEvaluation(
                criterion_id,
                CriterionStatus.STALE,
                reason_code="evidence_not_from_current_observation",
            )
            continue
        strong = tuple(
            item
            for item in current
            if item.strength in {"strong", "authoritative"}
            and item.source not in {"receipt", "execution_receipt"}
        )
        if not strong:
            admitted[criterion_id] = CriterionEvaluation(
                criterion_id,
                CriterionStatus.UNKNOWN,
                evidence_refs=tuple(item.evidence_id for item in current if item.evidence_id),
                evaluated_at_observation_ref=observation.snapshot_id,
                reason_code="no_independent_strong_evidence",
            )
            continue
        passed = {item.passed for item in strong}
        status = (
            CriterionStatus.CONFLICT
            if len(passed) > 1
            else CriterionStatus.SATISFIED
            if True in passed
            else CriterionStatus.UNSATISFIED
        )
        admitted[criterion_id] = CriterionEvaluation(
            criterion_id,
            status,
            observed_value=tuple(item.observed for item in strong),
            evidence_refs=tuple(item.evidence_id for item in strong if item.evidence_id),
            evaluated_at_observation_ref=observation.snapshot_id,
            reason_code="independent_typed_evidence",
            authoritative_final_recheck=any(
                item.source in {"external_evaluator", "independent_http_json", "api_state"}
                and item.strength in {"strong", "authoritative"}
                for item in strong
            ),
        )
    return tuple(admitted.values())


def output_source_bindings(observation: Observation) -> dict[str, tuple[str, ...]]:
    raw = observation.metadata.get("output_source_bindings")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(output_id): tuple(str(item) for item in refs if str(item))
        for output_id, refs in raw.items()
        if isinstance(refs, (tuple, list))
    }
