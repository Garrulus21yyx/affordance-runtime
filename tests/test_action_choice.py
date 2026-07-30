from __future__ import annotations

import asyncio

import pytest

from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength
from affordance_runtime.simplified_runtime_contracts import (
    SourceReference,
    StateCriterion,
    StepActivityStatus,
    StepSpec,
)
from affordance_runtime.unified_observation import (
    UnifiedObservationTarget,
    UnifiedObservationView,
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


def _step(*, criterion: StateCriterion, step_id: str = "step:1") -> StepSpec:
    return StepSpec(
        step_id=step_id,
        objective="Complete the current step",
        completion_criteria=(criterion,),
        source_refs=(_source(),),
    )


def _observation(*targets: UnifiedObservationTarget) -> UnifiedObservationView:
    return UnifiedObservationView(
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
    assert choice.target_id == "semantic:slider"


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
    assert result.reason_code == "action_choice_target_unresolved"


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
                state={"selected_options": ("Red",), "enabled": True, "visible": True},
            )
        ),
    )

    assert isinstance(result, ActionChoiceSet)
    choice = result.choices[0]
    assert choice.action_kind == PlannerActionKind.SELECT_OPTION
    assert choice.target_id == "semantic:select"
    assert choice.parameters == {"option": "Blue"}


def test_action_choice_builder_does_not_treat_available_options_as_selected() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:option",
        subject="list",
        relation=CriterionRelation.IS_SELECTED,
        expected_value="Ertha",
    )
    step = _step(criterion=criterion, step_id="step:select")

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


def test_action_choice_builder_resolves_legacy_submission_subject_to_unique_submit() -> None:
    from affordance_runtime.action_choice import ActionChoiceBuilder, ActionChoiceSet

    criterion = _criterion(
        criterion_id="criterion:submit",
        subject="settings submission",
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
