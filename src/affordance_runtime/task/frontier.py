"""Mechanical admission and verification for one rolling active objective."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.evaluation.contracts import (
    CriterionEvaluationStatus,
    TaskEvaluation,
)
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.task.frontier_contracts import (
    ActiveObjective,
    FactAvailable,
    FactReferenceExpected,
    LiteralExpected,
    NoObjectiveOperation,
    ObjectiveCheckpoint,
    ObjectiveCheckpointStatus,
    ObjectiveOperation,
    ProposeObjective,
    ReplaceObjective,
    RetainObjective,
    TargetAbsent,
    TargetFieldEquals,
    TargetPresent,
    TaskOutcomeIs,
    VerifiedRequirement,
    VerifiedTaskState,
    VerifiedValue,
    objective_id,
)
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.evidence_refs import canonical_fact_ref


class ObjectiveAdmissionCode(StrEnum):
    ACTIVE_OBJECTIVE_REQUIRED = "active_objective_required"
    ACTIVE_OBJECTIVE_ALREADY_EXISTS = "active_objective_already_exists"
    STALE_ACTIVE_OBJECTIVE = "stale_active_objective"
    UNKNOWN_REQUIREMENT = "unknown_objective_requirement"
    SATISFIED_REQUIREMENT = "satisfied_objective_requirement"
    OBJECTIVE_ALREADY_SATISFIED = "objective_already_satisfied"
    UNKNOWN_TARGET = "unknown_objective_target"
    UNKNOWN_FACT = "unknown_objective_fact"


@dataclass(frozen=True)
class ObjectiveAdmissionIssue:
    code: ObjectiveAdmissionCode
    field_paths: tuple[str, ...]
    expected: dict[str, object]
    actual: dict[str, object]


@dataclass(frozen=True)
class PreparedObjectiveOperation:
    operation: ObjectiveOperation
    expected_active_objective_id: str
    next_active_objective: ActiveObjective | None
    allocated_sequence: int = 0


@dataclass(frozen=True)
class ObjectiveAdmissionResult:
    prepared: PreparedObjectiveOperation | None = None
    issue: ObjectiveAdmissionIssue | None = None

    def __post_init__(self) -> None:
        if (self.prepared is None) == (self.issue is None):
            raise ValueError("objective admission result must have exactly one outcome")


class ObjectiveVerificationDisposition(StrEnum):
    ACTIVE = "active"
    VERIFIED = "verified"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class ObjectiveVerification:
    disposition: ObjectiveVerificationDisposition
    evidence_refs: tuple[str, ...] = ()
    reason_code: str = "objective_still_active"


def synchronize_verified_task_state(
    task: TaskGoal,
    evaluation: TaskEvaluation,
    observation: WorldObservation,
    previous: VerifiedTaskState | None,
) -> VerifiedTaskState:
    """Project current evaluator/world truth while preserving verified checkpoints."""

    evaluated = {item.criterion_id: item for item in evaluation.criteria}
    requirements_list = []
    for requirement_id in (criterion_id(item) for item in task.success_criteria):
        item = evaluated.get(requirement_id)
        requirements_list.append(VerifiedRequirement(
            requirement_id,
            item.status if item is not None else CriterionEvaluationStatus.UNKNOWN,
            item.evidence_refs if item is not None else (),
        ))
    requirements = tuple(requirements_list)
    frontier = tuple(
        item.requirement_id
        for item in requirements
        if item.status is not CriterionEvaluationStatus.SATISFIED
    )
    prior_values = {item.fact_ref: item for item in previous.values} if previous else {}
    for fact in observation.facts:
        ref = canonical_fact_ref(fact.fact_id)
        prior_values[ref] = VerifiedValue(
            ref,
            fact.subject_id,
            fact.predicate,
            fact.value,
            observation.observation_id,
        )
    return VerifiedTaskState(
        requirements,
        frontier,
        tuple(prior_values.values()),
        previous.objective_checkpoints if previous else (),
    )


def prepare_objective_operation(
    operation: ObjectiveOperation,
    *,
    state: VerifiedTaskState,
    active: ActiveObjective | None,
    observation: WorldObservation,
    evaluation: TaskEvaluation,
    context_id: str,
    next_sequence: int,
) -> ObjectiveAdmissionResult:
    if isinstance(operation, NoObjectiveOperation):
        return _accepted(operation, active, active)
    if isinstance(operation, RetainObjective):
        if active is None:
            return _rejected(
                ObjectiveAdmissionCode.ACTIVE_OBJECTIVE_REQUIRED,
                ("objective_operation.active_objective_id",),
                {"active_objective_required": True},
                {"active_objective_present": False},
            )
        if operation.active_objective_id != active.objective_id:
            return _stale(
                operation.active_objective_id,
                active.objective_id,
                "objective_operation.active_objective_id",
            )
        return _accepted(operation, active, active)
    if isinstance(operation, ProposeObjective):
        if active is not None:
            return _rejected(
                ObjectiveAdmissionCode.ACTIVE_OBJECTIVE_ALREADY_EXISTS,
                ("objective_operation.kind",),
                {"allowed_operation": "retain_or_replace"},
                {"active_objective_present": True},
            )
        previous_id = ""
        requirement_ids = operation.intended_requirement_ids
        predicate = operation.predicate
    else:
        assert isinstance(operation, ReplaceObjective)
        if active is None:
            return _rejected(
                ObjectiveAdmissionCode.ACTIVE_OBJECTIVE_REQUIRED,
                ("objective_operation.replaces_objective_id",),
                {"active_objective_required": True},
                {"active_objective_present": False},
            )
        if operation.replaces_objective_id != active.objective_id:
            return _stale(
                operation.replaces_objective_id,
                active.objective_id,
                "objective_operation.replaces_objective_id",
            )
        previous_id = active.objective_id
        requirement_ids = operation.intended_requirement_ids
        predicate = operation.predicate
    requirement_issue = _requirement_issue(requirement_ids, state)
    if requirement_issue is not None:
        return ObjectiveAdmissionResult(issue=requirement_issue)
    reference_issue = _reference_issue(predicate, state, observation)
    if reference_issue is not None:
        return ObjectiveAdmissionResult(issue=reference_issue)
    created = ActiveObjective(
        objective_id(next_sequence), requirement_ids, predicate, context_id,
    )
    if verify_active_objective(
        created, state, observation, evaluation,
    ).disposition is ObjectiveVerificationDisposition.VERIFIED:
        return _rejected(
            ObjectiveAdmissionCode.OBJECTIVE_ALREADY_SATISFIED,
            ("objective_operation.predicate",),
            {"predicate_must_be_unresolved": True},
            {"predicate_already_satisfied": True},
        )
    return ObjectiveAdmissionResult(prepared=PreparedObjectiveOperation(
        operation, previous_id, created, next_sequence,
    ))


def verify_active_objective(
    active: ActiveObjective,
    state: VerifiedTaskState,
    observation: WorldObservation,
    evaluation: TaskEvaluation,
    *,
    evidence_refs: tuple[str, ...] = (),
) -> ObjectiveVerification:
    predicate = active.predicate
    if isinstance(predicate, FactAvailable):
        available = next(
            (item for item in state.values if item.fact_ref == predicate.fact_ref),
            None,
        )
        return _verification(
            available is not None,
            (predicate.fact_ref,) if available is not None else (),
        )
    if isinstance(predicate, TargetFieldEquals):
        target = next(
            (item for item in observation.targets if item.target_id == predicate.target_id),
            None,
        )
        if target is None:
            return ObjectiveVerification(
                ObjectiveVerificationDisposition.INVALIDATED,
                (),
                "objective_target_invalidated",
            )
        expected = _expected_value(predicate.expected, state)
        if expected is _MISSING:
            return ObjectiveVerification(
                ObjectiveVerificationDisposition.INVALIDATED,
                (),
                "objective_fact_invalidated",
            )
        satisfied = (
            predicate.field_name in target.state
            and target.state[predicate.field_name] == expected
        )
        return _verification(satisfied, evidence_refs if satisfied else ())
    if isinstance(predicate, TargetPresent):
        return _verification(
            any(item.target_id == predicate.target_id for item in observation.targets),
            evidence_refs,
        )
    if isinstance(predicate, TargetAbsent):
        absent = not any(
            item.target_id == predicate.target_id for item in observation.targets
        )
        complete = bool(observation.coverage) and all(
            item is CoverageState.COMPLETE for item in observation.coverage.values()
        )
        return _verification(absent and complete, evidence_refs)
    assert isinstance(predicate, TaskOutcomeIs)
    return _verification(
        evaluation.status.value == predicate.status.value,
        evaluation.completion_evidence_refs
        if evaluation.status.value == predicate.status.value
        else (),
    )


def apply_objective_verification(
    active: ActiveObjective,
    verification: ObjectiveVerification,
    state: VerifiedTaskState,
    observation_id: str,
) -> VerifiedTaskState:
    if verification.disposition is ObjectiveVerificationDisposition.ACTIVE:
        return state
    checkpoint = ObjectiveCheckpoint(
        active.objective_id,
        active.intended_requirement_ids,
        active.predicate,
        ObjectiveCheckpointStatus(
            verification.disposition.value,
        ),
        observation_id,
        verification.evidence_refs,
    )
    return VerifiedTaskState(
        state.requirements,
        state.current_frontier,
        state.values,
        (*state.objective_checkpoints, checkpoint),
    )


def _accepted(operation, previous, next_active) -> ObjectiveAdmissionResult:
    return ObjectiveAdmissionResult(prepared=PreparedObjectiveOperation(
        operation,
        previous.objective_id if previous is not None else "",
        next_active,
    ))


def _stale(provided: str, expected: str, field_path: str) -> ObjectiveAdmissionResult:
    return _rejected(
        ObjectiveAdmissionCode.STALE_ACTIVE_OBJECTIVE,
        (field_path,),
        {"active_objective_id": expected},
        {"matches_active_objective": provided == expected},
    )


def _requirement_issue(
    requirement_ids: tuple[str, ...],
    state: VerifiedTaskState,
) -> ObjectiveAdmissionIssue | None:
    known = {item.requirement_id: item for item in state.requirements}
    unknown = tuple(item for item in requirement_ids if item not in known)
    if unknown:
        return ObjectiveAdmissionIssue(
            ObjectiveAdmissionCode.UNKNOWN_REQUIREMENT,
            ("objective_operation.intended_requirement_ids",),
            {"known_requirement_ids": tuple(known)},
            {"unknown_requirement_count": len(unknown)},
        )
    satisfied = tuple(
        item
        for item in requirement_ids
        if known[item].status is CriterionEvaluationStatus.SATISFIED
    )
    if satisfied:
        return ObjectiveAdmissionIssue(
            ObjectiveAdmissionCode.SATISFIED_REQUIREMENT,
            ("objective_operation.intended_requirement_ids",),
            {"requirement_must_be_unresolved": True},
            {"satisfied_requirement_count": len(satisfied)},
        )
    return None


def _reference_issue(predicate, state, observation) -> ObjectiveAdmissionIssue | None:
    if isinstance(predicate, TargetFieldEquals | TargetPresent | TargetAbsent):
        target_id = predicate.target_id
        if not any(item.target_id == target_id for item in observation.targets):
            return ObjectiveAdmissionIssue(
                ObjectiveAdmissionCode.UNKNOWN_TARGET,
                ("objective_operation.predicate.target_id",),
                {"target_must_be_current": True},
                {"target_present": False},
            )
    if (
        isinstance(predicate, TargetFieldEquals)
        and isinstance(predicate.expected, FactReferenceExpected)
        and not any(item.fact_ref == predicate.expected.fact_ref for item in state.values)
    ):
        return ObjectiveAdmissionIssue(
            ObjectiveAdmissionCode.UNKNOWN_FACT,
            ("objective_operation.predicate.expected.fact_ref",),
            {"fact_must_be_verified": True},
            {"fact_available": False},
        )
    return None


def _rejected(code, paths, expected, actual) -> ObjectiveAdmissionResult:
    return ObjectiveAdmissionResult(issue=ObjectiveAdmissionIssue(
        code, paths, expected, actual,
    ))


def _verification(
    satisfied: bool,
    evidence_refs: tuple[str, ...],
) -> ObjectiveVerification:
    return ObjectiveVerification(
        ObjectiveVerificationDisposition.VERIFIED
        if satisfied
        else ObjectiveVerificationDisposition.ACTIVE,
        tuple(evidence_refs) if satisfied else (),
        "objective_predicate_verified" if satisfied else "objective_still_active",
    )


_MISSING = object()


def _expected_value(expected, state):
    if isinstance(expected, LiteralExpected):
        return expected.value
    assert isinstance(expected, FactReferenceExpected)
    value = next(
        (item.value for item in state.values if item.fact_ref == expected.fact_ref),
        _MISSING,
    )
    return value
