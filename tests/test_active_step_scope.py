from __future__ import annotations

import pytest

from affordance_runtime.planning import PlannerActionKind, PlannerProposal
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    RelationIntent,
    SourceReference,
    StateCriterion,
    StepActivityStatus,
    StepSpec,
)


def _source() -> SourceReference:
    return SourceReference(source_id="source:user", source_unit_id="unit:1")


def _criterion(subject: str) -> StateCriterion:
    return StateCriterion(
        criterion_id=f"criterion:{subject}",
        source_refs=(_source(),),
        subject=subject,
        relation=CriterionRelation.EQUALS,
        expected_value="Alice",
        evidence_policy=EvidencePolicy(
            minimum_strength=EvidenceStrength.INDEPENDENT,
            allowed_source_kinds=("dom_state",),
        ),
    )


def _step() -> StepSpec:
    return StepSpec(
        step_id="step:name",
        objective="Type Alice into Name",
        interaction=ElementIntent("semantic:name", (_source(),)),
        completion_criteria=(_criterion("semantic:name"),),
        source_refs=(_source(),),
    )


def _proposal(target_id: str) -> PlannerProposal:
    return PlannerProposal(
        proposal_id=f"proposal:{target_id}",
        based_on_task_revision=1,
        based_on_state_version=1,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=target_id,
        parameters={"text": "Alice"},
        expected_effects=("Name equals Alice",),
    )


def _drag_proposal(target_id: str, destination_id: str) -> PlannerProposal:
    return PlannerProposal(
        proposal_id=f"proposal:{target_id}:{destination_id}",
        based_on_task_revision=1,
        based_on_state_version=1,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id=target_id,
        destination_affordance_id=destination_id,
        parameters={},
        expected_effects=("Item moved",),
    )


def test_active_step_scope_allows_current_step_target() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    scope = ActiveStepScope.from_active_step(
        task_revision=1,
        evaluated_at_state_version=1,
        snapshot_id="snapshot-1",
        step=_step(),
        activity_status=StepActivityStatus.ACTIVE,
    )

    decision = scope.evaluate(_proposal("semantic:name"))

    assert decision.allowed is True
    assert decision.reason_code == "within_active_step_scope"


def test_value_transfer_scope_authorizes_typed_destination_not_source() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    step = StepSpec(
        step_id="step:transfer",
        objective="Transfer a sourced value",
        interaction=RelationIntent(
            source=ElementIntent("semantic:source", (_source(),)),
            destination=ElementIntent("semantic:destination", (_source(),)),
            relation="value_transfer",
        ),
        completion_criteria=(_criterion("semantic:destination"),),
        source_refs=(_source(),),
    )
    scope = ActiveStepScope.from_active_step(
        task_revision=1,
        evaluated_at_state_version=1,
        snapshot_id="snapshot-1",
        step=step,
        activity_status=StepActivityStatus.ACTIVE,
    )

    assert scope.evaluate(_proposal("semantic:destination")).allowed is True
    assert scope.evaluate(_proposal("semantic:source")).reason_code == "target_outside_active_step"


def test_active_step_scope_blocks_wrong_action_kind_for_current_step_target() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    scope = ActiveStepScope(
        task_revision=1,
        evaluated_at_state_version=1,
        snapshot_id="snapshot-1",
        activity_status=StepActivityStatus.ACTIVE,
        active_step_id="step:name",
        permitted_target_ids=("semantic:name",),
        permitted_action_kinds=(PlannerActionKind.TYPE_TEXT.value,),
    )
    proposal = PlannerProposal(
        proposal_id="proposal:activate:name",
        based_on_task_revision=1,
        based_on_state_version=1,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="semantic:name",
        parameters={},
    )

    decision = scope.evaluate(proposal)

    assert decision.allowed is False
    assert decision.reason_code == "action_outside_active_step"


def test_active_step_scope_blocks_drag_destination_outside_current_step() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    scope = ActiveStepScope(
        task_revision=1,
        evaluated_at_state_version=1,
        snapshot_id="snapshot-1",
        activity_status=StepActivityStatus.ACTIVE,
        active_step_id="step:drag",
        permitted_target_ids=("semantic:source",),
        permitted_action_kinds=(PlannerActionKind.DRAG.value,),
        permitted_destination_ids=("semantic:destination",),
    )

    decision = scope.evaluate(_drag_proposal("semantic:source", "semantic:other"))

    assert decision.allowed is False
    assert decision.reason_code == "destination_outside_active_step"


def test_active_step_scope_blocks_cross_step_target() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    scope = ActiveStepScope.from_active_step(
        task_revision=1,
        evaluated_at_state_version=1,
        snapshot_id="snapshot-1",
        step=_step(),
        activity_status=StepActivityStatus.ACTIVE,
    )

    decision = scope.evaluate(_proposal("semantic:submit"))

    assert decision.allowed is False
    assert decision.reason_code == "target_outside_active_step"
    assert decision.blocking_step_id == "step:name"


def test_active_step_scope_rejects_stale_proposal_identity() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    scope = ActiveStepScope.from_active_step(
        task_revision=2,
        evaluated_at_state_version=4,
        snapshot_id="snapshot-2",
        step=_step(),
        activity_status=StepActivityStatus.ACTIVE,
    )

    stale = PlannerProposal(
        proposal_id="proposal:stale",
        based_on_task_revision=1,
        based_on_state_version=4,
        snapshot_id="snapshot-2",
        action_kind=PlannerActionKind.FINISH,
    )

    decision = scope.evaluate(stale)

    assert decision.allowed is False
    assert decision.reason_code == "stale_task_revision"


def test_active_step_scope_does_not_permit_effectful_action_without_active_step() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    scope = ActiveStepScope.no_active_step(
        task_revision=1,
        evaluated_at_state_version=1,
        snapshot_id="snapshot-1",
        activity_status=StepActivityStatus.COMPLETED,
    )

    decision = scope.evaluate(_proposal("semantic:name"))

    assert decision.allowed is False
    assert decision.reason_code == "no_active_step"


def test_active_step_scope_requires_active_status_for_active_step() -> None:
    from affordance_runtime.active_step_scope import ActiveStepScope

    with pytest.raises(ValueError, match="active status"):
        ActiveStepScope.from_active_step(
            task_revision=1,
            evaluated_at_state_version=1,
            snapshot_id="snapshot-1",
            step=_step(),
            activity_status=StepActivityStatus.READY_NOT_ACTIVATED,
        )
