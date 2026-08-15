"""Private fixed-case fixtures for target-loop internal attestations."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.agent import Abort, RequestActionPage, SelectAction
from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.benchmarks.support import StaticEnvironment
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.model.policy import ModelBackedAgentPolicy, ModelMetadata, ResolvedModelDecision
from affordance_runtime.model.policy.spec import AgentDecisionPayload, payload_to_decision
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


class FirstActionPolicy:
    async def decide(self, context):
        return SelectAction(context.context_id, context.actions.options[0].action_id)


@dataclass
class PagingPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        if self.calls == 1:
            return RequestActionPage(context.context_id, cursor=context.actions.next_cursor)
        return SelectAction(context.context_id, context.actions.options[0].action_id)


@dataclass
class SelectThenAbortPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        if self.calls == 1:
            return SelectAction(context.context_id, context.actions.options[0].action_id)
        return Abort(context.context_id, "stale opportunity attested", "no_progress")


@dataclass
class ScriptedDecisionPort:
    fail: bool = False
    calls: int = 0

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return frozenset({DecisionCapability.SELECT_ACTION})

    async def generate(self, request):
        self.calls += 1
        if self.fail:
            return ModelFailure(ModelFailureKind.TIMEOUT, "fixture timeout", False)
        import json

        context = json.loads(request.serialized_context)
        option = context["actions"]["options"][0]
        payload = {
            "type": "select_action", "context_id": context["context_id"],
            "action_id": option["action_id"], "parameters": {}, "destination_id": "",
        }
        decision = payload_to_decision(AgentDecisionPayload.model_validate(payload), request.context_id)
        return ResolvedModelDecision(decision, ModelMetadata("fixture", "scripted", "response:1"))


def policy_for(profile: str):
    if profile == "deterministic":
        return FirstActionPolicy()
    if profile in {"scripted-model", "local-http-semantic-judge"}:
        return ModelBackedAgentPolicy(ScriptedDecisionPort())
    raise ValueError(f"unsupported fixed target-loop profile: {profile}")


class SharedTaskEvaluator:
    async def evaluate(self, task, observation):
        expanded = any(fact.predicate == "expanded" and fact.value is True for fact in observation.facts)
        ref = next(fact.fact_id for fact in observation.facts if fact.predicate == "expanded")
        status = CriterionEvaluationStatus.SATISFIED if expanded else CriterionEvaluationStatus.UNSATISFIED
        criteria = tuple(CriterionEvaluation(criterion_id(item), status, (ref,), "current shared state") for item in task.success_criteria)
        return TaskEvaluation(
            task.task_id, observation.observation_id,
            TaskEvaluationStatus.COMPLETE if expanded else TaskEvaluationStatus.INCOMPLETE,
            "shared state evaluated", criteria, (ref,) if expanded else (),
        )


class CurrentFactActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        before_values = {fact.predicate: fact.value for fact in before.facts}
        changed = next((fact for fact in after.facts if before_values.get(fact.predicate) != fact.value), None)
        if changed is None:
            return ActionEvaluation(request.request_id, before.observation_id, after.observation_id, ActionEvaluationStatus.UNKNOWN, "no exact obligation")
        return ActionEvaluation(
            request.request_id, before.observation_id, after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED, "relevant state changed", (changed.fact_id,),
        )


def shared_task() -> TaskGoal:
    return TaskGoal(
        "enable-shared", "Enable shared state", allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "expanded", "subject_id": "shared:1", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.LOW,
    )


def shared_world(identity: str, expanded: bool, surface: str) -> WorldObservation:
    profile = {"dom": ObservationSourceProfile.dom(), "visual": ObservationSourceProfile.visual(), "wot": ObservationSourceProfile.wot()}[surface]
    target = SemanticTarget("shared:1", "control", "shared control", {"expanded": expanded})
    fact = StateFact(f"fact:{identity}:expanded", target.target_id, "expanded", expanded, identity)
    binding = ActionBinding(
        f"binding:{identity}", identity, identity, f"revision:{identity}", f"fingerprint:{identity}",
        target.target_id, target.target_id, surface, surface, "activate", "invoke",
        "local_reversible", ("shared_state_enabled",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"backend_private": surface}, risk=ActionRisk.LOW,
    )
    source = SurfaceObservation(identity, surface, f"revision:{identity}", profile, (target,), (fact,), (binding,))
    return WorldObservation(identity, (target,), (fact,), (binding,), {surface: CoverageState.COMPLETE}, sources=(source,))


def shared_environment(surface: str, *, sent_unknown: bool = False) -> StaticEnvironment:
    status = DispatchStatus.SENT_UNKNOWN if sent_unknown else DispatchStatus.SENT
    return StaticEnvironment(
        (shared_world(f"{surface}:before", False, surface), shared_world(f"{surface}:after", not sent_unknown, surface)),
        (ActionResult(
            "*", status, surface, not sent_unknown,
            ActionError.EXECUTION_FAILED if sent_unknown else None,
        ),),
    )


def paging_world(identity: str, expanded: bool) -> WorldObservation:
    targets, bindings = [], []
    for index in range(40):
        target = SemanticTarget(f"target:{index:02d}", "control", f"control {index}", {"expanded": expanded})
        targets.append(target)
        bindings.append(ActionBinding(
            f"binding:{identity}:{index}", identity, identity, f"revision:{identity}", f"fingerprint:{identity}:{index}",
            target.target_id, target.target_id, "dom", "dom", "activate", "click",
            "local_reversible", ("shared_state_enabled",),
            {"type": "object", "properties": {}, "additionalProperties": False}, {"route": index}, risk=ActionRisk.LOW,
        ))
    fact = StateFact(f"fact:{identity}:expanded", "shared:1", "expanded", expanded, identity)
    source = SurfaceObservation(
        identity, "dom", f"revision:{identity}", ObservationSourceProfile.dom(),
        tuple(targets), (fact,), tuple(bindings),
    )
    return WorldObservation(
        identity, tuple(targets), (fact,), tuple(bindings), {"dom": CoverageState.COMPLETE}, sources=(source,),
    )


def paging_environment() -> StaticEnvironment:
    return StaticEnvironment(
        (paging_world("paging:before", False), paging_world("paging:after", True)),
        (ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )


@dataclass
class StaleOnceEnvironment(StaticEnvironment):
    stale_checks: int = field(default=0, init=False)

    def is_current(self, request):
        self.stale_checks += 1
        return self.stale_checks > 1 and super().is_current(request)


def stale_environment() -> StaleOnceEnvironment:
    return StaleOnceEnvironment(
        (
            shared_world("stale:before", False, "dom"),
            shared_world("stale:refresh", False, "dom"),
        ),
        (ActionResult("*", DispatchStatus.NOT_SENT, "dom", False, ActionError.UNSUPPORTED_ACTION),),
    )


def low_risk_environment() -> StaticEnvironment:
    return StaticEnvironment(
        (
            shared_world("low:before", False, "dom"),
            shared_world("low:middle", False, "dom"),
            shared_world("low:after", True, "dom"),
        ),
        (
            ActionResult("*", DispatchStatus.SENT, "dom", True),
            ActionResult("*", DispatchStatus.SENT, "dom", True),
        ),
    )


def confirmation_environment() -> StaticEnvironment:
    before = _risk_world("confirm:before", False, ActionRisk.MEDIUM)
    rebound = _risk_world("confirm:rebound", False, ActionRisk.MEDIUM)
    after = _risk_world("confirm:after", True, ActionRisk.MEDIUM)
    return StaticEnvironment((before, rebound, after), (ActionResult("*", DispatchStatus.SENT, "dom", True),))


def confirmation_task() -> TaskGoal:
    return TaskGoal(
        "confirmed-enable", "Enable with confirmation", allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "expanded", "subject_id": "shared:1", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.MEDIUM,
    )


def _risk_world(identity: str, expanded: bool, risk: ActionRisk) -> WorldObservation:
    world = shared_world(identity, expanded, "dom")
    binding = world.bindings[0]
    replacement = ActionBinding(
        binding.binding_id, binding.world_observation_id, binding.source_observation_id,
        binding.source_revision, binding.target_fingerprint, binding.target_id,
        binding.source_target_id, binding.surface, binding.executor_id, binding.semantic_action,
        binding.primitive_action, binding.effect_category, binding.semantic_effects,
        binding.parameter_schema, binding.payload, risk=risk,
    )
    source = SurfaceObservation(
        identity, "dom", f"revision:{identity}", ObservationSourceProfile.dom(),
        world.targets, world.facts, (replacement,),
    )
    return WorldObservation(identity, world.targets, world.facts, (replacement,), world.coverage, sources=(source,))


@dataclass
class ForbiddenRouteEnvironment(StaticEnvironment):
    benchmark_forbidden_effect_attempts: int = field(default=0, init=False)

    async def execute(self, request):
        if "forbidden_effect" in request.selection.semantic_effects:
            self.benchmark_forbidden_effect_attempts += 1
        return await super().execute(request)


def forbidden_environment() -> ForbiddenRouteEnvironment:
    before = shared_world("forbidden:before", False, "dom")
    allowed = before.bindings[0]
    forbidden = ActionBinding(
        "binding:forbidden", before.observation_id, before.observation_id,
        "revision:forbidden:before", "fingerprint:forbidden", allowed.target_id,
        allowed.source_target_id, "dom", "dom", "activate", "click",
        "external", ("forbidden_effect",), allowed.parameter_schema, {"route": "forbidden"},
        risk=ActionRisk.HIGH,
    )
    source = SurfaceObservation(
        before.observation_id, "dom", "revision:forbidden:before", ObservationSourceProfile.dom(),
        before.targets, before.facts, (allowed, forbidden),
    )
    before = WorldObservation(
        before.observation_id, before.targets, before.facts, (allowed, forbidden),
        before.coverage, sources=(source,),
    )
    return ForbiddenRouteEnvironment(
        (before, shared_world("forbidden:after", True, "dom")),
        (ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )


def forbidden_task() -> TaskGoal:
    return TaskGoal(
        "forbidden-route", "Use only allowed effect", allowed_effects=("shared_state_enabled",),
        forbidden_effects=("forbidden_effect",),
        success_criteria=({"id": "expanded", "subject_id": "shared:1", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.LOW,
    )
