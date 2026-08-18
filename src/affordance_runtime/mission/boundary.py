"""Mechanical admission boundary for MissionState writes."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.evaluation.evidence import validate_evidence_refs
from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    AcceptedFact,
    AuditBoundaryResult,
    AuditBundle,
    AuditDelta,
    AuditDeltaStatus,
    AuditedOutcome,
    MissionState,
)


@dataclass(frozen=True)
class AuditBoundary:
    """The only writer of accepted mission state."""

    def accept(
        self,
        mission: MissionState,
        delta: AuditDelta,
        bundle: AuditBundle,
    ) -> AuditBoundaryResult:
        if delta.base_mission_version != mission.version:
            return AuditBoundaryResult(False, mission, "version_conflict")
        if delta.status not in {
            AuditDeltaStatus.AUDITED_SATISFIED,
            AuditDeltaStatus.AUDITED_UNSATISFIED,
        }:
            return AuditBoundaryResult(False, mission, "audit_status_not_promotable")
        outcome_issue = _validate_outcomes(mission, delta, bundle)
        if outcome_issue:
            return AuditBoundaryResult(False, mission, outcome_issue)
        invalidation_issue = _validate_invalidations(mission, delta)
        if invalidation_issue:
            return AuditBoundaryResult(False, mission, invalidation_issue)
        fact_issue = _validate_fact_promotions(mission, delta, bundle)
        if fact_issue:
            return AuditBoundaryResult(False, mission, fact_issue)
        invalidated = set(delta.invalidate_fact_keys)
        existing_outcomes = {item.audit_id: item for item in mission.audited_outcomes}
        accepted_outcomes = tuple(
            AuditedOutcome(item.audit_id, item.status, item.evidence_refs, item.summary)
            for item in delta.completed_outcomes
            if item.audit_id not in existing_outcomes
        )
        retained_facts = tuple(item for item in mission.accepted_facts if item.key not in invalidated)
        new_facts = tuple(
            AcceptedFact(item.key, _require_record(bundle, item.evidence_ref), item.purpose, mission.version + 1)
            for item in delta.promote_facts
            if item.key not in {existing.key for existing in retained_facts}
        )
        if not accepted_outcomes and not new_facts and retained_facts == mission.accepted_facts:
            return AuditBoundaryResult(False, mission, "audit_delta_noop")
        next_state = MissionState(
            mission.version + 1,
            (*mission.audited_outcomes, *accepted_outcomes),
            (*retained_facts, *new_facts),
            (*mission.audit_lineage, *(item.audit_id for item in delta.completed_outcomes)),
        )
        return AuditBoundaryResult(True, next_state)


def _validate_outcomes(mission: MissionState, delta: AuditDelta, bundle: AuditBundle) -> str:
    if not delta.completed_outcomes:
        return "audit_outcome_required"
    existing = {item.audit_id for item in mission.audited_outcomes}
    seen: set[str] = set()
    for item in delta.completed_outcomes:
        if item.audit_id in seen or item.audit_id in existing:
            return "audit_id_conflict"
        seen.add(item.audit_id)
        try:
            validate_evidence_refs(item.evidence_refs, allow_empty=False)
        except ValueError:
            return "invalid_evidence_ref"
        for evidence_ref in item.evidence_refs:
            record = bundle.resolve(evidence_ref)
            if not _public_current_record(record, bundle):
                return "evidence_lineage_invalid"
    return ""


def _validate_invalidations(mission: MissionState, delta: AuditDelta) -> str:
    if not delta.invalidate_fact_keys:
        return ""
    cited = {
        evidence_ref
        for outcome in delta.completed_outcomes
        for evidence_ref in outcome.evidence_refs
    }
    if not cited:
        return "invalidation_evidence_required"
    existing = {item.key for item in mission.accepted_facts}
    if not any(key in existing for key in delta.invalidate_fact_keys):
        return "audit_delta_noop"
    return ""


def _validate_fact_promotions(
    mission: MissionState,
    delta: AuditDelta,
    bundle: AuditBundle,
) -> str:
    existing = {item.key: item for item in mission.accepted_facts}
    promoted_keys: set[str] = set()
    for item in delta.promote_facts:
        if item.key in promoted_keys:
            return "fact_key_conflict"
        promoted_keys.add(item.key)
        record = bundle.resolve(item.evidence_ref)
        if not _public_current_record(record, bundle):
            return "evidence_lineage_invalid"
        assert record is not None
        if to_json_compatible(record.value) != to_json_compatible(item.value):
            return "promoted_value_mismatch"
        previous = existing.get(item.key)
        if previous is not None and previous.record.evidence_ref != item.evidence_ref:
            return "fact_key_conflict"
    return ""


def _require_record(bundle: AuditBundle, evidence_ref: str) -> EvidenceRecord:
    record = bundle.resolve(evidence_ref)
    if record is None:
        raise ValueError("accepted evidence disappeared during boundary admission")
    return record


def _public_current_record(record: EvidenceRecord | None, bundle: AuditBundle) -> bool:
    if record is None:
        return False
    source_coverage = bundle.source_coverages.get(record.source_observation_id, "")
    return bool(
        record.observation_id == bundle.observation_id
        and record.source_observation_id in set(bundle.source_observation_ids)
        and record.has_typed_source
        and source_coverage != "stale"
    )
