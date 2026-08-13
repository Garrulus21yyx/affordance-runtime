"""Benchmark-only proof that all decision variants enter production Runtime control."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from affordance_runtime.agent import (
    Abort,
    AgentLoopStatus,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    TargetRuntime,
    Wait,
)
from affordance_runtime.agent.accounting import RunAccounting
from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
)
from affordance_runtime.agent.control_transition import AdmissionStatus
from affordance_runtime.agent.decision_control import run_policy_turn
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopState
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
from affordance_runtime.world import ActionPager, ActionSpaceBuilder, StateFact, SurfaceObservation
from affordance_runtime.world.admission_issue import AdmissionIssue, AdmissionIssueCode
from affordance_runtime.world.contracts import ActionSpace, WorldObservation

from .decision_matrix import DECISION_VARIANTS

if TYPE_CHECKING:
    from affordance_runtime.agent.loop import AgentLoop


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
    result = await TargetRuntime(
        AgentDecisionPorts(policy),
        CurrentFactActionEvaluator(),
        evaluator,
        context_builder=context_builder,
        wait_controller=waiter,
    ).run_task(environment, shared_task())
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
        return common and outcome.task_evaluation_calls >= 2
    if outcome.decision_variant == "wait":
        return common and outcome.waited_ms == 10 and outcome.wait_budget_decreased and outcome.context_ids_unique
    return common and outcome.status == AgentLoopStatus.FAILED


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

    async def decide(self, context):
        del context
        return self.decision


@dataclass
class _ReplayPage:
    page_id: str
    visible_action_ids: tuple[str, ...]
    destinations: dict[str, tuple[str, ...]]
    next_cursor: str
    query: str
    target_id: str
    relevance_role: object = None

    @property
    def visible_destinations(self):
        return tuple(
            (action_id, self.destinations.get(action_id, ()))
            for action_id in self.visible_action_ids
        )

    @property
    def relevance(self):
        return ()

    @property
    def total_count(self):
        return len(self.visible_action_ids)

    @property
    def has_more(self):
        return bool(self.next_cursor)

    @property
    def offset(self):
        return 0

    def visible_destination_ids(self, action_id: str) -> tuple[str, ...]:
        return self.destinations.get(action_id, ())

    def selection_issue(self, action_id: str, destination_id: str = ""):
        if action_id not in self.visible_action_ids:
            return AdmissionIssue(
                AdmissionIssueCode.ACTION_OUTSIDE_CURRENT_PAGE, ("actions",),
            )
        if destination_id and destination_id not in self.visible_destination_ids(action_id):
            return AdmissionIssue(
                AdmissionIssueCode.DESTINATION_OUTSIDE_CURRENT_PAGE,
                ("destination_id",),
            )
        return None


@dataclass
class _ReplayContextBuilder:
    context: object

    def build(self, *args, **kwargs):
        del args, kwargs
        return self.context

    def page(self, *args, **kwargs):
        del args, kwargs
        return _ReplayPage("page:replayed", (), {}, "", "", "")


async def replay_runtime_decision(case, decision) -> ReplayedRuntimeOutcome:
    value = json.loads(case.serialized_context)
    before = _evidence_world("replay:before", getattr(decision, "evidence_refs", ()))
    fresh = _evidence_world("replay:fresh", ())
    environment = StaticEnvironment((before, fresh))
    task = shared_task()
    acquisition = await environment.reset(task)
    if acquisition.observation is None:
        raise RuntimeError("runtime replay initial acquisition failed")
    state = AgentLoopState(acquisition.observation, remaining_turns=3)
    evaluator, waiter = _CountingTaskEvaluator(), _Waiter()
    accounting = RunAccounting()
    accounting.record(AttemptReceipt(
        accounting.next_attempt_id(), AttemptOperation.RESET, "reset",
        acquisition.origin, acquisition.origin, AttemptDisposition.RETURNED,
        acquisition.reason_code, 1, 0, 0, 0, acquisition_status=acquisition.status,
    ))
    session = AgentRunSession(
        cast("AgentLoop", SimpleNamespace()), task, environment, state,
        accounting=accounting,
    )
    options = value.get("actions", {}).get("options", ())
    visible = tuple(str(item.get("action_id") or "") for item in options)
    destinations = {
        str(item.get("action_id") or ""): tuple(
            str(destination.get("destination_id") or "")
            for destination in item.get("destinations", {}).get("items", ())
        )
        for item in options
    }
    actions = value.get("actions", {})
    role = actions.get("active_relevance_filter") or None
    page = _ReplayPage(
        "page:current", visible, destinations, str(actions.get("next_cursor") or ""),
        str(actions.get("active_query") or ""), str(actions.get("active_target_filter") or ""),
        SimpleNamespace(value=role) if role else None,
    )
    session.current_action_page = page  # type: ignore[assignment]
    capabilities = tuple(
        SimpleNamespace(modality=item["modality"], assurance=item["assurance"])
        for item in value.get("world", {}).get("observation_capabilities", ())
    )
    context = SimpleNamespace(
        context_id=value["context_id"], world=SimpleNamespace(observation_capabilities=capabilities),
    )
    executions = 0

    async def dry_run(*args):
        nonlocal executions
        scope = args[-1]
        scope.record_admission(AdmissionStatus.ADMITTED, "dry_run_admitted")
        executions += 1
        return "dry-run-admitted"

    outcome = await run_policy_turn(
        session, ActionSpace(before.observation_id, ()),
        await evaluator.evaluate(task, before), _ReplayPolicy(decision),
        cast(ContextBuilder, _ReplayContextBuilder(context)), evaluator, waiter, dry_run,
        ActionSpaceBuilder(),
    )
    status = outcome.status.value if hasattr(outcome, "status") else "continued"
    policy_failure = bool(getattr(outcome, "policy_failure", None))
    page_changed = getattr(session.current_action_page, "page_id", "") != "page:current"
    replayed = ReplayedRuntimeOutcome(
        False, status, executions, session.observation_count, page_changed,
        evaluator.calls, waiter.waited_ms, policy_failure,
    )
    return replace(replayed, success=_replay_matches(_variant_name(decision), replayed))


def _replay_matches(variant: str, outcome: ReplayedRuntimeOutcome) -> bool:
    if variant == "select_action":
        return outcome.execution_count == 1 and outcome.status == "continued"
    if variant == "request_observation":
        return outcome.execution_count == 0 and outcome.observation_count == 2
    if variant == "request_action_page":
        return outcome.execution_count == 0 and outcome.page_changed
    if variant == "ask_user":
        return outcome.execution_count == 0 and outcome.status == "waiting_user"
    if variant == "propose_done":
        return outcome.execution_count == 0 and outcome.task_evaluation_calls >= 2
    if variant == "wait":
        return outcome.execution_count == 0 and outcome.waited_ms > 0 and outcome.observation_count == 2
    return outcome.execution_count == 0 and outcome.status == "failed" and not outcome.policy_failure


def _variant_name(decision) -> str:
    return {
        "SelectAction": "select_action", "RequestObservation": "request_observation",
        "RequestActionPage": "request_action_page", "AskUser": "ask_user",
        "ProposeDone": "propose_done", "Wait": "wait", "Abort": "abort",
    }.get(type(decision).__name__, "")


def _evidence_world(identity: str, refs) -> WorldObservation:
    base = shared_world(identity, False, "dom")
    fact_refs = tuple(ref for ref in refs if str(ref).startswith("fact:"))
    facts = tuple(
        StateFact(ref, base.targets[0].target_id, "expanded", False, identity)
        for ref in (fact_refs or (base.facts[0].fact_id,))
    )
    artifact_sources = []
    for ref in refs:
        if str(ref).startswith("artifact:"):
            _, source_id, key = str(ref).rsplit(":", 2)
            artifact_sources.append(SurfaceObservation(
                source_id, "dom", f"revision:{source_id}", base.sources[0].source_profile,
                artifacts={key: {"public_summary": "current benchmark evidence"}},
            ))
    source = SurfaceObservation(
        identity, "dom", f"revision:{identity}", base.sources[0].source_profile,
        base.targets, facts, base.bindings,
    )
    return WorldObservation(
        identity, base.targets, facts, base.bindings, base.coverage,
        sources=(source, *artifact_sources),
    )
