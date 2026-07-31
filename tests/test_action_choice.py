from __future__ import annotations

import asyncio

import pytest

from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.interaction_grounding import GroundingResult, GroundingStatus
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    ElementOperationKind,
    InteractionIntent,
    RegionIntent,
    RelationIntent,
    SourceReference,
    StateCriterion,
    StepActivityStatus,
    StepSpec,
    ValueExpr,
    ValueExprKind,
    interaction_for_state,
)
from affordance_runtime.unified_observation import (
    UnifiedObservation,
    UnifiedObservationTarget,
)


def _source() -> SourceReference:
    return SourceReference(source_id="source:user", source_unit_id="unit:1")


def _policy() -> EvidencePolicy:
    return EvidencePolicy(
        minimum_strength=EvidenceStrength.INDEPENDENT,
        allowed_source_kinds=("dom_state",),
    )


def _criterion(
    *,
    criterion_id: str,
    subject: str,
    relation: CriterionRelation = CriterionRelation.EQUALS,
    expected_value: str | bool | int | float | None = "Alice",
) -> StateCriterion:
    return StateCriterion(
        criterion_id=criterion_id,
        source_refs=(_source(),),
        subject=subject,
        relation=relation,
        expected_value=expected_value,
        evidence_policy=_policy(),
    )


def _step(
    *,
    criterion: StateCriterion,
    step_id: str = "step:1",
    interaction: InteractionIntent | None = None,
) -> StepSpec:
    return StepSpec(
        step_id=step_id,
        objective="Complete the current step",
        interaction=interaction or ElementIntent(criterion.subject, (_source(),)),
        completion_criteria=(criterion,),
        source_refs=(_source(),),
    )


def _observation(*targets: UnifiedObservationTarget) -> UnifiedObservation:
    return UnifiedObservation(
        snapshot_id="snapshot:1",
        page_revision="page:1",
        environment_revision="env:1",
        observed_text="",
        targets=targets,
    )


def _scope(step: StepSpec) -> ActiveStepScope:
    return ActiveStepScope.from_active_step(
        task_revision=1,
        evaluated_at_state_version=7,
        snapshot_id="snapshot:1",
        step=step,
        activity_status=StepActivityStatus.ACTIVE,
    )


def test_action_choice_builder_requires_calibrated_non_dom_region_evidence() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:spatial-point",
        subject="coordinate (2,-2)",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RegionIntent(
            "coordinate (2,-2)",
            "spatial.point.current_geometry",
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:dom-lookalike",
                surface="dom",
                role="point",
                label="coordinate (2,-2)",
                supported_actions=("point_activate",),
                state={"spatial_evidence": "calibrated_current_geometry"},
                confidence=1.0,
            ),
            UnifiedObservationTarget(
                target_id="semantic:visual-point",
                surface="visual",
                role="point",
                label="coordinate (2,-2)",
                supported_actions=("point_activate",),
                state={"spatial_evidence": "calibrated_current_geometry"},
                confidence=0.95,
                source_refs=("artifact:screenshot-current",),
            ),
            UnifiedObservationTarget(
                target_id="semantic:wrong-sign-point",
                surface="svg",
                role="point",
                label="coordinate (-2,-2)",
                supported_actions=("point_activate",),
                state={"spatial_evidence": "calibrated_current_geometry"},
                confidence=1.0,
                source_refs=("artifact:svg-current",),
            ),
        ),
        capabilities=frozenset({"spatial.point.current_geometry"}),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].action_kind == PlannerActionKind.POINT_ACTIVATE
    assert result.choices[0].target_id == "semantic:visual-point"


def test_action_choice_builder_does_not_fabricate_region_without_capability() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:spatial-point",
        subject="renamed spatial mark",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RegionIntent(
            "renamed spatial mark",
            "spatial.point.current_geometry",
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:visual-point",
                surface="svg",
                role="point",
                label="renamed spatial mark",
                supported_actions=("point_activate",),
                state={"spatial_evidence": "calibrated_current_geometry"},
                confidence=1.0,
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "interaction_capability_missing"


def test_action_choice_builder_rejects_uncalibrated_region_geometry() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:spatial-point",
        subject="renamed spatial mark",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RegionIntent(
            "renamed spatial mark",
            "spatial.point.current_geometry",
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:visual-point",
                surface="visual",
                role="point",
                label="renamed spatial mark",
                supported_actions=("point_activate",),
                state={},
                confidence=0.95,
                source_refs=("artifact:screenshot-current",),
            )
        ),
        capabilities=frozenset({"spatial.point.current_geometry"}),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "region_calibrated_geometry_missing"


