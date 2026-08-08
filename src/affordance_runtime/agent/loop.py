"""Observe/select/bind/execute/reobserve/evaluate target AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.decisions import AskUser, Finish, Reobserve, SelectAction, Stop
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.agent.result import (
    AgentResult,
    add_counts,
    build_result,
    observation_budget_result,
)
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
from affordance_runtime.world.contracts import (
    ActionRisk,
    ActionSpace,
    AdmittedActionSelection,
)
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.view import build_agent_world_view


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
        probes = 0
        while state.remaining_turns > 0:
            initial_evaluation = await self.task_evaluator.evaluate(task, state.current_observation)
            if initial_evaluation.status == TaskEvaluationStatus.COMPLETE:
                return build_result(AgentLoopStatus.DONE, task, state, observations, executions, initial_evaluation.reason, probes)
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
                return build_result(AgentLoopStatus.WAITING_USER, task, state, observations, executions, decision.question, probes)
            if isinstance(decision, Stop):
                return build_result(AgentLoopStatus.FAILED, task, state, observations, executions, decision.reason, probes)
            if isinstance(decision, Finish):
                state.append_turn(Turn(state.current_observation.observation_id, decision, task_evaluation=initial_evaluation))
                continue
            if isinstance(decision, Reobserve):
                if observations >= task.loop_budget.max_observations:
                    return observation_budget_result(task, state, observations, executions)
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
                return add_counts(
                    outcome,
                    observations + outcome.observation_count,
                    executions + outcome.execution_count,
                    probes + outcome.currentness_probe_count,
                )
            state, observed, executed, probed, terminal = outcome
            observations += observed
            executions += executed
            probes += probed
            if terminal is not None:
                return add_counts(terminal, observations, executions, probes)
        return build_result(
            AgentLoopStatus.FAILED,
            task,
            state,
            observations,
            executions,
            "agent loop turn budget exhausted",
            probes,
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
        selection = admitted
        if not can_observe:
            return observation_budget_result(task, state, 0, 0)
        before = state.current_observation
        try:
            request = self.binder.bind(selection, before)
        except BindingError:
            state.current_observation = await environment.observe("binding unavailable; refresh world")
            return state, 1, 0, 0, None
        intent = request.intent
        result = await environment.execute(request)
        probed = _probe_count(result)
        if result.request_id != request.request_id or result.backend != request.binding.executor_id:
            state.append_turn(Turn(before.observation_id, decision, intent, request.request_id, result))
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "action result lineage mismatch")
            executed = int(result.dispatch_status != DispatchStatus.NOT_SENT)
            return state, 0, executed, probed, terminal
        if result.dispatch_status == DispatchStatus.NOT_SENT:
            state.append_turn(
                Turn(before.observation_id, decision, intent=intent, request_id=request.request_id, result=result)
            )
            if result.error is not None and result.error.value == "stale_binding":
                state.current_observation = await environment.observe("stale binding; refresh world")
                return state, 1, 0, probed, None
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "action was not dispatched")
            return state, 0, 0, probed, terminal
        after = await environment.observe("fresh post-action observation")
        if after.observation_id == before.observation_id:
            state.append_turn(
                Turn(before.observation_id, decision, intent, request.request_id, result, after.observation_id)
            )
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "post-action identity was reused")
            return state, 1, 1, probed, terminal
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
        return state, 1, 1, probed, self._post_action_terminal(
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
    ) -> AdmittedActionSelection | AgentResult:
        option = action_space.find(decision.action_id)
        if option is None:
            return build_result(
                AgentLoopStatus.BLOCKED,
                task,
                state,
                0,
                0,
                "policy selected an action outside the current ActionSpace",
            )
        try:
            selection = self.action_space_builder.admit(option, dict(decision.parameters))
        except ValueError as exc:
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, str(exc))
        if task.risk_profile in {RiskProfile.MEDIUM, RiskProfile.HIGH} or option.risk != ActionRisk.LOW:
            state.pending_confirmation = ActionIntent(
                selection.semantic_action,
                selection.target_id,
                dict(selection.parameters),
            )
            return build_result(
                AgentLoopStatus.WAITING_CONFIRMATION,
                task,
                state,
                0,
                0,
                "C1 admits only explicitly low-risk actions",
            )
        if task.risk_profile == RiskProfile.READ_ONLY and option.semantic_action != "read":
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "read-only task cannot execute effects")
        return selection

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
            return build_result(AgentLoopStatus.DONE, task, state, 0, 0, task_evaluation.reason)
        if result.dispatch_status == DispatchStatus.SENT_UNKNOWN:
            if action_evaluation.status in {
                ActionEvaluationStatus.VERIFIED,
                ActionEvaluationStatus.NOT_VERIFIED,
            }:
                return None
            if action_evaluation.status == ActionEvaluationStatus.REJECTED:
                return build_result(
                    AgentLoopStatus.FAILED,
                    task,
                    state,
                    0,
                    0,
                    action_evaluation.reason,
                )
            state.pending_unknown_request = request
            return build_result(
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
def _probe_count(result: ActionResult) -> int:
    value = result.adapter_evidence.get("currentness_probe_count", 0)
    return int(value) if isinstance(value, int | float) else 0
