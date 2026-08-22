from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from affordance_runtime.actions import ActionBinding, ActionRisk, ActionSpace, ActionSpaceBuilder
from affordance_runtime.agent.context.compact_world_renderer import (
    CapacityExceeded,
    Empty,
    InvalidCursor,
    InvalidRegion,
    Matches,
    Opened,
    Page,
    StaleContext,
    inspect_actor_world,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.benchmarks.webarena_verified import (
    DeliveryRetrievalProbe,
    _delivery_probe_item_diagnostic,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_tool_catalog
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.agent.core_loop_support import _task, _world
from tests.support.model_delivery import catalog_for, resolve_catalog_call


def _evaluation(task: TaskGoal, observation_id: str) -> TaskEvaluation:
    return TaskEvaluation(
        task.task_id,
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "semantic delivery fixture",
    )


def test_delivery_probe_requires_one_item_to_close_label_role_operation_and_manifest() -> None:
    probe = DeliveryRetrievalProbe("Search", ("search",), ("searchbox",), ("type_text",))
    action = SimpleNamespace(target_ref="E7", operation="type_text")

    label_only = _delivery_probe_item_diagnostic(
        SimpleNamespace(target_ref="N1", label="Search", role="generic", operation=""),
        probe,
        ("N1", "E7"),
        (action,),
    )
    role_operation_only = _delivery_probe_item_diagnostic(
        SimpleNamespace(target_ref="E7", label="Query", role="searchbox", operation="type_text"),
        probe,
        ("N1", "E7"),
        (action,),
    )
    joint = _delivery_probe_item_diagnostic(
        SimpleNamespace(target_ref="E7", label="Search", role="searchbox", operation="type_text"),
        probe,
        ("N1", "E7"),
        (action,),
    )

    assert label_only == {
        "label": True,
        "label_and_kind": False,
        "label_kind_operation": False,
        "path": True,
        "matched": False,
    }
    assert not role_operation_only["matched"]
    assert joint["matched"]

    path_probe = DeliveryRetrievalProbe(
        "Search",
        ("search",),
        ("searchbox",),
        ("type_text",),
        ("workspace",),
    )
    wrong_path = _delivery_probe_item_diagnostic(
        SimpleNamespace(
            target_ref="E7",
            label="Search",
            role="searchbox",
            operation="type_text",
            functional_path=("Overview",),
        ),
        path_probe,
        ("E7",),
        (action,),
    )
    assert wrong_path["path"] is False
    assert wrong_path["matched"] is False


def _functional_world(*, rows: int = 3):
    row_ids = tuple(f"row:{index}" for index in range(rows))
    targets = (
        SemanticTarget("home", "link", "Home"),
        *(SemanticTarget(item, "button", f"Item {index}") for index, item in enumerate(row_ids)),
    )
    nodes = (
        ObservationStructureNode("root", "document", "Catalog", child_structure_ids=("empty", "nav", "main")),
        ObservationStructureNode("empty", "generic", "", parent_structure_id="root", child_structure_ids=("icon",)),
        ObservationStructureNode("icon", "img", "", parent_structure_id="empty"),
        ObservationStructureNode(
            "nav", "navigation", "Primary", parent_structure_id="root", child_structure_ids=("home",)
        ),
        ObservationStructureNode("home", "link", "Home", parent_structure_id="nav", semantic_target_id="home"),
        ObservationStructureNode(
            "main", "main", "Products", parent_structure_id="root", child_structure_ids=("heading", "list")
        ),
        ObservationStructureNode("heading", "heading", "Featured", parent_structure_id="main"),
        ObservationStructureNode("list", "list", "Products", parent_structure_id="main", child_structure_ids=row_ids),
        *(
            ObservationStructureNode(
                item,
                "listitem",
                f"Item {index}",
                parent_structure_id="list",
                semantic_target_id=item,
            )
            for index, item in enumerate(row_ids)
        ),
    )
    source = SurfaceObservation(
        "source:catalog",
        "browser",
        "revision:catalog",
        ObservationSourceProfile.dom(),
        targets,
        structure=nodes,
        structure_total_count=len(nodes),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return result.observation


def _table_world(*, rows: int = 5, coverage: CoverageState = CoverageState.COMPLETE):
    header_ids = ("header:product", "header:price", "header:quantity")
    row_ids = tuple(f"body:row:{index}" for index in range(rows))
    cell_ids = tuple(f"{row_id}:cell:{column}" for row_id in row_ids for column in ("product", "price", "quantity"))
    targets = (
        SemanticTarget(header_ids[0], "columnheader", "Product"),
        SemanticTarget(header_ids[1], "columnheader", "Price"),
        SemanticTarget(header_ids[2], "columnheader", "Quantity"),
        *(
            SemanticTarget(
                cell_id,
                "StaticText",
                (f"Product {index}" if column == "product" else "$19.00" if column == "price" else str(index + 1)),
            )
            for index, row_id in enumerate(row_ids)
            for column, cell_id in (
                ("product", f"{row_id}:cell:product"),
                ("price", f"{row_id}:cell:price"),
                ("quantity", f"{row_id}:cell:quantity"),
            )
        ),
    )
    nodes = (
        ObservationStructureNode("root", "document", "Dashboard", child_structure_ids=("main",)),
        ObservationStructureNode(
            "main", "main", "Dashboard", parent_structure_id="root", child_structure_ids=("table",)
        ),
        ObservationStructureNode(
            "table",
            "table",
            "Bestsellers summary",
            parent_structure_id="main",
            child_structure_ids=("table:head", "table:body"),
        ),
        ObservationStructureNode(
            "table:head",
            "rowgroup",
            "",
            parent_structure_id="table",
            child_structure_ids=("header:row",),
        ),
        ObservationStructureNode(
            "header:row",
            "row",
            "",
            parent_structure_id="table:head",
            child_structure_ids=header_ids,
        ),
        *(
            ObservationStructureNode(
                header_id,
                "columnheader",
                label,
                parent_structure_id="header:row",
                semantic_target_id=header_id,
            )
            for header_id, label in zip(header_ids, ("Product", "Price", "Quantity"), strict=True)
        ),
        ObservationStructureNode(
            "table:body",
            "rowgroup",
            "",
            parent_structure_id="table",
            child_structure_ids=row_ids,
        ),
        *(
            ObservationStructureNode(
                row_id,
                "row",
                "",
                parent_structure_id="table:body",
                child_structure_ids=tuple(item for item in cell_ids if item.startswith(f"{row_id}:")),
            )
            for row_id in row_ids
        ),
        *(
            ObservationStructureNode(
                cell_id,
                "StaticText",
                next(target.label for target in targets if target.target_id == cell_id),
                parent_structure_id=cell_id.rsplit(":cell:", 1)[0],
                semantic_target_id=cell_id,
            )
            for cell_id in cell_ids
        ),
    )
    source = SurfaceObservation(
        "source:dashboard",
        "browser",
        "revision:dashboard",
        ObservationSourceProfile.dom(),
        targets,
        coverage=coverage,
        structure=nodes,
        structure_total_count=len(nodes),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return result.observation


def _captured_dashboard_world():
    trace_path = Path(
        "evidence/live/w1b-one-task-0-zhipu-glm46-readable-tools-run2/traces/webarena-verified-w1b-task-0/trace.jsonl"
    )
    with trace_path.open(encoding="utf-8") as stream:
        payload = next(json.loads(line)["observation"] for line in stream if '"event":"observation"' in line)
    captured = payload["sources"][0]
    targets = tuple(SemanticTarget(**item) for item in captured["targets"])
    structures = tuple(ObservationStructureNode(**item) for item in captured["structure"])
    bindings = []
    for item in captured["bindings"]:
        values = dict(item)
        values["semantic_effects"] = tuple(values["semantic_effects"])
        values["eligible_destination_ids"] = tuple(values["eligible_destination_ids"])
        values["risk"] = ActionRisk(values["risk"])
        bindings.append(ActionBinding(**values))
    source = SurfaceObservation(
        captured["observation_id"],
        captured["surface"],
        captured["revision"],
        ObservationSourceProfile.dom(),
        targets,
        bindings=tuple(bindings),
        coverage=CoverageState(captured["coverage"]),
        structure=structures,
        structure_total_count=captured["structure_total_count"],
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return result.observation


def test_actor_normalization_conserves_supported_public_state_relation_and_fact() -> None:
    target = SemanticTarget(
        "target:one",
        "textbox",
        "Search",
        {"value": "exact user text", "selected": True, "semantic.dom.attribute.placeholder": "Find"},
        {"owns": ("target:two",)},
    )
    world = (
        WorldFusion()
        .fuse(
            (
                SurfaceObservation(
                    "source:lossless",
                    "browser",
                    "revision:lossless",
                    ObservationSourceProfile.dom(),
                    (target, SemanticTarget("target:two", "region", "Results")),
                    (StateFact("fact:value", "target:one", "value", "exact user text", "source:lossless"),),
                ),
            )
        )
        .observation
    )
    assert world is not None
    task = TaskGoal("lossless", "Inspect the search state")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    encoded = json.dumps(to_json_compatible(context.actor_world), ensure_ascii=False)

    assert "exact user text" in encoded
    assert "selected" in encoded
    assert "placeholder" in encoded
    assert "owns" in encoded
    assert '"value": "F1"' in encoded
    assert all(not item.truncated for item in context.actor_world.documents)


def test_functional_partition_uses_landmarks_headings_lists_and_merges_empty_icon_fragments() -> None:
    world = _functional_world(rows=3)
    index = WorldDeliveryIndex.from_observation(world)

    assert {item.role for item in index.regions} >= {"document", "navigation", "main", "list"}
    assert any(item.heading == "Featured" or "Featured" in item.direct_labels for item in index.regions)
    assert not any(item.root_structure_id in {"empty", "icon"} for item in index.regions)
    repeated = next(item for item in index.regions if item.role == "list")
    assert repeated.repeated_item_roots == ("row:0", "row:1", "row:2")
    assert set(index.target_region_keys) == {item.target_id for item in world.targets}


def test_repeated_collection_inspect_pages_at_twenty_complete_items() -> None:
    world = _functional_world(rows=25)
    task = TaskGoal("paging", "Inspect products")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    region = next(item for item in context.region_index.regions if item.role == "list")
    outcome = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        observation=world,
        action="read_region",
        region_ref=region.public_ref,
    )

    assert isinstance(outcome, Opened)
    assert len(outcome.items) == 20
    assert outcome.next_cursor


def test_table_is_one_atomic_region_with_headers_and_complete_rows() -> None:
    world = _table_world(coverage=CoverageState.TRUNCATED)
    task = TaskGoal("table", "Inspect the current summary")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
    )
    tables = tuple(item for item in context.region_index.regions if item.role == "table")

    assert len(tables) == 1
    table = tables[0]
    assert table.repeated_item_roots == tuple(f"body:row:{index}" for index in range(5))
    assert not any(item.role in {"rowgroup", "row", "listitem"} for item in context.region_index.regions)
    assert set(table.member_structure_ids) >= {"table", "table:head", "table:body"}
    assert table.source_coverage == "partial"
    assert table.region_membership == "complete"
    assert table.scope_path == ("Dashboard", "Bestsellers summary")
    assert table.counts["filter_controls"] == 0

    outcome = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        observation=world,
        action="read_region",
        region_ref=table.public_ref,
    )

    assert isinstance(outcome, Opened)
    assert outcome.source_coverage == "partial"
    assert outcome.region_membership == "complete"
    assert outcome.result_page == "1/1"
    schema_labels = {item["label"] for item in outcome.items if item.get("kind") == "schema_member"}
    rows = tuple(item for item in outcome.items if item.get("kind") == "complete_item")
    assert schema_labels >= {"Product", "Price", "Quantity"}
    assert len(rows) == 5
    assert all(len(item["targets"]) == 3 for item in rows)

    view = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        observation=world,
    )
    descriptor = next(line for line in view.text.splitlines() if f"[{table.public_ref}]" in line)
    assert 'context=["Dashboard","Bestsellers summary"]' in descriptor
    assert "available_filter_controls=0" in descriptor


def test_captured_dashboard_world_preserves_table_scope_rows_and_reports_action() -> None:
    world = _captured_dashboard_world()
    task = TaskGoal(
        "captured-dashboard",
        "Find the top-selling products in the requested year using the product report.",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        _evaluation(task, world.observation_id),
    )
    table = next(
        item
        for item in context.region_index.regions
        if item.role == "table"
        and item.repeated_item_roots
        and any("bestsellers" in scope.casefold() for scope in item.scope_path)
    )
    opened = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        observation=world,
        action="read_region",
        region_ref=table.public_ref,
    )
    view = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        observation=world,
        action_candidates=context.action_candidates,
    )
    reports = next(
        item
        for item in context.complete_actions
        if item.target_label.casefold().endswith("reports") and item.semantic_action == "activate"
    )

    # R refs are current-partition handles, not cross-version identities. The
    # old capture called this table R14; removing preceding orphan rowgroup
    # regions may legitimately renumber it while preserving exact resolution.
    assert context.region_index.resolve_public_ref(table.public_ref) is table
    assert table.scope_path[-2:] == ("Dashboard / Magento Admin", "Bestsellers")
    assert table.counts["filter_controls"] == 0
    assert not any(item.role == "rowgroup" for item in context.region_index.regions)
    assert isinstance(opened, Opened)
    assert opened.result_page == "1/1"
    assert any(item.get("kind") == "schema_member" for item in opened.items)
    assert len(tuple(item for item in opened.items if item.get("kind") == "complete_item")) == 5
    assert reports.target_ref in view.manifest.executable_refs
    assert f"[{reports.target_ref}] activate" in view.text


