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
    AdmissionStatus,
    ControlContinuation,
    ControlTransition,
    PendingKind,
)
from affordance_runtime.agent.decisions import (
    Abort,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.user_input import UserInputContinuation
from affordance_runtime.evaluation.contracts import (
    EvaluationInterruption,
    TaskEvaluationStatus,
    TaskOutcomeKind,
)
from affordance_runtime.execution.contracts import ActionError, DispatchStatus
from affordance_runtime.world.acquisition import (
    AcquisitionStage,
    AcquisitionStatus,
    ObservationRequestKind,
)

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


@dataclass(frozen=True)
class ApplyUserInputContinuation:
    continuation: UserInputContinuation


ControlCommand: TypeAlias = AppendRoot | ApplyContinuation | ApplyUserInputContinuation


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
    if isinstance(command, ApplyUserInputContinuation):
        return _apply_user_input_continuation(state, command.continuation)
    return ControlRejected("unsupported_control_command")


def _append_root(state: ControlState, command: AppendRoot) -> ControlReduction:
    transition = command.transition
    if not isinstance(transition, ControlTransition):
        return ControlRejected("invalid_root_transition")
    if state.recent_transitions and (state.recent_transitions[-1].pending_kind is PendingKind.CONFIRMATION):
        return ControlRejected("pending_confirmation_must_resolve")
    if state.recent_transitions and str(state.recent_transitions[-1].resulting_status or "") == "waiting_user":
        return ControlRejected("waiting_state_requires_typed_resume")
    if type(command.recent_limit) is not int or command.recent_limit <= 0:
        return ControlRejected("invalid_recent_transition_limit")
    if transition.sequence != state.total_count + 1:
        return ControlRejected("noncontiguous_root_sequence")
    if not _identity_matches_sequence(transition.transition_id, transition.sequence):
        return ControlRejected("root_identity_sequence_mismatch")
    if state.recent_transitions and transition.before_observation is not state.recent_transitions[-1].after_observation:
        return ControlRejected("observation_epoch_discontinuity")
    if any(item.transition_id == transition.transition_id for item in state.recent_transitions):
        return ControlRejected("duplicate_root_transition")
    outcome_error = _pending_status_error(
        transition.pending_kind, transition.resulting_status, transition.task_evaluation
    )
    if outcome_error:
        return ControlRejected(outcome_error)
    if (transition.pending_kind is PendingKind.CONFIRMATION) != bool(
        transition.admission is not None and transition.admission.status is AdmissionStatus.CONFIRMATION_REQUIRED
    ):
        return ControlRejected("confirmation_admission_mismatch")
    transition_error = _transition_fact_error(
        transition.execution_attempts,
        transition.acquisition_attempts,
        transition.attempt_receipts,
    )
    if transition_error:
        return ControlRejected(transition_error)
    after_world_error = _after_world_lineage_error(transition, transition.before_observation)
    if after_world_error:
        return ControlRejected(after_world_error)
    ordering_error = _new_fact_order_error(
        _latest_transition_fact_sequence(state.recent_transitions, "attempt"),
        _latest_transition_fact_sequence(state.recent_transitions, "acquisition"),
        transition.attempt_receipts,
        transition.acquisition_attempts,
    )
    if ordering_error:
        return ControlRejected(ordering_error)
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
        continuation.execution_attempts,
        continuation.acquisition_attempts,
        continuation.attempt_receipts,
    )
    if transition_error:
        return ControlRejected(transition_error)
    after_world_error = _after_world_lineage_error(continuation, transition.after_observation)
    if after_world_error:
        return ControlRejected(after_world_error)
    ordering_error = _new_fact_order_error(
        _latest_transition_fact_sequence(state.recent_transitions, "attempt"),
        _latest_transition_fact_sequence(state.recent_transitions, "acquisition"),
        continuation.attempt_receipts,
        continuation.acquisition_attempts,
    )
    if ordering_error:
        return ControlRejected(ordering_error)

    updated = replace(
        transition,
        execution_attempts=(
            *transition.execution_attempts,
            *continuation.execution_attempts,
        ),
        acquisition_attempts=(
            *transition.acquisition_attempts,
            *continuation.acquisition_attempts,
        ),
        linked_acquisitions=(
            *transition.linked_acquisitions,
            *continuation.linked_acquisitions,
        ),
        attempt_receipts=(
            *transition.attempt_receipts,
            *continuation.attempt_receipts,
        ),
        after_observation=continuation.after_observation,
        evaluation=continuation.evaluation or transition.evaluation,
        direct_task_evaluation=(continuation.direct_task_evaluation if continuation.evaluation is None else None),
        progress=type(transition.progress)(
            transition.progress.event_count + continuation.progress.event_count,
            continuation.progress.latest_event_type or transition.progress.latest_event_type,
        ),
        pending_kind=continuation.pending_kind,
        resulting_status=continuation.resulting_status,
        reason_code=continuation.reason_code,
        continuation_admission=continuation.admission or transition.continuation_admission,
        continuation_decision=continuation.decision or transition.continuation_decision,
    )
    values = list(state.recent_transitions)
    values[index] = updated
    terminal = str(updated.resulting_status or "")
    if terminal not in _TERMINAL:
        terminal = ""
    next_state = replace(
        state,
        recent_transitions=tuple(values),
        sent_unknown_total_count=(state.sent_unknown_total_count + _sent_unknown(continuation.attempt_receipts)),
        continued_root_ids=(
            *state.continued_root_ids,
            continuation.source_transition_id,
        ),
        terminal_status=terminal,
    )
    return _accept_candidate(next_state, updated)


