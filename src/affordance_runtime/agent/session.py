"""In-memory, single-run pause and confirmation continuation state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.result import AgentResult
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.environment import WorldEnvironment

if TYPE_CHECKING:
    from affordance_runtime.agent.loop import AgentLoop


@dataclass
class AgentRunSession:
    agent_loop: AgentLoop
    task: TaskGoal
    environment: WorldEnvironment
    state: AgentLoopState
    observation_count: int = 1
    execution_count: int = 0
    currentness_probe_count: int = 0
    approved_confirmation: ConfirmationRequest | None = field(default=None, repr=False)
    resolved_confirmation_ids: set[str] = field(default_factory=set, repr=False)
    last_result: AgentResult | None = field(default=None, repr=False)

    async def run_until_pause(self) -> AgentResult:
        if self.last_result is not None:
            return self.last_result
        self.last_result = await self.agent_loop._run_session(self)
        return self.last_result

    async def resolve_confirmation(self, decision: ConfirmationDecision) -> AgentResult:
        self.last_result = await self.agent_loop._resolve_confirmation(self, decision)
        return self.last_result

    @property
    def is_terminal(self) -> bool:
        return bool(
            self.last_result
            and self.last_result.status
            in {AgentLoopStatus.DONE, AgentLoopStatus.BLOCKED, AgentLoopStatus.CANCELLED, AgentLoopStatus.FAILED}
        )
