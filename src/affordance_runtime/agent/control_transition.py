"""Canonical bounded accounting for one accepted policy decision."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

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
    request_id: str
    backend: str
    dispatch_status: DispatchStatus
    transport_success: bool
    error: ActionError | None


@dataclass(frozen=True)
class AcquisitionSummary:
    status: AcquisitionStatus
    origin: AcquisitionOrigin
    reason_code: str
    attempts: int
    request_kind: str = ""

    def __post_init__(self) -> None:
        _require_reason_code(self.reason_code)
        if self.attempts < 0:
            raise ValueError("acquisition attempts cannot be negative")


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
    acquisition: AcquisitionSummary | None
    acquisition_attempts: tuple[AcquisitionSummary, ...]
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
    execution: ExecutionSummary | None
    intent: ActionIntent | None
    request_id: str
    action_evaluation: ActionEvaluation | None
    task_evaluation: TaskEvaluation | None
    pending_kind: PendingKind
    resulting_status: AgentLoopStatus | None
    reason_code: str

    def __post_init__(self) -> None:
        if not self.source_transition_id.startswith("transition:"):
            raise ValueError("continuation requires a root transition source")
        _require_reason_code(self.reason_code)


class ControlTransitionScope:
    """Ephemeral fact collector with exactly-once root finalization."""

    def __init__(self, state: AgentLoopState, decision: AgentDecision) -> None:
        self._decision = decision
        self._before_id = state.current_observation.observation_id
        self._progress_total = state.progress_event_total_count
        self._turn = Turn(self._before_id, decision)
        self._admission: AdmissionSummary | None = None
        self._acquisitions: list[AcquisitionSummary] = []
        self._reason_code = ""
        self._finalized = False

    def record_turn(self, turn: Turn) -> None:
        if turn.decision != self._decision or turn.before_observation_id != self._before_id:
            raise ValueError("transition facts do not belong to the accepted decision")
        self._turn = turn

    def record_admission(self, status: AdmissionStatus, reason_code: str) -> None:
        self._admission = AdmissionSummary(status, reason_code)
        self._reason_code = reason_code

    def record_acquisition(
        self,
        status: AcquisitionStatus,
        origin: AcquisitionOrigin,
        reason_code: str,
        attempts: int,
        request_kind: ObservationRequestKind | str = "",
    ) -> None:
        self._acquisitions.append(AcquisitionSummary(
            status,
            origin,
            reason_code,
            attempts,
            str(request_kind),
        ))
        self._reason_code = reason_code

    def set_reason(self, reason_code: str) -> None:
        _require_reason_code(reason_code)
        self._reason_code = reason_code

    def finalize(self, state: AgentLoopState, outcome: object) -> ControlTransition:
        if self._finalized:
            raise RuntimeError("accepted decision scope was already finalized")
        self._finalized = True
        status = _outcome_status(outcome)
        sequence = state.control_transition_total_count + 1
        turn = self._turn
        after_id = turn.after_observation_id or state.current_observation.observation_id
        reason_code = self._reason_code or _default_reason(self._decision, status, turn)
        transition = ControlTransition(
            _transition_id(sequence, self._before_id, self._decision.context_id),
            sequence,
            self._before_id,
            self._decision,
            self._admission,
            _execution_summary(turn),
            _aggregate_acquisition(self._acquisitions),
            tuple(self._acquisitions),
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


class ControlContinuationScope:
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
        self._decision = decision
        self._before_id = state.current_observation.observation_id
        self._turn = Turn(self._before_id, decision)
        self._acquisitions: list[AcquisitionSummary] = []
        self._reason_code = ""
        self._finalized = False

    def record_turn(self, turn: Turn) -> None:
        if turn.decision != self._decision or turn.before_observation_id != self._before_id:
            raise ValueError("continuation facts do not belong to its root decision")
        self._turn = turn

    def record_admission(self, status: AdmissionStatus, reason_code: str) -> None:
        del status
        self.set_reason(reason_code)

    def record_acquisition(
        self,
        status: AcquisitionStatus,
        origin: AcquisitionOrigin,
        reason_code: str,
        attempts: int,
        request_kind: ObservationRequestKind | str = "",
    ) -> None:
        self._acquisitions.append(AcquisitionSummary(
            status,
            origin,
            reason_code,
            attempts,
            str(request_kind),
        ))
        self._reason_code = reason_code

    def set_reason(self, reason_code: str) -> None:
        _require_reason_code(reason_code)
        self._reason_code = reason_code

    def finalize(self, state: AgentLoopState, outcome: object) -> ControlContinuation:
        if self._finalized:
            raise RuntimeError("confirmation continuation was already finalized")
        self._finalized = True
        continuation = ControlContinuation(
            self._source_transition_id,
            state.current_observation.observation_id,
            _aggregate_acquisition(self._acquisitions),
            tuple(self._acquisitions),
            _execution_summary(self._turn),
            self._turn.intent,
            self._turn.request_id,
            self._turn.action_evaluation,
            self._turn.task_evaluation,
            _pending_kind(state),
            _outcome_status(outcome),
            self._reason_code or _default_reason(self._decision, _outcome_status(outcome), self._turn),
        )
        state.latest_control_continuation = continuation
        state._apply_control_continuation(continuation)
        return continuation


def continuation_from_state(
    state: AgentLoopState,
    source_transition_id: str,
    *,
    status: AgentLoopStatus | None,
    reason_code: str,
    acquisition: AcquisitionSummary | None = None,
    result: ActionResult | None = None,
) -> ControlContinuation:
    continuation = ControlContinuation(
        source_transition_id,
        state.current_observation.observation_id,
        acquisition,
        (acquisition,) if acquisition is not None else (),
        _execution_summary(Turn(state.current_observation.observation_id, state.recent_control_transitions[-1].decision, result=result)) if result else None,
        None,
        "",
        None,
        None,
        _pending_kind(state),
        status,
        reason_code,
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
    return ExecutionSummary(
        turn.request_id or turn.result.request_id,
        turn.result.backend,
        turn.result.dispatch_status,
        turn.result.transport_success,
        turn.result.error,
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


def _outcome_status(outcome: object):
    if hasattr(outcome, "status"):
        return outcome.status
    if isinstance(outcome, tuple) and outcome:
        terminal = outcome[-1]
        return terminal.status if terminal is not None else None
    return None


def _default_reason(decision: AgentDecision, status: object, turn: Turn) -> str:
    if turn.result is not None and turn.result.error is not None:
        return str(turn.result.error)
    decision_name = re.sub(r"(?<!^)(?=[A-Z])", "_", type(decision).__name__).lower()
    status_name = str(status or "continued")
    return f"{decision_name}_{status_name}"[:96]