def _apply_user_input_continuation(
    state: ControlState,
    continuation: UserInputContinuation,
) -> ControlReduction:
    if not isinstance(continuation, UserInputContinuation):
        return ControlRejected("invalid_user_input_continuation")
    if continuation.source_transition_id in state.continued_root_ids:
        return ControlRejected("user_input_root_already_consumed")
    index = next(
        (
            index
            for index, transition in enumerate(state.recent_transitions)
            if transition.transition_id == continuation.source_transition_id
        ),
        None,
    )
    if index is None:
        return ControlRejected("user_input_root_outside_bounded_suffix")
    transition = state.recent_transitions[index]
    if (
        index != len(state.recent_transitions) - 1
        or not isinstance(transition.decision, AskUser)
        or transition.pending_kind is not PendingKind.USER
        or str(transition.resulting_status) != "waiting_user"
    ):
        return ControlRejected("root_is_not_pending_user_input")
    if continuation.previous_task_revision < 1 or continuation.task_revision != (
        continuation.previous_task_revision + 1
    ):
        return ControlRejected("task_revision_not_consecutive")
    updated = replace(
        transition,
        pending_kind=PendingKind.NONE,
        resulting_status=None,
        reason_code="user_input_submitted",
    )
    values = list(state.recent_transitions)
    values[index] = updated
    next_state = replace(
        state,
        recent_transitions=tuple(values),
        continued_root_ids=(*state.continued_root_ids, continuation.source_transition_id),
    )
    return _accept_candidate(next_state, updated)


def _current_task_evaluation(continuation, previous, after_observation_id):
    candidate = continuation or previous
    if candidate is None or candidate.observation_id != after_observation_id:
        return None
    return candidate


def _sent_unknown(receipts) -> int:
    return sum(
        item.operation is AttemptOperation.EXECUTE and item.dispatch_status is DispatchStatus.SENT_UNKNOWN
        for item in receipts
    )


def _identity_matches_sequence(transition_id: str, sequence: int) -> bool:
    prefix = f"transition:{sequence}"
    if transition_id == prefix:
        return True
    suffix = transition_id.removeprefix(f"{prefix}:")
    return len(suffix) == 20 and all(item in "0123456789abcdef" for item in suffix)