def test_page_map_manifest_is_atomic_and_folded_descriptors_contain_no_exact_refs() -> None:
    world = _functional_world(rows=25)
    task = TaskGoal("manifest", "Use primary navigation")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    view = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        observation=world,
        action_candidates=context.action_candidates,
    )
    page_map = view.text.split("ActiveView exact=true", 1)[0]

    assert view.projection == "page_map"
    assert set(view.manifest.region_refs) == set(context.region_index.public_refs)
    assert not any(f"[{prefix}" in page_map for prefix in ("E", "N", "F"))
    for ref in view.manifest.exact_refs:
        assert view.text.count(f"[{ref}]") == 1


def test_inspect_world_closed_outcome_algebra_and_currentness() -> None:
    world = _functional_world(rows=3)
    task = TaskGoal("inspect", "Inspect products")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    kwargs = {
        "snapshot": context.actor_world,
        "grounding": context.grounding,
        "region_index": context.region_index,
        "observation": world,
    }
    region_ref = context.region_index.regions[0].public_ref

    assert isinstance(inspect_actor_world(**kwargs, action="read_region", region_ref=region_ref), Opened)
    assert isinstance(inspect_actor_world(**kwargs, action="find", query="Item 1"), Matches)
    assert isinstance(inspect_actor_world(**kwargs, action="find", query="absent"), Empty)
    assert isinstance(inspect_actor_world(**kwargs, action="view_all"), Page)
    assert isinstance(inspect_actor_world(**kwargs, action="read_region", region_ref="R999"), InvalidRegion)
    assert isinstance(inspect_actor_world(**kwargs, action="view_all", cursor="bad"), InvalidCursor)
    assert isinstance(inspect_actor_world(**kwargs, action="view_all", hard_limit=1), CapacityExceeded)
    stale = replace(context.region_index, world_observation_id="world:stale")
    assert isinstance(
        inspect_actor_world(**{**kwargs, "region_index": stale}, action="view_all"),
        StaleContext,
    )


