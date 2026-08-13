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
from affordance_runtime.task.aggregate_objective import (
    AggregateDisposition,
    AggregateObjectiveState,
    refresh_aggregate_objective_state,
)
from affordance_runtime.task.frontier import PreparedObjectiveOperation
from affordance_runtime.task.frontier_contracts import ActiveObjective, VerifiedTaskState
from affordance_runtime.task.hypothesis_contracts import (
    HypothesisItemRejection,
    RequirementHypothesisState,
)
from affordance_runtime.task.objective_sequence import (
    ObjectiveSequenceState,
    SequenceDisposition,
    refresh_objective_sequence_state,
)
from affordance_runtime.task.planning_contracts import LocalObjective, TaskPlan
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort, SnapshotScopeEnumerator
from affordance_runtime.task.set_objective import SetDisposition
from affordance_runtime.task.set_objective_state import SetObjectiveState, refresh_set_objective_state
from affordance_runtime.task_action_family_resolution import action_family_value
from affordance_runtime.world.contracts import WorldObservation

MAX_SEEN_ACTION_PAGE_RESULTS = 64
MAX_REQUIREMENT_HYPOTHESIS_PROPOSALS = 4
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
    SEMANTIC_INGRESS = "semantic_ingress"
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
    active_objective: LocalObjective | ActiveObjective | None = None
    active_set_objective: SetObjectiveState | None = None
    active_objective_sequence: ObjectiveSequenceState | None = None
    active_aggregate_objective: AggregateObjectiveState | None = None
    scope_enumerator: ScopeEnumeratorPort = field(default_factory=SnapshotScopeEnumerator, repr=False)
    verified_task_state: VerifiedTaskState | None = None
    requirement_hypotheses: RequirementHypothesisState = field(
        default_factory=RequirementHypothesisState,
    )
    requirement_hypothesis_failure_reason: str = ""
    recent_requirement_hypothesis_rejections: tuple[HypothesisItemRejection, ...] = ()
    requirement_hypothesis_accepted_total_count: int = 0
    requirement_hypothesis_rejected_total_count: int = 0
    requirement_hypothesis_rejection_code_counts: dict[str, int] = field(default_factory=dict)
    requirement_hypothesis_proposal_count: int = 0
    requirement_hypothesis_last_basis: str = ""
    objective_sequence: int = 0
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
    semantic_objective_count: int = 0
    visual_evidence_attempt_keys: tuple[str, ...] = ()

    @property
    def semantic_control_mode(self) -> SemanticControlMode:
        sequence = self.active_objective_sequence
        if sequence is not None:
            if sequence.disposition is SequenceDisposition.READY:
                return SemanticControlMode.MEMBER_EXECUTION
            if sequence.disposition is SequenceDisposition.WAITING_POSTCONDITION:
                return SemanticControlMode.STABILITY_CHECK
            if sequence.disposition is SequenceDisposition.COMPLETE:
                return SemanticControlMode.OBJECTIVE_TRANSITION
            return SemanticControlMode.EVIDENCE_RESOLUTION
        aggregate = self.active_aggregate_objective
        if aggregate is not None:
            if aggregate.disposition is AggregateDisposition.READY:
                return SemanticControlMode.MEMBER_EXECUTION
            if aggregate.disposition is AggregateDisposition.NEED_EFFECT_RESOLUTION:
                return SemanticControlMode.EFFECT_RESOLUTION
            if aggregate.disposition is AggregateDisposition.COMPLETE:
                return SemanticControlMode.OBJECTIVE_TRANSITION
            return SemanticControlMode.EVIDENCE_RESOLUTION
        active = self.active_set_objective
        if active is None:
            return (
                SemanticControlMode.SEMANTIC_INGRESS
                if self.semantic_objective_count == 0
                else SemanticControlMode.OBJECTIVE_TRANSITION
            )
        disposition = active.reduction.disposition
        if disposition in {
            SetDisposition.READY_FOR_NEXT_MEMBER,
            SetDisposition.AGENT_SELECT_NEXT,
        }:
            return SemanticControlMode.MEMBER_EXECUTION
        if disposition is SetDisposition.NEED_EFFECT_RESOLUTION:
            return SemanticControlMode.EFFECT_RESOLUTION
        if disposition is SetDisposition.NEED_STABILITY_CHECK:
            return SemanticControlMode.STABILITY_CHECK
        if disposition is SetDisposition.CERTIFIED:
            return SemanticControlMode.OBJECTIVE_TRANSITION
        return SemanticControlMode.EVIDENCE_RESOLUTION

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
        if (
            self.active_objective_sequence is not None
            and transition.after_observation_id != self.active_objective_sequence.observation_epoch
        ):
            action = transition.action_evaluation
            intent = transition.intent
            acted_entity_id = (
                intent.target_id
                if intent is not None
                and self.active_objective_sequence.active_step is not None
                and action_family_value(intent.semantic_action)
                == self.active_objective_sequence.active_step.action_template.semantic_action
                else ""
            )
            self.active_objective_sequence = refresh_objective_sequence_state(
                self.active_objective_sequence,
                self.current_observation,
                acted_entity_id=acted_entity_id,
                action_status=(action.status if action is not None and acted_entity_id else None),
                effect_evidence_refs=(action.evidence_refs if action is not None and acted_entity_id else ()),
                enumerator=self.scope_enumerator,
            )
        if (
            self.active_aggregate_objective is not None
            and transition.after_observation_id != self.active_aggregate_objective.universe.observation_epoch
        ):
            action = transition.action_evaluation
            intent = transition.intent
            aggregate = self.active_aggregate_objective
            acted_entity_id = (
                intent.target_id
                if intent is not None
                and action_family_value(intent.semantic_action) == aggregate.objective.semantic_action
                else ""
            )
            self.active_aggregate_objective = refresh_aggregate_objective_state(
                aggregate,
                self.current_observation,
                acted_entity_id=acted_entity_id,
                action_status=action.status if action is not None and acted_entity_id else None,
                effect_evidence_refs=(action.evidence_refs if action is not None and acted_entity_id else ()),
                enumerator=self.scope_enumerator,
            )
        if (
            self.active_set_objective is not None
            and transition.after_observation_id != self.active_set_objective.universe.observation_epoch
        ):
            action = transition.action_evaluation
            intent = transition.intent
            settled_members = {
                *self.active_set_objective.candidate_entity_ids,
                *(item.entity_id for item in self.active_set_objective.obligations),
            }
            certified_successor = (
                self.active_set_objective.reduction.disposition is SetDisposition.CERTIFIED
                and intent is not None
                and intent.target_id not in settled_members
            )
            if certified_successor:
                self.progress_revision += 1
                return
            acted_entity_id = (
                intent.target_id
                if intent is not None
                and intent.semantic_action == self.active_set_objective.objective.action_template.semantic_action
                else ""
            )
            self.active_set_objective = refresh_set_objective_state(
                self.active_set_objective,
                self.current_observation,
                acted_entity_id=acted_entity_id,
                action_status=action.status if action is not None and acted_entity_id else None,
                effect_evidence_refs=action.evidence_refs if action is not None and acted_entity_id else (),
                enumerator=self.scope_enumerator,
            )
        self.progress_revision += 1

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

    def set_active_objective(self, objective: LocalObjective | ActiveObjective) -> None:
        if self.active_objective != objective:
            self.active_objective = objective
            self.progress_revision += 1

    def clear_active_objective(self) -> None:
        if self.active_objective is not None:
            self.active_objective = None
            self.progress_revision += 1

    def install_verified_task_state(self, task_state: VerifiedTaskState) -> None:
        if self.verified_task_state != task_state:
            self.verified_task_state = task_state
            self.progress_revision += 1

    def install_requirement_hypotheses(
        self,
        hypotheses: RequirementHypothesisState,
        *,
        failure_reason: str = "",
    ) -> None:
        if self.requirement_hypotheses != hypotheses or self.requirement_hypothesis_failure_reason != failure_reason:
            self.requirement_hypotheses = hypotheses
            self.requirement_hypothesis_failure_reason = failure_reason
            self.progress_revision += 1

    def record_requirement_hypothesis_proposal(self, basis: str) -> None:
        if (
            not basis.strip()
            or len(basis) > 640
            or self.requirement_hypothesis_proposal_count >= MAX_REQUIREMENT_HYPOTHESIS_PROPOSALS
        ):
            raise ValueError("requirement hypothesis proposal budget is invalid")
        self.requirement_hypothesis_proposal_count += 1
        self.requirement_hypothesis_last_basis = basis

    def record_requirement_hypothesis_admission(
        self,
        accepted_count: int,
        rejections: tuple[HypothesisItemRejection, ...],
    ) -> None:
        values = tuple(rejections)
        if (
            type(accepted_count) is not int
            or accepted_count < 0
            or accepted_count + len(values) > 8
            or any(not isinstance(item, HypothesisItemRejection) for item in values)
        ):
            raise ValueError("requirement hypothesis admission outcome is invalid")
        self.requirement_hypothesis_accepted_total_count += accepted_count
        self.requirement_hypothesis_rejected_total_count += len(values)
        for item in values:
            code = item.code.value
            self.requirement_hypothesis_rejection_code_counts[code] = (
                self.requirement_hypothesis_rejection_code_counts.get(code, 0) + 1
            )
        self.recent_requirement_hypothesis_rejections = values
        self.progress_revision += 1

    def commit_objective_operation(self, prepared: PreparedObjectiveOperation) -> None:
        """Commit an already validated operation exactly once against current state."""

        current = self.active_objective if isinstance(self.active_objective, ActiveObjective) else None
        current_id = current.objective_id if current is not None else ""
        if current_id != prepared.expected_active_objective_id:
            raise ValueError("prepared objective operation is stale")
        if prepared.allocated_sequence:
            if prepared.allocated_sequence != self.objective_sequence + 1:
                raise ValueError("prepared objective sequence is stale")
            self.objective_sequence = prepared.allocated_sequence
        if self.active_objective != prepared.next_active_objective:
            self.active_objective = prepared.next_active_objective
            self.progress_revision += 1

    def replace_plan(self, plan: TaskPlan | None) -> None:
        if self.plan != plan:
            self.plan = plan
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