def _transition_fact_error(executions, acquisitions, receipts) -> str:
    """Use receipts only to cross-check exact aggregates, never to rebuild them."""

    if any(receipt.operation is AttemptOperation.RESET for receipt in receipts):
        return "reset_receipt_outside_control_root"
    closed_execution_receipts = tuple(
        receipt
        for receipt in receipts
        if receipt.operation is AttemptOperation.EXECUTE
        and (
            receipt.disposition is AttemptDisposition.RETURNED
            or (receipt.disposition is AttemptDisposition.CANCELLED and receipt.dispatch_status is not None)
        )
    )
    receipt_ids = tuple(receipt.attempt_id for receipt in receipts)
    if len(receipt_ids) != len(set(receipt_ids)):
        return "duplicate_attempt_receipt"
    if len(executions) != len(closed_execution_receipts):
        return "execution_receipt_count_mismatch"
    if len(executions) > 2:
        return "execution_reroute_limit_exceeded"
    if len({item.request.request_id for item in executions}) != len(executions):
        return "duplicate_execution_request"
    if len(executions) == 2 and executions[0].result.dispatch_status is not DispatchStatus.NOT_SENT:
        return "reroute_after_dispatch"
    if sum(item.result.dispatch_status is not DispatchStatus.NOT_SENT for item in executions) > 1:
        return "multiple_effectful_dispatches"
    for outcome, receipt in zip(executions, closed_execution_receipts, strict=True):
        if (
            outcome.request.request_id != receipt.expected_request_id
            or outcome.result.request_id != receipt.actual_request_id
            or outcome.result.dispatch_status is not receipt.dispatch_status
        ):
            return "execution_receipt_fact_mismatch"
        post = outcome.post_acquisition
        if (post is None) != (receipt.acquisition_status is None):
            return "execution_receipt_acquisition_mismatch"
    execution_posts = tuple(item.post_acquisition for item in executions if item.post_acquisition is not None)
    standalone_acquisitions = tuple(item for item in acquisitions if not any(item is post for post in execution_posts))
    closed_capture_receipts = tuple(
        item
        for item in receipts
        if item.operation is AttemptOperation.CAPTURE
        and (
            item.disposition is AttemptDisposition.RETURNED
            or (
                item.disposition is AttemptDisposition.CANCELLED
                and item.acquisition_status is AcquisitionStatus.CANCELLED
            )
        )
    )
    if len(standalone_acquisitions) != len(closed_capture_receipts):
        return "capture_receipt_count_mismatch"
    for acquisition, receipt in zip(
        standalone_acquisitions,
        closed_capture_receipts,
        strict=True,
    ):
        attempts = int(acquisition.stage is not AcquisitionStage.PRE_SELECTION_UNAVAILABLE)
        expected_status = (
            AcquisitionStatus.FAILED
            if acquisition.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE and attempts
            else acquisition.status
        )
        actual_origin = None if not attempts else acquisition.origin
        if (
            str(acquisition.request.kind) != receipt.request_kind
            or receipt.actual_origin is not actual_origin
            or receipt.acquisition_attempts != attempts
            or (
                receipt.acquisition_status is not expected_status
                and not (
                    acquisition.status is AcquisitionStatus.ACQUIRED
                    and receipt.acquisition_status is AcquisitionStatus.FAILED
                    and receipt.reason_code
                    in {
                        "independent_capture_origin_invalid",
                        "observation_identity_reused",
                    }
                )
            )
        ):
            return "capture_receipt_fact_mismatch"
    return ""


def _after_world_lineage_error(transition, before_observation) -> str:
    """Fold exact successful acquisition receipts into the authoritative after world."""

    execution_receipts = tuple(
        item
        for item in transition.attempt_receipts
        if item.operation is AttemptOperation.EXECUTE
        and (
            item.disposition is AttemptDisposition.RETURNED
            or (item.disposition is AttemptDisposition.CANCELLED and item.dispatch_status is not None)
        )
    )
    posts = tuple(item.post_acquisition for item in transition.execution_attempts)
    post_acquisitions = tuple(item for item in posts if item is not None)
    standalone = tuple(
        item for item in transition.acquisition_attempts if not any(item is post for post in post_acquisitions)
    )
    capture_receipts = tuple(
        item
        for item in transition.attempt_receipts
        if item.operation is AttemptOperation.CAPTURE
        and (
            item.disposition is AttemptDisposition.RETURNED
            or (
                item.disposition is AttemptDisposition.CANCELLED
                and item.acquisition_status is AcquisitionStatus.CANCELLED
            )
        )
    )
    acquisitions_by_attempt = {
        receipt.attempt_id: outcome.post_acquisition
        for outcome, receipt in zip(transition.execution_attempts, execution_receipts, strict=True)
        if outcome.post_acquisition is not None
    }
    acquisitions_by_attempt.update(
        {receipt.attempt_id: acquisition for acquisition, receipt in zip(standalone, capture_receipts, strict=True)}
    )
    expected = before_observation
    for receipt in transition.attempt_receipts:
        acquisition = acquisitions_by_attempt.get(receipt.attempt_id)
        if acquisition is not None and receipt.acquisition_status is AcquisitionStatus.ACQUIRED:
            if acquisition.observation is None:
                return "acquired_receipt_without_world"
            expected = acquisition.observation
    if transition.after_observation is not expected:
        return "after_world_lineage_mismatch"
    return ""