def test_world_paging_is_runtime_owned_and_continues_without_a_cursor_argument() -> None:
    world = _functional_world(rows=80)
    task = TaskGoal("read-pages", "Inspect products")
    builder = ContextBuilder()
    first = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
    )
    _, first_catalog = catalog_for(first)
    region_ref = max(
        first.region_index.regions,
        key=lambda region: len(region.member_target_ids),
    ).public_ref

    opened = resolve_catalog_call(
        first_catalog,
        ToolCall("read_region", {"region_ref": region_ref}),
        expected_context_id=first.context_id,
    ).decision

    assert opened.result["has_more"] is True
    assert "cursor" not in opened.result
    assert opened.delivery_lens is not None and opened.delivery_lens.next_cursor
    second = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        delivery_lens=opened.delivery_lens,
        region_index=first.region_index,
    )
    _, second_catalog = catalog_for(second)
    continuation = next(item for item in second_catalog.specs if item.name == "read_next_page")
    assert continuation.input_schema["properties"] == {}

    continued = resolve_catalog_call(
        second_catalog,
        ToolCall("read_next_page", {}),
        expected_context_id=second.context_id,
    ).decision
    assert continued.result["items"]
    assert "cursor" not in continued.arguments
    assert "cursor" not in continued.result


def test_tool_schemas_are_stable_and_manifest_actions_resolve_to_complete_action_space() -> None:
    task = _task()
    small_world = _world("world:small", False)
    context = ContextBuilder().build(
        task,
        small_world,
        ActionSpaceBuilder().build(task, small_world),
        _evaluation(task, small_world.observation_id),
    )
    _, catalog = catalog_for(context)
    view = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        observation=small_world,
    )
    schemas = json.dumps([to_json_compatible(item.input_schema) for item in catalog.specs])

    assert '"enum": ["E' not in schemas
    assert '"enum": ["F' not in schemas
    assert '"enum": ["R' not in schemas
    assert all(ref in {item.target_ref for item in context.complete_actions} for ref in view.manifest.executable_refs)
    assert catalog.serialized_bytes < 8_000


