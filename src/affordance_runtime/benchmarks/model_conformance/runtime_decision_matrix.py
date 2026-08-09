"""Benchmark-only proof that all decision variants enter production Runtime control."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.benchmarks.target_loop.support import (
    CurrentFactActionEvaluator,
    SharedTaskEvaluator,
    paging_environment,
    shared_environment,
    shared_task,
    shared_world,
)
from affordance_runtime.model_boundary import ContextBuilder
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import ActionPager

from .decision_matrix import DECISION_VARIANTS


@dataclass(frozen=True)
class RuntimeDecisionOutcome:
    decision_variant: str
    status: str
    execution_count: int
    observation_count: int
    context_count: int
    context_ids_unique: bool
    page_changed: bool
    target_action_visible: bool
    pending_question: str
    task_evaluation_calls: int
    waited_ms: int
    wait_budget_decreased: bool
    policy_failure: bool


@dataclass
class _Policy:
    variant: str
    calls: int = 0
    contexts: list[AgentContext] = field(default_factory=list)

    async def decide(self, context: AgentContext):
        self.calls += 1
        self.contexts.append(context)
        if self.calls > 1:
            return Abort(context.context_id, "runtime control proof complete", "no_progress")
        if self.variant == "select_action":
            return SelectAction(context.context_id, context.actions.options[0].action_id)
        if self.variant == "request_observation":
            capability = context.world.observation_capabilities[0]
            return RequestObservation(
                context.context_id,
                context.world.targets.items[0].target_id,
                capability.modality,
                capability.assurance,
                "refresh current evidence",
            )
        if self.variant == "request_action_page":
            return RequestActionPage(
                context.context_id,
                context.actions.active_query,
                context.actions.active_target_filter,
                context.actions.active_relevance_filter,
                context.actions.next_cursor,
            )
        if self.variant == "ask_user":
            return AskUser(context.context_id, "Which required value should be used?", ("value",))
        if self.variant == "propose_done":
            criteria = tuple(item.criterion_id for item in context.task.success_criteria.items)
            evidence = (context.world.facts.items[0].fact_ref,)
            return ProposeDone(context.context_id, criteria, evidence, "completion proposal", ())
        if self.variant == "wait":
            return Wait(context.context_id, "allow the state to settle", 10)
        return Abort(context.context_id, "the operation is unsupported", "unsupported")


@dataclass
class _CountingTaskEvaluator:
    inner: SharedTaskEvaluator = field(default_factory=SharedTaskEvaluator)
    calls: int = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        return await self.inner.evaluate(task, observation)


@dataclass
class _Waiter:
    waited_ms: int = 0

    async def wait(self, max_wait_ms: int) -> None:
        self.waited_ms += max_wait_ms


async def run_scripted_runtime_decision_matrix() -> tuple[RuntimeDecisionOutcome, ...]:
    return tuple([await _run_variant(variant) for variant in DECISION_VARIANTS])


async def _run_variant(variant: str) -> RuntimeDecisionOutcome:
    policy = _Policy(variant)
    evaluator = _CountingTaskEvaluator()
    waiter = _Waiter()
    paging = variant == "request_action_page"
    if paging:
        environment = paging_environment()
    elif variant in {"request_observation", "wait"}:
        environment = StaticEnvironment((
            shared_world(f"{variant}:before", False, "dom"),
            shared_world(f"{variant}:fresh", False, "dom"),
        ))
    else:
        environment = shared_environment("dom")
    context_builder = ContextBuilder(pager=ActionPager(page_size=1)) if paging else ContextBuilder()
    result = await AgentEpisodeRunner(AgentLoop(
        policy,
        CurrentFactActionEvaluator(),
        evaluator,
        context_builder=context_builder,
        wait_controller=waiter,
    )).run(environment, shared_task())
    context_ids = tuple(item.context_id for item in policy.contexts)
    page_changed = paging and len(policy.contexts) > 1 and (
        policy.contexts[0].actions.options[0].action_id
        != policy.contexts[1].actions.options[0].action_id
    )
    return RuntimeDecisionOutcome(
        variant,
        result.status.value,
        result.execution_count,
        result.observation_count,
        len(policy.contexts),
        len(context_ids) == len(set(context_ids)),
        page_changed,
        page_changed,
        result.message if result.status == AgentLoopStatus.WAITING_USER else "",
        evaluator.calls,
        waiter.waited_ms,
        variant == "wait" and len(policy.contexts) > 1 and (
            policy.contexts[1].budgets.remaining_wait_ms
            < policy.contexts[0].budgets.remaining_wait_ms
        ),
        result.policy_failure is not None,
    )


def runtime_outcome_matches(outcome: RuntimeDecisionOutcome) -> bool:
    common = outcome.execution_count == 0 and not outcome.policy_failure
    if outcome.decision_variant == "select_action":
        return outcome.status == AgentLoopStatus.DONE and outcome.execution_count == 1
    if outcome.decision_variant == "request_observation":
        return common and outcome.observation_count == 2 and outcome.context_count == 2 and outcome.context_ids_unique
    if outcome.decision_variant == "request_action_page":
        return common and outcome.page_changed and outcome.target_action_visible and outcome.context_ids_unique
    if outcome.decision_variant == "ask_user":
        return common and outcome.status == AgentLoopStatus.WAITING_USER and bool(outcome.pending_question)
    if outcome.decision_variant == "propose_done":
        return common and outcome.task_evaluation_calls >= 3
    if outcome.decision_variant == "wait":
        return common and outcome.waited_ms == 10 and outcome.wait_budget_decreased and outcome.context_ids_unique
    return common and outcome.status == AgentLoopStatus.FAILED
