import json

import numpy as np
import pytest

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolPhase,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.surfaces.browsergym import projection as projection_module
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    MAX_OBSERVATION_GROUNDING_REGIONS,
    CoverageState,
    EntityInventoryIssueCode,
    EntityInventoryStatus,
    SemanticInventoryStatus,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import ax_node, raw_observation, reset_task_state
from tests.support.surfaces.browsergym.projection_support import (
    project_browsergym_observation,
)

_IDENTITY = BrowserGymEntityIdentityMap(b"browsergym-world-projection-tests")


def test_public_page_route_excludes_credentials_query_and_fragment() -> None:
    assert (
        projection_module._public_page_route(
            "https://user:secret@example.test:8443/catalog/item-7?token=private#details"
        )
        == "https://example.test:8443/catalog/item-7"
    )
    assert projection_module._public_page_route("javascript:alert(1)") == ""


def test_public_page_title_is_browser_owned_bounded_display_metadata() -> None:
    assert projection_module._public_page_title("  OpenStreetMap\nDirections  ") == ("OpenStreetMap Directions")
    assert len(projection_module._public_page_title("x" * 500)) == 240


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


_RUNTIME_ROLES = {"viewport", "focused_context", "browser_context"}


def _page_targets(world):
    return tuple(item for item in world.targets if item.role not in _RUNTIME_ROLES)


def _runtime_targets(world):
    return tuple(item for item in world.targets if item.role in _RUNTIME_ROLES)


def _page_bindings(world):
    page_target_ids = {item.target_id for item in _page_targets(world)}
    return tuple(item for item in world.bindings if item.target_id in page_target_ids)


def _page_structure(world):
    page_target_ids = {item.target_id for item in _page_targets(world)}
    return tuple(
        item
        for item in world.sources[0].structure
        if item.semantic_target_id in page_target_ids or item.semantic_target_id == ""
    )


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
    assert len(_page_targets(projected.world)) == 3
    assert {item.role for item in _runtime_targets(projected.world)} == {"viewport", "focused_context"}
    assert len(_page_bindings(projected.world)) == 6
    assert projected.target_count_total == 5
    assert str(projected.world.source_manifest[0].coverage) == "complete"
    public = repr(projected.world)
    assert "private-" not in public
    assert "selector" not in public and "bid" not in public
    select = next(item for item in _page_bindings(projected.world) if item.semantic_action == "select_option")
    assert select.parameter_schema["properties"]["value"]["enum"] == ("A", "B")
    select_target = next(item for item in projected.world.targets if item.role == "combobox")
    assert tuple(select_target.state["option_domain"]) == ("A", "B")
    private_select = next(item for item in projected.private_bindings if item.binding_id == select.binding_id)
    assert dict(private_select.option_values) == {"A": "A", "B": "B"}
    inventory = projected.world.sources[0].semantic_inventory
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (
        inventory.recognized_target_count,
        inventory.projected_target_count,
        inventory.actionable_target_count,
        inventory.non_executable_target_count,
        inventory.omitted_target_count,
        inventory.informational_target_count,
    ) == (5, 5, 5, 0, 0, 0)
    retained = projected.world.sources[0].entity_inventory
    assert retained.status is EntityInventoryStatus.COMPLETE
    assert (retained.entity_count, retained.entity_total_count) == (5, 5)
    assert (retained.option_value_count, retained.option_value_total_count) == (2, 2)