def _transition_lifecycle_error(
    transition: ControlTransition,
    *,
    root_consumed: bool = False,
) -> str:
    """Close the supported finalized-record lifecycle cross-product."""

    is_selection = isinstance(transition.decision, SelectAction)
    admission = transition.admission.status if transition.admission is not None else None
    execute_receipts = tuple(item for item in transition.attempt_receipts if item.operation is AttemptOperation.EXECUTE)
    has_execution = bool(transition.execution_attempts or execute_receipts)
    has_evaluation = bool(transition.action_evaluation is not None or transition.task_evaluation is not None)
    feedback = transition.control_feedback
    physical_disposition_error = _physical_disposition_error(transition)
    if physical_disposition_error:
        return physical_disposition_error
    if str(transition.resulting_status or "") == "done" and not (
        transition.task_evaluation is not None and transition.task_evaluation.status is TaskEvaluationStatus.COMPLETE
    ):
        return "success_without_terminal_task_authority"
    if feedback is not None:
        if feedback.kind is ControlFeedbackKind.REPAIRABLE_REJECTION:
            source_matches = (
                feedback.source is ControlFeedbackSource.ACTION_ADMISSION
                and is_selection
                and admission is AdmissionStatus.REJECTED
            )
            if (
                not source_matches
                or has_execution
                or transition.acquisition_attempts
                or transition.attempt_receipts
                or transition.before_observation_id != transition.after_observation_id
            ):
                return "repair_feedback_lifecycle_mismatch"
        if feedback.kind is ControlFeedbackKind.OBSERVATION_TRAVERSAL_REQUIRED and (
            feedback.source is not ControlFeedbackSource.OBSERVATION_COVERAGE
            or has_execution
            or transition.acquisition_attempts
            or transition.attempt_receipts
            or transition.before_observation_id != transition.after_observation_id
            or str(transition.resulting_status or "") != ""
        ):
            return "observation_traversal_feedback_lifecycle_mismatch"
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
    preserves_world_without_phase = isinstance(transition.decision, Abort | AskUser | RequestActionPage)
    if preserves_world_without_phase and (
        transition.acquisition_attempts
        or transition.linked_acquisitions
        or transition.attempt_receipts
        or transition.evaluation is not None
        or transition.direct_task_evaluation is not None
        or transition.before_observation is not transition.after_observation
    ):
        return "decision_phase_shape_mismatch"
    if isinstance(transition.decision, ProposeDone) and (
        transition.acquisition_attempts
        or transition.linked_acquisitions
        or transition.attempt_receipts
        or transition.evaluation is not None
        or transition.before_observation is not transition.after_observation
    ):
        return "completion_phase_shape_mismatch"
    if isinstance(transition.decision, Wait) and (
        transition.linked_acquisitions
        or transition.evaluation is not None
        or transition.direct_task_evaluation is not None
        or any(item.operation is not AttemptOperation.CAPTURE for item in transition.attempt_receipts)
        or transition.pending_kind is not PendingKind.NONE
        or str(transition.resulting_status or "") not in {"", "failed", "blocked", "cancelled"}
    ):
        return "wait_phase_shape_mismatch"
    if isinstance(transition.decision, RequestObservation) and (
        transition.linked_acquisitions
        or transition.direct_task_evaluation is not None
        or any(item.operation is not AttemptOperation.CAPTURE for item in transition.attempt_receipts)
        or (transition.evaluation is not None and transition.evaluation.observation_trigger is None)
    ):
        return "observation_phase_shape_mismatch"
    if is_selection and transition.evaluation is not None and transition.evaluation.execution is None:
        return "selection_evaluation_trigger_mismatch"
    if isinstance(transition.evaluation, EvaluationInterruption):
        expected = "cancelled" if transition.evaluation.reason_code.cancelled else "failed"
        if str(transition.resulting_status or "") != expected:
            return "evaluation_interruption_disposition_mismatch"
    if is_selection and transition.execution_attempts:
        effective_decision = transition.continuation_decision or transition.decision
        if any(item.request.context_id != effective_decision.context_id for item in transition.execution_attempts):
            return "execution_context_lineage_mismatch"
        if len(transition.execution_attempts) == 2:
            first, second = transition.execution_attempts
            if first.result.error not in {
                ActionError.STALE_BINDING,
                ActionError.CURRENTNESS_UNAVAILABLE,
                ActionError.RATE_LIMITED,
                ActionError.UNSUPPORTED_ACTION,
            }:
                return "unsupported_reroute_cause"
            if not _equivalent_reroute_selection(first.request.selection, second.request.selection):
                return "reroute_selection_lineage_mismatch"
    phase_order_error = _decision_acquisition_order_error(transition)
    if phase_order_error:
        return phase_order_error
    if admission is AdmissionStatus.CONFIRMATION_REQUIRED:
        if root_consumed:
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
    if transition.continuation_admission is not None:
        continued_selection = transition.continuation_admission.selection
        original_confirmation = transition.admission.confirmation_request if transition.admission is not None else None
        if (
            not root_consumed
            or admission is not AdmissionStatus.CONFIRMATION_REQUIRED
            or transition.continuation_admission.status is not AdmissionStatus.CONFIRMED
            or not isinstance(transition.continuation_decision, SelectAction)
            or continued_selection is None
            or transition.continuation_decision.action_id != continued_selection.action_id
            or transition.continuation_decision.parameters != continued_selection.parameters
            or transition.continuation_decision.destination_id != continued_selection.destination_id
            or transition.continuation_admission.confirmation_request is not original_confirmation
            or (
                not transition.execution_attempts
                and not (
                    transition.reason_code == "already_satisfied" and transition.direct_task_evaluation is not None
                )
            )
        ):
            return "confirmation_readmission_lifecycle_mismatch"
    elif transition.continuation_decision is not None:
        return "continuation_decision_without_admission"
    if admission is AdmissionStatus.CONFIRMED:
        return "confirmed_admission_outside_continuation"
    if admission is AdmissionStatus.REJECTED:
        repairable = bool(feedback is not None and feedback.kind is ControlFeedbackKind.REPAIRABLE_REJECTION)
        if (
            transition.pending_kind is not PendingKind.NONE
            or has_execution
            or transition.action_evaluation is not None
            or str(transition.resulting_status or "")
            not in ({"", "blocked", "failed"} if repairable else {"blocked", "failed"})
        ):
            return "rejected_admission_lifecycle_mismatch"
    if admission is AdmissionStatus.ADMITTED and (transition.pending_kind is PendingKind.CONFIRMATION):
        return "admitted_lifecycle_mismatch"
    if transition.pending_kind is PendingKind.CONFIRMATION and has_execution:
        return "confirmation_lifecycle_mismatch"
    if transition.action_evaluation is not None and not any(
        item.result.dispatch_status in {DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN}
        for item in transition.execution_attempts
    ):
        return "evaluation_without_dispatched_action"
    if isinstance(transition.decision, AskUser):
        if root_consumed:
            if transition.pending_kind is not PendingKind.NONE or transition.resulting_status is not None:
                return "decision_pending_mismatch"
        elif transition.pending_kind is not PendingKind.USER or str(transition.resulting_status) != "waiting_user":
            return "decision_pending_mismatch"
    if isinstance(transition.decision, Abort):
        coverage_advance = bool(
            feedback is not None
            and feedback.kind is ControlFeedbackKind.OBSERVATION_TRAVERSAL_REQUIRED
            and str(transition.resulting_status or "") == ""
        )
        coverage_unknown = str(transition.resulting_status or "") == "blocked" and transition.reason_code in {
            "negative_claim_source_coverage_unavailable",
            "negative_claim_inventory_incomplete",
            "model_page_capacity_exceeded",
            "observation_traversal_budget_exhausted",
        }
        if transition.pending_kind is not PendingKind.NONE or not (
            str(transition.resulting_status) == "failed" or coverage_advance or coverage_unknown
        ):
            return "decision_terminal_mismatch"
    return ""


