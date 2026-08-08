import pytest

from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionError, ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.model_boundary.evaluator_views import (
    build_model_action_evaluation_view,
    build_model_task_evaluation_view,
)
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import CoverageState, SemanticTarget, StateFact, WorldObservation


def _world() -> WorldObservation:
    return WorldObservation(
        "world:1",
        (SemanticTarget("target:1", "control", "Target"),),
        (StateFact("fact:1", "target:1", "enabled", True, "world:1"),),
        (),
        {"dom": CoverageState.COMPLETE},
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "task:1",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "enabled", "predicate": "enabled"},),
        requested_outputs=("receipt",),
        risk_profile=RiskProfile.LOW,
    )


def test_model_failure_is_bounded_typed_data_not_an_exception() -> None:
    failure = ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out" * 40, True)

    assert len(failure.reason) <= 240
    assert not isinstance(failure, Exception)
    with pytest.raises(ValueError, match="sensitive"):
        ModelFailure(ModelFailureKind.INVALID_RESPONSE, "Authorization: Bearer raw-secret", False)


def test_model_evaluator_views_exclude_bound_route_backend_and_adapter_evidence() -> None:
    world = _world()
    result = ActionResult(
        "request:private",
        DispatchStatus.NOT_SENT,
        "dom-private-backend",
        False,
        ActionError.STALE_BINDING,
        {"selector": "#private", "credential": "raw-secret"},
    )
    view = build_model_action_evaluation_view(
        _task(),
        world,
        world,
        ActionIntent("activate", "target:1", {"mode": "on"}),
        result,
        WorldEvidenceIndex.from_observation(world),
    )

    assert view.intent.semantic_action == "activate"
    assert view.result.dispatch_status == DispatchStatus.NOT_SENT
    assert view.result.public_error_category == ActionError.STALE_BINDING
    assert view.available_evidence_refs == ("fact:1",)
    assert view.before.facts.items[0].fact_ref == "fact:1"
    assert view.after.facts.items[0].fact_ref == "fact:1"
    representation = repr(view)
    for private in ("request:private", "dom-private-backend", "#private", "raw-secret", "adapter_evidence"):
        assert private not in representation


def test_model_task_evaluation_view_contains_public_criteria_outputs_and_evidence_only() -> None:
    world = _world()
    view = build_model_task_evaluation_view(
        _task(),
        world,
        WorldEvidenceIndex.from_observation(world),
    )

    assert view.task.success_criteria[0].criterion_id == "enabled"
    assert view.requested_output_ids == ("receipt",)
    assert view.available_evidence_refs == ("fact:1",)
    assert "required_output_integrity" not in repr(view)
