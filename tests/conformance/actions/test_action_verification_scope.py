from types import SimpleNamespace

from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_action_outcome
from affordance_runtime.execution import ActionIntent
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)


def _world(identity: str, enabled: bool):
    target = SemanticTarget("target:1", "button", "Enable", {"enabled": enabled})
    source = SurfaceObservation(
        f"source:{identity}",
        "dom",
        f"revision:{identity}",
        ObservationSourceProfile.dom(),
        (target,),
        (StateFact(f"fact:{identity}:enabled", target.target_id, "enabled", enabled, f"source:{identity}"),),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _request(expected_outcome: str = ""):
    return SimpleNamespace(
        request_id="request:1",
        intent=ActionIntent("activate", "target:1", expected_outcome=expected_outcome),
        selection=SimpleNamespace(),
    )


def test_task_goal_criterion_no_longer_promotes_action_local_result() -> None:
    task = TaskGoal(
        "task:enabled",
        "Enable target",
        success_criteria=({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True},),
    )
    before = _world("before", False)
    after = _world("after", True)
    proposal = ActionOutcome(
        "request:1",
        before.observation_id,
        after.observation_id,
        ObservedChange.CHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.STRUCTURAL,
        "local structural change only",
        ("fact:after:enabled",),
    )

    result = validate_action_outcome(
        proposal, task, _request(), before, after, WorldEvidenceIndex.from_observation(after),
    )

    assert result.observed_change is ObservedChange.CHANGED
    assert result.local_postcondition is LocalPostconditionStatus.UNKNOWN


def test_unresolved_natural_language_expected_outcome_remains_unknown() -> None:
    task = TaskGoal("task:nl", "Open the useful result")
    before = _world("before", False)
    after = _world("after", True)
    request = _request("the account menu is open")
    proposal = ActionOutcome(
        "request:1",
        before.observation_id,
        after.observation_id,
        ObservedChange.CHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.STRUCTURAL,
        "generic activation changed local state",
        ("fact:after:enabled",),
    )

    result = validate_action_outcome(
        proposal, task, request, before, after, WorldEvidenceIndex.from_observation(after),
    )

    assert result.observed_change is ObservedChange.CHANGED
    assert result.local_postcondition is LocalPostconditionStatus.UNKNOWN


def test_task_evaluator_remains_completion_authority() -> None:
    task = TaskGoal(
        "task:enabled",
        "Enable target",
        success_criteria=({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True},),
    )
    after = _world("after", True)

    evaluation = __import__("asyncio").run(ProductionTaskEvaluator().evaluate(task, after))

    assert evaluation.status is TaskEvaluationStatus.COMPLETE
