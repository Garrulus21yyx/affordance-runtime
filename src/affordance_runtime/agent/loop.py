"""Observe/select/bind/execute/reobserve/evaluate target AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.decisions import AskUser, Finish, Reobserve, SelectAction, Stop
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.agent.post_action_policy import post_action_result
from affordance_runtime.agent.result import AgentResult, add_counts, build_result, observation_budget_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus, Turn
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.confirmation.summary import build_confirmation_request
from affordance_runtime.evaluation.lineage import evaluation_matches_execution
from affordance_runtime.execution.contracts import ActionError, ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import ActionSpace, AdmittedActionSelection
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.view import build_agent_world_view


@dataclass
class AgentLoop:
    policy: AgentPolicy
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    recent_turn_limit: int = 12

    async def start(self, task: TaskGoal, environment: WorldEnvironment) -> AgentRunSession:
        current = await environment.observe("initial task grounding")
        state = AgentLoopState(
            current,
            remaining_turns=task.loop_budget.max_turns,
            recent_turn_limit=self.recent_turn_limit,
        )
        return AgentRunSession(self, task, environment, state)

    async def run(self, task: TaskGoal, environment: WorldEnvironment) -> AgentResult:
        return await (await self.start(task, environment)).run_until_pause()

    async def _run_session(self, session: AgentRunSession) -> AgentResult:
        task, state = session.task, session.state
        while state.remaining_turns > 0:
            task_evaluation = await self.task_evaluator.evaluate(task, state.current_observation)
            task_status = task_evaluation_loop_status(task_evaluation)
            if task_status is not None:
                return self._result(session, task_status, task_evaluation.reason)
            action_space = self.action_space_builder.build(task, state.current_observation)
            if session.approved_confirmation is not None:
                outcome = await self._execute_confirmed(session, action_space)
            else:
                outcome = await self._policy_turn(session, action_space, task_evaluation)
            result = self._apply_outcome(session, outcome)
            if result is not None:
                return result
        return self._result(session, AgentLoopStatus.FAILED, "agent loop turn budget exhausted")

    async def _policy_turn(self, session: AgentRunSession, action_space: ActionSpace, task_evaluation):
        task, state = session.task, session.state
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
            return build_result(AgentLoopStatus.WAITING_USER, task, state, 0, 0, decision.question)
        if isinstance(decision, Stop):
            return build_result(AgentLoopStatus.FAILED, task, state, 0, 0, decision.reason)
        if isinstance(decision, Finish):
            state.append_turn(Turn(state.current_observation.observation_id, decision, task_evaluation=task_evaluation))
            return None
        if isinstance(decision, Reobserve):
            if not self._can_observe(session):
                return observation_budget_result(task, state, 0, 0)
            state.append_turn(Turn(state.current_observation.observation_id, decision))
            state.current_observation = await session.environment.observe(decision.reason)
            session.observation_count += 1
            return None
        return await self._execute_selection(session, action_space, decision)

    async def _execute_selection(
        self,
        session: AgentRunSession,
        action_space: ActionSpace,
        decision: SelectAction,
    ):
        admitted = self._admit_selection(session.task, session.state, action_space, decision)
        if isinstance(admitted, AgentResult):
            return admitted
        return await self._execute_admitted(session, admitted, decision)

    async def _execute_confirmed(self, session: AgentRunSession, action_space: ActionSpace):
        confirmed = session.approved_confirmation
        assert confirmed is not None
        candidates = []
        for option in action_space.options:
            if option.semantic_action != confirmed.intent.semantic_action or option.target_id != confirmed.intent.target_id:
                continue
            try:
                selection = self.action_space_builder.admit(
                    option,
                    dict(confirmed.intent.parameters),
                    confirmed.intent.destination_id,
                )
            except ValueError:
                continue
            candidates.append((selection, self.risk_policy.assess(session.task, selection)))
        exact = next((item for item in candidates if item[1].subject_id == confirmed.subject_id), None)
        if exact is not None:
            selection = exact[0]
            decision = SelectAction(
                selection.action_id,
                dict(selection.parameters),
                selection.destination_id,
            )
            return await self._execute_admitted(session, selection, decision)
        session.approved_confirmation = None
        return None

    async def _execute_admitted(
        self,
        session: AgentRunSession,
        selection: AdmittedActionSelection,
        decision: SelectAction,
    ):
        task, state, environment = session.task, session.state, session.environment
        if not self._can_observe(session):
            return observation_budget_result(task, state, 0, 0)
        before = state.current_observation
        try:
            request = self.binder.bind(selection, before)
        except BindingError:
            state.current_observation = await environment.observe("binding unavailable; refresh world")
            return state, 1, 0, 0, None
        result = await environment.execute(request)
        probed = _probe_count(result)
        if result.request_id != request.request_id or result.backend != request.binding.executor_id:
            state.append_turn(Turn(before.observation_id, decision, request.intent, request.request_id, result))
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "action result lineage mismatch")
            return state, 0, int(result.dispatch_status != DispatchStatus.NOT_SENT), probed, terminal
        if result.dispatch_status == DispatchStatus.NOT_SENT:
            state.append_turn(Turn(before.observation_id, decision, request.intent, request.request_id, result))
            if result.error in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
                state.current_observation = await environment.observe("currentness unavailable; refresh world")
                return state, 1, 0, probed, None
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "action was not dispatched")
            return state, 0, 0, probed, terminal
        after = await environment.observe("fresh post-action observation")
        if after.observation_id == before.observation_id:
            state.append_turn(Turn(before.observation_id, decision, request.intent, request.request_id, result, after.observation_id))
            terminal = build_result(AgentLoopStatus.FAILED, task, state, 0, 0, "post-action identity was reused")
            return state, 1, 1, probed, terminal
        action_evaluation = await self.action_evaluator.evaluate(task, before, request, result, after)
        if not evaluation_matches_execution(action_evaluation, request, before, after):
            state.append_turn(
                Turn(
                    before.observation_id,
                    decision,
                    request.intent,
                    request.request_id,
                    result,
                    after.observation_id,
                )
            )
            state.current_observation = after
            terminal = build_result(
                AgentLoopStatus.FAILED,
                task,
                state,
                0,
                0,
                "action evaluation lineage mismatch",
            )
            return state, 1, 1, probed, terminal
        task_evaluation = await self.task_evaluator.evaluate(task, after)
        state.append_turn(
            Turn(
                before.observation_id,
                decision,
                request.intent,
                request.request_id,
                result,
                after.observation_id,
                action_evaluation,
                task_evaluation,
            )
        )
        state.current_observation = after
        post_terminal = post_action_result(task, state, request, action_evaluation, task_evaluation)
        return state, 1, 1, probed, post_terminal

    def _admit_selection(
        self,
        task: TaskGoal,
        state: AgentLoopState,
        action_space: ActionSpace,
        decision: SelectAction,
    ) -> AdmittedActionSelection | AgentResult:
        option = action_space.find(decision.action_id)
        if option is None:
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "policy selected outside ActionSpace")
        try:
            selection = self.action_space_builder.admit(
                option,
                dict(decision.parameters),
                decision.destination_id,
            )
        except ValueError as exc:
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, str(exc))
        assessment = self.risk_policy.assess(task, selection)
        if assessment.decision == RiskDecisionKind.BLOCK:
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, assessment.reason)
        if assessment.decision == RiskDecisionKind.NEEDS_CONFIRMATION:
            intent = ActionIntent(
                selection.semantic_action,
                selection.target_id,
                dict(selection.parameters),
                selection.destination_id,
            )
            state.pending_confirmation = build_confirmation_request(
                intent,
                assessment,
                build_agent_world_view(state.current_observation),
            )
            return build_result(AgentLoopStatus.WAITING_CONFIRMATION, task, state, 0, 0, assessment.reason)
        return selection

    async def _resolve_confirmation(
        self,
        session: AgentRunSession,
        decision: ConfirmationDecision,
    ) -> AgentResult:
        pending = session.state.pending_confirmation
        if session.is_terminal or pending is None or decision.confirmation_id in session.resolved_confirmation_ids:
            return self._result(session, AgentLoopStatus.BLOCKED, "confirmation decision is stale or already resolved")
        if not decision.matches(pending):
            return self._result(session, AgentLoopStatus.BLOCKED, "confirmation decision identity mismatch")
        session.resolved_confirmation_ids.add(decision.confirmation_id)
        session.state.pending_confirmation = None
        if decision.decision == ConfirmationDecisionKind.DENY:
            session.approved_confirmation = None
            return self._result(session, AgentLoopStatus.CANCELLED, "user denied the semantic action")
        if not self._can_observe(session):
            return self._result(session, AgentLoopStatus.FAILED, "agent loop observation budget exhausted")
        session.approved_confirmation = pending
        previous_id = session.state.current_observation.observation_id
        fresh = await session.environment.observe("fresh observation after confirmation")
        session.observation_count += 1
        if fresh.observation_id == previous_id:
            session.approved_confirmation = None
            return self._result(session, AgentLoopStatus.FAILED, "confirmation observation identity was reused")
        session.state.current_observation = fresh
        session.last_result = None
        return await self._run_session(session)

    def _apply_outcome(self, session: AgentRunSession, outcome) -> AgentResult | None:
        if outcome is None:
            return None
        if isinstance(outcome, AgentResult):
            return add_counts(
                outcome,
                session.observation_count + outcome.observation_count,
                session.execution_count + outcome.execution_count,
                session.currentness_probe_count + outcome.currentness_probe_count,
            )
        _, observed, executed, probed, terminal = outcome
        session.observation_count += observed
        session.execution_count += executed
        session.currentness_probe_count += probed
        if executed:
            session.approved_confirmation = None
        if terminal is not None:
            return add_counts(
                terminal,
                session.observation_count,
                session.execution_count,
                session.currentness_probe_count,
            )
        return None

    @staticmethod
    def _can_observe(session: AgentRunSession) -> bool:
        return session.observation_count < session.task.loop_budget.max_observations

    @staticmethod
    def _result(session: AgentRunSession, status: AgentLoopStatus, message: str) -> AgentResult:
        return build_result(
            status,
            session.task,
            session.state,
            session.observation_count,
            session.execution_count,
            message,
            session.currentness_probe_count,
        )


@dataclass(frozen=True)
class AgentEpisodeRunner:
    agent_loop: AgentLoop

    async def start(self, environment: WorldEnvironment, task: TaskGoal) -> AgentRunSession:
        await environment.reset(task)
        return await self.agent_loop.start(task, environment)

    async def run(self, environment: WorldEnvironment, task: TaskGoal) -> AgentResult:
        return await (await self.start(environment, task)).run_until_pause()


def _probe_count(result: ActionResult) -> int:
    value = result.adapter_evidence.get("currentness_probe_count", 0)
    return int(value) if isinstance(value, int | float) else 0
