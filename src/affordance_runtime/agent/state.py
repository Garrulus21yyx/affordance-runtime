"""Bounded serial state for the target short loop."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.agent.control_feedback import ControlFeedback
from affordance_runtime.agent.control_transition import ControlContinuation, ControlTransition, Turn
from affordance_runtime.agent.progress_control import ProgressEvent
from affordance_runtime.agent.user_input import UserInputContinuation, UserInputRequest
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.execution.contracts import BoundActionRequest
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


@dataclass
class AgentLoopState:
    current_observation: WorldObservation
    recent_control_transitions: tuple[ControlTransition, ...] = ()
    control_transition_total_count: int = 0
    sent_unknown_total_count: int = 0
    control_transition_kind_counts: dict[str, int] = field(default_factory=dict)
    continued_control_root_ids: tuple[str, ...] = ()
    control_terminal_status: AgentLoopStatus | None = None
    task_revision: int = 1
    progress_revision: int = 0
    pending_revision: int = 0
    pending_user_question: str = ""
    pending_user_request: UserInputRequest | None = None
    pending_confirmation: ConfirmationRequest | None = None
    pending_unknown_request: BoundActionRequest | None = None
    unresolved_observable_request: BoundActionRequest | None = field(default=None, repr=False)
    pending_confirmation_transition_id: str = ""
    latest_control_continuation: ControlContinuation | None = None
    latest_user_input_continuation: UserInputContinuation | None = None
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

    def _apply_user_input_continuation(self, continuation: UserInputContinuation) -> None:
        from affordance_runtime.agent.control_reducer import (
            ApplyUserInputContinuation,
            ControlAccepted,
            ControlReductionError,
            reduce_control,
        )

        reduced = reduce_control(
            self._control_reducer_state(),
            ApplyUserInputContinuation(continuation),
        )
        if not isinstance(reduced, ControlAccepted):
            raise ControlReductionError(reduced)
        self._install_control_reducer_state(reduced.state)
        self.latest_user_input_continuation = continuation

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
            self.pending_user_request = None
            self.pending_revision += 1

    def set_pending_user_request(self, request: UserInputRequest) -> None:
        if not isinstance(request, UserInputRequest):
            raise TypeError("pending user input request must be typed")
        if request.question != self.pending_user_question:
            raise ValueError("pending user input request must match the pending question")
        if request.based_on_task_revision != self.task_revision:
            raise ValueError("pending user input request must match current task revision")
        if self.pending_user_request != request:
            self.pending_user_request = request
            self.pending_revision += 1

    def clear_pending_question(self) -> None:
        if self.pending_user_question or self.pending_user_request is not None:
            self.pending_user_question = ""
            self.pending_user_request = None
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

    def require_unknown_effect_observation(self, request: BoundActionRequest) -> None:
        """Latch SENT uncertainty that can still be resolved by a typed source."""

        if self.unresolved_observable_request != request:
            self.unresolved_observable_request = request
            self.progress_revision += 1

    def clear_unknown_effect_observation(self) -> None:
        if self.unresolved_observable_request is not None:
            self.unresolved_observable_request = None
            self.progress_revision += 1

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
