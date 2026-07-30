import asyncio
from dataclasses import dataclass, replace
from typing import Any

import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.compatibility_planner_algorithms import (
    _compiled_disclosure_operation,
    _explicit_form_field_obligations,
    _suggestion_selection_obligation,
)
from affordance_runtime.compatibility_planner_algorithms import (
    historical_compatibility_semantic_compiler_registry as default_semantic_compiler_registry,
)
from affordance_runtime.contracts import Observation
from affordance_runtime.generalist_planner import (
    GeneralistLMPlanner,
    GeneralistPlannerProfile,
    build_planner_context,
)
from affordance_runtime.model_port import ModelCallRecord
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.semantic_action_resolver import SemanticActionResolution
from affordance_runtime.semantic_compilers import SemanticCompilation, SemanticCompilerRegistry, SemanticConstraints
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


def test_semantic_action_resolution_parameters_are_immutable_from_source_payload() -> None:
    parameters = {"values": ["Alice"]}

    resolution = SemanticActionResolution(
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="field-1",
        parameters=parameters,
    )
    parameters["values"].append("Mallory")

    assert resolution.parameters["values"] == ["Alice"]
    with pytest.raises(TypeError):
        resolution.parameters["values"][0] = "Mallory"


def test_semantic_compilation_payloads_are_immutable_from_source_collections() -> None:
    parameters = {"values": ["Alice"]}
    compatible_targets = {"field": ("field-1",)}

    compilation = SemanticCompilation(
        action_kind=PlannerActionKind.TYPE_TEXT.value,
        target_affordance_id="field-1",
        parameters=parameters,
    )
    constraints = SemanticConstraints(
        permitted_action_kinds=(PlannerActionKind.TYPE_TEXT.value,),
        compatible_target_ids=compatible_targets,
    )
    parameters["values"].append("Mallory")
    compatible_targets["field"] = ("field-2",)

    assert compilation.parameters["values"] == ["Alice"]
    assert constraints.compatible_target_ids["field"] == ("field-1",)
    with pytest.raises(TypeError):
        compilation.parameters["values"][0] = "Mallory"
    with pytest.raises(TypeError):
        constraints.compatible_target_ids["field"] = ("field-2",)


@dataclass
class DragProposalModel:
    provider: str = "fixture"
    model: str = "semantic-drag"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: list[Any],
        output_schema: type[Any],
        config: Any,
    ) -> Any:
        del messages, config
        self.calls += 1
        return output_schema.model_validate(
            {
                "action_kind": PlannerActionKind.DRAG,
                "target_affordance_id": "dom_li_2",
                "destination_affordance_id": "dom_li_3",
            }
        )


@dataclass
class GovernanceClarificationModel:
    provider: str = "fixture"
    model: str = "governance-clarification"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: list[Any],
        output_schema: type[Any],
        config: Any,
    ) -> Any:
        del messages, config
        self.calls += 1
        return output_schema.model_validate(
            {
                "action_kind": "ask_user",
                "reason": "current evidence does not authorize one scoped next action",
            }
        )