def test_action_choice_builder_creates_exact_type_text_choice() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:name",
        subject="semantic:name",
        expected_value="Alice",
    )
    step = _step(criterion=criterion, step_id="step:name")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:name",
                surface="dom",
                role="textbox",
                label="Name",
                supported_actions=("type_text",),
                state={"value": ""},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.TYPE_TEXT
    assert choice.target_id == "semantic:name"
    assert choice.parameters == {"text": "Alice"}
    assert choice.criterion_ids == ("criterion:name",)
    assert choice.active_step_id == "step:name"


def test_action_choice_builder_creates_slider_press_key_choice() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:slider",
        subject="semantic:slider",
        expected_value=7,
    )
    step = _step(criterion=criterion, step_id="step:slider")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:slider",
                surface="dom",
                role="slider",
                label="Volume",
                supported_actions=("press_key",),
                state={"value": 5},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.PRESS_KEY
    assert choice.parameters == {"key": "ArrowRight"}


def test_action_choice_builder_emits_typed_focus_for_a_focusable_element() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:focused",
        subject="renamed editor",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "renamed editor",
            (_source(),),
            role="textbox",
            operation=ElementOperationKind.FOCUS,
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:renamed-editor",
                surface="dom",
                role="textbox",
                label="renamed editor",
                supported_actions=("focus", "type_text"),
                state={"focused": False},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].action_kind == PlannerActionKind.FOCUS
    assert not result.choices[0].parameters
    assert result.choices[0].target_id == "semantic:renamed-editor"


def test_action_choice_builder_creates_slider_choice_from_numeric_string_value() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:slider",
        subject="semantic:slider",
        expected_value="7",
    )
    step = _step(criterion=criterion, step_id="step:slider")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:slider",
                surface="dom",
                role="slider",
                label="Volume",
                supported_actions=("press_key",),
                state={"value": "5"},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.PRESS_KEY
    assert choice.parameters == {"key": "ArrowRight"}
    assert choice.target_id == "semantic:slider"


def test_action_choice_builder_uses_slider_context_text_for_direction() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:slider",
        subject="semantic:slider",
        expected_value="-3",
    )
    step = _step(criterion=criterion, step_id="step:slider")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:slider",
                surface="dom",
                role="slider",
                label="Value",
                supported_actions=("press_key",),
                state={"context_text": "-9", "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.PRESS_KEY
    assert choice.parameters == {"key": "ArrowRight"}
    assert choice.target_id == "semantic:slider"


def test_action_choice_builder_creates_slider_direction_without_current_value() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:slider",
        subject="semantic:slider",
        expected_value="-3",
    )
    step = _step(criterion=criterion, step_id="step:slider")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:slider",
                surface="dom",
                role="slider",
                label="Volume",
                supported_actions=("press_key",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.PRESS_KEY
    assert choice.parameters == {"key": "ArrowLeft"}
    assert choice.target_id == "semantic:slider"


def test_action_choice_builder_returns_typed_failure_for_no_feasible_action() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure
    from affordance_runtime.recovery_protocol import FailureKind

    criterion = _criterion(
        criterion_id="criterion:name",
        subject="semantic:name",
        expected_value="Alice",
    )
    step = _step(criterion=criterion, step_id="step:name")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:name",
                surface="dom",
                role="textbox",
                label="Name",
                supported_actions=("activate",),
                state={"value": ""},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.kind == FailureKind.NO_FEASIBLE_ACTION
    assert result.reason_code == "no_feasible_action_choice"


def test_action_choice_builder_distinguishes_unresolved_target_from_no_action() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure
    from affordance_runtime.recovery_protocol import FailureKind

    criterion = _criterion(
        criterion_id="criterion:legacy",
        subject="target",
        expected_value="clicked",
    )
    step = _step(criterion=criterion, step_id="step:legacy")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:target",
                surface="dom",
                role="button",
                label="Different",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.kind == FailureKind.GROUNDING_AMBIGUOUS
    assert result.reason_code == "interaction_target_absent"


def test_action_choice_builder_resolves_unique_exact_label_subject() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:target",
        subject="target",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=True,
    )
    step = _step(criterion=criterion, step_id="step:target")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:target-button",
                surface="dom",
                role="button",
                label="Target",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].target_id == "semantic:target-button"


