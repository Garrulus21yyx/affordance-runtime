"""Observe/select/bind/execute/reobserve/evaluate target AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.decisions import AskUser, Finish, Reobserve, SelectAction, Stop
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus, Turn
from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionIntent, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import ActionRisk, ActionSpace, WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.view import build_agent_world_view


@dataclass(frozen=True)
class AgentResult:
    status: AgentLoopStatus
    task: TaskGoal
    final_observation: WorldObservation
    turns: tuple[Turn, ...]
    observation_count: int
    execution_count: int
    message: str = ""


@dataclass
class AgentLoop:
    policy: AgentPolicy
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    recent_turn_limit: int = 12

    async def run(self, task: TaskGoal, environment: WorldEnvironment) -> AgentResult:
        current = await environment.observe("initial task grounding")
        state = AgentLoopState(
            current,
            remaining_turns=task.loop_budget.max_turns,
            recent_turn_limit=self.recent_turn_limit,
        )
        observations = 1
        executions = 0
        while state.remaining_turns > 0:
            initial_evaluation = await self.task_evaluator.evaluate(task, state.current_observation)
            if initial_evaluation.status == TaskEvaluationStatus.COMPLETE:
                return _result(AgentLoopStatus.DONE, task, state, observations, executions, initial_evaluation.reason)
            action_space = self.action_space_builder.build(task, state.current_observation)
            decision = await self.policy.decide(
                task,
                build_agent_world_view(state.current_observation),
                action_space,
                state.recent_turns,
                state.plan,
            )
            state.remaining_turns -= 1
            if isinstance(decision, AskUser):
                state.pending_user_question = decision.question
                return _result(AgentLoopStatus.WAITING_USER, task, state, observations, executions, decision.question)
            if isinstance(decision, Stop):
                return _result(AgentLoopStatus.FAILED, task, state, observations, executions, decision.reason)
            if isinstance(decision, Finish):
                state.append_turn(Turn(state.current_observation.observation_id, decision, task_evaluation=initial_evaluation))
                continue
            if isinstance(decision, Reobserve):
                if observations >= task.loop_budget.max_observations:
                    return _observation_budget_result(task, state, observations, executions)
                state.append_turn(Turn(state.current_observation.observation_id, decision))
                state.current_observation = await environment.observe(decision.reason)
                observations += 1
                continue
            outcome = await self._execute_selection(
                task,
                environment,
                state,
                action_space,
                decision,
                can_observe=observations < task.loop_budget.max_observations,
            )
            if isinstance(outcome, AgentResult):
                return _with_counts(outcome, observations + outcome.observation_count, executions + outcome.execution_count)
            state, observed, executed, terminal = outcome
            observations += observed
            executions += executed
            if terminal is not None:
                return _with_counts(terminal, observations, executions)
        return _result(
            AgentLoopStatus.FAILED,
            task,
            state,
            observations,
            executions,
            "agent loop turn budget exhausted",
        )

    async def _execute_selection(
        self,
        task: TaskGoal,
        environment: WorldEnvironment,
        state: AgentLoopState,
        action_space: ActionSpace,
        decision: SelectAction,
        *,
        can_observe: bool,
    ):
        admitted = self._admit_selection(task, state, action_space, decision)
        if isinstance(admitted, AgentResult):
            return admitted
        intent = admitted
        if not can_observe:
            return _observation_budget_result(task, state, 0, 0)
        before = state.current_observation
        try:
            request = self.binder.bind(intent, before)
        except BindingError:
            state.current_observation = await environment.observe("binding unavailable; refresh world")
            return state, 1, 0, None
        if not environment.is_current(request):
            state.append_turn(Turn(before.observation_id, decision, intent=intent, request_id=request.request_id))
            state.current_observation = await environment.observe("stale binding; refresh world")
            return state, 1, 0, None
        result = await environment.execute(request)
        after = await environment.observe("fresh post-action observation")
        if after.observation_id == before.observation_id:
            state.append_turn(
                Turn(before.observation_id, decision, intent, request.request_id, result, after.observation_id)
            )
            terminal = _result(
                AgentLoopStatus.FAILED,
                task,
                state,
                0,
                0,
                "environment reused the post-action observation identity",
            )
            return state, 1, 1, terminal
        if result.request_id != request.request_id or result.backend != request.binding.executor_id:
            state.append_turn(Turn(before.observation_id, decision, intent, request.request_id, result, after.observation_id))
            state.current_observation = after
            terminal = _result(
                AgentLoopStatus.FAILED,
                task,
                state,
                0,
                0,
                "action result lineage does not match the bound request",
            )
            return state, 1, 1, terminal
        action_evaluation = await self.action_evaluator.evaluate(task, before, request, result, after)
        task_evaluation = await self.task_evaluator.evaluate(task, after)
        state.append_turn(
            Turn(
                before.observation_id,
                decision,
                intent,
                request.request_id,
                result,
                after.observation_id,
                action_evaluation,
                task_evaluation,
            )
        )
        state.current_observation = after
        return state, 1, 1, self._post_action_terminal(
            task,
            state,
            request,
            result,
            action_evaluation,
            task_evaluation,
        )

    def _admit_selection(
        self,
        task: TaskGoal,
        state: AgentLoopState,
        action_space: ActionSpace,
        decision: SelectAction,
    ) -> ActionIntent | AgentResult:
        option = action_space.find(decision.action_id)
        if option is None:
            return _result(
                AgentLoopStatus.BLOCKED,
                task,
                state,
                0,
                0,
                "policy selected an action outside the current ActionSpace",
            )
        try:
            self.action_space_builder.validate_parameters(option, dict(decision.parameters))
        except ValueError as exc:
            return _result(AgentLoopStatus.BLOCKED, task, state, 0, 0, str(exc))
        intent = ActionIntent(option.semantic_action, option.target_id, dict(decision.parameters))
        if option.risk != ActionRisk.LOW:
            state.pending_confirmation = intent
            return _result(
                AgentLoopStatus.WAITING_CONFIRMATION,
                task,
                state,
                0,
                0,
                "C1 admits only explicitly low-risk actions",
            )
        if task.risk_profile == RiskProfile.READ_ONLY and option.semantic_action != "read":
            return _result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "read-only task cannot execute effects")
        return intent

    @staticmethod
    def _post_action_terminal(
        task: TaskGoal,
        state: AgentLoopState,
        request: BoundActionRequest,
        result: ActionResult,
        action_evaluation: ActionEvaluation,
        task_evaluation: TaskEvaluation,
    ) -> AgentResult | None:
        if task_evaluation.status == TaskEvaluationStatus.COMPLETE:
            return _result(AgentLoopStatus.DONE, task, state, 0, 0, task_evaluation.reason)
        if result.dispatch_status == DispatchStatus.SENT_UNKNOWN:
            if action_evaluation.status in {
                ActionEvaluationStatus.VERIFIED,
                ActionEvaluationStatus.NOT_VERIFIED,
            }:
                return None
            if action_evaluation.status == ActionEvaluationStatus.REJECTED:
                return _result(
                    AgentLoopStatus.FAILED,
                    task,
                    state,
                    0,
                    0,
                    action_evaluation.reason,
                )
            state.pending_unknown_request = request
            return _result(
                AgentLoopStatus.WAITING_USER,
                task,
                state,
                0,
                0,
                "effect remains unknown after fresh observation; request will not be replayed",
            )
        return None


@dataclass(frozen=True)
class AgentEpisodeRunner:
    agent_loop: AgentLoop

    async def run(self, environment: WorldEnvironment, task: TaskGoal) -> AgentResult:
        await environment.reset(task)
        return await self.agent_loop.run(task, environment)


def _result(
    status: AgentLoopStatus,
    task: TaskGoal,
    state: AgentLoopState,
    observation_count: int,
    execution_count: int,
    message: str,
) -> AgentResult:
    return AgentResult(
        status,
        task,
        state.current_observation,
        state.recent_turns,
        observation_count,
        execution_count,
        message,
    )


def _observation_budget_result(
    task: TaskGoal,
    state: AgentLoopState,
    observation_count: int,
    execution_count: int,
) -> AgentResult:
    return _result(
        AgentLoopStatus.FAILED,
        task,
        state,
        observation_count,
        execution_count,
        "agent loop observation budget exhausted",
    )


def _with_counts(result: AgentResult, observations: int, executions: int) -> AgentResult:
    return AgentResult(
        result.status,
        result.task,
        result.final_observation,
        result.turns,
        observations,
        executions,
        result.message,
    )
