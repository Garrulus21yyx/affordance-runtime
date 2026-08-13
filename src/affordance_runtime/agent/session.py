"""In-memory, single-run pause and confirmation continuation state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.accounting import RunAccounting
from affordance_runtime.agent.control_outcome import Terminate
from affordance_runtime.agent.progress_control import ProgressController
from affordance_runtime.agent.result import AgentResult, project_result
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.agent.user_input import (
    UserInputContinuation,
    UserInputResumed,
    UserInputResumeOutcome,
    UserInputResumeRejected,
    UserInputResumeRejectionCode,
    user_input_revision_rejection,
)
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import ReadyTask
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.environment import WorldEnvironment

if TYPE_CHECKING:
    from affordance_runtime.agent.control_transition import ControlContinuationScope
    from affordance_runtime.agent.loop import AgentLoop
    from affordance_runtime.model_boundary.context import AgentContext
    from affordance_runtime.world.action_paging import InternalActionPage
    from affordance_runtime.world.contracts import ActionSpace


@dataclass
class AgentRunSession:
    agent_loop: AgentLoop
    task: TaskGoal
    environment: WorldEnvironment
    state: AgentLoopState
    intent_context: IntentContext | None = None
    accounting: RunAccounting = field(default_factory=RunAccounting)
    pending_runtime_failure: RuntimeFailure | None = None
    approved_confirmation: ConfirmationRequest | None = field(default=None, repr=False)
    approved_confirmation_transition_id: str = field(default="", repr=False)
    confirmation_continuation_scope: ControlContinuationScope | None = field(
        default=None, repr=False
    )
    resolved_confirmation_ids: set[str] = field(default_factory=set, repr=False)
    resolved_user_input_request_ids: set[str] = field(default_factory=set, repr=False)
    last_result: AgentResult | None = field(default=None, repr=False)
    current_context_snapshot: AgentContext | None = field(default=None, repr=False)
    consumed_context_id: str = field(default="", repr=False)
    context_generation: int = field(default=0, repr=False)
    current_action_space: ActionSpace | None = field(default=None, repr=False)
    current_action_page: InternalActionPage | None = field(default=None, repr=False)
    progress_controller: ProgressController = field(default_factory=ProgressController, repr=False)

    @property
    def observation_count(self) -> int:
        return self.accounting.observation_attempts

    @property
    def execution_count(self) -> int:
        return self.accounting.execution_attempts

    @property
    def currentness_probe_count(self) -> int:
        return self.accounting.currentness_probes

    @property
    def waited_ms(self) -> int:
        return self.accounting.waited_ms

    def next_context_generation(self) -> int:
        self.context_generation += 1
        return self.context_generation

    def snapshot_partial_episode(self):
        from affordance_runtime.agent.session_snapshot import snapshot_partial_episode

        return snapshot_partial_episode(self)

    async def run_until_pause(self) -> AgentResult:
        if self.last_result is not None:
            return self.last_result
        try:
            self.last_result = await self.agent_loop._run_session(self)
        except asyncio.CancelledError:
            self._latch_terminal_exception(cancelled=True)
            raise
        except Exception:
            self._latch_terminal_exception(cancelled=False)
            raise
        return self.last_result

    async def resolve_confirmation(self, decision: ConfirmationDecision) -> AgentResult:
        if self.is_terminal:
            assert self.last_result is not None
            return self.last_result
        if self.state.pending_confirmation is None:
            if self.last_result is not None:
                return self.last_result
            self.last_result = project_result(
                self,
                Terminate(
                    AgentLoopStatus.BLOCKED,
                    "invalid_confirmation_decision",
                    "no confirmation is pending",
                ),
            )
            return self.last_result
        try:
            self.last_result = await self.agent_loop._resolve_confirmation(self, decision)
        except asyncio.CancelledError:
            self._latch_terminal_exception(cancelled=True)
            raise
        except Exception:
            self._latch_terminal_exception(cancelled=False)
            raise
        return self.last_result

    async def resume_user_input(
        self,
        input_request_id: str,
        admitted: ReadyTask,
    ) -> UserInputResumeOutcome:
        """Apply one admitted consecutive task revision and continue this session."""

        if not isinstance(admitted, ReadyTask):
            raise TypeError("user input continuation requires an admitted ReadyTask")
        if input_request_id in self.resolved_user_input_request_ids:
            return UserInputResumeRejected(UserInputResumeRejectionCode.ALREADY_SUBMITTED)
        pending = self.state.pending_user_request
        if self.is_terminal:
            return UserInputResumeRejected(UserInputResumeRejectionCode.TERMINAL_SESSION, pending)
        rejection = user_input_revision_rejection(
            pending,
            submitted_request_id=input_request_id,
            current_task=self.task,
            current_task_revision=self.state.task_revision,
            proposed_task=admitted.task,
        )
        if rejection is not None:
            return UserInputResumeRejected(rejection, pending)
        assert pending is not None
        revise_task = getattr(self.environment, "revise_task", None)
        if not callable(revise_task):
            return UserInputResumeRejected(
                UserInputResumeRejectionCode.ENVIRONMENT_REVISION_UNSUPPORTED,
                pending,
            )
        continuation = UserInputContinuation(
            input_request_id,
            pending.source_transition_id,
            admitted.task.task_id,
            self.state.task_revision,
            admitted.task.revision,
        )
        try:
            await revise_task(admitted.task)
        except asyncio.CancelledError:
            raise
        except Exception:
            return UserInputResumeRejected(
                UserInputResumeRejectionCode.ENVIRONMENT_REVISION_FAILED,
                pending,
            )

        self.state._apply_user_input_continuation(continuation)
        self.resolved_user_input_request_ids.add(input_request_id)
        self.task = admitted.task
        self.intent_context = admitted.intent_context
        self._invalidate_for_task_revision(admitted.task.revision)
        self.last_result = None
        return UserInputResumed(await self.run_until_pause())

    def _invalidate_for_task_revision(self, revision: int) -> None:
        """Invalidate every task-relative projection while retaining physical run facts."""

        state = self.state
        state.clear_pending_question()
        state.task_revision = revision
        state.current_task_evaluation = None
        state.local_objective_state = None
        state.local_objective_not_required_revision = 0
        state.recent_progress_events = ()
        state.progress_revision += 1
        state.pending_control_feedback = None
        state.control_feedback_scope_digest = ""
        state.consumed_control_issue_digests = ()
        state.seen_action_page_result_digests = ()
        state.observation_cursor = ""
        state.visual_evidence_attempt_keys = ()
        state.remaining_turns = min(state.remaining_turns, self.task.loop_budget.max_turns)
        self.current_context_snapshot = None
        self.consumed_context_id = ""
        self.current_action_space = None
        self.current_action_page = None
        self.progress_controller.reset()

    def _latch_terminal_exception(
        self, *, cancelled: bool,
    ) -> None:
        status = AgentLoopStatus.CANCELLED if cancelled else AgentLoopStatus.FAILED
        reason = "runtime_cancelled" if cancelled else "runtime_exception"
        failure = self.pending_runtime_failure
        self.pending_runtime_failure = None
        self.last_result = project_result(self, Terminate(
            status,
            reason,
            reason,
            failure_stage=failure.stage if failure else None,
            failure_kind=failure.kind if failure else None,
            exception_class=failure.exception_class if failure else "",
        ), runtime_failure=failure)

    @property
    def is_terminal(self) -> bool:
        return bool(
            self.last_result
            and self.last_result.status
            in {AgentLoopStatus.DONE, AgentLoopStatus.BLOCKED, AgentLoopStatus.CANCELLED, AgentLoopStatus.FAILED}
        )
