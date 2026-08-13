"""Thin episode entrypoint; AgentLoop.start owns logical initialization."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.loop import AgentLoop
from affordance_runtime.agent.result import AgentResult
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.task_plan_contracts import TaskPlan
from affordance_runtime.task_spec_authority import AdmittedTaskSpec
from affordance_runtime.world.environment import WorldEnvironment


@dataclass(frozen=True)
class AgentEpisodeRunner:
    agent_loop: AgentLoop

    async def start(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
        *,
        plan: TaskPlan | None = None,
        admitted_task: AdmittedTaskSpec | None = None,
    ) -> AgentRunSession:
        return await self.agent_loop.start(
            task, environment, intent_context, plan=plan, admitted_task=admitted_task
        )

    async def run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
        *,
        plan: TaskPlan | None = None,
        admitted_task: AdmittedTaskSpec | None = None,
    ) -> AgentResult:
        session = await self.start(
            environment, task, intent_context, plan=plan, admitted_task=admitted_task
        )
        return await session.run_until_pause()
