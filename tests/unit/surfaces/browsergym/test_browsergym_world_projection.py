import json

import numpy as np

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.serialization import serialize_agent_context
from affordance_runtime.surfaces.browsergym import projection as projection_module
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.projection import (
    project_browsergym_observation,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    EntityInventoryIssueCode,
    EntityInventoryStatus,
    SemanticInventoryStatus,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import ax_node, raw_observation, reset_task_state

_IDENTITY = BrowserGymEntityIdentityMap(b"browsergym-world-projection-tests")


def test_structural_projection_is_bounded_truthful_and_private() -> None:
    raw = raw_observation(
        ax_node("private-1", "button", "okay"),
        ax_node("private-2", "textbox", "", properties=(("required", False),)),
        ax_node("private-3", "combobox", "", value="A", properties=(("expanded", False),)),
        ax_node("private-4", "option", "A"),
        ax_node("private-5", "option", "B"),
    )
    snapshot = reset_task_state("obs:1")
    projected = project_browsergym_observation(
        raw,
        observation_id="obs:1",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=snapshot,
        entity_identity=_IDENTITY,
    )
    assert len(projected.world.targets) == 3
    assert len(projected.world.bindings) == 3
    assert projected.target_count_total == 3
    assert str(projected.world.coverage["browsergym"]) == "complete"
    public = repr(projected.world)
    assert "private-" not in public
    assert "selector" not in public and "bid" not in public
    select = next(item for item in projected.world.bindings if item.semantic_action == "select_option")
    assert select.parameter_schema["properties"]["value"]["enum"] == ("A", "B")
    select_target = next(item for item in projected.world.targets if item.role == "combobox")
    assert select_target.state["option_domain"] == ("A", "B")
    assert dict(projected.private_bindings[-1].option_values) == {"A": "A", "B": "B"}
    inventory = projected.world.sources[0].semantic_inventory
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (
        inventory.recognized_target_count,
        inventory.projected_target_count,
        inventory.actionable_target_count,
        inventory.non_executable_target_count,
        inventory.omitted_target_count,
        inventory.informational_target_count,
    ) == (3, 3, 3, 0, 0, 0)
    retained = projected.world.sources[0].entity_inventory
    assert retained.status is EntityInventoryStatus.COMPLETE
    assert (retained.entity_count, retained.entity_total_count) == (3, 3)
    assert (retained.option_value_count, retained.option_value_total_count) == (2, 2)


def test_entity_identity_is_stable_across_ax_order_and_unrelated_insertions() -> None:
    identity = BrowserGymEntityIdentityMap(b"stable-entity-identity-test-key")
    baseline = _project_with_identity(
        raw_observation(
            ax_node("save-private", "button", "Save"),
            ax_node("name-private", "textbox", "Name"),
        ),
        identity,
    )
    reordered = _project_with_identity(
        raw_observation(
            ax_node("unrelated-private", "StaticText", "Noise"),
            ax_node("name-private", "textbox", "Name"),
            ax_node("save-private", "button", "Save"),
        ),
        identity,
    )

    first = {item.label: item.target_id for item in baseline.world.targets}
    second = {item.label: item.target_id for item in reordered.world.targets}
    assert first["Save"] == second["Save"]
    assert first["Name"] == second["Name"]
    assert all(value.startswith("entity:") for value in second.values())
    assert "private" not in repr(reordered.world)


def test_entity_identity_distinguishes_same_label_and_page_incarnations() -> None:
    identity = BrowserGymEntityIdentityMap(b"scoped-entity-identity-test-key")
    raw = raw_observation(
        ax_node("first-private", "button", "Open"),
        ax_node("second-private", "button", "Open"),
    )
    first_page = _project_with_identity(raw, identity, page_identity="page:first")
    second_page = _project_with_identity(raw, identity, page_identity="page:second")

    first_ids = tuple(item.target_id for item in first_page.world.targets)
    second_ids = tuple(item.target_id for item in second_page.world.targets)
    assert len(set(first_ids)) == 2
    assert set(first_ids).isdisjoint(second_ids)


def test_newly_projected_checkbox_is_observable_and_actionable_without_private_routes() -> None:
    baseline_raw = raw_observation(ax_node("button", "button", "Save"))
    omitted_raw = raw_observation(
        ax_node("button", "button", "Save"),
        ax_node("check", "checkbox", "Remember"),
    )
    baseline = _project(baseline_raw)
    omitted = _project(omitted_raw)

    assert len(omitted.world.targets) == len(baseline.world.targets) + 1
    checkbox = next(item for item in omitted.world.targets if item.role == "checkbox")
    assert checkbox.label == "Remember"
    assert len(omitted.world.bindings) == len(baseline.world.bindings) + 1
    assert (
        next(item for item in omitted.world.bindings if item.target_id == checkbox.target_id).semantic_action
        == "activate"
    )
    assert omitted.world.coverage == baseline.world.coverage == {"browsergym": CoverageState.COMPLETE}
    task = TaskGoal(
        "task:inventory",
        "Save",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    assert len(ActionSpaceBuilder().build(task, omitted.world).options) == 2
    inventory = omitted.world.sources[0].semantic_inventory
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (inventory.recognized_target_count, inventory.projected_target_count) == (2, 2)


def test_static_text_is_projected_as_read_only_information() -> None:
    projected = _project(raw_observation(ax_node("static", "StaticText", "Information")))
    inventory = projected.world.sources[0].semantic_inventory
    assert projected.world.coverage["browsergym"] is CoverageState.COMPLETE
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert inventory.recognized_target_count == 1
    assert len(projected.world.targets) == 1
    assert projected.world.targets[0].role == "StaticText"
    assert projected.world.bindings == ()
    assert inventory.informational_target_count == 1


def test_structural_relations_use_only_current_public_target_ids() -> None:
    projected = _project(
        raw_observation(
            ax_node("table", "table", "Results", child_ids=("row",)),
            ax_node("row", "row", "Ada", parent_id="table", child_ids=("cell",)),
            ax_node("cell", "cell", "42", parent_id="row"),
        )
    )
    by_role = {item.role: item for item in projected.world.targets}
    assert by_role["row"].relations["parent_id"] == by_role["table"].target_id
    assert by_role["row"].relations["child_ids"] == (by_role["cell"].target_id,)
    assert projected.world.bindings == ()


def test_actor_world_snapshot_preserves_hierarchy_and_actionable_nodes() -> None:
    projected = _project(
        raw_observation(
            ax_node("panel", "group", "Products", child_ids=("row",)),
            ax_node("row", "row", "MacBook Pro", parent_id="panel", child_ids=("add",)),
            ax_node("add", "button", "Add to cart", parent_id="row"),
        )
    )
    task = TaskGoal(
        "task:hierarchy",
        "Add MacBook Pro to cart.",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    context = ContextBuilder().build(
        task,
        __import__(
            "affordance_runtime.agent.state",
            fromlist=["AgentLoopState"],
        ).AgentLoopState(projected.world, remaining_turns=2),
        ActionSpaceBuilder().build(task, projected.world),
        TaskEvaluation(
            task.task_id,
            projected.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    public = GroundedPolicyContextBinder._public_context(
        context,
        False,
    )
    roots = public["world"]["documents"][0]["roots"]
    panel = next(item for item in roots if item["label"] == "Products")
    row = panel["children"][0]
    button = row["children"][0]
    option = next(item for item in context.actions.options if item.target_label == "Add to cart")

    assert row["label"] == "MacBook Pro"
    assert button["label"] == "Add to cart"
    assert button["ref"] == option.target_ref
    encoded = json.dumps(public["world"])
    assert "entity:" not in encoded
    assert "observation:" not in encoded


def test_browsergym_clickable_generic_uses_descendant_text_without_exposing_routes() -> None:
    raw = raw_observation(
        ax_node("container", "generic", "", child_ids=("label",)),
        ax_node("label", "StaticText", "Open account", parent_id="container"),
    )
    raw["extra_element_properties"]["container"]["clickable"] = True
    projected = _project(raw)

    clickable = next(item for item in projected.world.targets if item.role == "clickable")
    label = next(item for item in projected.world.targets if item.role == "StaticText")
    assert clickable.label == "Open account"
    assert clickable.relations["child_ids"] == (label.target_id,)
    assert len(projected.world.bindings) == 1
    assert projected.world.bindings[0].target_id == clickable.target_id
    assert projected.world.bindings[0].semantic_action == "activate"
    assert "container" not in repr(projected.world)


def test_screenshot_is_typed_media_but_never_serialized_into_public_context() -> None:
    raw = raw_observation(ax_node("button", "button", "Save"))
    raw["screenshot"] = np.zeros((3, 4, 3), dtype=np.uint8)
    projected = _project(raw)
    media = projected.world.sources[0].media
    assert len(media) == 1
    assert media[0].mime_type == "image/png"
    assert media[0].data.startswith(b"\x89PNG")

    task = TaskGoal("task:image", "Save", allowed_effects=("external_ui_interaction",))
    state = __import__(
        "affordance_runtime.agent.state",
        fromlist=["AgentLoopState"],
    ).AgentLoopState(projected.world, remaining_turns=2)
    evaluation = TaskEvaluation(
        task.task_id,
        projected.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projected.world),
        evaluation,
    )
    assert context.image_inputs[0].sha256 == media[0].sha256
    serialized = serialize_agent_context(context)
    assert "image_inputs" not in serialized
    assert media[0].sha256 not in serialized


def test_inactive_tab_panel_descendants_do_not_gain_action_authority() -> None:
    def accordion(selected: bool):
        raw = raw_observation(
            ax_node(
                "header", "tab", "Section #37",
                properties=(("selected", selected),), child_ids=("header-text",),
            ),
            ax_node("header-text", "StaticText", "Section #37", parent_id="header"),
            ax_node(
                "panel", "tab", " Submit",
                properties=(("selected", selected),), child_ids=("submit",),
            ),
            ax_node("submit", "button", "Submit", parent_id="panel"),
        )
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["submit"]["visible"] = selected
        return raw

    collapsed = _project(accordion(False))
    collapsed_labels = {
        next(item.label for item in collapsed.world.targets if item.target_id == binding.target_id)
        for binding in collapsed.world.bindings
    }
    assert collapsed_labels == {"Section #37"}

    expanded = _project(accordion(True))
    expanded_labels = {
        next(item.label for item in expanded.world.targets if item.target_id == binding.target_id)
        for binding in expanded.world.bindings
    }
    assert expanded_labels == {"Section #37", "Submit"}


def test_projected_non_executable_and_quota_omission_are_distinct(monkeypatch) -> None:
    disabled = raw_observation(ax_node("disabled", "button", "Disabled"))
    disabled[PRIVATE_CONTROL_PROPERTIES_KEY]["disabled"]["enabled"] = False
    disabled_projection = _project(disabled)
    disabled_inventory = disabled_projection.world.sources[0].semantic_inventory
    assert disabled_inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (disabled_inventory.projected_target_count, disabled_inventory.non_executable_target_count) == (1, 1)
    assert disabled_inventory.actionable_target_count == 0

    many_options = raw_observation(
        ax_node("select", "combobox", "Choice"),
        *(ax_node(f"option-{index}", "option", f"Choice {index}") for index in range(17)),
    )
    select_projection = _project(many_options)
    select_inventory = select_projection.world.sources[0].semantic_inventory
    assert select_inventory.status is SemanticInventoryStatus.REPRESENTED
    assert select_inventory.non_executable_target_count == 1
    assert not select_projection.world.bindings

    monkeypatch.setattr(projection_module, "MAX_INVENTORY_TARGETS", 1)
    truncated = _project(
        raw_observation(
            ax_node("one", "button", "One"),
            ax_node("two", "button", "Two"),
            ax_node("radio", "radio", "Three"),
        )
    )
    truncated_inventory = truncated.world.sources[0].semantic_inventory
    assert truncated.world.coverage["browsergym"] is CoverageState.TRUNCATED
    assert truncated_inventory.status is SemanticInventoryStatus.PARTIAL
    assert (
        truncated_inventory.recognized_target_count,
        truncated_inventory.projected_target_count,
        truncated_inventory.omitted_target_count,
    ) == (3, 1, 2)
    retained = truncated.world.sources[0].entity_inventory
    assert retained.status is EntityInventoryStatus.PARTIAL
    assert EntityInventoryIssueCode.ENTITY_CAPACITY_EXCEEDED in retained.issue_codes


def test_fact_only_truncation_does_not_change_target_inventory(monkeypatch) -> None:
    monkeypatch.setattr(projection_module, "MAX_INVENTORY_FACTS", 0)
    projected = _project(
        raw_observation(
            ax_node("field", "textbox", "Name", value="Ada", properties=(("required", True),)),
        )
    )
    inventory = projected.world.sources[0].semantic_inventory
    assert projected.world.coverage["browsergym"] is CoverageState.TRUNCATED
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (inventory.recognized_target_count, inventory.projected_target_count) == (1, 1)
    retained = projected.world.sources[0].entity_inventory
    assert retained.status is EntityInventoryStatus.PARTIAL
    assert retained.issue_codes == (EntityInventoryIssueCode.FACT_CAPACITY_EXCEEDED,)


def test_model_page_limit_does_not_delete_entities_or_action_bindings() -> None:
    projected = _project(
        raw_observation(*(ax_node(f"button-{index}", "button", f"Button {index}") for index in range(65)))
    )

    assert len(projected.world.targets) == 65
    assert len(projected.world.bindings) == 65
    assert projected.world.coverage["browsergym"] is CoverageState.COMPLETE
    assert projected.world.sources[0].entity_inventory.status is EntityInventoryStatus.COMPLETE

    task = TaskGoal("task:paging", "Click Button 64", allowed_effects=("external_ui_interaction",))
    state = __import__(
        "affordance_runtime.agent.state",
        fromlist=["AgentLoopState"],
    ).AgentLoopState(projected.world, remaining_turns=2)
    evaluation = TaskEvaluation(
        task.task_id,
        projected.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projected.world),
        evaluation,
    )
    assert context.world.targets.total_count == 65
    assert len(context.world.targets.items) == 64
    assert context.world.targets.truncated is True
    assert context.world.traversal is not None
    assert context.world.traversal.status == "partial"

    state.set_observation_cursor(context.world.traversal.next_cursor)
    next_context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projected.world),
        evaluation,
    )
    assert any(item.label == "Button 64" for item in next_context.world.targets.items)
    assert next_context.world.traversal is None


def test_action_target_is_pinned_without_starving_fair_inventory_traversal() -> None:
    projected = _project(
        raw_observation(
            *(ax_node(f"noise-{index}", "StaticText", f"Noise {index}") for index in range(70)),
            ax_node("critical", "button", "Continue task"),
        )
    )
    task = TaskGoal(
        "task:adversarial-pinning",
        "Continue task",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    state = __import__(
        "affordance_runtime.agent.state",
        fromlist=["AgentLoopState"],
    ).AgentLoopState(projected.world, remaining_turns=2)
    evaluation = TaskEvaluation(
        task.task_id,
        projected.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projected.world),
        evaluation,
    )

    assert any(item.label == "Continue task" for item in context.world.targets.items)
    assert context.world.traversal is not None
    assert context.world.traversal.next_cursor
    assert len(context.world.targets.items) == 64


def test_private_handles_and_benchmark_identity_are_absent_from_agent_context() -> None:
    raw = raw_observation(ax_node("private-1", "button", "okay"))
    snapshot = reset_task_state("obs:1")
    world = project_browsergym_observation(
        raw,
        observation_id="obs:1",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=snapshot,
        entity_identity=_IDENTITY,
    ).world
    task = TaskGoal("task:opaque", raw["goal"], allowed_effects=("external_ui_interaction",))
    state = __import__(
        "affordance_runtime.agent.state",
        fromlist=["AgentLoopState"],
    ).AgentLoopState(world, remaining_turns=2)
    evaluation = TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing")
    context = ContextBuilder().build(task, state, ActionSpaceBuilder().build(task, world), evaluation)
    serialized = serialize_agent_context(context)
    for forbidden in ("private-1", "browsergym/miniwob", "selector", "expected_answer", "RAW_REWARD_GLOBAL"):
        assert forbidden not in serialized
    assert json.loads(serialized)["task"]["instruction"] == raw["goal"]
    source_wire = json.loads(serialized)["world"]["sources"][0]
    assert source_wire["projection_coverage"] == "complete"
    assert "coverage" not in source_wire
    assert source_wire["semantic_inventory"]["status"] == "represented"
    assert source_wire["entity_inventory"]["status"] == "complete"


def _project(raw):
    snapshot = reset_task_state("obs:1")
    return project_browsergym_observation(
        raw,
        observation_id="obs:1",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=snapshot,
        entity_identity=_IDENTITY,
    )


def _project_with_identity(raw, identity, *, page_identity="page:opaque"):
    snapshot = reset_task_state("obs:identity")
    return project_browsergym_observation(
        raw,
        observation_id="obs:identity",
        source_revision="revision:identity",
        page_identity=page_identity,
        episode_identity="episode:one",
        task_state=snapshot,
        entity_identity=identity,
    )