def test_lossless_fact_reference_algebra_covers_more_than_one_thousand_scalars() -> None:
    target = SemanticTarget("target:many-facts", "region", "Metrics")
    facts = tuple(
        StateFact(f"fact:metric:{index}", target.target_id, f"metric_{index}", index, "source:many")
        for index in range(1_005)
    )
    world = (
        WorldFusion()
        .fuse(
            (
                SurfaceObservation(
                    "source:many",
                    "browser",
                    "revision:many",
                    ObservationSourceProfile.dom(),
                    (target,),
                    facts,
                ),
            )
        )
        .observation
    )
    assert world is not None
    task = TaskGoal("many-facts", "Inspect metrics")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )

    assert len(context.private_fact_bindings) > 1_000
    assert "F1000" in context.private_fact_bindings


def _candidate_navigation_world(observation_id: str, *, include_account_settings: bool):
    overview_scope = SemanticTarget("scope:overview", "navigation", "Overview")
    account_scope = SemanticTarget("scope:account", "region", "Account Preferences")
    overview = SemanticTarget(
        "nav:overview-settings",
        "link",
        "Settings",
        relations={"parent_id": overview_scope.target_id},
    )
    targets = [overview_scope, account_scope, overview]
    nodes = [
        ObservationStructureNode(
            "root",
            "document",
            "Control Center",
            child_structure_ids=("nav", "main"),
        ),
        ObservationStructureNode(
            "nav",
            "navigation",
            "Primary navigation",
            parent_structure_id="root",
            child_structure_ids=("overview-scope", "overview-settings"),
        ),
        ObservationStructureNode(
            "overview-scope",
            "group",
            "Overview",
            parent_structure_id="nav",
            semantic_target_id=overview_scope.target_id,
        ),
        ObservationStructureNode(
            "overview-settings",
            "link",
            "Settings",
            parent_structure_id="nav",
            semantic_target_id=overview.target_id,
        ),
        ObservationStructureNode(
            "main",
            "main",
            "Account workspace",
            parent_structure_id="root",
            child_structure_ids=("heading", "tabs"),
        ),
        ObservationStructureNode(
            "heading",
            "heading",
            "Account > Preferences",
            parent_structure_id="main",
            semantic_target_id=account_scope.target_id,
        ),
        ObservationStructureNode(
            "tabs",
            "tablist",
            "Preference controls",
            parent_structure_id="main",
            child_structure_ids=("account-settings",) if include_account_settings else (),
        ),
    ]
    bindings = [_activate_binding(observation_id, overview)]
    if include_account_settings:
        account_settings = SemanticTarget(
            "action:account-settings",
            "menuitem",
            "Settings",
            {"selected": False},
            {"parent_id": account_scope.target_id},
        )
        targets.append(account_settings)
        nodes.append(
            ObservationStructureNode(
                "account-settings",
                "menuitem",
                "Settings",
                {"selected": False},
                parent_structure_id="tabs",
                semantic_target_id=account_settings.target_id,
            )
        )
        bindings.append(_activate_binding(observation_id, account_settings))
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        tuple(targets),
        bindings=tuple(bindings),
        structure=tuple(nodes),
        structure_total_count=len(nodes),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return result.observation


