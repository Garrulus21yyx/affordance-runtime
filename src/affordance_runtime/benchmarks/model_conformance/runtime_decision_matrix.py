"""Benchmark-only proof that all decision variants enter production Runtime control."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from affordance_runtime.actions import (
    ActionPager,
)
from affordance_runtime.agent import (
    Abort,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    RunStatus,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.app.composition import compose_target_runtime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.benchmarks.target_loop.support import (
    CurrentFactActionEvaluator,
    SharedTaskEvaluator,
    paging_environment,
    shared_environment,
    shared_task,
    shared_world,
)
from affordance_runtime.world import (
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from affordance_runtime.world.contracts import WorldObservation

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
    wait_refreshed: bool
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
        if self.variant == "request_evidence":
            return RequestObservation(
                context.context_id,
                "criterion_verification",
                context.world.targets.items[0].target_id,
                "",
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
    elif variant in {"request_evidence", "wait"}:
        environment = ScriptedEnvironment(
            initial_observation=shared_world(f"{variant}:before", False, "dom"),
            independent_observations=(shared_world(f"{variant}:fresh", False, "dom"),),
        )
    else:
        environment = shared_environment("dom")
    context_builder = ContextBuilder(pager=ActionPager(page_size=1)) if paging else ContextBuilder()
    result = await compose_target_runtime(
        policy,
        CurrentFactActionEvaluator(),
        evaluator,
        context_builder=context_builder,
        wait_controller=waiter,
    ).run_task(environment, shared_task())
    context_ids = tuple(item.context_id for item in policy.contexts)
    page_changed = (
        paging
        and len(policy.contexts) > 1
        and (policy.contexts[0].actions.options[0].action_id != policy.contexts[1].actions.options[0].action_id)
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
        (
            result.last_step.decision.question
            if result.status is RunStatus.WAITING_USER
            and result.last_step is not None
            and isinstance(result.last_step.decision, AskUser)
            else ""
        ),
        evaluator.calls,
        waiter.waited_ms,
        variant == "wait" and result.observation_count == 2 and waiter.waited_ms == 10,
        result.policy_failure is not None,
    )


def runtime_outcome_matches(outcome: RuntimeDecisionOutcome) -> bool:
    common = outcome.execution_count == 0 and not outcome.policy_failure
    if outcome.decision_variant == "select_action":
        return outcome.status == RunStatus.DONE and outcome.execution_count == 1
    if outcome.decision_variant == "request_evidence":
        return common and outcome.observation_count == 2 and outcome.context_count == 2 and outcome.context_ids_unique
    if outcome.decision_variant == "request_action_page":
        return common and outcome.page_changed and outcome.target_action_visible and outcome.context_ids_unique
    if outcome.decision_variant == "ask_user":
        return common and outcome.status == RunStatus.WAITING_USER and bool(outcome.pending_question)
    if outcome.decision_variant == "propose_done":
        return common and outcome.task_evaluation_calls >= 1
    if outcome.decision_variant == "wait":
        return common and outcome.waited_ms == 10 and outcome.wait_refreshed and outcome.context_ids_unique
    return common and outcome.status == RunStatus.BLOCKED


@dataclass(frozen=True)
class ReplayedRuntimeOutcome:
    success: bool
    status: str
    execution_count: int
    observation_count: int
    page_changed: bool
    task_evaluation_calls: int
    waited_ms: int
    policy_failure: bool


@dataclass
class _ReplayPolicy:
    decision: object
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        if self.calls > 1:
            return Abort(context.context_id, "runtime replay complete", "no_progress")
        if isinstance(self.decision, SelectAction):
            option = context.actions.options[0]
            destination_id = option.destinations.items[0].destination_id if option.destination_required else ""
            return replace(
                self.decision,
                context_id=context.context_id,
                action_id=option.action_id,
                destination_id=destination_id,
            )
        if isinstance(self.decision, RequestObservation):
            return replace(
                self.decision,
                context_id=context.context_id,
                subject_id=context.world.targets.items[0].target_id,
            )
        if isinstance(self.decision, RequestActionPage):
            return RequestActionPage(
                context.context_id,
                context.actions.active_query,
                context.actions.active_target_filter,
                context.actions.active_relevance_filter,
                context.actions.next_cursor,
            )
        return replace(self.decision, context_id=context.context_id)


async def replay_runtime_decision(case, decision) -> ReplayedRuntimeOutcome:
    value = json.loads(case.serialized_context)
    if isinstance(decision, SelectAction) and not _selection_belongs_to_one_option(value, decision):
        return ReplayedRuntimeOutcome(False, "blocked", 0, 1, False, 0, 0, False)
    before = _evidence_world("replay:before", getattr(decision, "evidence_refs", ()))
    fresh = _evidence_world("replay:fresh", ())
    variant = _variant_name(decision)
    if variant == "select_action":
        environment = shared_environment("dom")
    elif variant == "request_action_page":
        environment = paging_environment()
    else:
        environment = ScriptedEnvironment(initial_observation=before, independent_observations=(fresh,))
    task = shared_task()
    evaluator, waiter = _CountingTaskEvaluator(), _Waiter()
    policy = _ReplayPolicy(decision)
    runtime = compose_target_runtime(
        policy,
        CurrentFactActionEvaluator(),
        evaluator,
        wait_controller=waiter,
        context_builder=(ContextBuilder(pager=ActionPager(page_size=1)) if variant == "request_action_page" else None),
    )
    outcome = await runtime.run_task(environment, task)
    page_changed = variant == "request_action_page" and policy.calls > 1
    replayed = ReplayedRuntimeOutcome(
        False,
        outcome.status.value,
        outcome.execution_count,
        outcome.observation_count,
        page_changed,
        evaluator.calls,
        waiter.waited_ms,
        outcome.policy_failure is not None,
    )
    return replace(replayed, success=_replay_matches(_variant_name(decision), replayed))


def _replay_matches(variant: str, outcome: ReplayedRuntimeOutcome) -> bool:
    if variant == "select_action":
        return outcome.execution_count == 1 and outcome.status == "done"
    if variant == "request_evidence":
        return outcome.execution_count == 0 and outcome.observation_count == 2
    if variant == "request_action_page":
        return outcome.execution_count == 0 and outcome.page_changed
    if variant == "ask_user":
        return outcome.execution_count == 0 and outcome.status == "waiting_user"
    if variant == "propose_done":
        return outcome.execution_count == 0 and outcome.task_evaluation_calls >= 1
    if variant == "wait":
        return outcome.execution_count == 0 and outcome.waited_ms > 0 and outcome.observation_count == 2
    return outcome.execution_count == 0 and outcome.status == "blocked" and not outcome.policy_failure


def _selection_belongs_to_one_option(value: dict[str, object], decision: SelectAction) -> bool:
    actions = value.get("actions")
    options = actions.get("options", ()) if isinstance(actions, dict) else ()
    for option in options if isinstance(options, list | tuple) else ():
        if not isinstance(option, dict) or option.get("action_id") != decision.action_id:
            continue
        destinations = option.get("destinations", {})
        items = destinations.get("items", ()) if isinstance(destinations, dict) else ()
        allowed = {str(item.get("destination_id") or "") for item in items if isinstance(item, dict)}
        return not decision.destination_id or decision.destination_id in allowed
    return False


def _variant_name(decision) -> str:
    return {
        "SelectAction": "select_action",
        "RequestObservation": "request_evidence",
        "RequestActionPage": "request_action_page",
        "AskUser": "ask_user",
        "ProposeDone": "propose_done",
        "Wait": "wait",
        "Abort": "abort",
    }.get(type(decision).__name__, "")


def _evidence_world(identity: str, refs) -> WorldObservation:
    base = shared_world(identity, False, "dom")
    base_source = base.sources[0]
    local_target = base_source.targets[0]
    fact_refs = tuple(ref for ref in refs if str(ref).startswith("fact:"))
    facts = tuple(
        StateFact(ref, local_target.target_id, "expanded", False, identity)
        for ref in (fact_refs or (base.facts[0].fact_id,))
    )
    artifact_sources = []
    for ref in refs:
        if str(ref).startswith("artifact:"):
            _, source_id, key = str(ref).rsplit(":", 2)
            artifact_sources.append(
                SurfaceObservation(
                    source_id,
                    "dom",
                    f"revision:{source_id}",
                    base.sources[0].source_profile,
                    artifacts={key: {"public_summary": "current benchmark evidence"}},
                )
            )
    source = SurfaceObservation(
        identity,
        "dom",
        f"revision:{identity}",
        base_source.source_profile,
        base_source.targets,
        facts,
        base_source.bindings,
    )
    result = WorldFusion().fuse((source, *artifact_sources))
    if result.observation is None:
        raise ValueError(result.reason_code)
    return result.observation
