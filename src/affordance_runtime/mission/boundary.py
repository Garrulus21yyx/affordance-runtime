"""Mechanical admission boundary for MissionState writes."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.evaluation.evidence import validate_evidence_refs
from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    AcceptedFact,
    AcceptedWorkingOutcome,
    EvidenceBoundaryResult,
    EvidenceBundle,
    ManagerAssessment,
    MissionState,
    WorkingStateProposal,
)


@dataclass(frozen=True)
class AuditBoundary:
    """The only writer of accepted mission state."""

    def accept(
        self,
        mission: MissionState,
        proposal: WorkingStateProposal,
        bundle: EvidenceBundle,
    ) -> EvidenceBoundaryResult:
        if proposal.base_mission_version != mission.version:
            return EvidenceBoundaryResult(False, mission, "version_conflict")
        if proposal.assessment not in {
            ManagerAssessment.SATISFIED,
            ManagerAssessment.UNSATISFIED,
        }:
            return EvidenceBoundaryResult(False, mission, "working_assessment_not_promotable")
        outcome_issue = _validate_outcomes(mission, proposal, bundle)
        if outcome_issue:
            return EvidenceBoundaryResult(False, mission, outcome_issue)
        invalidation_issue = _validate_invalidations(mission, proposal)
        if invalidation_issue:
            return EvidenceBoundaryResult(False, mission, invalidation_issue)
        fact_issue = _validate_fact_promotions(mission, proposal, bundle)
        if fact_issue:
            return EvidenceBoundaryResult(False, mission, fact_issue)
        invalidated = set(proposal.invalidate_fact_keys)
        existing_outcomes = {item.outcome_id: item for item in mission.working_outcomes}
        accepted_outcomes = tuple(
            AcceptedWorkingOutcome(
                item.outcome_id,
                item.assessment,
                item.evidence_refs,
                item.summary,
                tuple(_require_record(bundle, ref) for ref in item.evidence_refs),
            )
            for item in proposal.completed_outcomes
            if item.outcome_id not in existing_outcomes
        )
        retained_facts = tuple(item for item in mission.accepted_facts if item.key not in invalidated)
        new_facts = tuple(
            AcceptedFact(item.key, _require_record(bundle, item.evidence_ref), item.purpose, mission.version + 1)
            for item in proposal.promote_facts
            if item.key not in {existing.key for existing in retained_facts}
        )
        if not accepted_outcomes and not new_facts and retained_facts == mission.accepted_facts:
            return EvidenceBoundaryResult(False, mission, "working_state_noop")
        next_state = MissionState(
            mission.version + 1,
            (*mission.working_outcomes, *accepted_outcomes),
            (*retained_facts, *new_facts),
            (*mission.evidence_lineage, *(item.outcome_id for item in proposal.completed_outcomes)),
        )
        return EvidenceBoundaryResult(True, next_state)


def _validate_outcomes(mission: MissionState, proposal: WorkingStateProposal, bundle: EvidenceBundle) -> str:
    if not proposal.completed_outcomes:
        return "" if proposal.promote_facts else "working_outcome_required"
    existing = {item.outcome_id for item in mission.working_outcomes}
    seen: set[str] = set()
    for item in proposal.completed_outcomes:
        if item.assessment is not proposal.assessment:
            return "working_assessment_conflict"
        if item.outcome_id in seen or item.outcome_id in existing:
            return "working_outcome_id_conflict"
        seen.add(item.outcome_id)
        try:
            validate_evidence_refs(item.evidence_refs, allow_empty=False)
        except ValueError:
            return "invalid_evidence_ref"
        for evidence_ref in item.evidence_refs:
            record = bundle.resolve(evidence_ref)
            if not _public_current_record(record, bundle):
                return "evidence_lineage_invalid"
    return ""


def _validate_invalidations(mission: MissionState, proposal: WorkingStateProposal) -> str:
    if not proposal.invalidate_fact_keys:
        return ""
    cited = {
        evidence_ref
        for outcome in proposal.completed_outcomes
        for evidence_ref in outcome.evidence_refs
    }
    if not cited:
        return "invalidation_evidence_required"
    existing = {item.key for item in mission.accepted_facts}
    if not any(key in existing for key in proposal.invalidate_fact_keys):
        return "working_state_noop"
    return ""


def _validate_fact_promotions(
    mission: MissionState,
    proposal: WorkingStateProposal,
    bundle: EvidenceBundle,
) -> str:
    existing = {item.key: item for item in mission.accepted_facts}
    promoted_keys: set[str] = set()
    for item in proposal.promote_facts:
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


def _require_record(bundle: EvidenceBundle, evidence_ref: str) -> EvidenceRecord:
    record = bundle.resolve(evidence_ref)
    if record is None:
        raise ValueError("accepted evidence disappeared during boundary admission")
    return record


def _public_current_record(record: EvidenceRecord | None, bundle: EvidenceBundle) -> bool:
    if record is None:
        return False
    source_coverage = bundle.source_coverages.get(record.source_observation_id, "")
    return bool(
        record.observation_id == bundle.observation_id
        and record.source_observation_id in set(bundle.source_observation_ids)
        and record.has_typed_source
        and source_coverage != "stale"
    )