@pytest.mark.parametrize(
    "subject",
    (
        "Confirm button",
        "button Confirm",
        "confirm_button",
        "button:label='Confirm'",
        "button:label:Confirm",
    ),
)
def test_action_choice_builder_binds_generic_label_and_role_identity(subject: str) -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:confirm",
        subject=subject,
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=True,
    )
    step = _step(
        criterion=criterion,
        step_id="step:confirm",
        interaction=interaction_for_state(
            subject,
            CriterionRelation.IS_COMPLETED,
            None,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:confirm",
                surface="dom",
                role="button",
                label="Confirm",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.grounding.targets[0].target_id == "semantic:confirm"
    assert result.choices[0].action_kind == PlannerActionKind.ACTIVATE


def test_action_choice_builder_binds_role_only_state_identifier() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:level",
        subject="slider_value_7",
        expected_value=7,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:level",
                surface="dom",
                role="slider",
                label="Level",
                supported_actions=("press_key",),
                state={"value": 5},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:level"
    assert result.choices[0].parameters == {"key": "ArrowRight"}


def test_action_choice_builder_binds_typed_role_ordinal_after_reordering() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:second",
        subject="checkbox_2_state",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:first",
                surface="dom",
                role="checkbox",
                label="Renamed A",
                supported_actions=("activate",),
                state={"checked": False},
            ),
            UnifiedObservationTarget(
                target_id="semantic:second",
                surface="dom",
                role="checkbox",
                label="Renamed B",
                supported_actions=("activate",),
                state={"checked": False},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:second"


@pytest.mark.parametrize("subject", ("radio_button_2", "radio_button[2]"))
def test_action_choice_builder_binds_compound_role_ordinal_after_reordering(
    subject: str,
) -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:second-radio",
        subject=subject,
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:renamed-first",
                surface="dom",
                role="radio",
                label="Renamed first",
                supported_actions=("activate",),
                state={"checked": False},
            ),
            UnifiedObservationTarget(
                target_id="semantic:renamed-second",
                surface="dom",
                role="radio",
                label="Renamed second",
                supported_actions=("activate",),
                state={"checked": False},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:renamed-second"


def test_action_choice_builder_emits_explicit_enabling_choice_for_missing_target() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet, ChoiceRole

    criterion = _criterion(
        criterion_id="criterion:report",
        subject="Quarterly report",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "Quarterly report",
            (_source(),),
            role="link",
            enabler=ElementIntent("Reports", (_source(),), role="button"),
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:reports",
                surface="dom",
                role="button",
                label="Reports",
                supported_actions=("activate",),
                state={"expanded": False, "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].target_id == "semantic:reports"
    assert result.choices[0].role == ChoiceRole.ENABLING
    assert result.choices[0].criterion_ids == ()


def test_action_choice_builder_liveness_blocks_satisfied_enabler() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:report",
        subject="Quarterly report",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "Quarterly report",
            (_source(),),
            role="link",
            enabler=ElementIntent("Reports", (_source(),), role="button"),
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:reports",
                surface="dom",
                role="button",
                label="Reports",
                supported_actions=("activate",),
                state={"expanded": True, "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "interaction_enabler_already_satisfied"


def test_action_choice_builder_prefers_direct_target_over_explicit_enabler() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet, ChoiceRole

    criterion = _criterion(
        criterion_id="criterion:report",
        subject="Quarterly report",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "Quarterly report",
            (_source(),),
            role="link",
            enabler=ElementIntent("Reports", (_source(),), role="button"),
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:reports",
                surface="dom",
                role="button",
                label="Reports",
                supported_actions=("activate",),
                state={"expanded": False, "enabled": True, "visible": True},
            ),
            UnifiedObservationTarget(
                target_id="semantic:quarterly-report",
                surface="dom",
                role="link",
                label="Quarterly report",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].target_id == "semantic:quarterly-report"
    assert result.choices[0].role == ChoiceRole.DIRECT
    assert result.choices[0].criterion_ids == ("criterion:report",)


def test_action_choice_builder_scopes_ordinal_to_typed_collection_after_reordering() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:second-result",
        subject="result",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "result",
            (_source(),),
            role="link",
            ordinal=2,
            match_by_role=True,
            collection_scope="primary-results",
            collection_cardinality=2,
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:secondary-first",
                surface="dom",
                role="link",
                label="Renamed alpha",
                supported_actions=("activate",),
                state={"collection_owner": "secondary-results"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:primary-first",
                surface="dom",
                role="link",
                label="Renamed beta",
                supported_actions=("activate",),
                state={"collection_owner": "primary-results", "collection_position": 1},
            ),
            UnifiedObservationTarget(
                target_id="semantic:secondary-second",
                surface="dom",
                role="link",
                label="Renamed gamma",
                supported_actions=("activate",),
                state={"collection_owner": "secondary-results"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:primary-second",
                surface="dom",
                role="link",
                label="Renamed delta",
                supported_actions=("activate",),
                state={"collection_owner": "primary-results", "collection_position": 2},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:primary-second"


def test_action_choice_builder_fails_closed_on_collection_cardinality_mismatch() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure
    from affordance_runtime.recovery_protocol import FailureKind

    criterion = _criterion(
        criterion_id="criterion:second-result",
        subject="result",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "result",
            (_source(),),
            role="link",
            ordinal=2,
            match_by_role=True,
            collection_scope="primary-results",
            collection_cardinality=3,
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:primary-first",
                surface="dom",
                role="link",
                label="One",
                supported_actions=("activate",),
                state={"collection_owner": "primary-results"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:primary-second",
                surface="dom",
                role="link",
                label="Two",
                supported_actions=("activate",),
                state={"collection_owner": "primary-results"},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.kind == FailureKind.GROUNDING_AMBIGUOUS
    assert result.reason_code == "interaction_collection_cardinality_mismatch"


def test_action_choice_builder_creates_typed_tree_expansion_choice() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:section-expanded",
        subject="Reports",
        relation=CriterionRelation.IS_EXPANDED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent("Reports", (_source(),), role="treeitem"),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:reports",
                surface="dom",
                role="treeitem",
                label="Reports",
                supported_actions=("activate",),
                state={"expanded": False, "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].action_kind == PlannerActionKind.ACTIVATE
    assert result.choices[0].target_id == "semantic:reports"


def test_action_choice_builder_emits_typed_scroll_enabler_until_boundary() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet, ChoiceRole

    criterion = _criterion(
        criterion_id="criterion:final-paragraph",
        subject="Final paragraph",
        relation=CriterionRelation.IS_VISIBLE,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "Final paragraph",
            (_source(),),
            enabler=ElementIntent(
                "Document",
                (_source(),),
                role="scroll_region",
                operation=ElementOperationKind.SCROLL_FORWARD,
            ),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:document-scroll",
                surface="dom",
                role="scroll_region",
                label="Document",
                supported_actions=("press_key",),
                state={
                    "scroll_top": 100,
                    "scroll_height": 500,
                    "client_height": 100,
                    "enabled": True,
                    "visible": True,
                },
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].action_kind == PlannerActionKind.PRESS_KEY
    assert result.choices[0].parameters == {"key": "PageDown"}
    assert result.choices[0].role == ChoiceRole.ENABLING
    assert result.choices[0].criterion_ids == ()


def test_action_choice_builder_liveness_blocks_scroll_enabler_at_boundary() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:final-paragraph",
        subject="Final paragraph",
        relation=CriterionRelation.IS_VISIBLE,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=ElementIntent(
            "Final paragraph",
            (_source(),),
            enabler=ElementIntent(
                "Document",
                (_source(),),
                role="scroll_region",
                operation=ElementOperationKind.SCROLL_FORWARD,
            ),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:document-scroll",
                surface="dom",
                role="scroll_region",
                label="Document",
                supported_actions=("press_key",),
                state={
                    "scroll_top": 400,
                    "scroll_height": 500,
                    "client_height": 100,
                    "enabled": True,
                    "visible": True,
                },
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "interaction_enabler_already_satisfied"


def test_action_choice_builder_transfers_exact_grounded_control_value() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:destination-value",
        subject="Destination",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RelationIntent(
            source=ElementIntent("Source", (_source(),), role="textbox"),
            destination=ElementIntent("Destination", (_source(),), role="textbox"),
            relation="value_transfer",
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=UnifiedObservation(
            snapshot_id="snapshot:1",
            page_revision="page:1",
            environment_revision="env:1",
            observed_text="Unrelated page text must never be transferred",
            targets=(
                UnifiedObservationTarget(
                    target_id="semantic:renamed-source",
                    surface="dom",
                    role="textbox",
                    label="Source",
                    supported_actions=("type_text",),
                    state={"control_value": "Exact source value"},
                ),
                UnifiedObservationTarget(
                    target_id="semantic:renamed-destination",
                    surface="dom",
                    role="textbox",
                    label="Destination",
                    supported_actions=("type_text",),
                    state={"control_value": ""},
                ),
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.TYPE_TEXT
    assert choice.target_id == "semantic:renamed-destination"
    assert choice.destination_id == ""
    assert choice.parameters == {"text": "Exact source value"}
    assert choice.criterion_ids == ("criterion:destination-value",)


def test_action_choice_builder_resolves_relative_drag_from_observed_collection_order() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:order",
        subject="Delta",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RelationIntent(
            source=ElementIntent("Delta", (_source(),)),
            destination=None,
            relation="relative_position",
            destination_offset=1,
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:third",
                surface="dom",
                role="listitem",
                label="Echo",
                supported_actions=("drag",),
                state={"collection_position": 3, "container_context": "queue"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:source",
                surface="dom",
                role="listitem",
                label="Delta",
                supported_actions=("drag",),
                state={"collection_position": 2, "container_context": "queue"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:unrelated-third",
                surface="dom",
                role="listitem",
                label="Other",
                supported_actions=("drag",),
                state={"collection_position": 3, "container_context": "other"},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].action_kind == PlannerActionKind.DRAG
    assert result.choices[0].target_id == "semantic:source"
    assert result.choices[0].destination_id == "semantic:third"


def test_action_choice_builder_resolves_absolute_position_from_observed_collection() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:absolute-order",
        subject="Vanya",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RelationIntent(
            source=ElementIntent("Vanya", (_source(),)),
            destination=None,
            relation="absolute_position",
            destination_ordinal=4,
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:fourth",
                surface="dom",
                role="listitem",
                label="Fourth renamed item",
                supported_actions=("drag",),
                state={"collection_position": 4, "container_context": "queue"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:vanya",
                surface="dom",
                role="listitem",
                label="Vanya",
                supported_actions=("drag",),
                state={"collection_position": 2, "container_context": "queue"},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:vanya"
    assert result.choices[0].destination_id == "semantic:fourth"


def test_action_choice_builder_resolves_size_relation_from_typed_observed_state() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:inside",
        subject="smaller box",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            "smaller box",
            CriterionRelation.HAS_CHANGED,
            None,
            (_source(),),
            interaction_relation=("drag_to", "larger box", None, None),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:large-renamed",
                surface="dom",
                role="generic",
                label="L",
                supported_actions=("drag",),
                state={"relative_size": "largest"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:small-renamed",
                surface="dom",
                role="generic",
                label="s",
                supported_actions=("drag",),
                state={"relative_size": "smallest"},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:small-renamed"
    assert result.choices[0].destination_id == "semantic:large-renamed"


def test_action_choice_builder_fails_closed_for_same_or_ambiguous_relation_endpoints() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:relation",
        subject="tile",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RelationIntent(
            source=ElementIntent("tile", (_source(),)),
            destination=ElementIntent("tile", (_source(),)),
            relation="drag_to",
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:tile",
                surface="dom",
                role="generic",
                label="tile",
                supported_actions=("drag",),
                state={},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "relation_endpoints_not_distinct"


def test_action_choice_builder_distinguishes_transfer_endpoints_by_element_kind() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    source_interaction = interaction_for_state(
        "textarea",
        CriterionRelation.IS_AVAILABLE,
        None,
        (_source(),),
    )
    destination_interaction = interaction_for_state(
        "textbox",
        CriterionRelation.EQUALS,
        None,
        (_source(),),
    )
    assert isinstance(source_interaction, ElementIntent)
    assert source_interaction.target == "textarea"
    assert source_interaction.role == "textbox"
    assert isinstance(destination_interaction, ElementIntent)
    criterion = _criterion(
        criterion_id="criterion:destination-value",
        subject="textbox",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RelationIntent(
            source=source_interaction,
            destination=destination_interaction,
            relation="value_transfer",
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:source-with-unrelated-label",
                surface="dom",
                role="textbox",
                label="Alpha",
                supported_actions=("type_text",),
                state={"element_tag": "textarea", "control_value": "Exact source value"},
            ),
            UnifiedObservationTarget(
                target_id="semantic:destination-with-unrelated-label",
                surface="dom",
                role="textbox",
                label="Beta",
                supported_actions=("type_text",),
                state={"element_tag": "input", "control_value": ""},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    assert result.choices[0].target_id == "semantic:destination-with-unrelated-label"
    assert result.choices[0].parameters == {"text": "Exact source value"}


@pytest.mark.parametrize(
    "source_state",
    (
        {},
        {"control_value": "partial", "control_value_suffix": "secret suffix"},
        {"control_value": "secret", "input_type": "password"},
    ),
)
def test_action_choice_builder_rejects_unavailable_or_unsafe_transfer_value(
    source_state: dict[str, object],
) -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:destination-value",
        subject="Destination",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=RelationIntent(
            source=ElementIntent("Source", (_source(),), role="textbox"),
            destination=ElementIntent("Destination", (_source(),), role="textbox"),
            relation="value_transfer",
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:source",
                surface="dom",
                role="textbox",
                label="Source",
                supported_actions=("type_text",),
                state=source_state,
            ),
            UnifiedObservationTarget(
                target_id="semantic:destination",
                surface="dom",
                role="textbox",
                label="Destination",
                supported_actions=("type_text",),
                state={"control_value": ""},
            ),
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "no_feasible_action_choice"


def test_action_choice_builder_binds_label_role_state_identifier() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:archive",
        subject="archive_button_state",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:archive",
                surface="dom",
                role="button",
                label="Archive",
                supported_actions=("activate",),
                state={"enabled": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:archive"


def test_action_choice_builder_binds_role_value_descriptor() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:entry",
        subject="text_field:Orchid",
        expected_value="Orchid",
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:entry",
                surface="dom",
                role="textbox",
                label="",
                supported_actions=("type_text",),
                state={"value": ""},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:entry"
    assert result.choices[0].parameters == {"text": "Orchid"}


@pytest.mark.parametrize(
    ("subject", "expected"),
    (
        ("date_field", "2031-09-17"),
        ("text_input_field:Cobalt", "Cobalt"),
    ),
)
def test_action_choice_builder_normalizes_composite_editable_roles(
    subject: str,
    expected: str,
) -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:editable",
        subject=subject,
        expected_value=expected,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:renamed-entry",
                surface="dom",
                role="textbox",
                label="Renamed entry",
                supported_actions=("type_text",),
                state={"value": ""},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:renamed-entry"
    assert result.choices[0].parameters == {"text": expected}


@pytest.mark.parametrize("observed_role", ("generic", "button"))
def test_action_choice_builder_uses_exact_label_and_compatible_capability(
    observed_role: str,
) -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:overview",
        subject="link:label:Overview",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:overview",
                surface="dom",
                role=observed_role,
                label="Overview",
                supported_actions=("activate",),
                state={"enabled": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:overview"


def test_action_choice_builder_rejects_roleless_capability_without_identity_match() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:overview",
        subject="link:label:Overview",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:unrelated",
                surface="dom",
                role="generic",
                label="Unrelated",
                supported_actions=("activate",),
                state={"enabled": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "interaction_target_absent"


def test_action_choice_builder_uses_unique_semantic_label_within_typed_role() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:close",
        subject="dialog_box_close_button",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:titlebar",
                surface="dom",
                role="button",
                label="ui-dialog-titlebar",
                supported_actions=("activate",),
                state={"enabled": True},
            ),
            UnifiedObservationTarget(
                target_id="semantic:close",
                surface="dom",
                role="button",
                label="Close",
                supported_actions=("activate",),
                state={"enabled": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].target_id == "semantic:close"


def test_action_choice_builder_does_not_guess_between_same_role_targets() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure

    criterion = _criterion(
        criterion_id="criterion:close",
        subject="dialog_box_close_button",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=None,
    )
    step = _step(
        criterion=criterion,
        interaction=interaction_for_state(
            criterion.subject,
            criterion.relation,
            criterion.expected_value,
            (_source(),),
        ),
    )
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            *(
                UnifiedObservationTarget(
                    target_id=f"semantic:button:{index}",
                    surface="dom",
                    role="button",
                    label=label,
                    supported_actions=("activate",),
                    state={"enabled": True},
                )
                for index, label in enumerate(("X", "Cancel"), start=1)
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "interaction_target_ambiguous"


def test_action_choice_builder_creates_has_changed_activation_choice_for_button() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:target",
        subject="target",
        relation=CriterionRelation.HAS_CHANGED,
        expected_value=None,
    )
    step = _step(criterion=criterion, step_id="step:target")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:target-button",
                surface="dom",
                role="button",
                label="Target",
                supported_actions=("click",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.ACTIVATE
    assert choice.target_id == "semantic:target-button"
    assert choice.parameters == {}


def test_action_choice_builder_creates_checkbox_activation_choice() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:checkbox",
        subject="semantic:checkbox",
        relation=CriterionRelation.IS_CHECKED,
        expected_value=True,
    )
    step = _step(criterion=criterion, step_id="step:checkbox")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:checkbox",
                surface="dom",
                role="checkbox",
                label="Subscribe",
                supported_actions=("activate",),
                state={"checked": False, "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.ACTIVATE
    assert choice.target_id == "semantic:checkbox"
    assert choice.parameters == {}


def test_action_choice_builder_skips_already_checked_checkbox() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure
    from affordance_runtime.recovery_protocol import FailureKind

    criterion = _criterion(
        criterion_id="criterion:checkbox",
        subject="semantic:checkbox",
        relation=CriterionRelation.IS_CHECKED,
        expected_value=True,
    )
    step = _step(criterion=criterion, step_id="step:checkbox")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:checkbox",
                surface="dom",
                role="checkbox",
                label="Subscribe",
                supported_actions=("activate",),
                state={"checked": True, "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.kind == FailureKind.NO_FEASIBLE_ACTION


def test_action_choice_builder_creates_select_option_choice() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:option",
        subject="semantic:select",
        relation=CriterionRelation.IS_SELECTED,
        expected_value="Blue",
    )
    step = _step(
        criterion=criterion,
        step_id="step:select",
        interaction=CollectionIntent(
            ElementIntent("Color", (_source(),), role="combobox"),
            ValueExpr(ValueExprKind.LITERAL, ("Blue",), (_source(),)),
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:select",
                surface="dom",
                role="combobox",
                label="Color",
                supported_actions=("select_option",),
                state={"selected_options": ("Red",), "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.SELECT_OPTION
    assert choice.target_id == "semantic:select"
    assert choice.parameters == {"option": "Blue"}


def test_action_choice_builder_binds_multiple_typed_collection_members() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:members",
        subject="legacy collection completion text",
        relation=CriterionRelation.IS_SELECTED,
        expected_value="Lumen, Vela",
    )
    step = _step(
        criterion=criterion,
        step_id="step:members",
        interaction=CollectionIntent(
            ElementIntent("Results", (_source(),), role="combobox"),
            ValueExpr(ValueExprKind.LITERAL, ("Lumen", "Vela"), (_source(),)),
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:results",
                surface="dom",
                role="combobox",
                label="Results",
                supported_actions=("select_option",),
                state={"selected_options": (), "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    assert result.choices[0].parameters == {"option": ["Lumen", "Vela"]}


def test_action_choice_builder_does_not_treat_available_options_as_selected() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:option",
        subject="list",
        relation=CriterionRelation.IS_SELECTED,
        expected_value="Ertha",
    )
    step = _step(
        criterion=criterion,
        step_id="step:select",
        interaction=CollectionIntent(
            ElementIntent("options", (_source(),), role="combobox"),
            ValueExpr(ValueExprKind.LITERAL, ("Ertha",), (_source(),)),
        ),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:options",
                surface="dom",
                role="combobox",
                label="options",
                supported_actions=("select_option",),
                state={"selected_options": ("Ertha",), "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.SELECT_OPTION
    assert choice.target_id == "semantic:options"
    assert choice.parameters == {"option": "Ertha"}


def test_action_choice_builder_skips_explicitly_selected_value() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceFailure
    from affordance_runtime.recovery_protocol import FailureKind

    criterion = _criterion(
        criterion_id="criterion:option",
        subject="semantic:select",
        relation=CriterionRelation.IS_SELECTED,
        expected_value="Blue",
    )
    step = _step(criterion=criterion, step_id="step:select")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:select",
                surface="dom",
                role="combobox",
                label="Color",
                supported_actions=("select_option",),
                state={"selected_value": "Blue", "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.kind == FailureKind.NO_FEASIBLE_ACTION


def test_action_choice_builder_creates_terminal_activation_choice() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:submit",
        subject="semantic:submit",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=True,
    )
    step = _step(criterion=criterion, step_id="step:submit")

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:submit",
                surface="dom",
                role="button",
                label="Submit",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.ACTIVATE
    assert choice.target_id == "semantic:submit"
    assert choice.criterion_ids == ("criterion:submit",)


def test_action_choice_builder_grounds_typed_submit_intent_independently_of_criterion_subject() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:submit",
        subject="settings submission",
        relation=CriterionRelation.IS_COMPLETED,
        expected_value=True,
    )
    step = _step(
        criterion=criterion,
        step_id="step:submit",
        interaction=ElementIntent("Submit", (_source(),), role="button"),
    )

    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:submit",
                surface="dom",
                role="button",
                label="Submit",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.ACTIVATE
    assert choice.target_id == "semantic:submit"


def test_action_choice_builder_does_not_expose_backend_or_verifier_authority() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:name",
        subject="semantic:name",
        expected_value="Alice",
    )
    step = _step(criterion=criterion, step_id="step:name")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:name",
                surface="dom",
                role="textbox",
                label="Name",
                supported_actions=("type_text",),
                state={"value": ""},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert not hasattr(choice, "backend")
    assert not hasattr(choice, "verifier_plan")
    assert not hasattr(choice, "expected_effects")
    assert not hasattr(choice, "evidence_requirements")


def test_action_selection_validator_returns_member_choice_only() -> None:
    from affordance_runtime.action_choice import (
        ActionChoiceBuilder,
        ActionChoiceSet,
        ActionSelection,
        ActionSelectionValidator,
    )

    criterion = _criterion(
        criterion_id="criterion:name",
        subject="semantic:name",
        expected_value="Alice",
    )
    step = _step(criterion=criterion, step_id="step:name")
    result = ActionChoiceBuilder().build(
        task_revision=1,
        state_version=7,
        step=step,
        scope=_scope(step),
        observation=_observation(
            UnifiedObservationTarget(
                target_id="semantic:name",
                surface="dom",
                role="textbox",
                label="Name",
                supported_actions=("type_text",),
                state={"value": ""},
            )
        ),
    )
    assert isinstance(result, ActionChoiceSet)

    selected = ActionSelectionValidator().validate(
        ActionSelection(
            choice_id=result.choices[0].choice_id,
            task_revision=1,
            state_version=7,
            snapshot_id="snapshot:1",
            active_step_id="step:name",
        ),
        result,
    )
    assert selected == result.choices[0]

    with pytest.raises(ValueError, match="unknown choice"):
        ActionSelectionValidator().validate(
            ActionSelection(
                choice_id="choice:missing",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
            ),
            result,
        )


def test_action_choice_dispatcher_returns_failure_without_model_call() -> None:
    from affordance_runtime.action_choice import (
        ActionChoiceDispatcher,
        ActionChoiceFailure,
    )
    from affordance_runtime.recovery_protocol import FailureKind, FailureOwner

    class Planner:
        called = False

        def select(self, request: object) -> object:
            self.called = True
            raise AssertionError("planner should not be called")

    failure = ActionChoiceFailure(
        kind=FailureKind.NO_FEASIBLE_ACTION,
        reason_code="no_feasible_action_choice",
    )
    planner = Planner()

    result = ActionChoiceDispatcher().choose(failure, planner=planner)

    assert result is failure
    assert planner.called is False
    assert failure.owner == FailureOwner.RUNTIME_RECOVERY


def test_action_choice_dispatcher_auto_selects_unique_choice_without_model_call() -> None:
    from affordance_runtime.action_choice import (
        ActionChoice,
        ActionChoiceDispatcher,
        ActionChoiceSet,
        ActionSelection,
    )

    class Planner:
        called = False

        def select(self, request: object) -> object:
            self.called = True
            raise AssertionError("planner should not be called")

    choices = ActionChoiceSet(
        task_revision=1,
        state_version=7,
        snapshot_id="snapshot:1",
        active_step_id="step:name",
        grounding=GroundingResult(GroundingStatus.RESOLVED),
        choices=(
            ActionChoice(
                choice_id="choice:one",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_id="semantic:name",
                parameters={"text": "Alice"},
                criterion_ids=("criterion:name",),
            ),
        ),
    )
    planner = Planner()

    result = ActionChoiceDispatcher().choose(choices, planner=planner)

    assert isinstance(result, ActionSelection)
    assert result.choice_id == "choice:one"
    assert planner.called is False


def test_action_choice_dispatcher_calls_planner_for_multiple_choices() -> None:
    from affordance_runtime.action_choice import (
        ActionChoice,
        ActionChoiceDispatcher,
        ActionChoiceSet,
        ActionSelection,
    )

    class Planner:
        called = False

        def select(self, request: object) -> ActionSelection:
            self.called = True
            assert len(request.choices) == 2  # type: ignore[attr-defined]
            return ActionSelection(
                choice_id="choice:two",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
            )

    choices = ActionChoiceSet(
        task_revision=1,
        state_version=7,
        snapshot_id="snapshot:1",
        active_step_id="step:name",
        grounding=GroundingResult(GroundingStatus.RESOLVED),
        choices=(
            ActionChoice(
                choice_id="choice:one",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_id="semantic:first",
                parameters={"text": "Alice"},
                criterion_ids=("criterion:name",),
            ),
            ActionChoice(
                choice_id="choice:two",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_id="semantic:second",
                parameters={"text": "Alice"},
                criterion_ids=("criterion:name",),
            ),
        ),
    )
    planner = Planner()

    result = ActionChoiceDispatcher().choose(choices, planner=planner)

    assert isinstance(result, ActionSelection)
    assert result.choice_id == "choice:two"
    assert planner.called is True


def test_action_choice_dispatcher_validates_async_planner_selection() -> None:
    from affordance_runtime.action_choice import (
        ActionChoice,
        ActionChoiceDispatcher,
        ActionChoiceFailure,
        ActionChoiceSet,
        ActionSelection,
    )
    from affordance_runtime.recovery_protocol import FailureKind

    class Planner:
        async def select(self, request: object) -> ActionSelection:
            return ActionSelection(
                choice_id="choice:missing",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
            )

    choices = ActionChoiceSet(
        task_revision=1,
        state_version=7,
        snapshot_id="snapshot:1",
        active_step_id="step:name",
        grounding=GroundingResult(GroundingStatus.RESOLVED),
        choices=(
            ActionChoice(
                choice_id="choice:one",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_id="semantic:first",
                parameters={"text": "Alice"},
                criterion_ids=("criterion:name",),
            ),
            ActionChoice(
                choice_id="choice:two",
                task_revision=1,
                state_version=7,
                snapshot_id="snapshot:1",
                active_step_id="step:name",
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_id="semantic:second",
                parameters={"text": "Alice"},
                criterion_ids=("criterion:name",),
            ),
        ),
    )

    result = ActionChoiceDispatcher().choose(choices, planner=Planner())

    resolved = asyncio.run(result)

    assert isinstance(resolved, ActionChoiceFailure)
    assert resolved.kind == FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE
    assert resolved.reason_code == "invalid_action_choice_selection"
