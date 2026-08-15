"""Exact immutable authority for one accepted policy decision."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, get_args

from affordance_runtime.actions.admission import AdmissionIssue
from affordance_runtime.actions.space_contracts import AdmittedActionSelection
from affordance_runtime.agent.attempt_receipt import AttemptReceipt
from affordance_runtime.agent.control_feedback import ControlFeedback
from affordance_runtime.agent.control_outcome import Continue, LoopDirective, Pause, Terminate
from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    EvaluationInterruption,
    EvaluationOutcome,
    TaskEvaluation,
)
from affordance_runtime.execution.contracts import ActionIntent, DispatchStatus, ExecutionOutcome
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.risk.contracts import RiskAssessment, RiskDecisionKind
from affordance_runtime.world.acquisition import AcquisitionStatus, ObservationAcquisition
from affordance_runtime.world.contracts import WorldObservation

if TYPE_CHECKING:
    from affordance_runtime.agent.observation_control import LinkedAcquisition
    from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus

_REASON = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_TRANSITION_ID = re.compile(r"transition:[1-9][0-9]{0,9}(?::[0-9a-f]{20})?")
_DECISION_TYPES = get_args(AgentDecision)


class AdmissionStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    ADMITTED = "admitted"
    REJECTED = "rejected"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMED = "confirmed"


class PendingKind(StrEnum):
    NONE = "none"
    USER = "user"
    CONFIRMATION = "confirmation"
    UNKNOWN_EFFECT = "unknown_effect"


@dataclass(frozen=True)
class ActionAdmissionOutcome:
    """Exact reached admission facts; absent fields were not reached or did not exist."""

    status: AdmissionStatus
    reason_code: str
    selection: AdmittedActionSelection | None = None
    issue: AdmissionIssue | None = None
    risk_assessment: RiskAssessment | None = None
    confirmation_request: ConfirmationRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AdmissionStatus):
            raise TypeError("admission status must be typed")
        _require_reason_code(self.reason_code)
        if self.selection is not None and not isinstance(self.selection, AdmittedActionSelection):
            raise TypeError("admission selection must be exact")
        if self.issue is not None and not isinstance(self.issue, AdmissionIssue):
            raise TypeError("admission issue must be exact")
        if self.risk_assessment is not None and not isinstance(self.risk_assessment, RiskAssessment):
            raise TypeError("admission risk assessment must be exact")
        if self.confirmation_request is not None and not isinstance(self.confirmation_request, ConfirmationRequest):
            raise TypeError("admission confirmation must be exact")
        if self.status is AdmissionStatus.NOT_APPLICABLE:
            if any(
                item is not None
                for item in (
                    self.selection,
                    self.issue,
                    self.risk_assessment,
                    self.confirmation_request,
                )
            ):
                raise ValueError("not-applicable admission cannot fabricate reached facts")
        elif self.status is AdmissionStatus.ADMITTED:
            if (
                self.selection is None
                or self.risk_assessment is None
                or self.risk_assessment.decision is not RiskDecisionKind.ALLOW
                or self.issue is not None
                or self.confirmation_request is not None
            ):
                raise ValueError("admitted outcome requires exact selection and allow assessment")
        elif self.status is AdmissionStatus.CONFIRMATION_REQUIRED:
            if (
                self.selection is None
                or self.risk_assessment is None
                or self.risk_assessment.decision is not RiskDecisionKind.NEEDS_CONFIRMATION
                or self.confirmation_request is None
                or self.issue is not None
            ):
                raise ValueError("confirmation outcome requires exact reached facts")
        elif self.status is AdmissionStatus.CONFIRMED:
            if (
                self.selection is None
                or self.risk_assessment is None
                or self.risk_assessment.decision not in {RiskDecisionKind.ALLOW, RiskDecisionKind.NEEDS_CONFIRMATION}
                or self.confirmation_request is None
                or self.issue is not None
            ):
                raise ValueError("confirmed outcome requires exact fresh admission and prior confirmation")
        elif self.status is AdmissionStatus.REJECTED:
            issue_rejection = self.issue is not None and self.selection is None and self.risk_assessment is None
            selected_rejection = self.issue is None and self.selection is not None
            if (
                not (issue_rejection or selected_rejection)
                or self.confirmation_request is not None
                or (self.risk_assessment is not None and self.risk_assessment.decision is RiskDecisionKind.ALLOW)
            ):
                raise ValueError("rejected outcome requires exact issue or selected rejection facts")
        if self.selection is not None and self.risk_assessment is not None:
            subject = self.risk_assessment.subject
            if (
                subject.semantic_action != self.selection.semantic_action
                or subject.target_id != self.selection.target_id
                or subject.destination_id != self.selection.destination_id
                or to_json_compatible(subject.parameters) != to_json_compatible(self.selection.parameters)
                or subject.selection_effects != tuple(sorted(self.selection.semantic_effects))
                or subject.effect_category != self.selection.effect_category
            ):
                raise ValueError("admission risk subject must derive from the exact selection semantics")
        if self.confirmation_request is not None and (
            self.risk_assessment is None or self.confirmation_request.subject != self.risk_assessment.subject
        ):
            raise ValueError("admission confirmation must compose the exact assessed subject")


@dataclass(frozen=True)
class ProgressDelta:
    event_count: int = 0
    latest_event_type: str = ""

    def __post_init__(self) -> None:
        if type(self.event_count) is not int or self.event_count < 0:
            raise ValueError("progress event count must be a non-negative integer")


@dataclass(frozen=True)
class ControlTransition:
    transition_id: str
    sequence: int
    before_observation: WorldObservation = field(repr=False)
    decision: AgentDecision
    admission: ActionAdmissionOutcome | None
    execution_attempts: tuple[ExecutionOutcome, ...] = field(repr=False)
    acquisition_attempts: tuple[ObservationAcquisition, ...] = field(repr=False)
    linked_acquisitions: tuple[LinkedAcquisition, ...] = field(repr=False)
    attempt_receipts: tuple[AttemptReceipt, ...]
    after_observation: WorldObservation = field(repr=False)
    evaluation: EvaluationOutcome | EvaluationInterruption | None = field(repr=False)
    direct_task_evaluation: TaskEvaluation | None
    progress: ProgressDelta
    pending_kind: PendingKind
    resulting_status: AgentLoopStatus | None
    reason_code: str
    decision_result: str = ""
    control_feedback: ControlFeedback | None = None
    before_task_evaluation: TaskEvaluation | None = None
    continuation_admission: ActionAdmissionOutcome | None = None
    continuation_decision: AgentDecision | None = None

    def __post_init__(self) -> None:
        from affordance_runtime.agent.state import AgentLoopStatus

        if type(self.sequence) is not int or self.sequence <= 0 or _TRANSITION_ID.fullmatch(self.transition_id) is None:
            raise ValueError("control transition identity is invalid")
        if not isinstance(self.before_observation, WorldObservation) or not isinstance(
            self.after_observation, WorldObservation
        ):
            raise TypeError("control transition must retain exact world values")
        if not isinstance(self.decision, _DECISION_TYPES):
            raise TypeError("control transition decision must be typed")
        if self.continuation_decision is not None and not isinstance(self.continuation_decision, _DECISION_TYPES):
            raise TypeError("control transition continuation decision must be typed")
        if self.admission is not None and not isinstance(self.admission, ActionAdmissionOutcome):
            raise TypeError("control transition admission must be typed")
        if self.continuation_admission is not None and not isinstance(
            self.continuation_admission, ActionAdmissionOutcome
        ):
            raise TypeError("control transition continuation admission must be typed")
        if any(not isinstance(item, ExecutionOutcome) for item in self.execution_attempts):
            raise TypeError("control transition execution attempts must be exact")
        if any(not isinstance(item, ObservationAcquisition) for item in self.acquisition_attempts):
            raise TypeError("control transition acquisition attempts must be exact")
        from affordance_runtime.agent.observation_control import LinkedAcquisition

        if any(not isinstance(item, LinkedAcquisition) for item in self.linked_acquisitions):
            raise TypeError("control transition fallback links must be exact")
        if any(not isinstance(item, AttemptReceipt) for item in self.attempt_receipts):
            raise TypeError("control transition receipts must be typed")
        if self.evaluation is not None and not isinstance(self.evaluation, EvaluationOutcome | EvaluationInterruption):
            raise TypeError("control transition evaluation must be exact")
        if self.direct_task_evaluation is not None and not isinstance(self.direct_task_evaluation, TaskEvaluation):
            raise TypeError("control transition direct task evaluation must be typed")
        if self.evaluation is not None and self.direct_task_evaluation is not None:
            raise ValueError("task evaluation authority cannot be duplicated")
        if not isinstance(self.progress, ProgressDelta) or not isinstance(self.pending_kind, PendingKind):
            raise TypeError("control transition control facts must be typed")
        if self.resulting_status is not None and not isinstance(self.resulting_status, AgentLoopStatus):
            raise TypeError("control transition resulting status must be typed")
        if self.control_feedback is not None and not isinstance(self.control_feedback, ControlFeedback):
            raise TypeError("control transition feedback must be typed")
        if self.evaluation is not None:
            if self.evaluation.before_observation is not self.before_observation and not any(
                item.observation is self.evaluation.before_observation for item in self.acquisition_attempts
            ):
                raise ValueError("transition/evaluation before authority mismatch")
            if self.evaluation.after_observation is not self.after_observation:
                raise ValueError("transition/evaluation after authority mismatch")
            if self.evaluation.execution is not None and not any(
                self.evaluation.execution is item for item in self.execution_attempts
            ):
                raise ValueError("transition evaluation execution is not reachable")
        if len({item.acquisition_id for item in self.acquisition_attempts}) != len(self.acquisition_attempts):
            raise ValueError("transition acquisition attempts cannot repeat")
        execution_posts = tuple(
            item.post_acquisition for item in self.execution_attempts if item.post_acquisition is not None
        )
        if any(not any(item is acquisition for acquisition in self.acquisition_attempts) for item in execution_posts):
            raise ValueError("transition execution post acquisition is not reachable")
        if self.after_observation is not self.before_observation and not any(
            item.observation is self.after_observation for item in self.acquisition_attempts
        ):
            raise ValueError("transition after world is not reachable from an exact acquisition")
        if len({item.acquisition.acquisition_id for item in self.linked_acquisitions}) != len(self.linked_acquisitions):
            raise ValueError("transition fallback links cannot repeat")
        if len({item.primary_acquisition_id for item in self.linked_acquisitions}) != len(self.linked_acquisitions):
            raise ValueError("transition primary acquisition can have at most one fallback")
        for linked in self.linked_acquisitions:
            primary_execution = next(
                (
                    item
                    for item in self.execution_attempts
                    if item.post_acquisition is not None
                    and item.post_acquisition.acquisition_id == linked.primary_acquisition_id
                ),
                None,
            )
            if primary_execution is None or primary_execution.post_acquisition is None:
                raise ValueError("transition fallback link is not reachable from execution")
            primary = primary_execution.post_acquisition
            if not any(linked.acquisition is item for item in self.acquisition_attempts):
                raise ValueError("transition fallback link is not reachable from execution")
            if (
                primary.status is AcquisitionStatus.ACQUIRED
                and primary.observation is not None
                and primary.observation.observation_id != primary_execution.request.world_observation_id
            ):
                raise ValueError("transition fallback cannot replace a fresh primary acquisition")
            if _identity_index(self.acquisition_attempts, primary) >= _identity_index(
                self.acquisition_attempts, linked.acquisition
            ):
                raise ValueError("transition fallback must follow its primary acquisition")
        if self.evaluation is not None:
            consumed = self.evaluation.consumed_acquisition
            if not any(consumed is item for item in self.acquisition_attempts):
                raise ValueError("transition evaluation acquisition is not reachable")
            if self.evaluation.execution is not None:
                evaluation_primary = self.evaluation.execution.post_acquisition
                is_linked = (
                    any(
                        item.primary_acquisition_id == evaluation_primary.acquisition_id and item.acquisition is consumed
                        for item in self.linked_acquisitions
                    )
                    if evaluation_primary is not None
                    else False
                )
                if consumed is not evaluation_primary and not is_linked:
                    raise ValueError("transition evaluation consumed an unlinked fallback")
        if self.execution_attempts and self.admission is not None:
            selection = (
                self.continuation_admission.selection
                if self.continuation_admission is not None
                else self.admission.selection
            )
            if selection is None or self.execution_attempts[0].request.selection is not selection:
                raise ValueError("first bound request must retain the exact admitted selection")
        task = self.task_evaluation
        if task is not None and task.observation_id != self.after_observation_id:
            raise ValueError("transition task evaluation must match after world")
        if self.before_task_evaluation is not None and (
            self.before_task_evaluation.observation_id != self.before_observation_id
            or task is not None
            and self.before_task_evaluation.task_id != task.task_id
        ):
            raise ValueError("transition before task evaluation lineage mismatch")
        _require_reason_code(self.reason_code)

    @property
    def before_observation_id(self) -> str:
        return self.before_observation.observation_id

    @property
    def after_observation_id(self) -> str:
        return self.after_observation.observation_id

    @property
    def execution(self) -> ExecutionOutcome | None:
        return self.execution_attempts[-1] if self.execution_attempts else None

    @property
    def acquisition(self) -> ObservationAcquisition | None:
        return self.acquisition_attempts[-1] if self.acquisition_attempts else None

    @property
    def intent(self) -> ActionIntent | None:
        return self.execution.request.intent if self.execution is not None else None

    @property
    def request_id(self) -> str:
        return self.execution.request.request_id if self.execution is not None else ""

    @property
    def action_evaluation(self) -> ActionEvaluation | None:
        return self.evaluation.action_evaluation if self.evaluation is not None else None

    @property
    def task_evaluation(self) -> TaskEvaluation | None:
        return (
            self.evaluation.task_evaluation
            if isinstance(self.evaluation, EvaluationOutcome)
            else self.direct_task_evaluation
        )


@dataclass(frozen=True)
class ControlContinuation:
    source_transition_id: str
    execution_attempts: tuple[ExecutionOutcome, ...] = field(repr=False)
    acquisition_attempts: tuple[ObservationAcquisition, ...] = field(repr=False)
    linked_acquisitions: tuple[LinkedAcquisition, ...] = field(repr=False)
    attempt_receipts: tuple[AttemptReceipt, ...]
    after_observation: WorldObservation = field(repr=False)
    evaluation: EvaluationOutcome | EvaluationInterruption | None = field(repr=False)
    direct_task_evaluation: TaskEvaluation | None
    progress: ProgressDelta
    pending_kind: PendingKind
    resulting_status: AgentLoopStatus | None
    reason_code: str
    admission: ActionAdmissionOutcome | None = None
    decision: AgentDecision | None = None

    @property
    def after_observation_id(self) -> str:
        return self.after_observation.observation_id

    @property
    def execution(self) -> ExecutionOutcome | None:
        return self.execution_attempts[-1] if self.execution_attempts else None

    @property
    def acquisition(self) -> ObservationAcquisition | None:
        return self.acquisition_attempts[-1] if self.acquisition_attempts else None

    @property
    def action_evaluation(self) -> ActionEvaluation | None:
        return self.evaluation.action_evaluation if self.evaluation is not None else None

    @property
    def task_evaluation(self) -> TaskEvaluation | None:
        return (
            self.evaluation.task_evaluation
            if isinstance(self.evaluation, EvaluationOutcome)
            else self.direct_task_evaluation
        )


class _FactAccumulator:
    def _initialize_facts(self, state: AgentLoopState, decision: AgentDecision) -> None:
        self._decision = decision
        self._before = state.current_observation
        self._after = state.current_observation
        self._progress_total = state.progress_event_total_count
        self._before_task_evaluation = (
            state.current_task_evaluation
            if state.current_task_evaluation is not None
            and state.current_task_evaluation.observation_id == self._before.observation_id
            else None
        )
        self._executions: list[ExecutionOutcome] = []
        self._acquisitions: list[ObservationAcquisition] = []
        self._linked_acquisitions: list[LinkedAcquisition] = []
        self._attempt_receipts: list[AttemptReceipt] = []
        self._evaluation: EvaluationOutcome | EvaluationInterruption | None = None
        self._direct_task_evaluation: TaskEvaluation | None = None
        self._decision_result = ""
        self._control_feedback: ControlFeedback | None = None
        self._reason_code = ""
        self._resulting_status: AgentLoopStatus | None = None
        self._finalized = False

    def record_execution_receipt(self, receipt: AttemptReceipt, outcome: ExecutionOutcome) -> None:
        self._attempt_receipts.append(receipt)
        self._executions.append(outcome)
        if outcome.result.dispatch_status is not DispatchStatus.NOT_SENT:
            self._direct_task_evaluation = None
        if outcome.post_acquisition is not None:
            self._acquisitions.append(outcome.post_acquisition)

    def record_after(self, observation: WorldObservation) -> None:
        if not isinstance(observation, WorldObservation):
            raise TypeError("control transition after world must be exact")
        self._after = observation

    def record_evaluation(self, outcome: EvaluationOutcome) -> None:
        if self._evaluation is not None:
            raise RuntimeError("control transition already has evaluation authority")
        self._evaluation = outcome
        self._direct_task_evaluation = None

    def record_evaluation_interruption(self, outcome: EvaluationInterruption) -> None:
        if self._evaluation is not None:
            raise RuntimeError("control transition already has evaluation authority")
        self._evaluation = outcome
        self._direct_task_evaluation = None

    def record_evaluations(self, action: ActionEvaluation | None = None, task: TaskEvaluation | None = None) -> None:
        """Retain exact standalone evaluator output outside an EvaluationOutcome trigger."""
        if action is not None:
            raise ValueError("action evaluation must enter through exact EvaluationOutcome")
        if task is not None:
            self._direct_task_evaluation = task

    def record_decision_result(self, value: str) -> None:
        self._decision_result = value

    def record_control_feedback(self, feedback: ControlFeedback) -> None:
        if self._control_feedback is not None:
            raise RuntimeError("control transition already has feedback")
        self._control_feedback = feedback

    def record_acquisition(self, acquisition: ObservationAcquisition) -> None:
        if not isinstance(acquisition, ObservationAcquisition):
            raise TypeError("control acquisition must be exact")
        self._acquisitions.append(acquisition)

    def record_linked_acquisition(self, linked: LinkedAcquisition) -> None:
        from affordance_runtime.agent.observation_control import LinkedAcquisition

        if not isinstance(linked, LinkedAcquisition):
            raise TypeError("control fallback link must be exact")
        self._linked_acquisitions.append(linked)
        if not any(linked.acquisition is item for item in self._acquisitions):
            self._acquisitions.append(linked.acquisition)

    def record_attempt(self, receipt: AttemptReceipt, acquisition: ObservationAcquisition | None = None) -> None:
        self._attempt_receipts.append(receipt)
        if acquisition is not None:
            self.record_acquisition(acquisition)

    def set_reason(self, reason_code: str) -> None:
        _require_reason_code(reason_code)
        self._reason_code = reason_code

    def set_resulting_status(self, status: AgentLoopStatus) -> None:
        self._resulting_status = status

    @property
    def has_execution(self) -> bool:
        return bool(self._executions)

    @property
    def before_observation(self) -> WorldObservation:
        return self._before

    @property
    def reason_code(self) -> str:
        return self._reason_code

    @property
    def has_effectful_execution(self) -> bool:
        return any(item.result.dispatch_status is not DispatchStatus.NOT_SENT for item in self._executions)


class ControlTransitionScope(_FactAccumulator):
    def __init__(self, state: AgentLoopState, decision: AgentDecision) -> None:
        self._initialize_facts(state, decision)
        self._admission: ActionAdmissionOutcome | None = None

    def record_admission(
        self,
        status: AdmissionStatus,
        reason_code: str,
        *,
        selection: AdmittedActionSelection | None = None,
        issue: AdmissionIssue | None = None,
        risk_assessment: RiskAssessment | None = None,
        confirmation_request: ConfirmationRequest | None = None,
    ) -> None:
        self._admission = ActionAdmissionOutcome(
            status, reason_code, selection, issue, risk_assessment, confirmation_request
        )
        self._reason_code = reason_code

    def finalize(self, state: AgentLoopState, outcome: LoopDirective) -> ControlTransition:
        if self._finalized:
            raise RuntimeError("accepted decision scope was already finalized")
        self._finalized = True
        status = self._resulting_status or _outcome_status(outcome)
        sequence = state.control_transition_total_count + 1
        reason = self._reason_code or _default_reason(self._decision, status, self._executions)
        transition = ControlTransition(
            _transition_id(sequence, self._before.observation_id, self._decision.context_id),
            sequence,
            self._before,
            self._decision,
            self._admission,
            tuple(self._executions),
            tuple(self._acquisitions),
            tuple(self._linked_acquisitions),
            tuple(self._attempt_receipts),
            self._after,
            self._evaluation,
            self._direct_task_evaluation,
            _progress_delta(state, self._progress_total),
            _pending_kind(state),
            status,
            reason,
            self._decision_result,
            self._control_feedback,
            self._before_task_evaluation,
        )
        state._append_control_transition(transition)
        if state.pending_confirmation is not None:
            state.pending_confirmation_transition_id = transition.transition_id
        return transition


class ControlContinuationScope(_FactAccumulator):
    def __init__(self, state: AgentLoopState, decision: AgentDecision, source_transition_id: str) -> None:
        if not source_transition_id:
            raise ValueError("confirmation continuation requires its root transition")
        self._source_transition_id = source_transition_id
        self._initialize_facts(state, decision)
        self._admission: ActionAdmissionOutcome | None = None
        self._continuation_decision: AgentDecision | None = None

    def record_continuation_decision(self, decision: AgentDecision) -> None:
        if not isinstance(decision, _DECISION_TYPES):
            raise TypeError("confirmation continuation decision must be typed")
        self._continuation_decision = decision

    def record_admission(
        self,
        status: AdmissionStatus,
        reason_code: str,
        *,
        selection: AdmittedActionSelection | None = None,
        issue: AdmissionIssue | None = None,
        risk_assessment: RiskAssessment | None = None,
        confirmation_request: ConfirmationRequest | None = None,
    ) -> None:
        self._admission = ActionAdmissionOutcome(
            status,
            reason_code,
            selection,
            issue,
            risk_assessment,
            confirmation_request,
        )
        self.set_reason(reason_code)

    def finalize(self, state: AgentLoopState, outcome: LoopDirective) -> ControlContinuation:
        if self._finalized:
            raise RuntimeError("confirmation continuation was already finalized")
        self._finalized = True
        continuation = ControlContinuation(
            self._source_transition_id,
            tuple(self._executions),
            tuple(self._acquisitions),
            tuple(self._linked_acquisitions),
            tuple(self._attempt_receipts),
            self._after,
            self._evaluation,
            self._direct_task_evaluation,
            _progress_delta(state, self._progress_total),
            _pending_kind(state),
            self._resulting_status or _outcome_status(outcome),
            self._reason_code
            or _default_reason(self._decision, self._resulting_status or _outcome_status(outcome), self._executions),
            self._admission,
            self._continuation_decision,
        )
        state._apply_control_continuation(continuation)
        return continuation


def _require_reason_code(value: str) -> None:
    if not _REASON.fullmatch(value):
        raise ValueError("reason_code must be a bounded stable snake-case code")


def _identity_index(values: tuple[object, ...], expected: object) -> int:
    return next(index for index, value in enumerate(values) if value is expected)


def _transition_id(sequence: int, observation_id: str, context_id: str) -> str:
    digest = hashlib.sha256(f"{sequence}\0{observation_id}\0{context_id}".encode()).hexdigest()[:20]
    return f"transition:{sequence}:{digest}"


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


def _default_reason(decision: AgentDecision, status: object, executions: list[ExecutionOutcome]) -> str:
    if executions and executions[-1].result.error is not None:
        return str(executions[-1].result.error)
    decision_name = re.sub(r"(?<!^)(?=[A-Z])", "_", type(decision).__name__).lower()
    return f"{decision_name}_{status or 'continued'}"[:96]