def _decision_acquisition_order_error(transition: ControlTransition) -> str:
    execution_posts = tuple(
        item.post_acquisition for item in transition.execution_attempts if item.post_acquisition is not None
    )
    standalone = tuple(
        item for item in transition.acquisition_attempts if not any(item is post for post in execution_posts)
    )
    captures = tuple(
        item
        for item in transition.attempt_receipts
        if item.operation is AttemptOperation.CAPTURE
        and (
            item.disposition is AttemptDisposition.RETURNED
            or (
                item.disposition is AttemptDisposition.CANCELLED
                and item.acquisition_status is AcquisitionStatus.CANCELLED
            )
        )
    )
    if len(standalone) != len(captures):
        return "decision_capture_shape_mismatch"
    pairs = tuple(zip(standalone, captures, strict=True))
    standalone_kinds = tuple(item.request.kind for item, _ in pairs)
    if len(set(standalone_kinds)) != len(standalone_kinds):
        return "duplicate_decision_capture_kind"
    if len(transition.execution_attempts) == 2:
        first, second = transition.execution_attempts
        refreshes = tuple(
            acquisition
            for acquisition, _ in pairs
            if acquisition.request.kind is ObservationRequestKind.CURRENTNESS_REFRESH
        )
        requires_refresh = first.result.error in {
            ActionError.STALE_BINDING,
            ActionError.CURRENTNESS_UNAVAILABLE,
        }
        if requires_refresh:
            if (
                len(refreshes) != 1
                or refreshes[0].observation is None
                or second.request.world_observation_id != refreshes[0].observation.observation_id
                or second.request.selection is first.request.selection
            ):
                return "reroute_currentness_refresh_mismatch"
        elif refreshes or second.request.selection is not first.request.selection:
            return "unexpected_reroute_currentness_refresh"
        if second.request.binding.binding_id == first.request.binding.binding_id:
            return "reroute_binding_not_advanced"
    if isinstance(transition.decision, RequestObservation):
        if any(item.request.kind is not ObservationRequestKind.POLICY_REQUEST for item, _ in pairs):
            return "observation_capture_kind_mismatch"
        return ""
    if isinstance(transition.decision, Wait):
        if any(item.request.kind is not ObservationRequestKind.WAIT_REFRESH for item, _ in pairs):
            return "wait_capture_kind_mismatch"
        return ""
    if not isinstance(transition.decision, SelectAction):
        return "decision_capture_shape_mismatch" if pairs else ""

    execution_receipts = tuple(
        item
        for item in transition.attempt_receipts
        if item.operation is AttemptOperation.EXECUTE and item.dispatch_status is not None
    )
    for acquisition, receipt in pairs:
        position = _identity_index(transition.attempt_receipts, receipt)
        preceding = tuple(
            item for item in execution_receipts if _identity_index(transition.attempt_receipts, item) < position
        )
        following = tuple(
            item for item in execution_receipts if _identity_index(transition.attempt_receipts, item) > position
        )
        kind = acquisition.request.kind
        if kind is ObservationRequestKind.BINDING_REFRESH:
            if execution_receipts:
                return "binding_refresh_order_mismatch"
        elif kind is ObservationRequestKind.CONFIRMATION_REFRESH:
            if preceding:
                return "confirmation_refresh_order_mismatch"
        elif kind is ObservationRequestKind.CURRENTNESS_REFRESH:
            if len(preceding) != 1 or preceding[0].dispatch_status is not DispatchStatus.NOT_SENT or not following:
                return "currentness_refresh_order_mismatch"
        elif kind is ObservationRequestKind.POST_ACTION_FALLBACK:
            effectful_preceding = tuple(
                item for item in preceding if item.dispatch_status is not DispatchStatus.NOT_SENT
            )
            if (
                len(effectful_preceding) != 1
                or following
                or not any(item.acquisition is acquisition for item in transition.linked_acquisitions)
            ):
                return "post_action_fallback_order_mismatch"
        else:
            return "selection_capture_kind_mismatch"
    return ""


