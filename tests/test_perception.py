from affordance_runtime.grounding import EvidenceKind, GroundingSource
from affordance_runtime.perception import derive_perception_requirements, perception_task_terms
from affordance_runtime.task_intake import OperationClass, TaskSpec


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


def test_ascending_number_sequence_requires_visual_svg_observation() -> None:
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

    assert EvidenceKind.VISUAL_APPEARANCE in requirements.required_properties
    assert GroundingSource.SVG in requirements.acceptable_evidence
    assert {"ascending", "numbers"}.issubset(perception_task_terms(task))


def test_descending_letter_sequence_uses_the_same_ordering_evidence_rule() -> None:
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

    assert requirements.required_properties == frozenset(
        {EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}
    )
    assert GroundingSource.SVG in requirements.acceptable_evidence
    assert GroundingSource.DOM in requirements.acceptable_evidence
