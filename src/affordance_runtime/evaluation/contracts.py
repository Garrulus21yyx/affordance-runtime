"""Evaluation results do not carry execution authority."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.evaluation.evidence import validate_evidence_refs
from affordance_runtime.execution.contracts import DispatchStatus, ExecutionOutcome
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.acquisition import ObservationAcquisition
from affordance_runtime.world.contracts import WorldObservation


class ActionEvaluationStatus(StrEnum):
    EFFECT_CONFIRMED = "effect_confirmed"
    NO_EFFECT_CONFIRMED = "no_effect_confirmed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class TaskEvaluationStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


class TaskOutcomeKind(StrEnum):
    RUNNING_INCOMPLETE = "running_incomplete"
    TERMINAL_SUCCESS = "terminal_success"
    TERMINAL_FAILURE = "terminal_failure"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"


class EvaluationInterruptionReason(StrEnum):
    ACTION_CANCELLED = "action_evaluation_cancelled"
    ACTION_INVALID = "action_evaluation_invalid"
    ACTION_CALL_FAILED = "action_evaluation_call_failed"
    TASK_CANCELLED = "task_evaluation_cancelled"
    TASK_INVALID = "task_evaluation_invalid"
    TASK_CALL_FAILED = "task_evaluation_call_failed"

    @property
    def cancelled(self) -> bool:
        return self in {self.ACTION_CANCELLED, self.TASK_CANCELLED}

    @property
    def action_phase(self) -> bool:
        return self in {self.ACTION_CANCELLED, self.ACTION_INVALID, self.ACTION_CALL_FAILED}


class CriterionEvaluationStatus(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionEvaluation:
    request_id: str
    before_observation_id: str
    after_observation_id: str
    status: ActionEvaluationStatus
    reason: str
    evidence_refs: tuple[str, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, ActionEvaluationStatus):
            raise TypeError("action evaluation status must be typed")
        if not all(
            value.strip()
            for value in (
                self.request_id,
                self.before_observation_id,
                self.after_observation_id,
                self.reason,
            )
        ):
            raise ValueError("action evaluation requires request, observation lineage, and reason")
        if self.before_observation_id == self.after_observation_id:
            raise ValueError("action evaluation requires distinct before and after observations")
        confirmed = self.status in {
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        }
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=not confirmed),
        )
        if _contains_secret_key(self.evidence):
            raise ValueError("action evaluation evidence cannot contain secret fields")
        object.__setattr__(self, "evidence", freeze_json(self.evidence))


@dataclass(frozen=True)
class CriterionEvaluation:
    criterion_id: str
    status: CriterionEvaluationStatus
    evidence_refs: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, CriterionEvaluationStatus):
            raise TypeError("criterion evaluation status must be typed")
        if not self.criterion_id.strip() or not self.reason.strip():
            raise ValueError("criterion evaluation requires identity and reason")
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(
                tuple(self.evidence_refs),
                allow_empty=self.status != CriterionEvaluationStatus.SATISFIED,
            ),
        )


@dataclass(frozen=True)
class EvaluatedOutput:
    output_id: str
    value: object
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.output_id.strip():
            raise ValueError("evaluated output requires identity")
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=False),
        )


_OUTCOME_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")


@dataclass(frozen=True)
class TaskOutcomeFact:
    """Generic canonical task-domain outcome; no adapter oracle payload is public."""

    kind: TaskOutcomeKind
    code: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TaskOutcomeKind):
            raise TypeError("task outcome kind must be typed")
        if not isinstance(self.code, str) or _OUTCOME_CODE.fullmatch(self.code) is None:
            raise ValueError("task outcome code must be a bounded identifier")
        requires_evidence = self.kind in {
            TaskOutcomeKind.TERMINAL_SUCCESS,
            TaskOutcomeKind.TERMINAL_FAILURE,
        }
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=not requires_evidence),
        )
        if not requires_evidence and self.evidence_refs:
            raise ValueError("nonterminal or unavailable task outcome cannot carry proof")


@dataclass(frozen=True)
class TaskEvaluation:
    task_id: str
    observation_id: str
    status: TaskEvaluationStatus
    reason: str
    criteria: tuple[CriterionEvaluation, ...] = ()
    completion_evidence_refs: tuple[str, ...] = ()
    outputs: tuple[EvaluatedOutput, ...] = ()
    outcome: TaskOutcomeFact | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskEvaluationStatus):
            raise TypeError("task evaluation status must be typed")
        if not self.task_id.strip() or not self.observation_id.strip() or not self.reason.strip():
            raise ValueError("task evaluation requires task, observation, and reason")
        criteria = tuple(self.criteria)
        outputs = tuple(self.outputs)
        if any(not isinstance(item, CriterionEvaluation) for item in criteria):
            raise TypeError("task evaluation criteria must be typed")
        if any(not isinstance(item, EvaluatedOutput) for item in outputs):
            raise TypeError("task evaluation outputs must be typed")
        if self.outcome is not None and not isinstance(self.outcome, TaskOutcomeFact):
            raise TypeError("task evaluation outcome must be typed")
        if len({item.criterion_id for item in criteria}) != len(criteria):
            raise ValueError("task evaluation criterion IDs must be unique")
        if len({item.output_id for item in outputs}) != len(outputs):
            raise ValueError("task evaluation output IDs must be unique")
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(
            self,
            "completion_evidence_refs",
            validate_evidence_refs(
                tuple(self.completion_evidence_refs),
                allow_empty=self.status != TaskEvaluationStatus.COMPLETE,
            ),
        )
        object.__setattr__(self, "outputs", outputs)
        if self.outcome is not None:
            expected = {
                TaskOutcomeKind.TERMINAL_SUCCESS: TaskEvaluationStatus.COMPLETE,
                TaskOutcomeKind.RUNNING_INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
                TaskOutcomeKind.TERMINAL_FAILURE: TaskEvaluationStatus.BLOCKED,
                TaskOutcomeKind.VERIFIER_UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
            }[self.outcome.kind]
            if self.status is not expected:
                raise ValueError("task outcome kind contradicts task evaluation status")
            if self.outcome.kind is TaskOutcomeKind.TERMINAL_SUCCESS:
                if self.outcome.evidence_refs != self.completion_evidence_refs:
                    raise ValueError("terminal success outcome and completion proof must agree")
            elif self.completion_evidence_refs:
                raise ValueError("non-success task outcome cannot carry completion proof")


@dataclass(frozen=True)
class EvaluationOutcome:
    """Exact correlation of the observations and phase outcome actually evaluated."""

    evaluation_id: str
    before_observation: WorldObservation
    execution: ExecutionOutcome | None
    observation_trigger: ObservationAcquisition | None
    consumed_acquisition: ObservationAcquisition
    after_observation: WorldObservation
    action_evaluation: ActionEvaluation | None
    task_evaluation: TaskEvaluation
    semantic_delta: None = None

    @classmethod
    def completed_after_execution(
        cls,
        before: WorldObservation,
        execution: ExecutionOutcome,
        consumed_acquisition: ObservationAcquisition,
        after: WorldObservation,
        action_evaluation: ActionEvaluation,
        task_evaluation: TaskEvaluation,
    ) -> EvaluationOutcome:
        return cls(
            _evaluation_id(consumed_acquisition),
            before,
            execution,
            None,
            consumed_acquisition,
            after,
            action_evaluation,
            task_evaluation,
        )

    @classmethod
    def completed_after_observation(
        cls,
        before: WorldObservation,
        observation_trigger: ObservationAcquisition,
        after: WorldObservation,
        task_evaluation: TaskEvaluation,
    ) -> EvaluationOutcome:
        return cls(
            _evaluation_id(observation_trigger),
            before,
            None,
            observation_trigger,
            observation_trigger,
            after,
            None,
            task_evaluation,
        )

    def __post_init__(self) -> None:
        if self.evaluation_id != _evaluation_id(self.consumed_acquisition):
            raise ValueError("evaluation outcome identity must derive from its consumed acquisition")
        if not isinstance(self.before_observation, WorldObservation) or not isinstance(
            self.after_observation, WorldObservation
        ):
            raise TypeError("evaluation outcome observations must be exact typed values")
        if (self.execution is None) == (self.observation_trigger is None):
            raise ValueError("evaluation outcome requires exactly one causal trigger")
        if not isinstance(self.consumed_acquisition, ObservationAcquisition):
            raise TypeError("evaluation consumed acquisition must be typed")
        if self.consumed_acquisition.observation is not self.after_observation:
            raise ValueError("evaluation must retain the acquisition that derived its after world")
        if not isinstance(self.task_evaluation, TaskEvaluation):
            raise TypeError("evaluation task result must be typed")
        if self.task_evaluation.observation_id != self.after_observation.observation_id:
            raise ValueError("task evaluation must match the consumed after world")
        if self.execution is not None:
            if self.execution.result.dispatch_status is DispatchStatus.NOT_SENT:
                raise ValueError("NOT_SENT execution cannot trigger action evaluation")
            if self.action_evaluation is None:
                raise ValueError("dispatched execution requires action evaluation")
            if (
                self.before_observation.observation_id != self.execution.request.world_observation_id
                or self.action_evaluation.request_id != self.execution.request.request_id
                or self.action_evaluation.before_observation_id != self.before_observation.observation_id
                or self.action_evaluation.after_observation_id != self.after_observation.observation_id
            ):
                raise ValueError("action evaluation lineage must match exact execution worlds")
        elif self.action_evaluation is not None:
            raise ValueError("observation-triggered evaluation cannot carry action evaluation")
        if self.observation_trigger is not None and self.observation_trigger is not self.consumed_acquisition:
            raise ValueError("observation-triggered evaluation must consume its exact trigger")


@dataclass(frozen=True)
class EvaluationInterruption:
    """Closed reached prefix when evaluation cannot produce a complete outcome."""

    evaluation_id: str
    before_observation: WorldObservation
    execution: ExecutionOutcome | None
    observation_trigger: ObservationAcquisition | None
    consumed_acquisition: ObservationAcquisition
    after_observation: WorldObservation
    action_evaluation: ActionEvaluation | None
    reason_code: EvaluationInterruptionReason

    @classmethod
    def interrupted_after_execution(
        cls,
        before: WorldObservation,
        execution: ExecutionOutcome,
        consumed_acquisition: ObservationAcquisition,
        after: WorldObservation,
        reason_code: EvaluationInterruptionReason,
        action_evaluation: ActionEvaluation | None = None,
    ) -> EvaluationInterruption:
        return cls(
            _evaluation_id(consumed_acquisition),
            before,
            execution,
            None,
            consumed_acquisition,
            after,
            action_evaluation,
            reason_code,
        )

    @classmethod
    def interrupted_after_observation(
        cls,
        before: WorldObservation,
        observation_trigger: ObservationAcquisition,
        after: WorldObservation,
        reason_code: EvaluationInterruptionReason,
    ) -> EvaluationInterruption:
        return cls(
            _evaluation_id(observation_trigger),
            before,
            None,
            observation_trigger,
            observation_trigger,
            after,
            None,
            reason_code,
        )

    def __post_init__(self) -> None:
        if self.evaluation_id != _evaluation_id(self.consumed_acquisition):
            raise ValueError("evaluation interruption identity is invalid")
        if not isinstance(self.reason_code, EvaluationInterruptionReason):
            raise TypeError("evaluation interruption reason must be typed")
        if (self.execution is None) == (self.observation_trigger is None):
            raise ValueError("evaluation interruption requires exactly one causal trigger")
        if self.consumed_acquisition.observation is not self.after_observation:
            raise ValueError("evaluation interruption must retain consumed after world")
        if self.execution is not None:
            if self.execution.result.dispatch_status is DispatchStatus.NOT_SENT:
                raise ValueError("NOT_SENT execution cannot enter evaluation")
            if self.before_observation.observation_id != self.execution.request.world_observation_id:
                raise ValueError("evaluation interruption before world must match execution")
            if self.action_evaluation is not None and (
                self.action_evaluation.request_id != self.execution.request.request_id
                or self.action_evaluation.before_observation_id != self.before_observation.observation_id
                or self.action_evaluation.after_observation_id != self.after_observation.observation_id
            ):
                raise ValueError("interrupted action evaluation lineage mismatch")
            if self.reason_code.action_phase != (self.action_evaluation is None):
                raise ValueError("evaluation interruption reason must match its reached evaluator phase")
        elif (
            self.observation_trigger is not self.consumed_acquisition
            or self.action_evaluation is not None
            or self.reason_code.action_phase
        ):
            raise ValueError("interrupted observation evaluation must retain its exact task trigger")


def _contains_secret_key(value: object) -> bool:
    markers = ("password", "secret", "token", "credential", "authorization", "api_key", "apikey")
    if isinstance(value, Mapping):
        return any(
            any(marker in str(key).casefold().replace("-", "_") for marker in markers) or _contains_secret_key(item)
            for key, item in value.items()
        )
    if isinstance(value, tuple | list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _evaluation_id(acquisition: ObservationAcquisition) -> str:
    return f"evaluation:{acquisition.acquisition_id}"