def _identity_index(values: tuple[object, ...], expected: object) -> int:
    return next(index for index, value in enumerate(values) if value is expected)


def _physical_disposition_error(transition: ControlTransition) -> str:
    receipts = transition.attempt_receipts
    cancelled = any(item.disposition is AttemptDisposition.CANCELLED for item in receipts)
    exceptional_failure = any(
        item.disposition in {AttemptDisposition.THREW, AttemptDisposition.MALFORMED} for item in receipts
    )
    closed_acquisition_statuses = tuple(
        item.acquisition_status for item in receipts if item.acquisition_status is not None
    )
    unresolved_acquisition_failure = bool(
        closed_acquisition_statuses
        and closed_acquisition_statuses[-1] in {AcquisitionStatus.FAILED, AcquisitionStatus.CAPABILITY_UNAVAILABLE}
    )
    if cancelled:
        return "cancellation_disposition_mismatch" if str(transition.resulting_status or "") != "cancelled" else ""
    if exceptional_failure:
        return "physical_failure_disposition_mismatch" if str(transition.resulting_status or "") != "failed" else ""
    if unresolved_acquisition_failure:
        status = str(transition.resulting_status or "")
        last_receipt = next(item for item in reversed(receipts) if item.acquisition_status is not None)
        effectful = any(
            item.result.dispatch_status is not DispatchStatus.NOT_SENT for item in transition.execution_attempts
        )
        if effectful:
            expected = "waiting_user"
        elif isinstance(transition.decision, Wait | RequestObservation):
            expected = "blocked" if last_receipt.acquisition_attempts == 0 else "failed"
        else:
            expected = "failed"
        return "physical_failure_disposition_mismatch" if status != expected else ""
    if (
        closed_acquisition_statuses
        and closed_acquisition_statuses[-1] is AcquisitionStatus.ACQUIRED
        and isinstance(transition.decision, Wait)
        and transition.resulting_status is not None
    ):
        return "successful_wait_disposition_mismatch"
    return ""