def _activate_binding(observation_id: str, target: SemanticTarget) -> ActionBinding:
    return ActionBinding(
        f"binding:{observation_id}:{target.target_id}",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{target.target_id}",
        target.target_id,
        target.target_id,
        "browser",
        "browsergym",
        "activate",
        "click",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"private_bid": target.target_id},
    )


def _candidate_context(world, instruction: str):
    task = TaskGoal(
        "candidate-navigation",
        instruction,
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        _evaluation(task, world.observation_id),
    )
    delivery = build_model_turn_delivery(context, include_images=False)
    return task, context, delivery


def test_task_related_current_action_is_promoted_with_structural_closure() -> None:
    world = _candidate_navigation_world("obs:with-settings", include_account_settings=True)
    _task_goal, context, view = _candidate_context(world, "Open Account Preferences Settings")
    target = next(item for item in context.complete_actions if item.target_id == "action:account-settings")
    _, catalog = catalog_for(context)
    resolved = resolve_catalog_call(
        catalog,
        ToolCall("activate", {"target": target.target_ref}),
        expected_context_id=context.context_id,
        expected_catalog_id=catalog.catalog_id,
    ).decision

    assert "ActionCandidates exact=true" in view.view.text
    assert f'[{target.target_ref}] activate menuitem "Settings"' in view.view.text
    assert 'path=["Control Center","Account workspace","Account Preferences","Settings"]' in view.view.text
    assert 'verbs=["activate"]' in view.view.text
    assert target.target_ref in view.manifest.executable_refs
    assert resolved.action_id == target.action_id


