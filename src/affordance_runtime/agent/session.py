"""In-memory, single-run pause and confirmation continuation state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.accounting import RunAccounting
from affordance_runtime.agent.control_outcome import Terminate
from affordance_runtime.agent.progress_control import ProgressController
from affordance_runtime.agent.result import AgentResult, project_result
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationRequest
from affordance_runtime.task.contracts import TaskGoal
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
    approved_confirmation: ConfirmationRequest | None = field(default=None, repr=False)
    approved_confirmation_transition_id: str = field(default="", repr=False)
    confirmation_continuation_scope: ControlContinuationScope | None = field(
        default=None, repr=False
    )
    resolved_confirmation_ids: set[str] = field(default_factory=set, repr=False)
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

    def _latch_terminal_exception(self, *, cancelled: bool) -> None:
        status = AgentLoopStatus.CANCELLED if cancelled else AgentLoopStatus.FAILED
        reason = "runtime_cancelled" if cancelled else "runtime_exception"
        self.last_result = project_result(self, Terminate(status, reason, reason))

    @property
    def is_terminal(self) -> bool:
        return bool(
            self.last_result
            and self.last_result.status
            in {AgentLoopStatus.DONE, AgentLoopStatus.BLOCKED, AgentLoopStatus.CANCELLED, AgentLoopStatus.FAILED}
        )