def test_explicit_browser_profile_projects_navigation_without_page_identity_inference() -> None:
    raw = raw_observation(ax_node("search", "textbox", "Search"), url="https://docs.example.test/guide")
    raw["open_pages_urls"] = np.asarray(
        (
            "https://example.test/start?private=1",
            "https://docs.example.test/guide",
        )
    )
    raw["open_pages_titles"] = np.asarray(("Example start", "Documentation guide"))
    raw["active_page_index"] = np.asarray([1])
    common = {
        "observation_id": "obs:navigation",
        "source_revision": "revision:navigation",
        "page_identity": "page:navigation",
        "episode_identity": "0",
        "task_state": reset_task_state("obs:navigation"),
        "entity_identity": BrowserGymEntityIdentityMap(b"browser-navigation-profile"),
    }

    miniwob = project_browsergym_observation(raw, **common)
    webarena = project_browsergym_observation(
        raw,
        browser_global_primitives=(
            "goto",
            "go_back",
            "go_forward",
            "new_tab",
            "tab_focus",
            "tab_close",
        ),
        **common,
    )

    assert all(item.role != "browser_context" for item in miniwob.world.targets)
    browser = next(item for item in webarena.world.targets if item.role == "browser_context")
    assert browser.state["active_tab_index"] == 1
    assert browser.state["navigation_scope"] == "unrestricted"
    assert browser.state["open_tabs"][0]["route"] == "https://example.test/start"
    assert browser.state["open_tabs"][0]["title"] == "Example start"
    assert browser.state["open_tabs"][1]["title"] == "Documentation guide"
    task = TaskGoal(
        "task:navigation",
        "Navigate",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    action_space = ActionSpaceBuilder().build(task, webarena.world)
    actions = {item.semantic_action: item for item in action_space.options if item.target_id == browser.target_id}
    assert set(actions) == {"goto", "go_back", "go_forward", "new_tab", "tab_focus", "tab_close"}
    assert actions["tab_focus"].parameter_schema["properties"]["index"]["enum"] == (0,)
    changed_title_raw = dict(raw)
    changed_title_raw["open_pages_titles"] = np.asarray(("Changed title", "Another title"))
    changed_title_raw["open_pages_urls"] = np.asarray(
        (
            "https://example.test/start?private=2",
            "https://docs.example.test/guide",
        )
    )
    changed_title = project_browsergym_observation(
        changed_title_raw,
        observation_id="obs:navigation-title-change",
        source_revision="revision:navigation-title-change",
        page_identity="page:navigation",
        episode_identity="0",
        task_state=reset_task_state("obs:navigation-title-change"),
        entity_identity=BrowserGymEntityIdentityMap(b"browser-navigation-profile"),
        browser_global_primitives=(
            "goto",
            "go_back",
            "go_forward",
            "new_tab",
            "tab_focus",
            "tab_close",
        ),
        browser_navigation_locations=None,
    )
    original_tab_focus = next(item for item in webarena.world.bindings if item.semantic_action == "tab_focus")
    changed_tab_focus = next(item for item in changed_title.world.bindings if item.semantic_action == "tab_focus")
    assert changed_tab_focus.target_fingerprint == original_tab_focus.target_fingerprint

    evaluation = TaskEvaluation(
        task.task_id,
        webarena.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(task, webarena.world, action_space, evaluation)
    delivery = build_model_turn_delivery(context, include_images=False)
    public = GroundedPolicyContextBinder._public_context(context, False, delivery)
    model_observation = public["observation"]
    assert isinstance(model_observation, str)
    assert model_observation == delivery.view.text
    assert "CurrentActionSubjects" in model_observation
    assert 'browser_context label="Browser navigation"' in model_observation
    assert '"title":"Example start"' in model_observation
    assert '"title":"Documentation guide"' in model_observation
    assert 'viewport label="Current page viewport"' in model_observation
    assert 'focused_context label="Current keyboard focus"' in model_observation
    assert '"active_tab_index":1' in model_observation
    assert '"index":0,"route":"https://example.test/start"' in model_observation
    assert '"index":1,"route":"https://docs.example.test/guide"' in model_observation
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION, delivery)
    browser_specs = {
        item.name: item
        for item in catalog.specs
        if item.name in {"goto", "go_back", "go_forward", "new_tab", "tab_focus", "tab_close"}
    }
    assert set(browser_specs) == set(actions)
    assert {route.operation for route in delivery.manifest.action_routes if route.operation in actions} == set(actions)
    assert all("target" not in item.input_schema["properties"] for item in browser_specs.values())
    assert browser_specs["tab_focus"].input_schema["properties"]["index"] == {
        "type": "integer",
        "minimum": 0,
    }
    goto = next(item for item in catalog.specs if item.name == "goto")
    assert tuple(goto.input_schema["required"]) == ("url",)
    assert "target" not in goto.input_schema["properties"]
    resolved = resolve_grounded_tool_call(
        catalog,
        ToolCall("goto", {"url": "https://docs.example.test/guide"}, "call:goto"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    )
    assert resolved.decision.action_id == actions["goto"].action_id
    assert resolved.decision.parameters == {"url": "https://docs.example.test/guide"}

    with pytest.raises(ValueError, match="browser-action profile"):
        project_browsergym_observation(
            raw,
            browser_global_primitives=("invented_navigation",),
            **common,
        )


def test_environment_navigation_scope_does_not_publish_its_private_location_allowlist() -> None:
    raw = raw_observation(url="https://wiki.example.test/wiki/Portland")
    raw["open_pages_urls"] = np.asarray(
        (
            "https://map.example.test:3000/",
            "https://wiki.example.test/wiki/Portland",
        )
    )
    raw["open_pages_titles"] = np.asarray(("OpenStreetMap", "Portland, Maine"))
    raw["active_page_index"] = np.asarray([1])
    projected = project_browsergym_observation(
        raw,
        observation_id="obs:restricted-navigation",
        source_revision="revision:restricted-navigation",
        page_identity="page:restricted-navigation",
        episode_identity="0",
        task_state=reset_task_state("obs:restricted-navigation"),
        entity_identity=BrowserGymEntityIdentityMap(b"restricted-browser-navigation"),
        browser_global_primitives=("goto", "tab_focus"),
        browser_navigation_locations=("map.example.test:3000", "wiki.example.test"),
    )
    browser = next(item for item in projected.world.targets if item.role == "browser_context")
    assert browser.state["navigation_scope"] == "environment_restricted"
    assert "allowed_navigation_locations" not in browser.state
    assert browser.state["open_tabs"][0]["title"] == "OpenStreetMap"
    task = TaskGoal(
        "task:restricted-navigation",
        "Use the configured browser environment",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    action_space = ActionSpaceBuilder().build(task, projected.world)
    context = ContextBuilder().build(
        task,
        projected.world,
        action_space,
        TaskEvaluation(
            task.task_id,
            projected.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )
    delivery = build_model_turn_delivery(context, include_images=False)
    assert '"navigation_scope":"environment_restricted"' in delivery.view.text
    assert "allowed_navigation_locations" not in delivery.view.text
    assert '"title":"OpenStreetMap"' in delivery.view.text
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION, delivery)
    goto = next(item for item in catalog.specs if item.name == "goto")
    serialized_schema = repr(goto.input_schema)
    assert "map.example.test" not in serialized_schema
    assert "wiki.example.test" not in serialized_schema
    assert goto.input_schema["properties"]["url"]["pattern"] == r"^https?://.+"
    allowed = resolve_grounded_tool_call(
        catalog,
        ToolCall("goto", {"url": "https://map.example.test:3000/search?q=Acadia"}, "call:allowed"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    )
    assert allowed.decision.parameters == {"url": "https://map.example.test:3000/search?q=Acadia"}
    external = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "goto",
            {"url": "https://external.example.test/resource"},
            "call:external",
        ),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    )
    assert external.decision.parameters == {"url": "https://external.example.test/resource"}


def test_screenshot_grounding_is_viewport_bounded_and_prioritizes_actions() -> None:
    nodes = tuple(
        ax_node(f"text-{index}", "StaticText", f"Text {index}")
        for index in range(MAX_OBSERVATION_GROUNDING_REGIONS + 100)
    )
    raw = raw_observation(
        *nodes,
        ax_node("action", "button", "Act"),
        ax_node("offscreen", "button", "Below viewport"),
    )
    raw["screenshot"] = np.zeros((240, 320, 3), dtype=np.uint8)
    for bid, physical in raw[PRIVATE_CONTROL_PROPERTIES_KEY].items():
        physical["bbox"] = [10, 10, 20, 20]
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["action"]["bbox"] = [310, 230, 20, 20]
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["offscreen"]["bbox"] = [10, 1_000, 20, 20]

    projected = _project(raw)

    media = projected.world.sources[0].media[0]
    targets = {item.label: item.target_id for item in projected.world.targets}
    regions = {item.target_id: item for item in media.grounding_regions}
    assert len(regions) == MAX_OBSERVATION_GROUNDING_REGIONS
    assert regions[targets["Act"]].bbox == (310, 230, 10, 10)
    assert targets["Below viewport"] not in regions


def test_hidden_native_select_keeps_one_semantic_binding_on_existing_projection_path() -> None:
    raw = raw_observation(
        ax_node("private-select", "combobox", "Height", value="5ft 10in"),
        ax_node("private-short", "option", "5ft 10in"),
        ax_node("private-tall", "option", "6 ft"),
    )
    physical = raw[PRIVATE_CONTROL_PROPERTIES_KEY]["private-select"]
    physical["visible"] = False
    physical["editable"] = False
    physical["options"].insert(0, {"label": "", "value": ""})

    projected = project_browsergym_observation(
        raw,
        observation_id="obs:hidden-select",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=reset_task_state("obs:hidden-select"),
        entity_identity=_IDENTITY,
    )

    assert len(_page_targets(projected.world)) == 1
    assert len(_page_bindings(projected.world)) == 1
    binding = _page_bindings(projected.world)[0]
    assert binding.semantic_action == binding.primitive_action == "select_option"
    assert binding.parameter_schema["properties"]["value"]["enum"] == (
        "5ft 10in",
        "6 ft",
    )
    assert "private-select" not in repr(projected.world)


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

    first = {item.label: item.target_id for item in _page_targets(baseline.world)}
    second = {item.label: item.target_id for item in _page_targets(reordered.world)}
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

    first_ids = tuple(item.target_id for item in _page_targets(first_page.world))
    second_ids = tuple(item.target_id for item in _page_targets(second_page.world))
    assert len(set(first_ids)) == 2
    assert set(first_ids).isdisjoint(second_ids)


def test_structure_identity_remains_unique_when_ax_nodes_share_one_bid() -> None:
    first = ax_node("shared-private", "LineBreak", "\n")
    second = ax_node("shared-private", "InlineTextBox", "")
    first["nodeId"] = "ax-node:first"
    second["nodeId"] = "ax-node:second"

    projected = _project_with_identity(
        raw_observation(first, second),
        BrowserGymEntityIdentityMap(b"shared-bid-structure-test-key"),
    )
    structure = _page_structure(projected.world)

    assert len(structure) == 2
    assert len({item.structure_id for item in structure}) == 2
    assert all(item.structure_id.startswith("structure:") for item in structure)


def test_newly_projected_checkbox_is_observable_and_actionable_without_private_routes() -> None:
    baseline_raw = raw_observation(ax_node("button", "button", "Save"))
    omitted_raw = raw_observation(
        ax_node("button", "button", "Save"),
        ax_node("check", "checkbox", "Remember"),
    )
    baseline = _project(baseline_raw)
    omitted = _project(omitted_raw)

    assert len(_page_targets(omitted.world)) == len(_page_targets(baseline.world)) + 1
    checkbox = next(item for item in omitted.world.targets if item.role == "checkbox")
    assert checkbox.label == "Remember"
    assert len(_page_bindings(omitted.world)) == len(_page_bindings(baseline.world)) + 2
    assert {item.semantic_action for item in _page_bindings(omitted.world) if item.target_id == checkbox.target_id} == {
        "activate",
        "press_key",
    }
    assert omitted.world.source_manifest[0].coverage is CoverageState.COMPLETE
    assert baseline.world.source_manifest[0].coverage is CoverageState.COMPLETE
    task = TaskGoal(
        "task:inventory",
        "Save",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    assert (
        len(ActionSpaceBuilder().build(task, omitted.world).options)
        == len(ActionSpaceBuilder().build(task, baseline.world).options) + 2
    )
    inventory = omitted.world.sources[0].semantic_inventory
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (inventory.recognized_target_count, inventory.projected_target_count) == (4, 4)


def test_focused_executable_bid_has_one_element_press_route_without_focused_fallback() -> None:
    raw = raw_observation(ax_node("search", "searchbox", "Search"))
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["search"]["focused"] = True

    projected = _project(raw)
    focused_target = next(item for item in projected.world.targets if item.label == "Search")
    press_bindings = tuple(item for item in _page_bindings(projected.world) if item.semantic_action == "press_key")

    assert len(press_bindings) == 1
    assert press_bindings[0].target_id == focused_target.target_id
    assert press_bindings[0].primitive_action == "press"
    assert all(item.role != "focused_context" for item in projected.world.targets)


def test_focused_context_fallback_remains_when_no_concrete_press_target_exists() -> None:
    projected = _project(raw_observation(ax_node("status", "status", "Ready")))

    focused = next(item for item in projected.world.targets if item.role == "focused_context")
    binding = next(
        item
        for item in projected.world.bindings
        if item.target_id == focused.target_id and item.semantic_action == "press_key"
    )

    assert binding.primitive_action == "keyboard_press"


def test_visible_structure_without_executable_binding_records_eligibility_reason() -> None:
    raw = raw_observation(ax_node("reports-menu-item", "link", "Bestsellers"))
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["reports-menu-item"]["visible"] = False
    projected = project_browsergym_observation(
        raw,
        observation_id="obs:eligibility",
        source_revision="revision:eligibility",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=reset_task_state("obs:eligibility"),
        entity_identity=_IDENTITY,
    )

    target = next(item for item in _page_targets(projected.world) if item.label == "Bestsellers")
    assert target.state["action.why_not_eligible"] == ("availability.visible_false",)
    assert not any(binding.target_id == target.target_id for binding in _page_bindings(projected.world))
    artifact = projected.world.sources[0].artifacts["browsergym_action_eligibility"]
    assert artifact["items"][0]["label"] == "Bestsellers"
    assert artifact["items"][0]["why_not_eligible"] == ("availability.visible_false",)

    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["reports-menu-item"]["visible"] = True
    stable = project_browsergym_observation(
        raw,
        observation_id="obs:eligible",
        source_revision="revision:eligible",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=reset_task_state("obs:eligible"),
        entity_identity=_IDENTITY,
    )
    stable_target = next(item for item in _page_targets(stable.world) if item.label == "Bestsellers")
    assert any(binding.target_id == stable_target.target_id for binding in _page_bindings(stable.world))


def test_drag_source_publishes_one_finite_semantic_destination_domain() -> None:
    raw = raw_observation(
        ax_node("source-private", "generic", "Quarterly report"),
        ax_node("destination-private", "generic", "Archive"),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["source-private"].update(
        {
            "gesture_role": "draggable",
            "gesture_group": "group-private",
            "gesture_kind": "move",
            "bbox": [10, 10, 40, 20],
        }
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["destination-private"].update(
        {
            "gesture_role": "drop_target",
            "gesture_group": "group-private",
            "bbox": [80, 10, 60, 40],
        }
    )

    projected = _project(raw)
    by_role = {item.role: item for item in projected.world.targets}
    source = by_role["draggable"]
    destination = by_role["drop_target"]
    binding = next(item for item in projected.world.bindings if item.semantic_action == "drag_to")

    assert binding.target_id == source.target_id
    assert binding.destination_required is True
    assert binding.eligible_destination_ids == (destination.target_id,)
    assert binding.parameter_schema == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    private = next(item for item in projected.private_bindings if item.binding_id == binding.binding_id)
    assert private.destination(destination.target_id).private_element_id == "destination-private"
    assert "source-private" not in repr(projected.world)
    assert "destination-private" not in repr(projected.world)


def test_static_text_is_projected_as_read_only_information() -> None:
    projected = _project(raw_observation(ax_node("static", "StaticText", "Information")))
    inventory = projected.world.sources[0].semantic_inventory
    assert projected.world.source_manifest[0].coverage is CoverageState.COMPLETE
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert inventory.recognized_target_count == 3
    assert len(_page_targets(projected.world)) == 1
    assert _page_targets(projected.world)[0].role == "StaticText"
    assert _page_bindings(projected.world) == ()
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
    assert _page_bindings(projected.world) == ()


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
        projected.world,
        ActionSpaceBuilder().build(task, projected.world),
        TaskEvaluation(
            task.task_id,
            projected.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    delivery = build_model_turn_delivery(context, include_images=False)
    public = GroundedPolicyContextBinder._public_context(context, False, delivery)
    option = next(item for item in context.complete_actions if item.target_label == "Add to cart")
    observation = public["observation"]

    assert "Products" in repr(context.actor_world)
    assert "MacBook Pro" in repr(context.actor_world)
    button_line = next(line for line in observation.splitlines() if f"[{option.target_ref}] button" in line)
    assert '"Add to cart"' in button_line
    assert 'verbs=["activate","press_key"]' in button_line
    assert 'path=["MacBook Pro","Add to cart"]' in button_line
    assert 'context=["Products","MacBook Pro"]' in button_line
    assert delivery.view.coverage["candidate_region_expansion_reason"] == "none"
    encoded = json.dumps(observation)
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
    clickable_bindings = tuple(
        item for item in _page_bindings(projected.world) if item.target_id == clickable.target_id
    )
    assert {item.semantic_action for item in clickable_bindings} == {"activate"}
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
    evaluation = TaskEvaluation(
        task.task_id,
        projected.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        task,
        projected.world,
        ActionSpaceBuilder().build(task, projected.world),
        evaluation,
    )
    assert context.image_inputs[0].sha256 == media[0].sha256
    delivery = build_model_turn_delivery(context, include_images=False)
    serialized = json.dumps(GroundedPolicyContextBinder._public_context(context, False, delivery))
    assert "image_inputs" not in serialized
    assert media[0].sha256 not in serialized


def test_inactive_tab_panel_descendants_do_not_gain_action_authority() -> None:
    def accordion(selected: bool):
        raw = raw_observation(
            ax_node(
                "header",
                "tab",
                "Section #37",
                properties=(("selected", selected),),
                child_ids=("header-text",),
            ),
            ax_node("header-text", "StaticText", "Section #37", parent_id="header"),
            ax_node(
                "panel",
                "tab",
                " Submit",
                properties=(("selected", selected),),
                child_ids=("submit",),
            ),
            ax_node("submit", "button", "Submit", parent_id="panel"),
        )
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["submit"]["visible"] = selected
        return raw

    collapsed = _project(accordion(False))
    collapsed_labels = {
        next(item.label for item in collapsed.world.targets if item.target_id == binding.target_id)
        for binding in _page_bindings(collapsed.world)
    }
    assert collapsed_labels == {"Section #37"}

    expanded = _project(accordion(True))
    expanded_labels = {
        next(item.label for item in expanded.world.targets if item.target_id == binding.target_id)
        for binding in _page_bindings(expanded.world)
    }
    assert expanded_labels == {"Section #37", "Submit"}


def test_projected_non_executable_and_large_option_domain_are_distinct() -> None:
    disabled = raw_observation(ax_node("disabled", "button", "Disabled"))
    disabled[PRIVATE_CONTROL_PROPERTIES_KEY]["disabled"]["enabled"] = False
    disabled_projection = _project(disabled)
    disabled_inventory = disabled_projection.world.sources[0].semantic_inventory
    assert disabled_inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (disabled_inventory.projected_target_count, disabled_inventory.non_executable_target_count) == (3, 1)
    assert disabled_inventory.actionable_target_count == 2

    many_options = raw_observation(
        ax_node("select", "combobox", "Choice"),
        *(ax_node(f"option-{index}", "option", f"Choice {index}") for index in range(17)),
    )
    select_projection = _project(many_options)
    select_inventory = select_projection.world.sources[0].semantic_inventory
    assert select_inventory.status is SemanticInventoryStatus.REPRESENTED
    assert select_inventory.non_executable_target_count == 0
    assert {item.semantic_action for item in _page_bindings(select_projection.world)} == {
        "press_key",
        "select_option",
    }
    assert select_inventory.omitted_target_count == 0


@pytest.mark.parametrize("option_count", (12, 13, 16, 17, 512, 513))
def test_select_option_domain_has_one_shared_capacity_contract(option_count: int) -> None:
    projected = _project(
        raw_observation(
            ax_node("select", "combobox", "Choice"),
            *(ax_node(f"option-{index}", "option", f"Choice {index}") for index in range(option_count)),
        )
    )
    select_bindings = tuple(item for item in _page_bindings(projected.world) if item.semantic_action == "select_option")

    if option_count <= 512:
        assert len(select_bindings) == 1
        assert len(select_bindings[0].parameter_schema["properties"]["value"]["enum"]) == option_count
        assert projected.world.source_manifest[0].coverage is CoverageState.COMPLETE
    else:
        assert select_bindings == ()
        inventory = projected.world.sources[0].entity_inventory
        assert inventory.status is EntityInventoryStatus.PARTIAL
        assert inventory.option_value_count == 512
        assert inventory.option_value_total_count == option_count
        assert EntityInventoryIssueCode.OPTION_DOMAIN_CAPACITY_EXCEEDED in inventory.issue_codes


def test_fact_only_truncation_does_not_change_target_inventory(monkeypatch) -> None:
    monkeypatch.setattr(projection_module, "MAX_INVENTORY_FACTS", 0)
    projected = _project(
        raw_observation(
            ax_node("field", "textbox", "Name", value="Ada", properties=(("required", True),)),
        )
    )
    inventory = projected.world.sources[0].semantic_inventory
    assert projected.world.source_manifest[0].coverage is CoverageState.TRUNCATED
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (inventory.recognized_target_count, inventory.projected_target_count) == (3, 3)
    retained = projected.world.sources[0].entity_inventory
    assert retained.status is EntityInventoryStatus.PARTIAL
    assert retained.issue_codes == (EntityInventoryIssueCode.FACT_CAPACITY_EXCEEDED,)


def test_model_page_limit_does_not_delete_entities_or_action_bindings() -> None:
    projected = _project(
        raw_observation(*(ax_node(f"button-{index}", "button", f"Button {index}") for index in range(65)))
    )

    assert len(_page_targets(projected.world)) == 65
    assert len(_page_bindings(projected.world)) == 130
    assert projected.world.source_manifest[0].coverage is CoverageState.COMPLETE
    assert projected.world.sources[0].entity_inventory.status is EntityInventoryStatus.COMPLETE

    task = TaskGoal(
        "task:paging",
        "Click Button 64",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    evaluation = TaskEvaluation(
        task.task_id,
        projected.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    action_space = ActionSpaceBuilder().build(task, projected.world)
    context = ContextBuilder().build(
        task,
        projected.world,
        action_space,
        evaluation,
    )
    assert len(action_space.options) == 132
    document = context.actor_world.documents[0]
    assert document.total_node_count == 67
    assert document.retained_node_count == 67
    assert document.truncated is False
    assert context.actor_world.traversal is None


def test_action_inventory_does_not_publish_a_first_512_partial_world() -> None:
    projected = _project(
        raw_observation(*(ax_node(f"button-{index}", "button", f"Button {index}") for index in range(513)))
    )

    assert len(_page_targets(projected.world)) == 513
    assert len(_page_bindings(projected.world)) == 1_026
    assert projected.world.source_manifest[0].coverage is CoverageState.COMPLETE
    assert projected.world.sources[0].entity_inventory.status is EntityInventoryStatus.COMPLETE


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
    evaluation = TaskEvaluation(
        task.task_id,
        projected.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        task,
        projected.world,
        ActionSpaceBuilder().build(task, projected.world),
        evaluation,
    )

    nodes = tuple(node for document in context.actor_world.documents for root in document.roots for node in _walk(root))
    assert any(item.label == "Continue task" for item in nodes)
    assert context.actor_world.traversal is None
    assert len(nodes) == 73


def test_off_viewport_capabilities_remain_complete_across_action_pages() -> None:
    raw = raw_observation(
        *(
            node
            for index in range(40)
            for node in (
                ax_node(f"control-{index}", "graphics-symbol", "", child_ids=(f"text-{index}",)),
                ax_node(f"text-{index}", "StaticText", f"Control {index}", parent_id=f"control-{index}"),
            )
        ),
        ax_node("submit", "button", "Submit"),
    )
    for index in range(40):
        bid = f"control-{index}"
        raw["extra_element_properties"][bid].update(
            {
                "clickable": True,
                "visibility": 1.0 if index < 8 else 0.0,
                "bbox": [20.0 + (index % 4) * 40.0, 40.0 + (index // 4) * 80.0, 24.0, 24.0],
            }
        )
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = raw["extra_element_properties"][bid]["bbox"]

    world = _project(raw).world
    task = TaskGoal(
        "task:complete-action-paging",
        "Activate the requested controls and submit.",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    action_space = ActionSpaceBuilder().build(task, world)
    builder = ContextBuilder()
    seen: set[str] = set()
    cursor = ""
    page_count = 0
    while True:
        page = builder.page(action_space, world, cursor=cursor)
        seen.update(page.visible_action_ids)
        page_count += 1
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert page_count > 1
    assert seen == {item.action_id for item in action_space.options}
    assert len(seen) == len(world.bindings) == 44


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
    evaluation = TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing")
    context = ContextBuilder().build(task, world, ActionSpaceBuilder().build(task, world), evaluation)
    serialized = repr((context.task, context.goal_plan, context.actions, context.actor_world))
    for forbidden in ("private-1", "browsergym/miniwob", "selector", "expected_answer", "RAW_REWARD_GLOBAL"):
        assert forbidden not in serialized
    assert context.task.instruction == raw["goal"]
    assert context.actor_world.sources[0].projection_coverage == "complete"
    assert context.actor_world.sources[0].inventory_coverage == "complete"


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