def test_future_action_is_not_invented_or_replaced_by_navigation_macro() -> None:
    world = _candidate_navigation_world("obs:overview-only", include_account_settings=False)
    _task_goal, context, view = _candidate_context(world, "Open Account Preferences Settings")
    _, catalog = catalog_for(context)

    assert all(item.target_id != "action:account-settings" for item in context.complete_actions)
    assert "navigate_to" not in {item.name for item in catalog.specs}


def test_fresh_world_promotes_newly_available_action() -> None:
    before = _candidate_navigation_world("obs:before-settings", include_account_settings=False)
    after = _candidate_navigation_world("obs:after-settings", include_account_settings=True)
    _task_goal, before_context, _before_view = _candidate_context(before, "Open Account Preferences Settings")
    _task_goal, after_context, after_view = _candidate_context(after, "Open Account Preferences Settings")

    assert all(item.target_id != "action:account-settings" for item in before_context.complete_actions)
    target = next(item for item in after_context.complete_actions if item.target_id == "action:account-settings")
    assert f'[{target.target_ref}] activate menuitem "Settings"' in after_view.view.text
    assert target.target_ref in after_view.manifest.executable_refs


def test_grounding_and_manifest_partition_executable_and_readonly_refs() -> None:
    world = _candidate_navigation_world("obs:ref-partition", include_account_settings=True)
    _task_goal, context, view = _candidate_context(world, "Open Account Preferences Settings")
    entities = {item.ref: item for item in context.grounding.entities}

    assert all(ref.startswith("E") and entities[ref].verbs for ref in view.manifest.executable_refs)
    assert all(ref.startswith("N") for ref in view.manifest.readonly_refs)
    assert all(bool(item.verbs) == item.ref.startswith("E") for item in entities.values())
    assert set(view.manifest.executable_refs).isdisjoint(view.manifest.readonly_refs)


