"""In-memory, single-run pause and confirmation continuation state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.progress_control import ProgressController
from affordance_runtime.agent.result import AgentResult
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
    observation_count: int = 1
    execution_count: int = 0
    currentness_probe_count: int = 0
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
    waited_ms: int = 0
    progress_controller: ProgressController = field(default_factory=ProgressController, repr=False)

    def next_context_generation(self) -> int:
        self.context_generation += 1
        return self.context_generation

    def snapshot_partial_episode(self):
        from affordance_runtime.agent.session_snapshot import snapshot_partial_episode

        return snapshot_partial_episode(self)

    async def run_until_pause(self) -> AgentResult:
        if self.last_result is not None:
            return self.last_result
        self.last_result = await self.agent_loop._run_session(self)
        return self.last_result

    async def resolve_confirmation(self, decision: ConfirmationDecision) -> AgentResult:
        if self.is_terminal:
            assert self.last_result is not None
            return self.last_result
        self.last_result = await self.agent_loop._resolve_confirmation(self, decision)
        return self.last_result

    @property
    def is_terminal(self) -> bool:
        return bool(
            self.last_result
            and self.last_result.status
            in {AgentLoopStatus.DONE, AgentLoopStatus.BLOCKED, AgentLoopStatus.CANCELLED, AgentLoopStatus.FAILED}
        )
