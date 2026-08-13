"""Bounded serial state for the target short loop."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.agent.control_feedback import ControlFeedback
from affordance_runtime.agent.control_transition import ControlContinuation, ControlTransition, Turn
from affordance_runtime.agent.progress_control import ProgressEvent
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.task.aggregate_objective import AggregateDisposition, AggregateObjectiveState
from affordance_runtime.task.execution_control import (
    refresh_step_execution,
    step_execution_observation_id,
)
from affordance_runtime.task.objective_sequence import ObjectiveSequenceState, SequenceDisposition
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort, SnapshotScopeEnumerator
from affordance_runtime.task.set_objective import SetDisposition
from affordance_runtime.task.set_objective_state import SetObjectiveState
from affordance_runtime.task.step_execution import StepExecutionState, materialize_step_execution
from affordance_runtime.task_plan_contracts import TaskPlan
from affordance_runtime.task_plan_progress import TaskProgress
from affordance_runtime.world.contracts import WorldObservation

MAX_SEEN_ACTION_PAGE_RESULTS = 64
_SEMANTIC_DIGEST = re.compile(r"[0-9a-f]{64}")


def _require_semantic_digest(value: object) -> str:
    if not isinstance(value, str) or _SEMANTIC_DIGEST.fullmatch(value) is None:
        raise ValueError("control semantic digest must be canonical SHA-256")
    return value


class AgentLoopStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SemanticControlMode(StrEnum):
    EVIDENCE_RESOLUTION = "evidence_resolution"
    MEMBER_EXECUTION = "member_execution"
    EFFECT_RESOLUTION = "effect_resolution"
    STABILITY_CHECK = "stability_check"
    OBJECTIVE_TRANSITION = "objective_transition"


@dataclass
class AgentLoopState:
    current_observation: WorldObservation
    recent_control_transitions: tuple[ControlTransition, ...] = ()
    control_transition_total_count: int = 0
    sent_unknown_total_count: int = 0
    control_transition_kind_counts: dict[str, int] = field(default_factory=dict)
    continued_control_root_ids: tuple[str, ...] = ()
    control_terminal_status: AgentLoopStatus | None = None
    plan: TaskPlan | None = None
    task_progress: TaskProgress | None = None
    task_spec_identity: str = ""
    active_step_execution: StepExecutionState | None = None
    scope_enumerator: ScopeEnumeratorPort = field(default_factory=SnapshotScopeEnumerator, repr=False)
    task_revision: int = 1
    progress_revision: int = 0
    pending_revision: int = 0
    pending_user_question: str = ""
    pending_confirmation: ConfirmationRequest | None = None
    pending_unknown_request: BoundActionRequest | None = None
    pending_confirmation_transition_id: str = ""
    latest_control_continuation: ControlContinuation | None = None
    current_task_evaluation: TaskEvaluation | None = field(default=None, repr=False)
    remaining_turns: int = 20
    final_result: dict[str, object] = field(default_factory=dict)
    recent_progress_events: tuple[ProgressEvent, ...] = ()
    progress_event_total_count: int = 0
    recent_turn_limit: int = 12
    progress_event_limit: int = 3
    control_feedback_scope_digest: str = ""
    consumed_control_issue_digests: tuple[str, ...] = ()
    seen_action_page_result_digests: tuple[str, ...] = ()
    pending_control_feedback: ControlFeedback | None = None
    control_feedback_total_count: int = 0
    control_feedback_delivery_total_count: int = 0
    control_repetition_total_count: int = 0
    control_issue_consumption_total_count: int = 0
    observation_cursor: str = ""
    semantic_control_required: bool = False
    visual_evidence_attempt_keys: tuple[str, ...] = ()

    @property
    def semantic_control_mode(self) -> SemanticControlMode:
        active = self.active_step_execution
        if isinstance(active, ObjectiveSequenceState):
            if active.disposition is SequenceDisposition.READY:
                return SemanticControlMode.MEMBER_EXECUTION
            if active.disposition is SequenceDisposition.WAITING_POSTCONDITION:
                return SemanticControlMode.STABILITY_CHECK
            if active.disposition is SequenceDisposition.COMPLETE:
                return SemanticControlMode.OBJECTIVE_TRANSITION
            return SemanticControlMode.EVIDENCE_RESOLUTION
        if isinstance(active, AggregateObjectiveState):
            if active.disposition is AggregateDisposition.READY:
                return SemanticControlMode.MEMBER_EXECUTION
            if active.disposition is AggregateDisposition.NEED_EFFECT_RESOLUTION:
                return SemanticControlMode.EFFECT_RESOLUTION
            if active.disposition is AggregateDisposition.COMPLETE:
                return SemanticControlMode.OBJECTIVE_TRANSITION
            return SemanticControlMode.EVIDENCE_RESOLUTION
        if isinstance(active, SetObjectiveState):
            if active.reduction.disposition in {
                SetDisposition.READY_FOR_NEXT_MEMBER,
                SetDisposition.AGENT_SELECT_NEXT,
            }:
                return SemanticControlMode.MEMBER_EXECUTION
            if active.reduction.disposition is SetDisposition.NEED_EFFECT_RESOLUTION:
                return SemanticControlMode.EFFECT_RESOLUTION
            if active.reduction.disposition is SetDisposition.NEED_STABILITY_CHECK:
                return SemanticControlMode.STABILITY_CHECK
            if active.reduction.disposition is SetDisposition.CERTIFIED:
                return SemanticControlMode.OBJECTIVE_TRANSITION
            return SemanticControlMode.EVIDENCE_RESOLUTION
        return SemanticControlMode.OBJECTIVE_TRANSITION

    @property
    def recent_turns(self) -> tuple[Turn, ...]:
        return tuple(item.as_turn() for item in self.recent_control_transitions)

    def _append_control_transition(self, transition: ControlTransition) -> None:
        from affordance_runtime.agent.control_reducer import (
            AppendRoot,
            ControlAccepted,
            ControlReductionError,
            reduce_control,
        )

        reduced = reduce_control(
            self._control_reducer_state(),
            AppendRoot(transition, self.recent_turn_limit),
        )
        if not isinstance(reduced, ControlAccepted):
            raise ControlReductionError(reduced)
        self._install_control_reducer_state(reduced.state)
        execution = self.active_step_execution
        if execution is not None and transition.after_observation_id != step_execution_observation_id(execution):
            action = transition.action_evaluation
            intent = transition.intent
            self.active_step_execution = refresh_step_execution(
                execution,
                self.current_observation,
                acted_entity_id=intent.target_id if intent is not None else "",
                semantic_action=intent.semantic_action if intent is not None else "",
                action_status=action.status if action is not None else None,
                effect_evidence_refs=action.evidence_refs if action is not None else (),
                enumerator=self.scope_enumerator,
            )
            self.advance_completed_plan_steps()
        self.progress_revision += 1

    def install_plan(self, plan: TaskPlan, *, task_spec_identity: str) -> None:
        """Install one admitted plan and materialize only its active step."""

        if not task_spec_identity.strip():
            raise ValueError("AgentLoop plan requires admitted TaskSpec identity")
        if self.plan is not None or self.task_progress is not None or self.active_step_execution is not None:
            raise ValueError("AgentLoop plan can only be installed once")
        if not plan.steps or any(step.execution is None for step in plan.steps):
            raise ValueError("every semantic AgentLoop step requires one execution contract")
        self.plan = plan
        self.task_spec_identity = task_spec_identity
        self.task_progress = TaskProgress()
        self._materialize_active_plan_step()
        self.advance_completed_plan_steps()
        self.progress_revision += 1

    def _materialize_active_plan_step(self) -> None:
        if self.plan is None or self.task_progress is None:
            self.active_step_execution = None
            return
        step_id = self.task_progress.activate_next(self.plan)
        if not step_id:
            self.active_step_execution = None
            return
        step = self.plan.step(step_id)
        if step is None or step.execution is None:
            raise ValueError("active TaskPlan step has no execution contract")
        self.active_step_execution = materialize_step_execution(
            step.step_id,
            step.execution,
            self.current_observation,
            enumerator=self.scope_enumerator,
        )

    def advance_completed_plan_steps(self) -> bool:
        """Advance only from reducer-certified active steps."""

        changed = False
        while self._advance_one_completed_plan_step():
            changed = True
        return changed

    def _advance_one_completed_plan_step(self) -> bool:
        active = self.active_step_execution
        if self.plan is None or self.task_progress is None or active is None:
            return False
        complete = bool(
            isinstance(active, ObjectiveSequenceState) and active.disposition is SequenceDisposition.COMPLETE
            or isinstance(active, AggregateObjectiveState) and active.disposition is AggregateDisposition.COMPLETE
            or isinstance(active, SetObjectiveState) and active.reduction.disposition is SetDisposition.CERTIFIED
        )
        if not complete:
            return False
        evidence_refs = (
            active.effect_evidence_refs
            if isinstance(active, ObjectiveSequenceState | AggregateObjectiveState)
            else active.certificate.closure_evidence_refs
            if active.certificate is not None
            else ()
        )
        step_id = self.task_progress.active_step_id
        if not step_id:
            raise ValueError("completed execution has no active TaskPlan step")
        step = self.plan.step(step_id)
        if step is None:
            raise ValueError("active TaskPlan step is missing")
        self.task_progress.complete(
            plan=self.plan,
            step_id=step_id,
            criterion_ids=tuple(item.criterion_id for item in step.completion_criteria),
            evidence_refs=tuple(evidence_refs),
            state_version=self.progress_revision,
        )
        self.active_step_execution = None
        self._materialize_active_plan_step()
        return True

    def _apply_control_continuation(self, continuation: ControlContinuation) -> None:
        from affordance_runtime.agent.control_reducer import (
            ApplyContinuation,
            ControlAccepted,
            ControlReductionError,
            reduce_control,
        )

        reduced = reduce_control(
            self._control_reducer_state(),
            ApplyContinuation(continuation),
        )
        if not isinstance(reduced, ControlAccepted):
            raise ControlReductionError(reduced)
        self._install_control_reducer_state(reduced.state)

    def _control_reducer_state(self):
        from affordance_runtime.agent.control_reducer import ControlState

        return ControlState(
            self.recent_control_transitions,
            self.control_transition_total_count,
            tuple(sorted(self.control_transition_kind_counts.items())),
            self.sent_unknown_total_count,
            self.continued_control_root_ids,
            str(self.control_terminal_status or ""),
        )

    def _install_control_reducer_state(self, reduced) -> None:
        self.recent_control_transitions = reduced.recent_transitions
        self.control_transition_total_count = reduced.total_count
        self.control_transition_kind_counts = dict(reduced.kind_counts)
        self.sent_unknown_total_count = reduced.sent_unknown_total_count
        self.continued_control_root_ids = reduced.continued_root_ids
        self.control_terminal_status = AgentLoopStatus(reduced.terminal_status) if reduced.terminal_status else None

    def _append_progress_event(self, event: ProgressEvent) -> None:
        self.recent_progress_events = (
            *self.recent_progress_events,
            event,
        )[-self.progress_event_limit :]
        self.progress_event_total_count += 1
        self.progress_revision += 1

    def set_pending_question(self, question: str) -> None:
        if self.pending_user_question != question:
            self.pending_user_question = question
            self.pending_revision += 1

    def clear_pending_question(self) -> None:
        if self.pending_user_question:
            self.pending_user_question = ""
            self.pending_revision += 1

    def set_pending_confirmation(self, confirmation: ConfirmationRequest) -> None:
        if self.pending_confirmation != confirmation:
            self.pending_confirmation = confirmation
            self.pending_revision += 1

    def clear_pending_confirmation(self) -> None:
        if self.pending_confirmation is not None:
            self.pending_confirmation = None
            self.pending_confirmation_transition_id = ""
            self.pending_revision += 1

    def set_pending_unknown_effect(self, request: BoundActionRequest) -> None:
        if self.pending_unknown_request != request:
            self.pending_unknown_request = request
            self.pending_revision += 1

    def clear_pending_unknown_effect(self) -> None:
        if self.pending_unknown_request is not None:
            self.pending_unknown_request = None
            self.pending_revision += 1

    def install_control_feedback(
        self,
        feedback: ControlFeedback,
        issue_digests: tuple[str, ...],
    ) -> None:
        if not isinstance(feedback, ControlFeedback):
            raise TypeError("pending feedback must be typed")
        if len(issue_digests) > 2 or len(set(issue_digests)) != len(issue_digests):
            raise ValueError("control issue budget state is invalid")
        prior = (
            self.consumed_control_issue_digests if self.control_feedback_scope_digest == feedback.scope_digest else ()
        )
        if feedback.consumes_issue_budget and feedback.issue_digest not in prior:
            self.control_issue_consumption_total_count += 1
        self.control_feedback_scope_digest = feedback.scope_digest
        self.consumed_control_issue_digests = tuple(issue_digests)
        self.pending_control_feedback = feedback
        self.control_feedback_total_count += 1
        self.pending_revision += 1

    def consume_control_feedback_for_policy(self) -> ControlFeedback | None:
        feedback = self.pending_control_feedback
        if feedback is not None:
            self.pending_control_feedback = None
            self.control_feedback_delivery_total_count += 1
            self.pending_revision += 1
        return feedback

    def begin_control_epoch(
        self,
        scope_digest: str,
        initial_page_result_digest: str = "",
    ) -> bool:
        """Install an identity-free epoch and seed its bounded page-result set."""

        scope_digest = _require_semantic_digest(scope_digest)
        if initial_page_result_digest:
            initial_page_result_digest = _require_semantic_digest(
                initial_page_result_digest,
            )
        changed = self.control_feedback_scope_digest != scope_digest
        if changed:
            self.control_feedback_scope_digest = scope_digest
            self.consumed_control_issue_digests = ()
            self.seen_action_page_result_digests = ()
            self.pending_control_feedback = None
            self.pending_revision += 1
        if initial_page_result_digest and not self.seen_action_page_result_digests:
            self.seen_action_page_result_digests = (initial_page_result_digest,)
        return changed

    def record_action_page_result(self, result_digest: str) -> bool:
        """Return true exactly once for each bounded result within an epoch."""

        result_digest = _require_semantic_digest(result_digest)
        if result_digest in self.seen_action_page_result_digests:
            return False
        if len(self.seen_action_page_result_digests) >= MAX_SEEN_ACTION_PAGE_RESULTS:
            return False
        self.seen_action_page_result_digests = (
            *self.seen_action_page_result_digests,
            result_digest,
        )
        changed = bool(self.consumed_control_issue_digests or self.pending_control_feedback is not None)
        self.consumed_control_issue_digests = ()
        self.pending_control_feedback = None
        if changed:
            self.pending_revision += 1
        return True

    def clear_control_issue_budget(self) -> None:
        changed = bool(
            self.control_feedback_scope_digest
            or self.consumed_control_issue_digests
            or self.seen_action_page_result_digests
            or self.pending_control_feedback is not None
        )
        self.control_feedback_scope_digest = ""
        self.consumed_control_issue_digests = ()
        self.seen_action_page_result_digests = ()
        self.pending_control_feedback = None
        if changed:
            self.pending_revision += 1

    def record_control_repetition(self) -> None:
        self.control_repetition_total_count += 1

    def install_observation(self, observation: WorldObservation) -> bool:
        """Install fresh identity and clear D state only for public semantic gain."""

        from affordance_runtime.world.public_semantic_digest import (
            public_world_semantic_digest,
        )

        changed = public_world_semantic_digest(observation) != public_world_semantic_digest(self.current_observation)
        snapshot_changed = observation.observation_id != self.current_observation.observation_id
        self.current_observation = observation
        self.current_task_evaluation = None
        if snapshot_changed:
            self.observation_cursor = ""
        if changed:
            self.clear_control_issue_budget()
        return changed

    def set_observation_cursor(self, cursor: str) -> None:
        if not cursor.strip() or len(cursor) > 512:
            raise ValueError("observation cursor must be a bounded opaque value")
        self.observation_cursor = cursor