def test_one_delivery_identity_owns_view_catalog_and_resolver_admission() -> None:
    world = _candidate_navigation_world("obs:delivery-identity", include_account_settings=True)
    _task_goal, context, _view = _candidate_context(world, "Open Account Preferences Settings")
    delivery, catalog = catalog_for(context)

    assert not hasattr(delivery.view, "manifest")
    assert catalog.manifest is delivery.manifest
    assert delivery.delivery_index is context.region_index
    assert catalog.delivery_index is context.region_index
    assert catalog.delivery_id == delivery.delivery_id

    displayed = re.findall(
        r"\[(E[1-9][0-9]{0,3})\].*?verbs=\[\"([a-z_]+)\"\]",
        delivery.view.text,
    )
    assert displayed
    for ref, operation in displayed:
        assert operation in {spec.name for spec in catalog.specs}
        resolved = resolve_catalog_call(
            catalog,
            ToolCall(operation, {"target": ref}),
            expected_context_id=context.context_id,
            expected_catalog_id=catalog.catalog_id,
        )
        assert resolved.decision.context_id == context.context_id

    with pytest.raises(GroundedToolResolutionError) as stale:
        resolve_catalog_call(
            catalog,
            ToolCall(displayed[0][1], {"target": displayed[0][0]}),
            expected_context_id=context.context_id,
            expected_delivery_id="delivery:" + "0" * 64,
        )
    assert stale.value.code is GroundedToolResolutionCode.STALE_CATALOG


def test_nonmanifest_ref_is_grounding_gap_and_new_world_rejects_old_delivery() -> None:
    before = _candidate_navigation_world("obs:delivery-before", include_account_settings=True)
    after = _candidate_navigation_world("obs:delivery-after", include_account_settings=True)
    _task_goal, before_context, _ = _candidate_context(before, "Open Account Preferences Settings")
    _task_goal, after_context, _ = _candidate_context(after, "Open Account Preferences Settings")
    delivery, catalog = catalog_for(before_context)

    with pytest.raises(GroundedToolResolutionError) as gap:
        resolve_catalog_call(
            catalog,
            ToolCall("activate", {"target": "E999"}),
            expected_context_id=before_context.context_id,
        )
    assert gap.value.code is GroundedToolResolutionCode.GROUNDING_GAP

    with pytest.raises(GroundedToolResolutionError) as stale:
        compile_grounded_tool_catalog(
            after_context,
            GroundedToolPhase.ACTION_SELECTION,
            delivery,
        )
    assert stale.value.code is GroundedToolResolutionCode.STALE_CATALOG


def test_tool_catalog_source_has_no_independent_renderer_or_string_ref_authority() -> None:
    import affordance_runtime.model.policy.grounded_tool_catalog as catalog_module

    source = Path(catalog_module.__file__).read_text(encoding="utf-8")
    assert "render_compact_actor_world" not in source
    assert "re.findall" not in source
    assert "re.search" not in source
