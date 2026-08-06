from affordance_runtime.grounding import EvidenceKind, GroundingSource
from affordance_runtime.perception import (
    PerceptionEscalation,
    derive_perception_requirements,
    perception_task_terms,
    route_perception_requirements,
)
from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
)
from affordance_runtime.task_intake import OperationClass, TaskSpec
from runtime_test_support import legacy_step_spec


def _task(objective: str) -> TaskSpec:
    return TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("target",),
        success_criteria=("task completes",),
        source_request_ref="test",
    )


def test_plain_form_task_remains_structured_and_does_not_budget_a_visual_model() -> None:
    requirements = derive_perception_requirements(_task("Choose Earth from the country field"))

    assert requirements.required_properties == frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})
    assert requirements.acceptable_evidence == frozenset({GroundingSource.DOM, GroundingSource.ACCESSIBILITY})
    assert requirements.model_call_budget == 0


def test_svg_spatial_task_requires_coherent_visual_and_spatial_evidence() -> None:
    requirements = derive_perception_requirements(_task("Click the point above the blue SVG shape"))

    assert requirements.required_properties == frozenset({EvidenceKind.SPATIAL, EvidenceKind.VISUAL_APPEARANCE})
    assert GroundingSource.SVG in requirements.acceptable_evidence
    assert requirements.preferred_sources[0] == GroundingSource.SVG
    assert requirements.model_call_budget == 1


def test_inside_relation_accepts_visual_spatial_grounding() -> None:
    requirements = derive_perception_requirements(_task("Drag the smaller box completely inside the larger box"))

    assert EvidenceKind.SPATIAL in requirements.required_properties
    assert EvidenceKind.VISUAL_APPEARANCE not in requirements.required_properties
    assert GroundingSource.VISUAL in requirements.acceptable_evidence


def test_visual_appearance_task_does_not_require_unavailable_dom_structure() -> None:
    requirements = derive_perception_requirements(_task("Choose the blue visual icon"))

    assert requirements.required_properties == frozenset({EvidenceKind.VISUAL_APPEARANCE})
    assert GroundingSource.VISUAL in requirements.acceptable_evidence
    assert GroundingSource.DOM not in requirements.acceptable_evidence


def test_named_icon_can_use_current_semantic_dom_evidence() -> None:
    requirements = derive_perception_requirements(_task("Find the email by Anne and click the star icon"))

    assert requirements.required_properties == frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})
    assert GroundingSource.DOM in requirements.acceptable_evidence


def test_named_color_field_does_not_require_visual_appearance() -> None:
    requirements = derive_perception_requirements(_task("Enter the value of Color into the text field"))

    assert requirements.required_properties == frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})
    assert GroundingSource.DOM in requirements.acceptable_evidence


def test_device_property_task_can_use_authoritative_wot_without_dom_text() -> None:
    requirements = derive_perception_requirements(_task("Read the device property"))

    assert requirements.required_properties == frozenset({EvidenceKind.DEVICE_STATE, EvidenceKind.STRUCTURAL})
    assert requirements.preferred_sources[:2] == (
        GroundingSource.WOT,
        GroundingSource.API,
    )


def test_hyphenated_task_target_contributes_visual_component_terms() -> None:
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click on a small black 8",
        operation_class=OperationClass.READ_ONLY,
        targets=("click-shape",),
        success_criteria=("task completes",),
        source_request_ref="test",
    )

    requirements = derive_perception_requirements(task)

    assert EvidenceKind.VISUAL_APPEARANCE in requirements.required_properties
    assert GroundingSource.SVG in requirements.acceptable_evidence
    assert {"click-shape", "shape"}.issubset(perception_task_terms(task))


def test_ascending_number_sequence_accepts_structured_or_visual_spatial_observation() -> None:
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click on the numbers in ascending order.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("ascending-numbers",),
        success_criteria=("The sequence is accepted.",),
        source_request_ref="test",
    )

    requirements = derive_perception_requirements(task)

    assert EvidenceKind.SPATIAL in requirements.required_properties
    assert EvidenceKind.VISUAL_APPEARANCE not in requirements.required_properties
    assert GroundingSource.SVG in requirements.acceptable_evidence
    assert {"ascending", "numbers"}.issubset(perception_task_terms(task))


def test_descending_letter_sequence_requires_spatial_but_not_unrelated_visual_appearance() -> None:
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click the letters in descending order.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("ordered-items",),
        success_criteria=("The sequence is accepted.",),
        source_request_ref="test",
    )

    requirements = derive_perception_requirements(task)

    assert requirements.required_properties == frozenset({EvidenceKind.SPATIAL})
    assert GroundingSource.SVG in requirements.acceptable_evidence
    assert GroundingSource.DOM in requirements.acceptable_evidence


