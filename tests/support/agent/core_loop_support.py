from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.actions import ActionBinding, ActionRisk
from affordance_runtime.agent import Abort, RequestObservation, SelectAction
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
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
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


def shared_world(observation_id: str, enabled: bool, *, risk: ActionRisk = ActionRisk.LOW) -> WorldObservation:
    target = SemanticTarget(
        "shared-toggle",
        "button",
        "Shared state enabled" if enabled else "Enable shared state",
        {"enabled": enabled},
    )
    binding = ActionBinding(
        binding_id=f"binding:{observation_id}",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=f"revision:{observation_id}",
        target_fingerprint=f"fingerprint:{observation_id}",
        target_id=target.target_id,
        source_target_id=target.target_id,
        surface="dom",
        executor_id="dom",
        semantic_action="activate",
        primitive_action="click",
        effect_category="local_reversible",
        semantic_effects=("shared_state_enabled",),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        payload={"selector": "#shared"},
        risk=risk,
    )
    fact = StateFact(f"fact:{observation_id}:enabled", target.target_id, "enabled", enabled, observation_id)
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (target,),
        (fact,),
        (binding,),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def shared_task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
        risk_profile=RiskProfile.LOW,
    )


@dataclass
class ScriptedPolicy:
    decisions: list[object]

    async def decide(self, context):
        decision = self.decisions.pop(0)
        if decision == "first":
            return SelectAction(context.context_id, context.actions.options[0].action_id)
        if isinstance(decision, (SelectAction, RequestObservation, Abort)):
            return replace(decision, context_id=context.context_id)
        return decision


class SharedTaskEvaluator:
    async def evaluate(self, task, observation):
        enabled = bool(observation.targets[0].state.get("enabled"))
        fact_ref = observation.facts[0].fact_id
        criteria = tuple(
            CriterionEvaluation(
                criterion_id(item),
                CriterionEvaluationStatus.SATISFIED if enabled else CriterionEvaluationStatus.UNSATISFIED,
                (fact_ref,),
                "criterion satisfied" if enabled else "criterion unsatisfied",
            )
            for item in task.success_criteria
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if enabled else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if enabled else "shared state is disabled",
            criteria,
            (fact_ref,) if enabled else (),
        )


class SharedActionOutcomeProjector:
    async def evaluate(self, task, before, request, result, after):
        del task
        changed = before.targets[0].state.get("enabled") != after.targets[0].state.get("enabled")
        if result.dispatch_status == DispatchStatus.SENT_UNKNOWN and not changed:
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNKNOWN,
                LocalPostconditionStatus.UNKNOWN,
                EvidenceMethod.NONE,
                "effect remains unknown",
            )
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED if changed else ObservedChange.UNCHANGED,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.STRUCTURAL,
            "state changed" if changed else "state did not change",
            (after.facts[0].fact_id,),
        )


def sent_result(status: DispatchStatus = DispatchStatus.SENT, success: bool = True) -> ActionResult:
    error = None if success else ActionError.EXECUTION_FAILED
    return ActionResult("*", status, "dom", success, error)


# Compact aliases keep fixtures readable at call sites without importing an executable test module.
_world = shared_world
_task = shared_task
_sent = sent_result