def _equivalent_reroute_selection(first, second) -> bool:
    return (
        first.semantic_action == second.semantic_action
        and first.target_id == second.target_id
        and first.effect_category == second.effect_category
        and first.semantic_effects == second.semantic_effects
        and first.schema_digest == second.schema_digest
        and first.observation_barrier == second.observation_barrier
        and first.destination_required == second.destination_required
        and first.eligible_destination_ids == second.eligible_destination_ids
        and first.verification_contract_digest == second.verification_contract_digest
        and first.parameters == second.parameters
        and first.destination_id == second.destination_id
        and ("low", "medium", "high", "irreversible").index(str(second.risk))
        <= ("low", "medium", "high", "irreversible").index(str(first.risk))
    )


def _new_fact_order_error(
    previous_attempt: int,
    previous_acquisition: int,
    receipts,
    acquisitions,
) -> str:
    attempt_sequences = tuple(_scoped_sequence(item.attempt_id, "attempt") for item in receipts)
    acquisition_sequences = tuple(_scoped_sequence(item.acquisition_id, "acquisition") for item in acquisitions)
    if attempt_sequences and (
        any(item <= 0 for item in attempt_sequences)
        or attempt_sequences != tuple(sorted(attempt_sequences))
        or attempt_sequences[0] <= previous_attempt
    ):
        return "attempt_identity_not_monotonic"
    if acquisition_sequences and (
        any(item <= 0 for item in acquisition_sequences)
        or acquisition_sequences != tuple(sorted(acquisition_sequences))
        or acquisition_sequences[0] <= previous_acquisition
    ):
        return "acquisition_identity_not_monotonic"
    return ""


def _latest_transition_fact_sequence(transitions, kind: str) -> int:
    if not transitions:
        return 0
    if kind == "attempt":
        values = (
            _scoped_sequence(receipt.attempt_id, "attempt")
            for transition in transitions
            for receipt in transition.attempt_receipts
        )
    else:
        values = (
            _scoped_sequence(acquisition.acquisition_id, "acquisition")
            for transition in transitions
            for acquisition in transition.acquisition_attempts
        )
    return max((0, *values))


