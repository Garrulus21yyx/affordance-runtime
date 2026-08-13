"""Public client lifecycle for the target natural-language Runtime."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.result import AgentResult
from affordance_runtime.agent.runtime import (
    TargetRuntime,
    TargetRuntimeStartOutcome,
    TargetRuntimeUserInputOutcome,
)
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.confirmation.contracts import ConfirmationDecision
from affordance_runtime.task.intake import NaturalLanguageTaskRequest, ReadyTask, TaskIntakeOutcome
from affordance_runtime.world.environment import WorldEnvironment


@dataclass(frozen=True)
class TargetRuntimeRunOutcome:
    """One admitted target session and its first run-until-pause result."""

    intake: TaskIntakeOutcome
    session: AgentRunSession | None = None
    result: AgentResult | None = None

    def __post_init__(self) -> None:
        admitted = isinstance(self.intake, ReadyTask)
        executable = self.session is not None and self.result is not None
        if admitted != executable:
            raise ValueError("target client run must align intake, session, and result")

    @property
    def started(self) -> bool:
        return self.session is not None


@dataclass(frozen=True)
class TargetRuntimeClient:
    """Execute target requests without exposing loop construction to callers."""

    runtime: TargetRuntime

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, TargetRuntime):
            raise TypeError("TargetRuntimeClient requires a TargetRuntime")

    async def start(
        self,
        environment: WorldEnvironment,
        request: NaturalLanguageTaskRequest,
    ) -> TargetRuntimeStartOutcome:
        return await self.runtime.start_request(environment, request)

    async def run(
        self,
        environment: WorldEnvironment,
        request: NaturalLanguageTaskRequest,
    ) -> TargetRuntimeRunOutcome:
        started = await self.start(environment, request)
        if started.session is None:
            return TargetRuntimeRunOutcome(started.intake)
        result = await started.session.run_until_pause()
        return TargetRuntimeRunOutcome(started.intake, started.session, result)

    async def submit_user_input(
        self,
        session: AgentRunSession,
        input_request_id: str,
        request: NaturalLanguageTaskRequest,
    ) -> TargetRuntimeUserInputOutcome:
        return await self.runtime.submit_user_input(session, input_request_id, request)

    async def resolve_confirmation(
        self,
        session: AgentRunSession,
        decision: ConfirmationDecision,
    ) -> AgentResult:
        return await session.resolve_confirmation(decision)