def test_route_requirements_do_not_apply_circle_evidence_to_later_submit_control() -> None:
    base = derive_perception_requirements(_task("Find and click on the center of the circle, then press Submit"))

    point = route_perception_requirements(
        base,
        action="point_activate",
        target_role="point",
        target_label="black circle",
    )
    submit = route_perception_requirements(
        base,
        action="activate",
        target_role="button",
        target_label="Submit",
    )

    assert point.required_properties == frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL})
    assert submit.required_properties == frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})


def test_route_requirements_treat_layout_word_as_optional_for_typed_target() -> None:
    base = derive_perception_requirements(_task("Copy the text in the textarea below and paste it into the textbox"))

    target = route_perception_requirements(
        base,
        action="type_text",
        target_role="textbox",
        target_label="Answer",
    )

    assert target.required_properties == frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})


def test_route_requirements_retain_visual_evidence_for_visual_icon_target() -> None:
    base = derive_perception_requirements(_task("Choose the blue visual icon"))

    target = route_perception_requirements(
        base,
        action="activate",
        target_role="button",
        target_label="blue icon",
    )

    assert target.required_properties == frozenset({EvidenceKind.VISUAL_APPEARANCE})


def test_route_requirements_retain_visual_evidence_exposed_by_target_candidates() -> None:
    base = derive_perception_requirements(_task("Activate the visual Save control"))

    target = route_perception_requirements(
        base,
        action="activate",
        target_role="button",
        target_label="Save",
        target_evidence=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
    )

    assert target.required_properties == frozenset({EvidenceKind.VISUAL_APPEARANCE})


def test_route_requirements_retain_visual_evidence_explicit_in_current_subgoal() -> None:
    base = derive_perception_requirements(_task("Activate the blue visual Save icon"))

    target = route_perception_requirements(
        base,
        action="activate",
        target_role="button",
        target_label="Save",
        target_context="Activate the blue visual Save icon",
        target_evidence=frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
    )

    assert target.required_properties == frozenset({EvidenceKind.VISUAL_APPEARANCE})


def test_route_requirements_do_not_widen_authoritative_device_sources() -> None:
    base = derive_perception_requirements(_task("Turn on the authoritative device property"))

    target = route_perception_requirements(
        base,
        action="activate",
        target_role="switch",
        target_label="Power",
        target_evidence=frozenset({EvidenceKind.STRUCTURAL}),
    )

    assert GroundingSource.DOM not in target.acceptable_evidence
    assert GroundingSource.ACCESSIBILITY not in target.acceptable_evidence
    assert target.required_properties == frozenset({EvidenceKind.DEVICE_STATE, EvidenceKind.STRUCTURAL})


def test_step_criterion_evidence_policy_drives_perception_even_when_task_is_plain() -> None:
    refs = (SourceReference("request", "request:chart"),)
    step = legacy_step_spec(
        step_id="inspect-chart",
        objective="Inspect the current chart",
        interaction=ElementIntent("Inspect the current chart", refs),
        completion_criteria=(
            StateCriterion(
                criterion_id="criterion:chart-point",
                source_refs=refs,
                subject="marked point spatial position",
                relation=StateCriterionRelation.IS_VISIBLE,
                evidence_policy=CriterionEvidencePolicy(
                    EvidenceStrength.INDEPENDENT,
                    ("visual_appearance", "spatial"),
                ),
            ),
        ),
        source_refs=refs,
    )

    requirements = derive_perception_requirements(
        _task("Review the report"),
        active_subgoal=step,
    )

    assert EvidenceKind.VISUAL_APPEARANCE in requirements.required_properties
    assert EvidenceKind.SPATIAL in requirements.required_properties
    assert {"inspect", "chart", "spatial", "position"}.issubset(
        perception_task_terms(_task("Review the report"), active_subgoal=step)
    )


def test_failed_structured_route_escalates_to_independent_visual_evidence() -> None:
    requirements = derive_perception_requirements(
        _task("Activate the named control"),
        escalation=PerceptionEscalation(
            reason="current DOM route failed before verification",
            failed_sources=frozenset({GroundingSource.DOM}),
        ),
    )

    assert EvidenceKind.VISUAL_APPEARANCE in requirements.required_properties
    assert GroundingSource.VISUAL in requirements.acceptable_evidence
    assert GroundingSource.DOM not in requirements.preferred_sources
    assert requirements.model_call_budget == 1