def _scoped_sequence(value: str, prefix: str) -> int:
    head, separator, sequence = value.partition(":")
    if head != prefix or separator != ":" or not sequence.isdigit() or int(sequence) <= 0:
        return -1
    return int(sequence)


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
    expected_sequences = tuple(range(state.total_count - len(sequences) + 1, state.total_count + 1))
    if sequences != expected_sequences or any(
        not _identity_matches_sequence(item.transition_id, item.sequence) for item in state.recent_transitions
    ):
        return "invalid_control_suffix"
    if any(
        current.after_observation is not following.before_observation
        for current, following in zip(
            state.recent_transitions,
            state.recent_transitions[1:],
            strict=False,
        )
    ):
        return "observation_epoch_discontinuity"
    if any(transition.resulting_status is not None for transition in state.recent_transitions[:-1]):
        return "invalid_nonlatest_stopping_transition"
    if (
        any(not isinstance(item, str) for item in state.continued_root_ids)
        or len(state.continued_root_ids) != len(set(state.continued_root_ids))
        or len(state.continued_root_ids) > state.total_count
    ):
        return "invalid_continuation_history"
    continued_sequences = tuple(_transition_sequence(item) for item in state.continued_root_ids)
    if any(sequence is None or sequence > state.total_count for sequence in continued_sequences):
        return "invalid_continuation_history"
    valid_continued_sequences = tuple(sequence for sequence in continued_sequences if sequence is not None)
    if valid_continued_sequences != tuple(sorted(valid_continued_sequences)):
        return "invalid_continuation_history"
    if any(not isinstance(item, tuple) or len(item) != 2 for item in state.kind_counts):
        return "invalid_control_kind_totals"
    if any(
        not isinstance(item[0], str) or item[0] not in _DECISION_KIND_NAMES or type(item[1]) is not int or item[1] <= 0
        for item in state.kind_counts
    ):
        return "invalid_control_kind_totals"
    counts = dict(state.kind_counts)
    if (
        len(counts) != len(state.kind_counts)
        or any(name not in _DECISION_KIND_NAMES for name in counts)
        or sum(counts.values()) != state.total_count
    ):
        return "invalid_control_kind_totals"
    suffix_kind_counts: dict[str, int] = {}
    for transition in state.recent_transitions:
        name = type(transition.decision).__name__
        suffix_kind_counts[name] = suffix_kind_counts.get(name, 0) + 1
    if any(count > counts.get(name, 0) for name, count in suffix_kind_counts.items()):
        return "invalid_control_kind_totals"
    suffix_receipts = tuple(
        receipt for transition in state.recent_transitions for receipt in transition.attempt_receipts
    )
    suffix_receipt_ids = tuple(item.attempt_id for item in suffix_receipts)
    if len(suffix_receipt_ids) != len(set(suffix_receipt_ids)):
        return "duplicate_attempt_receipt"
    suffix_attempt_sequences = tuple(_scoped_sequence(item.attempt_id, "attempt") for item in suffix_receipts)
    if any(item <= 0 for item in suffix_attempt_sequences) or suffix_attempt_sequences != tuple(
        sorted(suffix_attempt_sequences)
    ):
        return "attempt_identity_not_monotonic"
    suffix_acquisitions = tuple(
        acquisition for transition in state.recent_transitions for acquisition in transition.acquisition_attempts
    )
    suffix_acquisition_sequences = tuple(
        _scoped_sequence(item.acquisition_id, "acquisition") for item in suffix_acquisitions
    )
    if (
        len(suffix_acquisition_sequences) != len(set(suffix_acquisition_sequences))
        or any(item <= 0 for item in suffix_acquisition_sequences)
        or suffix_acquisition_sequences != tuple(sorted(suffix_acquisition_sequences))
    ):
        return "acquisition_identity_not_monotonic"
    for transition in state.recent_transitions:
        if _pending_status_error(
            transition.pending_kind,
            transition.resulting_status,
            transition.task_evaluation,
        ):
            return "pending_status_mismatch"
        fact_error = _transition_fact_error(
            transition.execution_attempts,
            transition.acquisition_attempts,
            transition.attempt_receipts,
        )
        if fact_error:
            return fact_error
        after_world_error = _after_world_lineage_error(transition, transition.before_observation)
        if after_world_error:
            return after_world_error
        lifecycle_error = _transition_lifecycle_error(
            transition,
            root_consumed=(transition.transition_id in state.continued_root_ids),
        )
        if lifecycle_error:
            return lifecycle_error
        confirmation_admission = bool(
            transition.admission is not None and transition.admission.status is AdmissionStatus.CONFIRMATION_REQUIRED
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
    if pending_confirmation_indexes and pending_confirmation_indexes != (len(state.recent_transitions) - 1,):
        return "invalid_pending_confirmation_position"
    suffix_sent_unknown = _sent_unknown(suffix_receipts)
    if not suffix_sent_unknown <= state.sent_unknown_total_count <= state.total_count:
        return "invalid_sent_unknown_total"
    visible_by_id = {item.transition_id: item for item in state.recent_transitions}
    for root_id in state.continued_root_ids:
        visible = visible_by_id.get(root_id)
        if visible is None:
            continue
        confirmation_resolved = bool(
            visible.admission is not None
            and visible.admission.status is AdmissionStatus.CONFIRMATION_REQUIRED
            and visible.pending_kind is not PendingKind.CONFIRMATION
        )
        user_input_resolved = bool(
            isinstance(visible.decision, AskUser)
            and visible.pending_kind is PendingKind.NONE
            and visible.resulting_status is None
        )
        if not (confirmation_resolved or user_input_resolved):
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
