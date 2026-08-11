"""Pure authority for bounded control-transition state changes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeAlias

from affordance_runtime.agent.attempt_receipt import AttemptDisposition, AttemptOperation
from affordance_runtime.agent.control_feedback import (
    ControlFeedbackKind,
    ControlFeedbackSource,
)
from affordance_runtime.agent.control_transition import (
    AcquisitionSummary,
    AdmissionStatus,
    ControlContinuation,
    ControlTransition,
    PendingKind,
)
from affordance_runtime.agent.decisions import Abort, AskUser, SelectAction
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus, TaskOutcomeKind
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.world.acquisition import AcquisitionStatus

_TERMINAL = {"done", "blocked", "cancelled", "failed"}
_DECISION_KIND_NAMES = {
    "Abort",
    "AskUser",
    "ProposeDone",
    "RequestActionPage",
    "RequestObservation",
    "SelectAction",
    "Wait",
}


@dataclass(frozen=True)
class ControlState:
    """Reducer-owned control facts projected into ``AgentLoopState``."""

    recent_transitions: tuple[ControlTransition, ...] = ()
    total_count: int = 0
    kind_counts: tuple[tuple[str, int], ...] = ()
    sent_unknown_total_count: int = 0
    continued_root_ids: tuple[str, ...] = ()
    terminal_status: str = ""


@dataclass(frozen=True)
class AppendRoot:
    transition: ControlTransition
    recent_limit: int


@dataclass(frozen=True)
class ApplyContinuation:
    continuation: ControlContinuation


ControlCommand: TypeAlias = AppendRoot | ApplyContinuation


@dataclass(frozen=True)
class ControlAccepted:
    state: ControlState
    transition: ControlTransition


@dataclass(frozen=True)
class ControlRejected:
    code: str


ControlReduction: TypeAlias = ControlAccepted | ControlRejected


class ControlReductionError(ValueError):
    """Compatibility exception for callers that cannot yet consume typed rejection."""

    def __init__(self, rejection: ControlRejected) -> None:
        self.rejection = rejection
        super().__init__(rejection.code)


def reduce_control(state: ControlState, command: ControlCommand) -> ControlReduction:
    """Apply one supported command without I/O, persistence, replay, or reconstruction."""

    invalid_state = validate_control_state(state)
    if invalid_state is not None:
        return invalid_state
    if state.terminal_status:
        return ControlRejected("terminal_state_is_absorbing")
    if isinstance(command, AppendRoot):
        return _append_root(state, command)
    if isinstance(command, ApplyContinuation):
        return _apply_continuation(state, command.continuation)
    return ControlRejected("unsupported_control_command")


def _append_root(state: ControlState, command: AppendRoot) -> ControlReduction:
    transition = command.transition
    if not isinstance(transition, ControlTransition):
        return ControlRejected("invalid_root_transition")
    if state.recent_transitions and (
        state.recent_transitions[-1].pending_kind is PendingKind.CONFIRMATION
    ):
        return ControlRejected("pending_confirmation_must_resolve")
    if state.recent_transitions and str(
        state.recent_transitions[-1].resulting_status or ""
    ) == "waiting_user":
        return ControlRejected("waiting_state_requires_typed_resume")
    if type(command.recent_limit) is not int or command.recent_limit <= 0:
        return ControlRejected("invalid_recent_transition_limit")
    if transition.sequence != state.total_count + 1:
        return ControlRejected("noncontiguous_root_sequence")
    if not _identity_matches_sequence(transition.transition_id, transition.sequence):
        return ControlRejected("root_identity_sequence_mismatch")
    if (
        state.recent_transitions
        and transition.before_observation_id
        != state.recent_transitions[-1].after_observation_id
    ):
        return ControlRejected("observation_epoch_discontinuity")
    if any(
        item.transition_id == transition.transition_id
        for item in state.recent_transitions
    ):
        return ControlRejected("duplicate_root_transition")
    outcome_error = _pending_status_error(
        transition.pending_kind, transition.resulting_status, transition.task_evaluation
    )
    if outcome_error:
        return ControlRejected(outcome_error)
    if (
        transition.pending_kind is PendingKind.CONFIRMATION
    ) != bool(
        transition.admission is not None
        and transition.admission.status is AdmissionStatus.CONFIRMATION_REQUIRED
    ):
        return ControlRejected("confirmation_admission_mismatch")
    transition_error = _transition_fact_error(
        transition.execution,
        transition.execution_attempts,
        transition.acquisition,
        transition.acquisition_attempts,
        transition.attempt_receipts,
    )
    if transition_error:
        return ControlRejected(transition_error)
    lifecycle_error = _transition_lifecycle_error(transition)
    if lifecycle_error:
        return ControlRejected(lifecycle_error)

    counts = dict(state.kind_counts)
    kind = type(transition.decision).__name__
    counts[kind] = counts.get(kind, 0) + 1
    terminal = str(transition.resulting_status or "")
    if terminal not in _TERMINAL:
        terminal = ""
    next_state = ControlState(
        (*state.recent_transitions, transition)[-command.recent_limit :],
        state.total_count + 1,
        tuple(sorted(counts.items())),
        state.sent_unknown_total_count + _sent_unknown(transition.attempt_receipts),
        state.continued_root_ids,
        terminal,
    )
    return _accept_candidate(next_state, transition)


def _apply_continuation(
    state: ControlState,
    continuation: ControlContinuation,
) -> ControlReduction:
    if not isinstance(continuation, ControlContinuation):
        return ControlRejected("invalid_control_continuation")
    if continuation.source_transition_id in state.continued_root_ids:
        return ControlRejected("confirmation_root_already_consumed")
    index = next(
        (
            index
            for index, transition in enumerate(state.recent_transitions)
            if transition.transition_id == continuation.source_transition_id
        ),
        None,
    )
    if index is None:
        return ControlRejected("confirmation_root_outside_bounded_suffix")
    transition = state.recent_transitions[index]
    if (
        transition.pending_kind is not PendingKind.CONFIRMATION
        or str(transition.resulting_status) != "waiting_confirmation"
    ):
        return ControlRejected("root_is_not_pending_confirmation")
    if (
        continuation.pending_kind is PendingKind.CONFIRMATION
        or str(continuation.resulting_status) == "waiting_confirmation"
    ):
        return ControlRejected("confirmation_continuation_must_resolve")
    outcome_error = _pending_status_error(
        continuation.pending_kind,
        continuation.resulting_status,
        _current_task_evaluation(
            continuation.task_evaluation,
            transition.task_evaluation,
            continuation.after_observation_id,
        ),
    )
    if outcome_error:
        return ControlRejected(outcome_error)
    transition_error = _transition_fact_error(
        continuation.execution,
        continuation.execution_attempts,
        continuation.acquisition,
        continuation.acquisition_attempts,
        continuation.attempt_receipts,
    )
    if transition_error:
        return ControlRejected(transition_error)

    acquisition_attempts = (
        *transition.acquisition_attempts,
        *continuation.acquisition_attempts,
    )
    updated = replace(
        transition,
        execution=continuation.execution or transition.execution,
        execution_attempts=(
            *transition.execution_attempts,
            *continuation.execution_attempts,
        ),
        acquisition=_aggregate_acquisition(acquisition_attempts),
        acquisition_attempts=acquisition_attempts,
        attempt_receipts=(
            *transition.attempt_receipts,
            *continuation.attempt_receipts,
        ),
        after_observation_id=continuation.after_observation_id,
        action_evaluation=(
            continuation.action_evaluation or transition.action_evaluation
        ),
        task_evaluation=_current_task_evaluation(
            continuation.task_evaluation,
            transition.task_evaluation,
            continuation.after_observation_id,
        ),
        progress=type(transition.progress)(
            transition.progress.event_count + continuation.progress.event_count,
            continuation.progress.latest_event_type
            or transition.progress.latest_event_type,
        ),
        pending_kind=continuation.pending_kind,
        resulting_status=continuation.resulting_status,
        reason_code=continuation.reason_code,
        intent=continuation.intent or transition.intent,
        request_id=continuation.request_id or transition.request_id,
    )
    values = list(state.recent_transitions)
    values[index] = updated
    terminal = str(updated.resulting_status or "")
    if terminal not in _TERMINAL:
        terminal = ""
    next_state = replace(
        state,
        recent_transitions=tuple(values),
        sent_unknown_total_count=(
            state.sent_unknown_total_count
            + _sent_unknown(continuation.attempt_receipts)
        ),
        continued_root_ids=(
            *state.continued_root_ids,
            continuation.source_transition_id,
        ),
        terminal_status=terminal,
    )
    return _accept_candidate(next_state, updated)


def _aggregate_acquisition(
    attempts: tuple[AcquisitionSummary, ...],
) -> AcquisitionSummary | None:
    if not attempts:
        return None
    final = attempts[-1]
    return replace(final, attempts=sum(item.attempts for item in attempts))


def _current_task_evaluation(continuation, previous, after_observation_id):
    candidate = continuation or previous
    if candidate is None or candidate.observation_id != after_observation_id:
        return None
    return candidate


def _sent_unknown(receipts) -> int:
    return sum(
        item.operation is AttemptOperation.EXECUTE
        and item.dispatch_status is DispatchStatus.SENT_UNKNOWN
        for item in receipts
    )


def _identity_matches_sequence(transition_id: str, sequence: int) -> bool:
    prefix = f"transition:{sequence}"
    if transition_id == prefix:
        return True
    suffix = transition_id.removeprefix(f"{prefix}:")
    return len(suffix) == 20 and all(item in "0123456789abcdef" for item in suffix)


def _transition_fact_error(execution, executions, acquisition, acquisitions, receipts) -> str:
    """Require returned execution summaries to be projections of physical receipts."""

    if any(receipt.operation is AttemptOperation.RESET for receipt in receipts):
        return "reset_receipt_outside_control_root"
    if execution != (executions[-1] if executions else None):
        return "execution_projection_mismatch"
    if acquisition != _aggregate_acquisition(acquisitions):
        return "acquisition_projection_mismatch"
    for item in acquisitions:
        if item.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE:
            if item.attempts != 0 or item.origin is not None:
                return "acquisition_attempt_status_mismatch"
        elif item.status is AcquisitionStatus.ACQUIRED:
            if (
                item.attempts != 1
                or item.origin is None
                or item.origin is not item.expected_origin
            ):
                return "acquisition_attempt_status_mismatch"
        elif item.attempts != 1:
            return "acquisition_attempt_status_mismatch"
    returned = tuple(
        receipt
        for receipt in receipts
        if receipt.operation is AttemptOperation.EXECUTE
        and receipt.disposition is AttemptDisposition.RETURNED
    )
    receipt_ids = tuple(receipt.attempt_id for receipt in receipts)
    if len(receipt_ids) != len(set(receipt_ids)):
        return "duplicate_attempt_receipt"
    if len(executions) != len(returned):
        return "execution_receipt_count_mismatch"
    for summary, receipt in zip(executions, returned, strict=True):
        if (
            summary.expected_request_id != receipt.expected_request_id
            or summary.request_id != receipt.actual_request_id
            or summary.dispatch_status is not receipt.dispatch_status
            or summary.currentness_probe_count != receipt.currentness_probe_count
        ):
            return "execution_receipt_fact_mismatch"
    physical_acquisitions = tuple(item for item in acquisitions if item.attempts)
    receipt_acquisitions = tuple(
        AcquisitionSummary(
            receipt.acquisition_status,
            receipt.actual_origin,
            receipt.reason_code,
            receipt.acquisition_attempts,
            receipt.request_kind,
            receipt.expected_origin,
        )
        for receipt in receipts
        if receipt.acquisition_attempts and receipt.acquisition_status is not None
    )
    if physical_acquisitions != receipt_acquisitions:
        return "acquisition_receipt_fact_mismatch"
    return ""


def _transition_lifecycle_error(
    transition: ControlTransition, *, confirmation_consumed: bool = False,
) -> str:
    """Close the supported finalized-record lifecycle cross-product."""

    is_selection = isinstance(transition.decision, SelectAction)
    admission = transition.admission.status if transition.admission is not None else None
    execute_receipts = tuple(
        item
        for item in transition.attempt_receipts
        if item.operation is AttemptOperation.EXECUTE
    )
    has_execution = bool(transition.execution_attempts or execute_receipts)
    has_evaluation = bool(
        transition.action_evaluation is not None
        or transition.task_evaluation is not None
    )
    feedback = transition.control_feedback
    if feedback is not None:
        if feedback.kind is ControlFeedbackKind.REPAIRABLE_REJECTION and (
            not is_selection
            or admission is not AdmissionStatus.REJECTED
            or feedback.source is not ControlFeedbackSource.ACTION_ADMISSION
            or has_execution
            or transition.acquisition_attempts
            or transition.attempt_receipts
            or transition.before_observation_id != transition.after_observation_id
        ):
            return "repair_feedback_lifecycle_mismatch"
        if feedback.kind is ControlFeedbackKind.NO_INFORMATION_GAIN:
            expected_source = {
                "RequestActionPage": ControlFeedbackSource.ACTION_PAGE,
                "RequestObservation": ControlFeedbackSource.POLICY_OBSERVATION,
            }.get(type(transition.decision).__name__)
            if feedback.source is not expected_source or has_execution:
                return "no_gain_feedback_lifecycle_mismatch"

    if is_selection != (admission is not None):
        return "decision_admission_mismatch"
    if not is_selection and (
        has_execution
        or transition.action_evaluation is not None
        or transition.intent is not None
        or transition.request_id
    ):
        return "decision_execution_mismatch"
    if admission is AdmissionStatus.CONFIRMATION_REQUIRED:
        if confirmation_consumed:
            if transition.pending_kind is PendingKind.CONFIRMATION:
                return "confirmation_lifecycle_mismatch"
        elif (
            transition.pending_kind is not PendingKind.CONFIRMATION
            or str(transition.resulting_status) != "waiting_confirmation"
            or has_execution
            or has_evaluation
            or transition.acquisition_attempts
            or transition.attempt_receipts
        ):
            return "confirmation_lifecycle_mismatch"
    if admission is AdmissionStatus.REJECTED:
        repairable = bool(
            feedback is not None
            and feedback.kind is ControlFeedbackKind.REPAIRABLE_REJECTION
        )
        if (
            transition.pending_kind is not PendingKind.NONE
            or has_execution
            or transition.action_evaluation is not None
            or str(transition.resulting_status or "") not in (
                {"", "blocked", "failed"} if repairable else {"blocked", "failed"}
            )
        ):
            return "rejected_admission_lifecycle_mismatch"
    if admission is AdmissionStatus.ADMITTED and (
        transition.pending_kind is PendingKind.CONFIRMATION
    ):
        return "admitted_lifecycle_mismatch"
    if transition.pending_kind is PendingKind.CONFIRMATION and has_execution:
        return "confirmation_lifecycle_mismatch"
    if transition.action_evaluation is not None and not any(
        item.dispatch_status in {DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN}
        for item in transition.execution_attempts
    ):
        return "evaluation_without_dispatched_action"
    if isinstance(transition.decision, AskUser) and (
        transition.pending_kind is not PendingKind.USER
        or str(transition.resulting_status) != "waiting_user"
    ):
        return "decision_pending_mismatch"
    if isinstance(transition.decision, Abort) and (
        transition.pending_kind is not PendingKind.NONE
        or str(transition.resulting_status) != "failed"
    ):
        return "decision_terminal_mismatch"
    return ""


def _accept_candidate(
    candidate: ControlState,
    transition: ControlTransition,
) -> ControlReduction:
    invalid = validate_control_state(candidate)
    if invalid is not None:
        return invalid
    return ControlAccepted(candidate, transition)


def validate_control_state(state: object) -> ControlRejected | None:
    """Validate any current or candidate state through the single total boundary."""

    if not isinstance(state, ControlState):
        return ControlRejected("invalid_control_state")
    code = _invalid_state_code(state)
    return ControlRejected(code) if code else None


def _pending_status_error(pending_kind, resulting_status, task_evaluation=None) -> str:
    status = str(resulting_status or "")
    if task_evaluation is not None and task_evaluation.outcome is not None:
        terminal_outcome = {
            TaskOutcomeKind.TERMINAL_SUCCESS: (PendingKind.NONE, "done"),
            TaskOutcomeKind.TERMINAL_FAILURE: (PendingKind.NONE, "blocked"),
        }.get(task_evaluation.outcome.kind)
        if terminal_outcome is not None and (pending_kind, status) != terminal_outcome:
            return "task_outcome_disposition_mismatch"
    expected = {
        PendingKind.NONE: {"", *_TERMINAL},
        PendingKind.USER: {"waiting_user"},
        PendingKind.CONFIRMATION: {"waiting_confirmation"},
        PendingKind.UNKNOWN_EFFECT: {"waiting_user"},
    }
    if status in expected[pending_kind]:
        return ""
    if (
        pending_kind is PendingKind.NONE
        and status == "waiting_user"
        and task_evaluation is not None
        and task_evaluation.status is TaskEvaluationStatus.UNKNOWN
    ):
        return ""
    return "pending_status_mismatch"


def _invalid_state_code(state: ControlState) -> str:
    if (
        not isinstance(state.recent_transitions, tuple)
        or not isinstance(state.kind_counts, tuple)
        or not isinstance(state.continued_root_ids, tuple)
    ):
        return "invalid_control_state_shape"
    if (
        type(state.total_count) is not int
        or state.total_count < 0
        or type(state.sent_unknown_total_count) is not int
        or state.sent_unknown_total_count < 0
    ):
        return "invalid_control_totals"
    if not isinstance(state.terminal_status, str):
        return "invalid_terminal_status"
    if state.terminal_status and state.terminal_status not in _TERMINAL:
        return "invalid_terminal_status"
    if len(state.recent_transitions) > state.total_count or any(
        not isinstance(item, ControlTransition) for item in state.recent_transitions
    ):
        return "invalid_control_suffix"
    if bool(state.recent_transitions) != bool(state.total_count):
        return "invalid_control_suffix"
    sequences = tuple(item.sequence for item in state.recent_transitions)
    expected_sequences = tuple(
        range(state.total_count - len(sequences) + 1, state.total_count + 1)
    )
    if (
        sequences != expected_sequences
        or any(
            not _identity_matches_sequence(item.transition_id, item.sequence)
            for item in state.recent_transitions
        )
    ):
        return "invalid_control_suffix"
    if any(
        current.after_observation_id != following.before_observation_id
        for current, following in zip(
            state.recent_transitions,
            state.recent_transitions[1:],
            strict=False,
        )
    ):
        return "observation_epoch_discontinuity"
    if any(
        transition.resulting_status is not None
        for transition in state.recent_transitions[:-1]
    ):
        return "invalid_nonlatest_stopping_transition"
    if (
        any(not isinstance(item, str) for item in state.continued_root_ids)
        or len(state.continued_root_ids) != len(set(state.continued_root_ids))
        or len(state.continued_root_ids) > state.total_count
    ):
        return "invalid_continuation_history"
    continued_sequences = tuple(
        _transition_sequence(item) for item in state.continued_root_ids
    )
    if any(
        sequence is None or sequence > state.total_count
        for sequence in continued_sequences
    ):
        return "invalid_continuation_history"
    valid_continued_sequences = tuple(
        sequence for sequence in continued_sequences if sequence is not None
    )
    if valid_continued_sequences != tuple(sorted(valid_continued_sequences)):
        return "invalid_continuation_history"
    if any(
        not isinstance(item, tuple) or len(item) != 2
        for item in state.kind_counts
    ):
        return "invalid_control_kind_totals"
    if any(
        not isinstance(item[0], str)
        or item[0] not in _DECISION_KIND_NAMES
        or type(item[1]) is not int
        or item[1] <= 0
        for item in state.kind_counts
    ):
        return "invalid_control_kind_totals"
    counts = dict(state.kind_counts)
    if len(counts) != len(state.kind_counts) or any(
        name not in _DECISION_KIND_NAMES for name in counts
    ) or sum(counts.values()) != state.total_count:
        return "invalid_control_kind_totals"
    suffix_kind_counts: dict[str, int] = {}
    for transition in state.recent_transitions:
        name = type(transition.decision).__name__
        suffix_kind_counts[name] = suffix_kind_counts.get(name, 0) + 1
    if any(
        count > counts.get(name, 0)
        for name, count in suffix_kind_counts.items()
    ):
        return "invalid_control_kind_totals"
    suffix_receipts = tuple(
        receipt
        for transition in state.recent_transitions
        for receipt in transition.attempt_receipts
    )
    suffix_receipt_ids = tuple(item.attempt_id for item in suffix_receipts)
    if len(suffix_receipt_ids) != len(set(suffix_receipt_ids)):
        return "duplicate_attempt_receipt"
    for transition in state.recent_transitions:
        if _pending_status_error(
            transition.pending_kind,
            transition.resulting_status,
            transition.task_evaluation,
        ):
            return "pending_status_mismatch"
        fact_error = _transition_fact_error(
            transition.execution,
            transition.execution_attempts,
            transition.acquisition,
            transition.acquisition_attempts,
            transition.attempt_receipts,
        )
        if fact_error:
            return fact_error
        lifecycle_error = _transition_lifecycle_error(
            transition,
            confirmation_consumed=(
                transition.transition_id in state.continued_root_ids
            ),
        )
        if lifecycle_error:
            return lifecycle_error
        confirmation_admission = bool(
            transition.admission is not None
            and transition.admission.status is AdmissionStatus.CONFIRMATION_REQUIRED
        )
        if transition.pending_kind is PendingKind.CONFIRMATION:
            if not confirmation_admission:
                return "confirmation_admission_mismatch"
        elif confirmation_admission and transition.transition_id not in state.continued_root_ids:
            return "confirmation_admission_mismatch"
    pending_confirmation_indexes = tuple(
        index
        for index, transition in enumerate(state.recent_transitions)
        if transition.pending_kind is PendingKind.CONFIRMATION
    )
    if pending_confirmation_indexes and pending_confirmation_indexes != (
        len(state.recent_transitions) - 1,
    ):
        return "invalid_pending_confirmation_position"
    suffix_sent_unknown = _sent_unknown(suffix_receipts)
    if not suffix_sent_unknown <= state.sent_unknown_total_count <= state.total_count:
        return "invalid_sent_unknown_total"
    visible_by_id = {
        item.transition_id: item for item in state.recent_transitions
    }
    for root_id in state.continued_root_ids:
        visible = visible_by_id.get(root_id)
        if visible is not None and (
            visible.admission is None
            or visible.admission.status is not AdmissionStatus.CONFIRMATION_REQUIRED
            or visible.pending_kind is PendingKind.CONFIRMATION
        ):
            return "invalid_continuation_history"
    latest_terminal = ""
    if state.recent_transitions:
        candidate = str(state.recent_transitions[-1].resulting_status or "")
        latest_terminal = candidate if candidate in _TERMINAL else ""
    if state.terminal_status != latest_terminal:
        return "terminal_status_projection_mismatch"
    return ""


def _transition_sequence(transition_id: object) -> int | None:
    if not isinstance(transition_id, str):
        return None
    parts = transition_id.split(":", 2)
    if len(parts) < 2 or parts[0] != "transition" or not parts[1].isdigit():
        return None
    sequence = int(parts[1])
    return sequence if sequence > 0 else None
