"""Runtime admission/lifecycle and verifier-only predicate assessment."""

from __future__ import annotations

from dataclasses import dataclass, replace

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
    HypothesisItemRejection,
    HypothesisPredicateAssessment,
    HypothesisProposalMode,
    HypothesisRejectionCode,
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

HypothesisAdmissionCode = HypothesisRejectionCode


@dataclass(frozen=True)
class HypothesisAdmissionResult:
    state: RequirementHypothesisState
    accepted_count: int
    accepted_item_indices: tuple[int, ...] = ()
    rejections: tuple[HypothesisItemRejection, ...] = ()

    @property
    def rejected_codes(self) -> tuple[HypothesisRejectionCode, ...]:
        return tuple(item.code for item in self.rejections)

    @property
    def rejected_count(self) -> int:
        return len(self.rejections)


def admit_requirement_hypotheses(
    current: RequirementHypothesisState,
    batch: RequirementHypothesisProposalBatch,
    observation: WorldObservation,
) -> HypothesisAdmissionResult:
    if batch.mode is HypothesisProposalMode.INITIAL and current.hypotheses:
        return HypothesisAdmissionResult(
            current,
            0,
            (),
            tuple(
                sorted(
                    (
                        *batch.rejections,
                        *(
                            HypothesisItemRejection(
                                item_index,
                                HypothesisAdmissionCode.INITIAL_ALREADY_APPLIED,
                            )
                            for item_index in batch.proposal_item_indices
                        ),
                    ),
                    key=lambda item: item.item_index,
                )
            ),
        )
    admissible: list[tuple[int, RequirementHypothesisProposal]] = []
    rejections = list(batch.rejections)
    for item_index, proposal in zip(
        batch.proposal_item_indices,
        batch.proposals,
        strict=True,
    ):
        issue = _admission_issue(proposal, observation)
        if issue is None:
            admissible.append((item_index, proposal))
        else:
            rejections.append(HypothesisItemRejection(item_index, issue))

    retained = list(current.hypotheses)
    if batch.mode is HypothesisProposalMode.REPLACE and (admissible or not rejections):
        retained = [
            replace(item, status=TrackedHypothesisStatus.RETIRED)
            if item.status is TrackedHypothesisStatus.ACTIVE
            else item
            for item in retained
        ]
    known_digests = {_proposal_key(item) for item in retained if item.status is TrackedHypothesisStatus.ACTIVE}
    novel = []
    for item_index, proposal in admissible:
        digest = _proposal_key(proposal)
        if digest in known_digests:
            rejections.append(
                HypothesisItemRejection(
                    item_index,
                    HypothesisAdmissionCode.DUPLICATE,
                )
            )
            continue
        known_digests.add(digest)
        novel.append((item_index, proposal))
    if batch.mode is HypothesisProposalMode.REPLACE and novel:
        retained = _retain_recent_history(retained, len(novel))
    available = max(0, MAX_TRACKED_HYPOTHESES - len(retained))
    admitted = novel[:available]
    rejections.extend(
        HypothesisItemRejection(item_index, HypothesisAdmissionCode.CAPACITY_EXCEEDED)
        for item_index, _ in novel[available:]
    )

    sequence = current.next_sequence
    for _, proposal in admitted:
        retained.append(
            TrackedRequirementHypothesis(
                f"hypothesis:{sequence}",
                proposal.summary,
                proposal.predicate,
                proposal.candidate_entity_ids,
                TrackedHypothesisStatus.ACTIVE,
            )
        )
        sequence += 1
    changed = tuple(retained) != current.hypotheses
    return HypothesisAdmissionResult(
        RequirementHypothesisState(
            tuple(retained),
            current.revision + int(changed),
            sequence,
        ),
        len(admitted),
        tuple(item_index for item_index, _ in admitted),
        tuple(sorted(rejections, key=lambda item: item.item_index)),
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
                HypothesisPredicateAssessment.CONTRADICTED if complete else HypothesisPredicateAssessment.UNKNOWN,
                (),
            )
        expected = _expected(predicate, facts)
        if expected is _MISSING:
            return HypothesisPredicateAssessment.UNKNOWN, ()
        if target.state.get(predicate.field_name, _MISSING) != expected:
            return HypothesisPredicateAssessment.UNKNOWN, ()
        evidence = tuple(
            ref
            for ref, fact in facts.items()
            if fact.subject_id == predicate.target_id
            and fact.predicate == predicate.field_name
            and fact.value == expected
        )[:1]
        return HypothesisPredicateAssessment.SATISFIED, evidence
    if isinstance(predicate, TargetPresent):
        if predicate.target_id in targets:
            return HypothesisPredicateAssessment.SATISFIED, ()
        return (
            HypothesisPredicateAssessment.CONTRADICTED if complete else HypothesisPredicateAssessment.UNKNOWN,
            (),
        )
    if isinstance(predicate, TargetAbsent):
        if predicate.target_id in targets:
            return HypothesisPredicateAssessment.CONTRADICTED, ()
        return (
            HypothesisPredicateAssessment.SATISFIED if complete else HypothesisPredicateAssessment.UNKNOWN,
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
    if not observation.coverage or any(item is not CoverageState.COMPLETE for item in observation.coverage.values()):
        return False
    return bool(observation.sources) and all(
        source.entity_inventory.status is EntityInventoryStatus.COMPLETE for source in observation.sources
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


def _retain_recent_history(
    retained: list[TrackedRequirementHypothesis],
    incoming_count: int,
) -> list[TrackedRequirementHypothesis]:
    """Bound retired diagnostic history without starving rolling replacement."""

    history_capacity = max(0, MAX_TRACKED_HYPOTHESES - incoming_count)
    if len(retained) <= history_capacity:
        return retained
    return retained[-history_capacity:] if history_capacity else []
