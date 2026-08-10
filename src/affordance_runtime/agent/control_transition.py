"""Canonical bounded accounting for one accepted policy decision."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.agent.attempt_receipt import AttemptOperation, AttemptReceipt
from affordance_runtime.agent.control_outcome import Continue, LoopDirective, Pause, Terminate
from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import (
    ActionError,
    ActionIntent,
    ActionResult,
    DispatchStatus,
)
from affordance_runtime.world.acquisition import AcquisitionOrigin, AcquisitionStatus

if TYPE_CHECKING:
    from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
    from affordance_runtime.world.acquisition import ObservationRequestKind

_REASON = re.compile(r"^[a-z][a-z0-9_]{0,95}$")


class AdmissionStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    ADMITTED = "admitted"
    REJECTED = "rejected"
    CONFIRMATION_REQUIRED = "confirmation_required"


class PendingKind(StrEnum):
    NONE = "none"
    USER = "user"
    CONFIRMATION = "confirmation"
    UNKNOWN_EFFECT = "unknown_effect"


@dataclass(frozen=True)
class AdmissionSummary:
    status: AdmissionStatus
    reason_code: str

    def __post_init__(self) -> None:
        _require_reason_code(self.reason_code)


@dataclass(frozen=True)
class ExecutionSummary:
    expected_request_id: str
    request_id: str
    backend: str
    dispatch_status: DispatchStatus
    transport_success: bool
    error: ActionError | None
    currentness_probe_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch_status, DispatchStatus):
            raise TypeError("execution summary dispatch status must be typed")
        if self.error is not None and not isinstance(self.error, ActionError):
            raise TypeError("execution summary error must be typed")
        if type(self.transport_success) is not bool:
            raise TypeError("execution summary transport success must be boolean")
        if type(self.currentness_probe_count) is not int or self.currentness_probe_count < 0:
            raise ValueError("currentness probe count must be a non-negative integer")


@dataclass(frozen=True)
class AcquisitionSummary:
    status: AcquisitionStatus
    origin: AcquisitionOrigin | None
    reason_code: str
    attempts: int
    request_kind: str = ""
    expected_origin: AcquisitionOrigin | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AcquisitionStatus):
            raise TypeError("acquisition summary status must be typed")
        if self.origin is not None and not isinstance(self.origin, AcquisitionOrigin):
            raise TypeError("acquisition summary origin must be typed")
        if self.expected_origin is not None and not isinstance(
            self.expected_origin, AcquisitionOrigin
        ):
            raise TypeError("acquisition summary expected origin must be typed")
        _require_reason_code(self.reason_code)
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("acquisition attempts must be a non-negative integer")


@dataclass(frozen=True)
class ProgressDelta:
    event_count: int = 0
    latest_event_type: str = ""

    def __post_init__(self) -> None:
        if self.event_count < 0:
            raise ValueError("progress event count cannot be negative")


@dataclass(frozen=True)
class Turn:
    """Compatibility view projected from the canonical transition suffix."""

    before_observation_id: str
    decision: AgentDecision
    intent: ActionIntent | None = None
    request_id: str = ""
    result: ActionResult | None = None
    after_observation_id: str = ""
    action_evaluation: ActionEvaluation | None = None
    task_evaluation: TaskEvaluation | None = None
    decision_result: str = ""


@dataclass(frozen=True)
class ControlTransition:
    transition_id: str
    sequence: int
    before_observation_id: str
    decision: AgentDecision
    admission: AdmissionSummary | None
    execution: ExecutionSummary | None
    execution_attempts: tuple[ExecutionSummary, ...]
    acquisition: AcquisitionSummary | None
    acquisition_attempts: tuple[AcquisitionSummary, ...]
    attempt_receipts: tuple[AttemptReceipt, ...]
    after_observation_id: str
    action_evaluation: ActionEvaluation | None
    task_evaluation: TaskEvaluation | None
    progress: ProgressDelta
    pending_kind: PendingKind
    resulting_status: AgentLoopStatus | None
    reason_code: str
    intent: ActionIntent | None = None
    request_id: str = ""
    decision_result: str = ""

    def __post_init__(self) -> None:
        if self.sequence <= 0 or not self.transition_id.startswith("transition:"):
            raise ValueError("control transition identity is invalid")
        if not self.before_observation_id or not self.after_observation_id:
            raise ValueError("control transition requires before/after identity")
        if (
            self.action_evaluation is not None
            and self.action_evaluation.after_observation_id != self.after_observation_id
        ):
            raise ValueError("action evaluation must match transition after observation")
        if (
            self.task_evaluation is not None
            and self.task_evaluation.observation_id != self.after_observation_id
        ):
            raise ValueError("task evaluation must match transition after observation")
        _require_reason_code(self.reason_code)

    def as_turn(self) -> Turn:
        execution_before = (
            self.action_evaluation.before_observation_id
            if self.action_evaluation is not None
            else self.before_observation_id
        )
        result = (
            ActionResult(
                self.execution.request_id,
                self.execution.dispatch_status,
                self.execution.backend,
                self.execution.transport_success,
                self.execution.error,
            )
            if self.execution is not None
            else None
        )
        return Turn(
            execution_before,
            self.decision,
            self.intent,
            self.request_id,
            result,
            self.after_observation_id,
            self.action_evaluation,
            self.task_evaluation,
            self.decision_result,
        )


@dataclass(frozen=True)
class ControlContinuation:
    source_transition_id: str
    after_observation_id: str
    acquisition: AcquisitionSummary | None
    acquisition_attempts: tuple[AcquisitionSummary, ...]
    attempt_receipts: tuple[AttemptReceipt, ...]
    execution: ExecutionSummary | None
    execution_attempts: tuple[ExecutionSummary, ...]
    intent: ActionIntent | None
    request_id: str
    action_evaluation: ActionEvaluation | None
    task_evaluation: TaskEvaluation | None
    progress: ProgressDelta
    pending_kind: PendingKind
    resulting_status: AgentLoopStatus | None
    reason_code: str

    def __post_init__(self) -> None:
        if not self.source_transition_id.startswith("transition:"):
            raise ValueError("continuation requires a root transition source")
        _require_reason_code(self.reason_code)


class _FactAccumulator:
    """Shared monotonic merge owner for root and continuation facts."""

    def _initialize_facts(self, state: AgentLoopState, decision: AgentDecision) -> None:
        self._decision = decision
        self._before_id = state.current_observation.observation_id
        self._progress_total = state.progress_event_total_count
        self._intent: ActionIntent | None = None
        self._request_id = ""
        self._result: ActionResult | None = None
        self._executions: list[ExecutionSummary] = []
        self._after_id = ""
        self._action_evaluation: ActionEvaluation | None = None
        self._task_evaluation: TaskEvaluation | None = None
        self._decision_result = ""
        self._acquisitions: list[AcquisitionSummary] = []
        self._attempt_receipts: list[AttemptReceipt] = []
        self._reason_code = ""
        self._resulting_status: AgentLoopStatus | None = None
        self._finalized = False

    def record_execution(
        self, request_id: str, intent: ActionIntent | None, result: ActionResult,
        currentness_probe_count: int = 0,
    ) -> None:
        self._intent = intent
        self._request_id = request_id
        self._result = result
        if result.dispatch_status is not DispatchStatus.NOT_SENT:
            self._task_evaluation = None
        self._executions.append(_execution_summary_from_result(
            request_id, result, currentness_probe_count,
        ))

    def record_execution_receipt(
        self, receipt: AttemptReceipt, request_id: str,
        intent: ActionIntent | None, result: ActionResult,
    ) -> None:
        self._attempt_receipts.append(receipt)
        self.record_execution(request_id, intent, result, receipt.currentness_probe_count)
        if receipt.acquisition_status is not None and receipt.acquisition_attempts:
            self.record_acquisition(
                receipt.acquisition_status, receipt.actual_origin, receipt.reason_code,
                receipt.acquisition_attempts, receipt.request_kind,
                expected_origin=receipt.expected_origin,
            )

    def record_after(self, observation_id: str) -> None:
        self._after_id = observation_id

    def record_evaluations(
        self, action: ActionEvaluation | None = None,
        task: TaskEvaluation | None = None,
    ) -> None:
        self._action_evaluation = action or self._action_evaluation
        self._task_evaluation = task or self._task_evaluation

    def record_decision_result(self, value: str) -> None:
        self._decision_result = value

    def _as_turn(self) -> Turn:
        return Turn(
            self._before_id, self._decision, self._intent, self._request_id,
            self._result, self._after_id, self._action_evaluation,
            self._task_evaluation, self._decision_result,
        )

    def set_resulting_status(self, status: AgentLoopStatus) -> None:
        self._resulting_status = status

    def record_acquisition(
        self, status: AcquisitionStatus, origin: AcquisitionOrigin | None,
        reason_code: str, attempts: int,
        request_kind: ObservationRequestKind | str = "", *,
        expected_origin: AcquisitionOrigin | None = None,
    ) -> None:
        self._acquisitions.append(AcquisitionSummary(
            status, origin, reason_code, attempts, str(request_kind), expected_origin,
        ))
        self._reason_code = reason_code

    def record_attempt(self, receipt: AttemptReceipt) -> None:
        self._attempt_receipts.append(receipt)
        if receipt.operation is AttemptOperation.CAPTURE:
            self.record_acquisition(
                receipt.acquisition_status or AcquisitionStatus.FAILED,
                receipt.actual_origin, receipt.reason_code,
                receipt.acquisition_attempts, receipt.request_kind,
                expected_origin=receipt.expected_origin,
            )

    def set_reason(self, reason_code: str) -> None:
        _require_reason_code(reason_code)
        self._reason_code = reason_code

    @property
    def has_execution(self) -> bool:
        return self._result is not None

    @property
    def reason_code(self) -> str:
        return self._reason_code

    @property
    def has_effectful_execution(self) -> bool:
        return bool(
            self._result is not None
            and self._result.dispatch_status is not DispatchStatus.NOT_SENT
        )


class ControlTransitionScope(_FactAccumulator):
    """Ephemeral fact collector with exactly-once root finalization."""

    def __init__(self, state: AgentLoopState, decision: AgentDecision) -> None:
        self._initialize_facts(state, decision)
        self._admission: AdmissionSummary | None = None

    def record_admission(self, status: AdmissionStatus, reason_code: str) -> None:
        self._admission = AdmissionSummary(status, reason_code)
        self._reason_code = reason_code


    def finalize(self, state: AgentLoopState, outcome: LoopDirective) -> ControlTransition:
        if self._finalized:
            raise RuntimeError("accepted decision scope was already finalized")
        self._finalized = True
        status = self._resulting_status or _outcome_status(outcome)
        sequence = state.control_transition_total_count + 1
        turn = self._as_turn()
        after_id = turn.after_observation_id or state.current_observation.observation_id
        reason_code = self._reason_code or _default_reason(self._decision, status, turn)
        transition = ControlTransition(
            _transition_id(sequence, self._before_id, self._decision.context_id),
            sequence,
            self._before_id,
            self._decision,
            self._admission,
            self._executions[-1] if self._executions else None,
            tuple(self._executions),
            _aggregate_acquisition(self._acquisitions),
            tuple(self._acquisitions),
            tuple(self._attempt_receipts),
            after_id,
            turn.action_evaluation,
            turn.task_evaluation,
            _progress_delta(state, self._progress_total),
            _pending_kind(state),
            status,
            reason_code,
            turn.intent,
            turn.request_id,
            turn.decision_result,
        )
        state._append_control_transition(transition)
        if state.pending_confirmation is not None:
            state.pending_confirmation_transition_id = transition.transition_id
        return transition


class ControlContinuationScope(_FactAccumulator):
    """Typed confirmation continuation that never increments root count."""

    def __init__(
        self,
        state: AgentLoopState,
        decision: AgentDecision,
        source_transition_id: str,
    ) -> None:
        if not source_transition_id:
            raise ValueError("confirmation continuation requires its root transition")
        self._source_transition_id = source_transition_id
        self._initialize_facts(state, decision)

    def record_admission(self, status: AdmissionStatus, reason_code: str) -> None:
        del status
        self.set_reason(reason_code)


    def finalize(self, state: AgentLoopState, outcome: LoopDirective) -> ControlContinuation:
        if self._finalized:
            raise RuntimeError("confirmation continuation was already finalized")
        self._finalized = True
        continuation = ControlContinuation(
            self._source_transition_id,
            state.current_observation.observation_id,
            _aggregate_acquisition(self._acquisitions),
            tuple(self._acquisitions),
            tuple(self._attempt_receipts),
            self._executions[-1] if self._executions else None,
            tuple(self._executions),
            self._intent,
            self._request_id,
            self._action_evaluation,
            self._task_evaluation,
            _progress_delta(state, self._progress_total),
            _pending_kind(state),
            self._resulting_status or _outcome_status(outcome),
            self._reason_code or _default_reason(
                self._decision,
                self._resulting_status or _outcome_status(outcome),
                self._as_turn(),
            ),
        )
        state.latest_control_continuation = continuation
        state._apply_control_continuation(continuation)
        return continuation


def _require_reason_code(value: str) -> None:
    if not _REASON.fullmatch(value):
        raise ValueError("reason_code must be a bounded stable snake-case code")


def _transition_id(sequence: int, observation_id: str, context_id: str) -> str:
    digest = hashlib.sha256(f"{sequence}\0{observation_id}\0{context_id}".encode()).hexdigest()[:20]
    return f"transition:{sequence}:{digest}"


def _execution_summary(turn: Turn) -> ExecutionSummary | None:
    if turn.result is None:
        return None
    return _execution_summary_from_result(turn.request_id, turn.result, 0)


def _execution_summary_from_result(
    expected_request_id: str,
    result: ActionResult,
    currentness_probe_count: int,
) -> ExecutionSummary:
    return ExecutionSummary(
        expected_request_id,
        result.request_id,
        result.backend,
        result.dispatch_status,
        result.transport_success,
        result.error,
        currentness_probe_count,
    )


def _aggregate_acquisition(
    attempts: list[AcquisitionSummary],
) -> AcquisitionSummary | None:
    if not attempts:
        return None
    final = attempts[-1]
    return AcquisitionSummary(
        final.status,
        final.origin,
        final.reason_code,
        sum(item.attempts for item in attempts),
        final.request_kind,
        final.expected_origin,
    )


def _progress_delta(state: AgentLoopState, previous_total: int) -> ProgressDelta:
    count = state.progress_event_total_count - previous_total
    latest = state.recent_progress_events[-1].event_type if count and state.recent_progress_events else ""
    return ProgressDelta(count, latest)


def _pending_kind(state: AgentLoopState) -> PendingKind:
    if state.pending_unknown_request is not None:
        return PendingKind.UNKNOWN_EFFECT
    if state.pending_user_question:
        return PendingKind.USER
    if state.pending_confirmation is not None:
        return PendingKind.CONFIRMATION
    return PendingKind.NONE


def _outcome_status(outcome: LoopDirective):
    match outcome:
        case Continue():
            return None
        case Pause(status=status) | Terminate(status=status):
            return status


def _default_reason(decision: AgentDecision, status: object, turn: Turn) -> str:
    if turn.result is not None and turn.result.error is not None:
        return str(turn.result.error)
    decision_name = re.sub(r"(?<!^)(?=[A-Z])", "_", type(decision).__name__).lower()
    status_name = str(status or "continued")
    return f"{decision_name}_{status_name}"[:96]
