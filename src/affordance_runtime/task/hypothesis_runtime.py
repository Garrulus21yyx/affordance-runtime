"""Runtime admission/lifecycle and verifier-only predicate assessment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.evaluation.contracts import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.task.frontier_contracts import (
    FactAvailable,
    FactReferenceExpected,
    LiteralExpected,
    TargetAbsent,
    TargetFieldEquals,
    TargetPresent,
    TaskOutcomeIs,
)
from affordance_runtime.task.hypothesis_contracts import (
    MAX_TRACKED_HYPOTHESES,
    HypothesisPredicateAssessment,
    HypothesisProposalMode,
    RequirementHypothesisProposal,
    RequirementHypothesisProposalBatch,
    RequirementHypothesisState,
    TrackedHypothesisStatus,
    TrackedRequirementHypothesis,
)
from affordance_runtime.world.contracts import (
    CoverageState,
    EntityInventoryStatus,
    WorldObservation,
)
from affordance_runtime.world.evidence_refs import canonical_fact_ref


class HypothesisAdmissionCode(StrEnum):
    ACCEPTED = "accepted"
    UNKNOWN_ENTITY = "unknown_hypothesis_entity"
    UNKNOWN_FACT = "unknown_hypothesis_fact"
    UNKNOWN_FIELD = "unknown_hypothesis_field"
    CAPACITY_EXCEEDED = "hypothesis_capacity_exceeded"
    INITIAL_ALREADY_APPLIED = "initial_hypotheses_already_applied"


@dataclass(frozen=True)
class HypothesisAdmissionResult:
    state: RequirementHypothesisState
    accepted_count: int
    rejected_codes: tuple[HypothesisAdmissionCode, ...] = ()


def admit_requirement_hypotheses(
    current: RequirementHypothesisState,
    batch: RequirementHypothesisProposalBatch,
    observation: WorldObservation,
) -> HypothesisAdmissionResult:
    if batch.mode is HypothesisProposalMode.INITIAL and current.hypotheses:
        return HypothesisAdmissionResult(
            current,
            0,
            (HypothesisAdmissionCode.INITIAL_ALREADY_APPLIED,),
        )
    issues = tuple(
        dict.fromkeys(
            issue
            for proposal in batch.proposals
            if (issue := _admission_issue(proposal, observation)) is not None
        )
    )
    if issues:
        return HypothesisAdmissionResult(current, 0, issues)

    retained = list(current.hypotheses)
    if batch.mode is HypothesisProposalMode.REPLACE:
        retained = [
            replace(item, status=TrackedHypothesisStatus.RETIRED)
            if item.status is TrackedHypothesisStatus.ACTIVE else item
            for item in retained
        ]
    known_digests = {_proposal_key(item) for item in retained}
    novel = [
        proposal
        for proposal in batch.proposals
        if _proposal_key(proposal) not in known_digests
    ]
    if len(retained) + len(novel) > MAX_TRACKED_HYPOTHESES:
        return HypothesisAdmissionResult(
            current,
            0,
            (HypothesisAdmissionCode.CAPACITY_EXCEEDED,),
        )

    sequence = current.next_sequence
    for proposal in novel:
        retained.append(TrackedRequirementHypothesis(
            f"hypothesis:{sequence}",
            proposal.summary,
            proposal.predicate,
            proposal.candidate_entity_ids,
            TrackedHypothesisStatus.ACTIVE,
        ))
        sequence += 1
    changed = tuple(retained) != current.hypotheses
    return HypothesisAdmissionResult(
        RequirementHypothesisState(
            tuple(retained),
            current.revision + int(changed),
            sequence,
        ),
        len(novel),
    )


def assess_requirement_hypotheses(
    current: RequirementHypothesisState,
    observation: WorldObservation,
    evaluation: TaskEvaluation,
) -> RequirementHypothesisState:
    values = []
    for item in current.hypotheses:
        if item.status is TrackedHypothesisStatus.RETIRED:
            values.append(item)
            continue
        assessment, evidence = assess_hypothesis_predicate(
            item.predicate,
            observation,
            evaluation,
        )
        values.append(replace(item, assessment=assessment, evidence_refs=evidence))
    changed = tuple(values) != current.hypotheses
    return RequirementHypothesisState(
        tuple(values),
        current.revision + int(changed),
        current.next_sequence,
    )


def assess_hypothesis_predicate(predicate, observation, evaluation):
    targets = {item.target_id: item for item in observation.targets}
    facts = {canonical_fact_ref(item.fact_id): item for item in observation.facts}
    complete = _inventory_complete(observation)
    if isinstance(predicate, FactAvailable):
        return (
            (HypothesisPredicateAssessment.SATISFIED, (predicate.fact_ref,))
            if predicate.fact_ref in facts
            else (HypothesisPredicateAssessment.UNKNOWN, ())
        )
    if isinstance(predicate, TargetFieldEquals):
        target = targets.get(predicate.target_id)
        if target is None:
            return (
                HypothesisPredicateAssessment.CONTRADICTED
                if complete else HypothesisPredicateAssessment.UNKNOWN,
                (),
            )
        expected = _expected(predicate, facts)
        if expected is _MISSING:
            return HypothesisPredicateAssessment.UNKNOWN, ()
        if target.state.get(predicate.field_name, _MISSING) != expected:
            return HypothesisPredicateAssessment.UNKNOWN, ()
        evidence = tuple(
            ref for ref, fact in facts.items()
            if fact.subject_id == predicate.target_id
            and fact.predicate == predicate.field_name
            and fact.value == expected
        )[:1]
        return HypothesisPredicateAssessment.SATISFIED, evidence
    if isinstance(predicate, TargetPresent):
        if predicate.target_id in targets:
            return HypothesisPredicateAssessment.SATISFIED, ()
        return (
            HypothesisPredicateAssessment.CONTRADICTED
            if complete else HypothesisPredicateAssessment.UNKNOWN,
            (),
        )
    if isinstance(predicate, TargetAbsent):
        if predicate.target_id in targets:
            return HypothesisPredicateAssessment.CONTRADICTED, ()
        return (
            HypothesisPredicateAssessment.SATISFIED
            if complete else HypothesisPredicateAssessment.UNKNOWN,
            (),
        )
    assert isinstance(predicate, TaskOutcomeIs)
    if evaluation.status.value == predicate.status.value:
        return HypothesisPredicateAssessment.SATISFIED, evaluation.completion_evidence_refs
    if evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
        return HypothesisPredicateAssessment.CONTRADICTED, evaluation.completion_evidence_refs
    return HypothesisPredicateAssessment.UNKNOWN, ()


def _admission_issue(
    proposal: RequirementHypothesisProposal,
    observation: WorldObservation,
) -> HypothesisAdmissionCode | None:
    targets = {item.target_id: item for item in observation.targets}
    facts = {canonical_fact_ref(item.fact_id) for item in observation.facts}
    if any(item not in targets for item in proposal.candidate_entity_ids):
        return HypothesisAdmissionCode.UNKNOWN_ENTITY
    predicate = proposal.predicate
    target_id = getattr(predicate, "target_id", "")
    if target_id and target_id not in targets:
        return HypothesisAdmissionCode.UNKNOWN_ENTITY
    if isinstance(predicate, FactAvailable) and predicate.fact_ref not in facts:
        return HypothesisAdmissionCode.UNKNOWN_FACT
    if isinstance(predicate, TargetFieldEquals):
        if predicate.field_name not in targets[predicate.target_id].state:
            return HypothesisAdmissionCode.UNKNOWN_FIELD
        if isinstance(predicate.expected, FactReferenceExpected):
            if predicate.expected.fact_ref not in facts:
                return HypothesisAdmissionCode.UNKNOWN_FACT
    return None


def _inventory_complete(observation: WorldObservation) -> bool:
    if not observation.coverage or any(
        item is not CoverageState.COMPLETE for item in observation.coverage.values()
    ):
        return False
    return bool(observation.sources) and all(
        source.entity_inventory.status is EntityInventoryStatus.COMPLETE
        for source in observation.sources
    )


def _expected(predicate: TargetFieldEquals, facts):
    if isinstance(predicate.expected, LiteralExpected):
        return predicate.expected.value
    fact = facts.get(predicate.expected.fact_ref)
    return fact.value if fact is not None else _MISSING


def _proposal_key(value) -> tuple[object, ...]:
    predicate = value.predicate
    expected = getattr(predicate, "expected", None)
    if isinstance(expected, LiteralExpected):
        expected = ("literal", expected.value)
    elif isinstance(expected, FactReferenceExpected):
        expected = ("fact", expected.fact_ref)
    return (
        predicate.kind.value,
        getattr(predicate, "fact_ref", ""),
        getattr(predicate, "target_id", ""),
        getattr(predicate, "field_name", ""),
        getattr(predicate, "status", ""),
        expected,
        tuple(value.candidate_entity_ids),
    )


_MISSING = object()
