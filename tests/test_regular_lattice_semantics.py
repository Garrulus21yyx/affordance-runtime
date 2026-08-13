from __future__ import annotations

import random

import numpy as np
from browsergym_adapter_support import ax_node, raw_observation

from affordance_runtime.agent import AgentLoopState, EstablishSetObjective
from affordance_runtime.benchmarks.external_smoke.browsergym_entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import (
    project_browsergym_observation,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary import ContextBuilder
from affordance_runtime.model_policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model_policy.tool_contracts import ToolCall
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ActionSpaceBuilder
from affordance_runtime.world.regular_lattice import (
    LatticeDerivationCode,
    SpatialNode,
    VisibleNumericLabel,
    derive_regular_lattice,
)


def _nodes(group: str = "grid") -> tuple[SpatialNode, ...]:
    return tuple(
        SpatialNode(f"n:{row}:{column}", group, (20 + 45 * column, 90 + 45 * row, 14, 14))
        for column in range(5)
        for row in range(5)
    )


def _labels(prefix: str = "", *, x_offset: int = 0, y_offset: int = 0):
    x_labels = tuple(
        VisibleNumericLabel(
            f"{prefix}x:{value}", f"{prefix}axis-x", value,
            (20 + 45 * column + x_offset, 195 + y_offset, 12, 16),
        )
        for column, value in ((0, -2), (1, -1), (3, 1), (4, 2))
    )
    y_labels = tuple(
        VisibleNumericLabel(
            f"{prefix}y:{value}", f"{prefix}axis-y", value,
            (102 + x_offset, 90 + 45 * row + y_offset, 12, 16),
        )
        for row, value in ((0, 2), (1, 1), (3, -1), (4, -2))
    )
    return x_labels + y_labels


def test_regular_lattice_derivation_is_order_independent_and_infers_y_orientation() -> None:
    nodes = list(_nodes())
    labels = list(_labels())
    random.Random(19).shuffle(nodes)
    random.Random(23).shuffle(labels)

    result = derive_regular_lattice(tuple(nodes), tuple(labels))

    assert result.code is LatticeDerivationCode.DERIVED
    assert len(result.memberships) == 25
    target = next(item for item in result.memberships if item.x == 1 and item.y == -2)
    assert (target.row_index, target.column_index) == (4, 3)


def test_regular_lattice_derivation_fails_closed_without_axes_or_with_multiple_grids() -> None:
    missing = derive_regular_lattice(_nodes(), ())
    assert missing.code is LatticeDerivationCode.AXIS_LABELS_UNAVAILABLE
    assert missing.memberships == ()

    second_nodes = tuple(
        SpatialNode(item.node_id + ":b", "grid-b", (
            item.bbox[0] + 400, item.bbox[1], item.bbox[2], item.bbox[3],
        ))
        for item in _nodes()
    )
    multiple = derive_regular_lattice(
        _nodes() + second_nodes,
        _labels() + _labels("b-", x_offset=400),
    )
    assert multiple.code is LatticeDerivationCode.MULTIPLE_LATTICES
    assert multiple.memberships == ()


def test_irregular_or_duplicate_cells_do_not_publish_coordinates() -> None:
    irregular = list(_nodes())
    irregular[-1] = SpatialNode("replacement", "grid", irregular[0].bbox)
    result = derive_regular_lattice(tuple(irregular), _labels())
    assert result.code is LatticeDerivationCode.NO_REGULAR_LATTICE
    assert result.memberships == ()


def test_projection_publishes_generic_facts_for_model_selected_exact_objective() -> None:
    raw = _raw_grid()
    projection = _projection(raw)
    matching = [
        target for target in projection.world.targets
        if target.state.get("grid_coordinate") == {"x": 1, "y": -2}
    ]
    assert len(matching) == 1
    target = matching[0]
    assert target.state["grid_membership"]["row_index"] == 4
    assert target.state["grid_membership"]["column_index"] == 3
    assert target.state["grid_coordinate_confidence"] == 1.0
    assert {
        fact.predicate for fact in projection.world.facts if fact.subject_id == target.target_id
    }.issuperset({"grid_coordinate", "grid_membership", "grid_coordinate_confidence"})

    task = TaskGoal(
        "task:grid",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    action_space = ActionSpaceBuilder().build(task, projection.world)
    state = AgentLoopState(projection.world, remaining_turns=5)
    context = ContextBuilder().build(
        task,
        state,
        action_space,
        TaskEvaluation(
            task.task_id,
            projection.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )
    catalog = compile_grounded_tool_catalog(context)

    establish = next(
        spec
        for spec in catalog.specs
        if 'public fact "grid_coordinate"' in spec.description
    )
    package = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            establish.name,
            {"value": {"x": 1, "y": -2}, "quantifier": "exactly_one"},
        ),
        expected_context_id=context.context_id,
    )
    assert isinstance(package.decision, EstablishSetObjective)
    assert package.decision.predicate.field_name == "grid_coordinate"
    assert package.decision.predicate.expected == {"x": 1, "y": -2}
    assert target.target_id in package.decision.candidate_target_ids


def test_exact_lattice_relation_is_available_without_screenshot_marks() -> None:
    raw = _raw_grid()
    raw.pop("screenshot")
    projection = _projection(raw)
    task = TaskGoal(
        "task:grid-dom-only",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    action_space = ActionSpaceBuilder().build(task, projection.world)
    context = ContextBuilder().build(
        task,
        AgentLoopState(projection.world, remaining_turns=5),
        action_space,
        TaskEvaluation(
            task.task_id,
            projection.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    catalog = compile_grounded_tool_catalog(context)

    establish = next(
        spec
        for spec in catalog.specs
        if 'public fact "grid_coordinate"' in spec.description
    )
    value = establish.input_schema["properties"]["value"]
    assert value["required"] == ["x", "y"]
    assert value["properties"] == {"x": {"type": "integer"}, "y": {"type": "integer"}}


def test_mandatory_semantic_ingress_hides_direct_grid_actions() -> None:
    raw = _raw_grid()
    projection = _projection(raw)
    task = TaskGoal(
        "task:grid-mandatory-ingress",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    action_space = ActionSpaceBuilder().build(task, projection.world)
    state = AgentLoopState(
        projection.world,
        remaining_turns=5,
        semantic_control_required=True,
    )
    context = ContextBuilder().build(
        task,
        state,
        action_space,
        TaskEvaluation(
            task.task_id,
            projection.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    catalog = compile_grounded_tool_catalog(context)

    assert context.set_control is not None
    assert context.set_control.semantic_mode == "semantic_ingress"
    assert not any(spec.name == "click" for spec in catalog.specs)
    assert tuple(spec.name for spec in catalog.specs) == ("establish_task_program",)


def _raw_grid():
    controls = [
        ax_node(f"point-{row}-{column}", "graphics-symbol", "", parent_id="grid-parent")
        for column in range(5)
        for row in range(5)
    ]
    label_nodes = []
    for axis, entries in (
        ("x", ((0, -2), (1, -1), (3, 1), (4, 2))),
        ("y", ((0, 2), (1, 1), (3, -1), (4, -2))),
    ):
        for index, value in entries:
            owner = f"label-{axis}-{index}"
            text = f"text-{axis}-{index}"
            label_nodes.extend((
                ax_node(owner, "generic", "", parent_id=f"axis-{axis}", child_ids=(text,)),
                ax_node(text, "StaticText", str(value), parent_id=owner),
            ))
    raw = raw_observation(
        *controls,
        *label_nodes,
        goal="Click on the grid coordinate (1,-2).",
    )
    for column in range(5):
        for row in range(5):
            bid = f"point-{row}-{column}"
            bbox = [20 + 45 * column, 90 + 45 * row, 14, 14]
            raw["extra_element_properties"][bid].update({
                "clickable": True,
                "visibility": 1.0,
                "bbox": bbox,
            })
            raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = bbox
    for axis, entries in (
        ("x", ((0, -2), (1, -1), (3, 1), (4, 2))),
        ("y", ((0, 2), (1, 1), (3, -1), (4, -2))),
    ):
        for index, _value in entries:
            bid = f"label-{axis}-{index}"
            raw["extra_element_properties"][bid]["bbox"] = (
                [20 + 45 * index, 195, 12, 16]
                if axis == "x" else [102, 90 + 45 * index, 12, 16]
            )
    raw["screenshot"] = np.full((340, 300, 3), 255, dtype=np.uint8)
    return raw


def _projection(raw):
    return project_browsergym_observation(
        raw,
        observation_id="observation:grid",
        source_revision="revision:grid",
        page_identity="page:grid",
        episode_identity="episode:grid",
        verifier=BrowserGymVerifierSnapshot(
            "run:grid",
            "observation:grid",
            "observation:grid",
            VerifierFactSource.RESET,
            ExternalVerifierStatus.INCOMPLETE,
            ExternalVerifierReason.VERIFIED_RUNNING,
        ),
        entity_identity=BrowserGymEntityIdentityMap(b"regular-lattice-test-key-32-byte"),
    )
