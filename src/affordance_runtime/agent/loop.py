"""Short observe/act/reobserve/evaluate loop with no global controller state."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.policy import AgentPolicy, LoopPolicy, TaskEvaluator
from affordance_runtime.agent.types import (
    AgentLoopStatus,
    AgentResult,
    AgentTurn,
    LoopDecisionKind,
    TaskGoal,
)
from affordance_runtime.environment_port import EnvironmentPort, ObservationRequest


@dataclass
class AgentLoop:
    policy: AgentPolicy
    evaluator: TaskEvaluator
    loop_policy: LoopPolicy = field(default_factory=LoopPolicy)

    async def run(self, goal: TaskGoal, environment: EnvironmentPort) -> AgentResult:
        current = await environment.observe(ObservationRequest("initial task grounding"))
        observations = 1
        executions = 0
        consecutive_unverified = 0
        turns: list[AgentTurn] = []

        for _ in range(goal.max_steps):
            decision = await self.policy.decide(goal, current, tuple(turns))
            if decision.kind == LoopDecisionKind.DONE:
                return self._result(AgentLoopStatus.DONE, goal, current, turns, observations, executions, decision.reason)
            if decision.kind == LoopDecisionKind.ASK_USER:
                return self._result(
                    AgentLoopStatus.WAITING_USER,
                    goal,
                    current,
                    turns,
                    observations,
                    executions,
                    decision.user_prompt,
                )
            if decision.kind == LoopDecisionKind.STOP:
                return self._result(
                    AgentLoopStatus.FAILED, goal, current, turns, observations, executions, decision.reason
                )
            if decision.kind == LoopDecisionKind.REPLAN:
                turns.append(AgentTurn(decision, current))
                continue
            if decision.kind == LoopDecisionKind.REOBSERVE:
                turns.append(AgentTurn(decision, current))
                current = await environment.observe(ObservationRequest(decision.reason))
                observations += 1
                continue

            assert decision.contract is not None
            if not environment.is_current(decision.contract):
                turns.append(AgentTurn(decision, current))
                current = await environment.observe(ObservationRequest("stale binding requires fresh grounding"))
                observations += 1
                continue
            receipt = await environment.execute(decision.contract)
            executions += 1
            after = await environment.observe(
                ObservationRequest("fresh post-action observation for independent evaluation")
            )
            observations += 1
            if current.snapshot_id and after.snapshot_id == current.snapshot_id:
                turns.append(AgentTurn(decision, current, receipt, after))
                return self._result(
                    AgentLoopStatus.FAILED,
                    goal,
                    after,
                    turns,
                    observations,
                    executions,
                    "environment did not provide a fresh post-action observation",
                )
            evaluation = await self.evaluator.evaluate(goal, current, receipt, after)
            turns.append(AgentTurn(decision, current, receipt, after, evaluation))
            current = after
            consecutive_unverified = 0 if evaluation.action_verified else consecutive_unverified + 1
            directive = self.loop_policy.after_action(
                receipt,
                evaluation,
                consecutive_unverified=consecutive_unverified,
            )
            if directive == LoopDecisionKind.DONE:
                return self._result(
                    AgentLoopStatus.DONE, goal, current, turns, observations, executions, evaluation.reason
                )
            if directive == LoopDecisionKind.ASK_USER:
                return self._result(
                    AgentLoopStatus.WAITING_USER,
                    goal,
                    current,
                    turns,
                    observations,
                    executions,
                    evaluation.user_prompt,
                )
            if directive == LoopDecisionKind.STOP:
                return self._result(
                    AgentLoopStatus.FAILED, goal, current, turns, observations, executions, evaluation.reason
                )
            if directive == LoopDecisionKind.REOBSERVE:
                current = await environment.observe(ObservationRequest("continue after verified local progress"))
                observations += 1

        return self._result(
            AgentLoopStatus.FAILED,
            goal,
            current,
            turns,
            observations,
            executions,
            "agent loop step budget exhausted",
        )

    @staticmethod
    def _result(
        status: AgentLoopStatus,
        goal: TaskGoal,
        observation,
        turns: list[AgentTurn],
        observation_count: int,
        execution_count: int,
        message: str,
    ) -> AgentResult:
        return AgentResult(
            status,
            goal,
            observation,
            tuple(turns),
            observation_count,
            execution_count,
            message,
        )


@dataclass(frozen=True)
class AgentEpisodeRunner:
    agent_loop: AgentLoop

    async def run(self, environment: EnvironmentPort, goal: TaskGoal) -> AgentResult:
        await environment.reset(goal)
        return await self.agent_loop.run(goal, environment)
