"""Observe/select/bind/execute/reobserve/evaluate target AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.decision_control import ensure_current_action_page, run_policy_turn
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.execution_cycle import execute_cycle
from affordance_runtime.agent.observation_control import FreshObservationUnavailable, observe_fresh
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.agent.result import AgentResult, add_counts, build_result
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.confirmation.summary import build_confirmation_request
from affordance_runtime.execution.contracts import ActionIntent
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder
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
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    recent_turn_limit: int = 12

    async def start(
        self,
        task: TaskGoal,
        environment: WorldEnvironment,
        intent_context: IntentContext | None = None,
    ) -> AgentRunSession:
        current = await environment.observe("initial task grounding")
        state = AgentLoopState(
            current,
            remaining_turns=task.loop_budget.max_turns,
            recent_turn_limit=self.recent_turn_limit,
        )
        return AgentRunSession(self, task, environment, state, intent_context)

    async def run(
        self,
        task: TaskGoal,
        environment: WorldEnvironment,
        intent_context: IntentContext | None = None,
    ) -> AgentResult:
        return await (await self.start(task, environment, intent_context)).run_until_pause()

    async def _run_session(self, session: AgentRunSession) -> AgentResult:
        task, state = session.task, session.state
        while state.remaining_turns > 0:
            try:
                task_evaluation = await validated_task_evaluation(
                    self.task_evaluator, task, state.current_observation
                )
            except ValueError as exc:
                return self._result(session, AgentLoopStatus.FAILED, str(exc))
            task_status = task_evaluation_loop_status(task_evaluation)
            if task_status is not None:
                return self._result(session, task_status, task_evaluation.reason)
            action_space = self.action_space_builder.build(task, state.current_observation)
            ensure_current_action_page(session, action_space, self.context_builder.pager)
            if session.approved_confirmation is not None:
                outcome = await self._execute_confirmed(session, action_space, task_evaluation)
            else:
                outcome = await run_policy_turn(
                    session,
                    action_space,
                    task_evaluation,
                    self.policy,
                    self.context_builder,
                    self.task_evaluator,
                    self.wait_controller,
                    self._execute_selection,
                )
            result = self._apply_outcome(session, outcome)
            if result is not None:
                return result
        return self._result(session, AgentLoopStatus.FAILED, "agent loop turn budget exhausted")

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

    async def _execute_confirmed(self, session: AgentRunSession, action_space: ActionSpace, task_evaluation):
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
            context = self.context_builder.build(
                session.task,
                session.state,
                action_space,
                task_evaluation,
                session.intent_context,
                session.current_action_page,
                observation_count=session.observation_count,
                context_generation=session.next_context_generation(),
            )
            session.current_context_snapshot = context
            session.consumed_context_id = context.context_id
            decision = SelectAction(
                context.context_id,
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
        return await execute_cycle(
            session,
            selection,
            decision,
            self.binder,
            self.action_evaluator,
            self.task_evaluator,
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
            state.set_pending_confirmation(build_confirmation_request(
                intent,
                assessment,
                build_agent_world_view(state.current_observation),
            ))
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
        session.state.clear_pending_confirmation()
        if decision.decision == ConfirmationDecisionKind.DENY:
            session.approved_confirmation = None
            return self._result(session, AgentLoopStatus.CANCELLED, "user denied the semantic action")
        if not self._can_observe(session):
            return self._result(session, AgentLoopStatus.FAILED, "agent loop observation budget exhausted")
        session.approved_confirmation = pending
        previous_id = session.state.current_observation.observation_id
        try:
            fresh = await observe_fresh(
                session.environment, previous_id, "fresh observation after confirmation"
            )
        except FreshObservationUnavailable as exc:
            session.observation_count += 1
            session.approved_confirmation = None
            return self._result(session, AgentLoopStatus.FAILED, str(exc))
        session.observation_count += 1
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

    async def start(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> AgentRunSession:
        await environment.reset(task)
        return await self.agent_loop.start(task, environment, intent_context)

    async def run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> AgentResult:
        return await (await self.start(environment, task, intent_context)).run_until_pause()
