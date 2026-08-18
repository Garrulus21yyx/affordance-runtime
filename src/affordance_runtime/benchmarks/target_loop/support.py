"""Private fixed-case fixtures for target-loop internal attestations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.agent import Abort, RequestActionPage, SelectAction
from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    ActionOutcome,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.model.policy import (
    ModelBackedAgentPolicy,
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
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
            return ModelInvocationResult(
                failure=ModelFailure(ModelFailureKind.TIMEOUT, "fixture timeout", False),
                attempts=(ModelGenerationAttempt(1, "initial", "fixture", "failed"),),
                diagnostics={"policy_model_call_count": 1},
            )
        option = request.agent_context.actions.options[0]
        decision = SelectAction(request.context_id, option.action_id)
        metadata = ModelMetadata("fixture", "scripted", "response:1")
        return ModelInvocationResult(
            output=ResolvedModelDecision(decision, metadata),
            metadata=metadata,
            attempts=(ModelGenerationAttempt(1, "initial", "fixture", "accepted"),),
            diagnostics={"policy_model_call_count": 1},
        )


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
        criteria = tuple(
            CriterionEvaluation(criterion_id(item), status, (ref,), "current shared state")
            for item in task.success_criteria
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if expanded else TaskEvaluationStatus.INCOMPLETE,
            "shared state evaluated",
            criteria,
            (ref,) if expanded else (),
        )


class CurrentFactActionOutcomeProjector:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        before_values = {fact.predicate: fact.value for fact in before.facts}
        changed = next((fact for fact in after.facts if before_values.get(fact.predicate) != fact.value), None)
        if changed is None:
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNKNOWN,
                LocalPostconditionStatus.UNKNOWN,
                EvidenceMethod.NONE,
                "no exact obligation",
            )
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.STRUCTURAL,
            "relevant state changed",
            (changed.fact_id,),
        )


def shared_task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "expanded", "subject_id": "shared:1", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.LOW,
    )


def shared_world(identity: str, expanded: bool, surface: str) -> WorldObservation:
    # The scripted benchmark has semantic structural facts even when its action
    # route is named ``visual``; it is not a screenshot provider fixture.
    profile = {
        "dom": ObservationSourceProfile.dom(),
        "visual": ObservationSourceProfile.dom(),
        "wot": ObservationSourceProfile.wot(),
    }[surface]
    target = SemanticTarget("shared:1", "control", "shared control", {"expanded": expanded})
    fact = StateFact(f"fact:{identity}:expanded", target.target_id, "expanded", expanded, identity)
    binding = ActionBinding(
        f"binding:{identity}",
        identity,
        identity,
        f"revision:{identity}",
        f"fingerprint:{identity}",
        target.target_id,
        target.target_id,
        surface,
        surface,
        "activate",
        "invoke",
        "local_reversible",
        ("shared_state_enabled",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"backend_private": surface},
        risk=ActionRisk.LOW,
    )
    source = SurfaceObservation(
        identity,
        surface,
        f"revision:{identity}",
        profile,
        (target,),
        (fact,),
        (binding,),
    )
    return _fuse_source(source)


def shared_environment(surface: str, *, sent_unknown: bool = False) -> ScriptedEnvironment:
    status = DispatchStatus.SENT_UNKNOWN if sent_unknown else DispatchStatus.SENT
    return ScriptedEnvironment(
        initial_observation=shared_world(f"{surface}:before", False, surface),
        post_observations=(shared_world(f"{surface}:after", not sent_unknown, surface),),
        results=(
            ActionResult(
                "*", status, surface, not sent_unknown, ActionError.EXECUTION_FAILED if sent_unknown else None
            ),
        ),
    )


def paging_world(identity: str, expanded: bool) -> WorldObservation:
    targets, bindings = [], []
    for index in range(40):
        target = SemanticTarget(
            "shared:1" if index == 0 else f"target:{index:02d}",
            "control",
            f"control {index}",
            {"expanded": expanded},
        )
        targets.append(target)
        bindings.append(
            ActionBinding(
                f"binding:{identity}:{index}",
                identity,
                identity,
                f"revision:{identity}",
                f"fingerprint:{identity}:{index}",
                target.target_id,
                target.target_id,
                "dom",
                "dom",
                "activate",
                "click",
                "local_reversible",
                ("shared_state_enabled",),
                {"type": "object", "properties": {}, "additionalProperties": False},
                {"route": index},
                risk=ActionRisk.LOW,
            )
        )
    fact = StateFact(f"fact:{identity}:expanded", "shared:1", "expanded", expanded, identity)
    source = SurfaceObservation(
        identity,
        "dom",
        f"revision:{identity}",
        ObservationSourceProfile.dom(),
        tuple(targets),
        (fact,),
        tuple(bindings),
    )
    return _fuse_source(source)


def _fuse_source(source: SurfaceObservation) -> WorldObservation:
    result = WorldFusion().fuse((source,))
    if result.observation is None:
        raise ValueError(result.reason_code)
    return result.observation


def paging_environment() -> ScriptedEnvironment:
    return ScriptedEnvironment(
        initial_observation=paging_world("paging:before", False),
        post_observations=(paging_world("paging:after", True),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )


@dataclass
class StaleOnceEnvironment(ScriptedEnvironment):
    stale_checks: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        current = self.adapter.is_current

        def stale_once(request):
            self.stale_checks += 1
            return self.stale_checks > 1 and current(request)

        self.adapter.is_current = stale_once  # type: ignore[method-assign]


def stale_environment() -> StaleOnceEnvironment:
    return StaleOnceEnvironment(
        initial_observation=shared_world("stale:before", False, "dom"),
        independent_observations=(shared_world("stale:refresh", False, "dom"),),
        results=(ActionResult("*", DispatchStatus.NOT_SENT, "dom", False, ActionError.UNSUPPORTED_ACTION),),
    )


def low_risk_environment() -> ScriptedEnvironment:
    return ScriptedEnvironment(
        initial_observation=shared_world("low:before", False, "dom"),
        post_observations=(shared_world("low:middle", False, "dom"), shared_world("low:after", True, "dom")),
        results=(
            ActionResult("*", DispatchStatus.SENT, "dom", True),
            ActionResult("*", DispatchStatus.SENT, "dom", True),
        ),
    )


def confirmation_environment() -> ScriptedEnvironment:
    before = _risk_world("confirm:before", False, ActionRisk.MEDIUM)
    rebound = _risk_world("confirm:rebound", False, ActionRisk.MEDIUM)
    after = _risk_world("confirm:after", True, ActionRisk.MEDIUM)
    return ScriptedEnvironment(
        initial_observation=before,
        independent_observations=(rebound,),
        post_observations=(after,),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )


def confirmation_task() -> TaskGoal:
    return TaskGoal(
        "confirmed-enable",
        "Enable with confirmation",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "expanded", "subject_id": "shared:1", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.MEDIUM,
    )


def _risk_world(identity: str, expanded: bool, risk: ActionRisk) -> WorldObservation:
    world = shared_world(identity, expanded, "dom")
    source = world.sources[0]
    replacement = replace(source.bindings[0], risk=risk)
    fused = WorldFusion().fuse((replace(source, bindings=(replacement,)),))
    if fused.observation is None:
        raise ValueError(fused.reason_code)
    return fused.observation


@dataclass
class ForbiddenRouteEnvironment(ScriptedEnvironment):
    benchmark_forbidden_effect_attempts: int = field(default=0, init=False)

    async def execute(self, request):
        if "forbidden_effect" in request.selection.semantic_effects:
            self.benchmark_forbidden_effect_attempts += 1
        return await super().execute(request)


def forbidden_environment() -> ForbiddenRouteEnvironment:
    before = shared_world("forbidden:before", False, "dom")
    allowed = before.bindings[0]
    forbidden = ActionBinding(
        "binding:forbidden",
        before.observation_id,
        before.observation_id,
        "revision:forbidden:before",
        "fingerprint:forbidden",
        allowed.target_id,
        allowed.source_target_id,
        "dom",
        "dom",
        "activate",
        "click",
        "external",
        ("forbidden_effect",),
        allowed.parameter_schema,
        {"route": "forbidden"},
        risk=ActionRisk.HIGH,
    )
    source = before.sources[0]
    local_allowed = source.bindings[0]
    local_forbidden = replace(
        forbidden,
        world_observation_id=source.observation_id,
        target_id=local_allowed.target_id,
        source_target_id=local_allowed.source_target_id,
        source_observation_id=source.observation_id,
        source_revision=source.revision,
    )
    fused = WorldFusion().fuse((replace(source, bindings=(local_allowed, local_forbidden)),))
    if fused.observation is None:
        raise ValueError(fused.reason_code)
    before = fused.observation
    return ForbiddenRouteEnvironment(
        initial_observation=before,
        post_observations=(shared_world("forbidden:after", True, "dom"),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )


def forbidden_task() -> TaskGoal:
    return TaskGoal(
        "forbidden-route",
        "Use only allowed effect",
        allowed_effects=("shared_state_enabled",),
        forbidden_effects=("forbidden_effect",),
        success_criteria=({"id": "expanded", "subject_id": "shared:1", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.LOW,
    )