def _drag_fixture(objective: str) -> tuple[TaskEnvelope, StateKernel, BrowserSnapshot]:
    model = DomAdapter().transduce(
        '<li class="ui-sortable-handle">Alpha</li>'
        '<li class="ui-sortable-handle">Beta</li>'
        '<li class="ui-sortable-handle">Gamma</li>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    task = TaskSpec(
        task_id="generic-sortable",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("sortable list",),
        success_criteria=("requested item position is observed",),
        evidence_requirements=("post-action list order",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, objective)
    state.remember_observation(observation)
    return TaskEnvelope(task_spec=task), state, BrowserSnapshot(observation, model)


def _governance_fixture(kind: str) -> tuple[TaskEnvelope, StateKernel, BrowserSnapshot]:
    if kind == "form":
        objective = 'Enter "Q1" into both text fields and press Submit.'
        markup = '<label>First</label><input id="first"><label>Second</label><input id="second"><button>Submit</button>'
    elif kind == "suggestion":
        objective = 'Enter an item that starts with "Com".'
        markup = '<label>Tags</label><input id="tags"><button>Submit</button>'
    else:
        objective = "Expand the section below and click Submit."
        markup = '<h3 role="tab" aria-expanded="false" aria-controls="panel">Section</h3><button>Submit</button>'
    model = DomAdapter().transduce(
        markup,
        environment_revision="governance-rev",
        snapshot_id="governance-snapshot",
    )
    if kind == "suggestion":
        model = replace(
            model,
            affordances=[
                replace(item, state={**item.state, "autocomplete": True})
                if item.state.get("element_tag") == "input"
                else item
                for item in model.affordances
            ],
        )
    observation = Observation(
        "governance-rev",
        snapshot_id="governance-snapshot",
        page_revision=model.page_revision,
    )
    task = TaskSpec(
        task_id=f"governance-{kind}",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=(),
        success_criteria=("the explicitly requested effect is observed",),
        source_request_ref="governance-fixture",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    return TaskEnvelope(task_spec=task), state, BrowserSnapshot(observation, model)


def test_compatibility_compilers_declare_applicability_evidence_and_negative_examples() -> None:
    registry = default_semantic_compiler_registry()

    assert registry.rules
    assert registry.constraint_rules
    for rule in (*registry.rules, *registry.constraint_rules):
        assert rule.compiler_id
        assert rule.applicability_description
        assert rule.evidence.output_action_kinds
        assert rule.evidence.verifier_requirements
        assert rule.evidence.negative_examples
        assert rule.evidence.source
        assert rule.evidence.version
        serialized = repr(rule).casefold()
        assert "browsergym" not in serialized
        assert "miniwob" not in serialized


def test_constraint_registry_is_explicit_and_disabled_registry_is_neutral() -> None:
    envelope, state, snapshot = _drag_fixture("Review the current list without changing it")
    context = build_planner_context(envelope, state, snapshot)
    permitted = list(context.permitted_action_kinds)
    compatible = {"drag": [item.id for item in context.affordances if item.action == "drag"]}

    constrained = default_semantic_compiler_registry().constrain(
        context,
        permitted,
        compatible,
    )

    assert constrained is not None
    assert constrained.compiler_id == "typed-planner-constraints-v1"
    assert constrained.evidence_ref == "runtime-generic-planner-constraint-conformance@1"
    assert SemanticCompilerRegistry.disabled().constrain(context, permitted, compatible) is None


def test_registry_negative_control_does_not_compile_an_unrequested_list_action() -> None:
    envelope, state, snapshot = _drag_fixture("Review the current list without changing it")
    context = build_planner_context(envelope, state, snapshot)

    assert default_semantic_compiler_registry().compile(context) is None


def test_typed_incremental_control_compiles_one_verified_direction_without_backend_data() -> None:
    model = DomAdapter().transduce(
        '<div><span class="ui-slider-handle" tabindex="0"></span><div>-1</div></div>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    task = TaskSpec(
        task_id="portable-slider",
        revision=1,
        objective="Select 3 with the slider, then continue.",
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("slider value is 3",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    context = build_planner_context(
        TaskEnvelope(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    compiled = default_semantic_compiler_registry().compile(context)

    assert compiled is not None
    assert compiled.compiler_id == "typed-incremental-control-v1"
    assert compiled.action_kind == "press_key"
    assert compiled.parameters == {"key": "ArrowRight"}


def test_typed_incremental_control_uses_bounded_page_step_for_large_distance() -> None:
    model = DomAdapter().transduce(
        '<div><span class="ui-slider-handle" tabindex="0"></span><div>13</div></div>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    task = TaskSpec(
        task_id="portable-incremental-control",
        revision=1,
        objective="Set the slider to 68, then continue.",
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("slider value is 68",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    context = build_planner_context(
        TaskEnvelope(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    compiled = default_semantic_compiler_registry().compile(context)

    assert compiled is not None
    assert compiled.compiler_id == "typed-incremental-control-v1"
    assert compiled.parameters == {"key": "PageUp"}


def _form_context(objective: str):
    model = DomAdapter().transduce(
        '<p><label>Username</label><input id="username" type="text"></p>'
        '<p><label>Password</label><input id="password" type="password"></p>'
        '<button id="submit">Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    task = TaskSpec(
        task_id="portable-form",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("form",),
        success_criteria=("all requested fields are submitted",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    return build_planner_context(TaskEnvelope(task_spec=task), state, BrowserSnapshot(observation, model))


def _suggestion_context(
    objective: str,
    *,
    current_value: str = "",
    options: tuple[str, ...] = (),
    second_control: bool = False,
):
    option_html = "".join(f'<div role="option" tabindex="0">{value}</div>' for value in options)
    second_html = '<label>Country</label><input id="country">' if second_control else ""
    model = DomAdapter().transduce(
        f'<label>Tags</label><input id="tags" value="{current_value}">'
        f"{second_html}{option_html}<button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    affordances = []
    for item in model.affordances:
        if item.state.get("element_tag") == "input":
            affordances.append(replace(item, state={**item.state, "autocomplete": True}))
        elif item.state.get("element_tag") == "div":
            affordances.append(
                replace(
                    item,
                    role="option",
                    action="activate",
                    state={**item.state, "programmatic_option": True},
                )
            )
        else:
            affordances.append(item)
    model = replace(model, affordances=affordances)
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    task = TaskSpec(
        task_id="portable-suggestion",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("suggestion value",),
        success_criteria=("a matching suggestion is submitted",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    return build_planner_context(TaskEnvelope(task_spec=task), state, BrowserSnapshot(observation, model))


def _disclosure_context(
    objective: str,
    *,
    expanded: tuple[bool, ...],
    visible_target: str = "",
):
    controls = "".join(
        f'<h3 id="section-{index}" role="tab" aria-expanded="{str(is_expanded).lower()}" '
        f'aria-controls="panel-{index}">Section {index}</h3>'
        for index, is_expanded in enumerate(expanded, start=1)
    )
    target = f"<button>{visible_target}</button>" if visible_target else ""
    model = DomAdapter().transduce(
        controls + target + "<button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    task = TaskSpec(
        task_id="portable-disclosure",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("disclosed content",),
        success_criteria=("requested disclosed action is complete",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    return build_planner_context(TaskEnvelope(task_spec=task), state, BrowserSnapshot(observation, model))


def test_explicit_form_compiler_binds_each_labelled_value_before_terminal() -> None:
    context = _form_context('Enter the username "Ada" and the password "s3cret" and press Submit.')
    registry = default_semantic_compiler_registry()

    first = registry.compile(context)
    assert first is not None
    assert first.compiler_id == "explicit-form-field-binding-v1"
    assert (first.action_kind, first.target_affordance_id, first.parameters) == (
        "type_text",
        "dom_input_1",
        {"text": "Ada"},
    )

    after_username = context.model_copy(update={"satisfied_action_targets": {"type_text": ("dom_input_1",)}})
    second = registry.compile(after_username)
    assert second is not None
    assert (second.action_kind, second.target_affordance_id, second.parameters) == (
        "type_text",
        "dom_input_2",
        {"text": "s3cret"},
    )

    complete = after_username.model_copy(
        update={"satisfied_action_targets": {"type_text": ("dom_input_1", "dom_input_2")}}
    )
    terminal = registry.compile(complete)
    assert terminal is not None
    assert (terminal.action_kind, terminal.target_affordance_id) == ("activate", "dom_button_1")


def test_explicit_form_compiler_applies_one_value_to_both_requested_fields() -> None:
    context = _form_context('Enter "Q1" into both text fields and press Submit.')

    obligations = _explicit_form_field_obligations(context)

    assert [(item.target_id, item.value) for item in obligations] == [
        ("dom_input_1", "Q1"),
        ("dom_input_2", "Q1"),
    ]


def test_explicit_form_compiler_falls_through_when_values_are_not_field_bound() -> None:
    context = _form_context('Enter "Ada" and "s3cret" into the fields.')

    assert _explicit_form_field_obligations(context) == ()

    click_only = _form_context('Click the button named "Submit".')
    assert _explicit_form_field_obligations(click_only) == ()


def test_suggestion_compiler_types_prefix_then_activates_one_matching_option() -> None:
    initial = _suggestion_context('Enter an item that starts with "Mo" and ends with "va".')

    first = default_semantic_compiler_registry().compile(initial)

    assert first is not None
    assert first.compiler_id == "typed-suggestion-selection-v1"
    assert (first.action_kind, first.target_affordance_id, first.parameters) == (
        "type_text",
        "dom_input_1",
        {"text": "Mo"},
    )

    with_options = _suggestion_context(
        'Enter an item that starts with "Mo" and ends with "va".',
        current_value="Mo",
        options=("Moldova", "Monaco"),
    )
    second = default_semantic_compiler_registry().compile(with_options)

    assert second is not None
    assert second.compiler_id == "typed-suggestion-selection-v1"
    assert (second.action_kind, second.target_affordance_id, second.parameters) == (
        "activate",
        "dom_div_1",
        {},
    )


def test_suggestion_compiler_submits_matching_current_value_without_refilling_prefix() -> None:
    context = _suggestion_context(
        'Enter an item that starts with "Com".',
        current_value="Comoros",
    )

    compiled = default_semantic_compiler_registry().compile(context)

    assert compiled is not None
    assert compiled.compiler_id == "typed-suggestion-selection-v1"
    assert (compiled.action_kind, compiled.target_affordance_id, compiled.parameters) == (
        "activate",
        "dom_button_1",
        {},
    )
    assert _explicit_form_field_obligations(context) == ()


def test_suggestion_compiler_falls_through_for_ambiguous_targets_or_options() -> None:
    ambiguous_options = _suggestion_context(
        'Enter an item that starts with "Com".',
        current_value="Com",
        options=("Comoros", "Computer"),
    )
    ambiguous_targets = _suggestion_context(
        'Enter an item that starts with "Com".',
        second_control=True,
    )

    assert _suggestion_selection_obligation(ambiguous_targets) is None
    assert default_semantic_compiler_registry().compile(ambiguous_options) is None
    assert default_semantic_compiler_registry().compile(ambiguous_targets) is None


def test_suggestion_compiler_binds_one_explicitly_named_control() -> None:
    context = _suggestion_context(
        'In Tags, enter an item that starts with "Com".',
        second_control=True,
    )

    obligation = _suggestion_selection_obligation(context)

    assert obligation is not None
    assert (obligation.target_id, obligation.prefix, obligation.suffix) == (
        "dom_input_1",
        "Com",
        "",
    )


def test_disclosure_compiler_opens_one_control_before_terminal_binding() -> None:
    context = _disclosure_context(
        "Expand the section below and click Submit.",
        expanded=(False,),
    )

    compiled = default_semantic_compiler_registry().compile(context)

    assert compiled is not None
    assert compiled.compiler_id == "typed-disclosure-control-v1"
    assert (compiled.action_kind, compiled.target_affordance_id, compiled.parameters) == (
        "activate",
        "dom_h3_1",
        {},
    )


def test_disclosure_compiler_prefers_one_objective_named_control_over_weak_sibling() -> None:
    context = _disclosure_context(
        "Expand the section below and click Submit.",
        expanded=(False, False),
    )
    affordances = tuple(
        item.model_copy(update={"label": "generated-control"}) if item.id == "dom_h3_2" else item
        for item in context.affordances
    )
    context = context.model_copy(update={"affordances": affordances})

    assert _compiled_disclosure_operation(context) == (
        PlannerActionKind.ACTIVATE,
        "dom_h3_1",
        {},
    )


def test_disclosure_compiler_scans_ordered_controls_until_named_target_is_visible() -> None:
    initial = _disclosure_context(
        'Expand the sections to find and click "Needle".',
        expanded=(False, False, False),
    )
    after_first = _disclosure_context(
        'Expand the sections to find and click "Needle".',
        expanded=(True, False, False),
    )
    found = _disclosure_context(
        'Expand the sections to find and click "Needle".',
        expanded=(False, True, False),
        visible_target="Needle",
    )

    first = _compiled_disclosure_operation(initial)
    second = _compiled_disclosure_operation(after_first)

    assert first == (PlannerActionKind.ACTIVATE, "dom_h3_1", {})
    assert second == (PlannerActionKind.ACTIVATE, "dom_h3_2", {})
    assert _compiled_disclosure_operation(found) == (
        PlannerActionKind.ACTIVATE,
        "dom_button_1",
        {},
    )


def test_disclosure_compiler_continues_past_case_only_quoted_near_match() -> None:
    context = _disclosure_context(
        'Expand the sections to find and click "proin".',
        expanded=(True, False, False),
        visible_target="Proin",
    )

    assert _compiled_disclosure_operation(context) == (
        PlannerActionKind.ACTIVATE,
        "dom_h3_2",
        {},
    )


def test_disclosure_compiler_does_not_choose_between_duplicate_exact_descendants() -> None:
    context = _disclosure_context(
        'Expand the sections to find and click "Needle".',
        expanded=(True, False),
        visible_target="Needle",
    )
    target = next(item for item in context.affordances if item.label == "Needle")
    context = context.model_copy(
        update={"affordances": (*context.affordances, target.model_copy(update={"id": "duplicate-target"}))}
    )

    assert _compiled_disclosure_operation(context) is None


def test_disclosure_compiler_falls_through_for_ambiguous_multi_control_request() -> None:
    context = _disclosure_context(
        "Open a section and continue.",
        expanded=(False, False),
    )

    assert _compiled_disclosure_operation(context) is None


def test_strict_default_disables_compatibility_compilers_without_removing_drag() -> None:
    envelope, enabled_state, snapshot = _drag_fixture("Drag Beta down by one position")
    enabled_model = DragProposalModel()
    enabled = asyncio.run(
        GeneralistLMPlanner(
            enabled_model,
            planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
        ).propose_legacy(envelope, enabled_state, snapshot)
    )

    _, disabled_state, _ = _drag_fixture("Drag Beta down by one position")
    disabled_model = DragProposalModel()
    disabled = asyncio.run(GeneralistLMPlanner(disabled_model).propose_legacy(envelope, disabled_state, snapshot))

    assert enabled.proposal is not None and disabled.proposal is not None
    assert enabled.proposal.action_kind == disabled.proposal.action_kind == PlannerActionKind.DRAG
    assert enabled.proposal.target_affordance_id == disabled.proposal.target_affordance_id == "dom_li_2"
    assert enabled.proposal.destination_affordance_id == disabled.proposal.destination_affordance_id == "dom_li_3"
    assert enabled_model.calls == 0
    assert disabled_model.calls == 1
    assert enabled.planner_context["planner_profile"] == "historical-compatibility"
    assert enabled.planner_context["semantic_compiler"]["compiler_id"] == "typed-affordance-semantics-v1"
    assert enabled.proposal_provenance is not None
    assert enabled.proposal_provenance.source.value == "deterministic_rule"
    assert enabled.proposal_provenance.profile_id == "historical-compatibility"
    assert disabled.planner_context["planner_profile"] == "strict-generalist"
    assert disabled.proposal_provenance is not None
    assert disabled.proposal_provenance.source.value == "model"
    assert "semantic_compiler" not in disabled.planner_context
    assert "semantic_constraints" not in disabled.planner_context


@pytest.mark.parametrize("kind", ["form", "suggestion", "disclosure"])
def test_strict_profile_does_not_execute_task_grammar_before_model_authority(kind: str) -> None:
    envelope, state, snapshot = _governance_fixture(kind)
    strict_model = GovernanceClarificationModel()

    strict = asyncio.run(GeneralistLMPlanner(strict_model).propose_legacy(envelope, state, snapshot))

    assert strict_model.calls == 1
    assert strict.proposal is not None
    assert strict.proposal.action_kind == PlannerActionKind.ASK_USER
    assert strict.planner_context["planner_profile"] == "strict-generalist"
    assert "semantic_compiler" not in strict.planner_context

    compatibility_model = GovernanceClarificationModel()
    compatibility = asyncio.run(
        GeneralistLMPlanner(
            compatibility_model,
            planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
        ).propose_legacy(envelope, state, snapshot)
    )

    assert compatibility_model.calls == 0
    assert compatibility.proposal is not None
    assert compatibility.proposal.action_kind != PlannerActionKind.ASK_USER
    assert compatibility.planner_context["planner_profile"] == "historical-compatibility"
    assert "semantic_compiler" in compatibility.planner_context


def test_strict_profile_rejects_a_nonempty_compatibility_registry() -> None:
    with pytest.raises(ValueError, match="strict-generalist"):
        GeneralistLMPlanner(
            DragProposalModel(),
            semantic_compilers=default_semantic_compiler_registry(),
        )


def test_semantic_registry_digest_is_stable_and_profile_sensitive() -> None:
    first = default_semantic_compiler_registry()
    second = default_semantic_compiler_registry()
    strict = SemanticCompilerRegistry.disabled()

    assert first.digest == second.digest
    assert first.compiler_ids == second.compiler_ids
    assert first.digest != strict.digest
    assert strict.compiler_ids == ()
