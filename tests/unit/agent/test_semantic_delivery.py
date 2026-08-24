from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionRisk, ActionSpace, ActionSpaceBuilder
from affordance_runtime.agent.context.action_candidate_projection import DeliveryObligationKind
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
    inspect_outcome_public,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.observation_delivery import (
    InformationDeltaKind,
    ObservationDeliveryStore,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.decisions import PublicEvidenceResult, SearchPageContentResult, SelectAction
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.benchmarks.webarena_verified import (
    DeliveryRetrievalProbe,
    _delivery_probe_item_diagnostic,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceipt,
    ExecutionReceiptBatch,
)
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
from tests.support.canonical_world import canonical_world
from tests.support.model_delivery import catalog_for, resolve_catalog_call


def _evaluation(task: TaskGoal, observation_id: str) -> TaskEvaluation:
    return TaskEvaluation(
        task.task_id,
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "semantic delivery fixture",
    )


def test_store_routes_future_readonly_tool_by_typed_result_not_operation_name() -> None:
    task = _task()
    world = _world("typed-future-reader", False)
    store = ObservationDeliveryStore()
    decision = SearchPageContentResult(
        "context:fixture",
        "future_readonly_tool",
        {"subject": "current"},
        PublicEvidenceResult.from_value(
            {
                "kind": "Evidence",
                "items": (
                    {"identity": {"name": "Reader 界🙂"}, "content": {"text": "complete"}},
                ),
            },
            source_scope="current",
        ),
        "call:future-reader",
    )
    transition = store.reduce(
        StepResult(
            decision,
            world,
            world,
            _evaluation(task, world.observation_id),
            feedback="local_tool_result",
        ),
        step_index=1,
    )

    inventory = transition.next_store.public_result_inventory
    assert inventory is not None
    assert inventory.records[0].operation == "future_readonly_tool"
    assert inventory.records[0].public_value == decision.result.records[0]


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


def _many_region_world(*, count: int = 16, suffix: str = "current"):
    region_ids = tuple(f"region:{index}" for index in range(count))
    target_ids = tuple(f"content:{index}" for index in range(count))
    targets = tuple(
        SemanticTarget(target_id, "StaticText", f"Needle {index}")
        for index, target_id in enumerate(target_ids)
    )
    nodes = (
        ObservationStructureNode("root", "generic", "Catalog", child_structure_ids=region_ids),
        *(
            ObservationStructureNode(
                region_id,
                "region",
                f"Section {index}",
                parent_structure_id="root",
                child_structure_ids=(target_ids[index],),
            )
            for index, region_id in enumerate(region_ids)
        ),
        *(
            ObservationStructureNode(
                target_id,
                "StaticText",
                f"Needle {index}",
                parent_structure_id=region_ids[index],
                semantic_target_id=target_id,
            )
            for index, target_id in enumerate(target_ids)
        ),
    )
    source = SurfaceObservation(
        f"source:many-regions:{suffix}",
        "browser",
        f"revision:many-regions:{suffix}",
        ObservationSourceProfile.dom(),
        targets,
        structure=nodes,
        structure_total_count=len(nodes),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return result.observation


def _long_record_world(lengths: tuple[int, ...], *, suffix: str = "current"):
    row_ids = tuple(f"comment:{index}" for index in range(len(lengths)))
    targets = tuple(
        SemanticTarget(row_id, "StaticText", f"Comment {index} " + "x" * length)
        for index, (row_id, length) in enumerate(zip(row_ids, lengths, strict=True))
    )
    nodes = (
        ObservationStructureNode("root", "document", "Reviews", child_structure_ids=("reviews",)),
        ObservationStructureNode(
            "reviews",
            "list",
            "Customer reviews",
            parent_structure_id="root",
            child_structure_ids=row_ids,
        ),
        *(
            ObservationStructureNode(
                row_id,
                "listitem",
                f"Review {index}",
                parent_structure_id="reviews",
                semantic_target_id=row_id,
            )
            for index, row_id in enumerate(row_ids)
        ),
    )
    source = SurfaceObservation(
        f"source:long-records:{suffix}",
        "browser",
        f"revision:long-records:{suffix}",
        ObservationSourceProfile.dom(),
        targets,
        structure=nodes,
        structure_total_count=len(nodes),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return result.observation


def _serialized_outcome_bytes(outcome) -> int:
    return len(
        json.dumps(
            to_json_compatible(inspect_outcome_public(outcome)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def _read_complete_region(context, region_ref: str, *, hard_limit: int):
    cursor = ""
    seen_cursors: set[str] = set()
    outcomes = []
    while True:
        outcome = inspect_actor_world(
            context.actor_world,
            context.grounding,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            observation=context.current_observation,
            action="read_region",
            region_ref=region_ref,
            cursor=cursor,
            hard_limit=hard_limit,
        )
        assert isinstance(outcome, Opened)
        assert outcome.items
        assert _serialized_outcome_bytes(outcome) <= hard_limit
        outcomes.append(outcome)
        if not outcome.next_cursor:
            return tuple(outcomes)
        assert outcome.next_cursor not in seen_cursors
        seen_cursors.add(outcome.next_cursor)
        cursor = outcome.next_cursor


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
    public_fact_ref = context.canonical_world.private_fact_id_refs["fact:value"]
    assert f'"value": "{public_fact_ref}"' in encoded
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


def test_change_first_delivery_keeps_latest_gui_result_across_local_reads() -> None:
    before = _world("world:before", False)
    after = _world("world:after", True)
    delta = WorldTransitionProjector().project(before, after)
    task = _task()
    option = ActionSpaceBuilder().build(task, before).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, before, "context:fixture", tool_call_id="call:effect")
    execution_result = ActionResult(request.request_id, DispatchStatus.SENT, "fixture", True)
    external_step = StepResult(
        SelectAction("context:fixture", option.action_id, tool_call_id="call:effect"),
        before,
        after,
        _evaluation(task, after.observation_id),
        execution_receipts=ExecutionReceiptBatch(
            (ExecutionReceipt(request, execution_result, before.observation_id, after.observation_id),),
            ExecutionCompletion.COMPLETE,
        ),
        feedback="action_dispatched",
        public_world_delta=delta,
        before_public_world=canonical_world(before),
        after_public_world=canonical_world(after),
    )
    store = ObservationDeliveryStore().reduce(external_step, step_index=1).next_store
    local_read = StepResult(
        SearchPageContentResult(
            "context:fixture",
            "future_readonly_tool",
            {"query": "none"},
            PublicEvidenceResult.from_value(
                {"kind": "NoMatches", "items": ()},
                source_scope="current",
            ),
        ),
        after,
        after,
        _evaluation(task, after.observation_id),
        feedback="local_tool_result",
    )

    local_store = store.reduce(local_read, step_index=2).next_store
    assert local_store.latest_effect is store.latest_effect

    action_space = ActionSpaceBuilder().build(task, after)
    index = WorldDeliveryIndex.from_observation(
        after,
        action_space.options,
        public_world_delta=delta,
        previous_index=WorldDeliveryIndex.from_observation(before),
    )
    context = ContextBuilder().build(
        task,
        after,
        action_space,
        _evaluation(task, after.observation_id),
        region_index=index,
        delivery_store=local_store,
    )
    delivery = build_model_turn_delivery(context, include_images=False)
    rendered = delivery.view.text

    headings = (
        "LatestEffect",
        "CurrentFindings",
        "ChangedRegions",
        "ActionCandidates",
        "PageOutline",
        "RecoveryDirectory",
    )
    positions = tuple(rendered.index(item) for item in headings)
    assert positions == tuple(sorted(positions))
    assert "EvidenceCandidates" not in rendered
    assert "value=true" in rendered
    assert store.latest_effect is not None
    assert store.latest_effect.inventory.inventory_id.startswith("public-effect:")
    assert set(delivery.manifest.executable_refs) <= set(context.grounding.target_refs.values())


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
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=context.canonical_world.region_refs[region.key],
    )

    assert isinstance(outcome, Opened)
    assert len(outcome.items) == 20
    assert outcome.next_cursor


def test_region_read_pages_long_records_by_final_payload_bytes_without_loss() -> None:
    world = _long_record_world((4000,) * 25)
    task = TaskGoal("byte-paging", "Inspect all reviews")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    region = next(item for item in context.region_index.regions if item.role == "list")
    region_ref = context.canonical_world.region_refs[region.key]
    complete = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=region_ref,
        page_size=1000,
        hard_limit=10 * 1024 * 1024,
    )
    assert isinstance(complete, Opened)

    pages = _read_complete_region(context, region_ref, hard_limit=64 * 1024)
    delivered = tuple(item for page in pages for item in page.items)

    assert len(pages) >= 2
    assert delivered == complete.items
    assert len({json.dumps(to_json_compatible(item), sort_keys=True) for item in delivered}) == len(delivered)
    assert all(item.get("kind") != "content_fragment" for item in delivered)


def test_single_oversized_region_record_uses_lossless_typed_fragments() -> None:
    world = _long_record_world((100_000, 100), suffix="fragment")
    task = TaskGoal("fragment-paging", "Inspect all reviews")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    region = next(item for item in context.region_index.regions if item.role == "list")
    region_ref = context.canonical_world.region_refs[region.key]
    complete = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=region_ref,
        page_size=1000,
        hard_limit=10 * 1024 * 1024,
    )
    assert isinstance(complete, Opened)

    pages = _read_complete_region(context, region_ref, hard_limit=64 * 1024)
    fragments = tuple(
        item for page in pages for item in page.items if item.get("kind") == "content_fragment"
    )
    ordinary = tuple(
        item for page in pages for item in page.items if item.get("kind") != "content_fragment"
    )
    reconstructed = json.loads("".join(str(item["content_json"]) for item in fragments))

    assert len(fragments) >= 2
    assert len({item["record_digest"] for item in fragments}) == 1
    assert tuple(item["fragment_offset"] for item in fragments) == tuple(
        sum(len(str(prior["content_json"])) for prior in fragments[:index])
        for index in range(len(fragments))
    )
    assert fragments[-1]["fragment_final"] is True
    assert reconstructed == to_json_compatible(complete.items[0])
    assert to_json_compatible(ordinary) == to_json_compatible(complete.items[1:])


@settings(max_examples=10, deadline=None)
@given(
    lengths=st.lists(
        st.integers(min_value=0, max_value=6000),
        min_size=2,
        max_size=25,
    ).map(tuple)
)
def test_region_read_byte_pages_generated_exactly_cover_public_inventory(lengths) -> None:
    world = _long_record_world(lengths, suffix=f"generated-{sum(lengths)}-{len(lengths)}")
    task = TaskGoal("generated-byte-paging", "Inspect all records")
    context = ContextBuilder().build(
        task, world, ActionSpace(world.observation_id, ()), _evaluation(task, world.observation_id)
    )
    region = next(item for item in context.region_index.regions if item.role == "list")
    region_ref = context.canonical_world.region_refs[region.key]
    complete = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=region_ref,
        page_size=1000,
        hard_limit=10 * 1024 * 1024,
    )
    assert isinstance(complete, Opened)

    pages = _read_complete_region(context, region_ref, hard_limit=4096)
    reconstructed = []
    fragments: list[Mapping[str, object]] = []
    for page in pages:
        for item in page.items:
            if item.get("kind") == "content_fragment":
                fragments.append(item)
                if item["fragment_final"]:
                    reconstructed.append(
                        json.loads("".join(str(part["content_json"]) for part in fragments))
                    )
                    fragments = []
            else:
                assert not fragments
                reconstructed.append(item)

    assert not fragments
    assert to_json_compatible(reconstructed) == to_json_compatible(complete.items)


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
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=context.canonical_world.region_refs[table.key],
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
        canonical_world=context.canonical_world,
        observation=world,
    )
    table_ref = context.canonical_world.region_refs[table.key]
    descriptor = next(line for line in view.text.splitlines() if f"[{table_ref}]" in line)
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
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=context.canonical_world.region_refs[table.key],
    )
    view = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
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
    assert context.region_index.get(
        context.canonical_world.resolve_region_ref(context.canonical_world.region_refs[table.key])
    ) is table
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
        canonical_world=context.canonical_world,
        observation=world,
        action_candidates=context.action_candidates,
    )
    page_map = view.text.split("ActiveView exact=true", 1)[0]

    assert view.projection == "page_map"
    assert set(view.manifest.region_refs) == set(context.canonical_world.region_refs.values())
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
        "canonical_world": context.canonical_world,
        "observation": world,
    }
    region_ref = context.canonical_world.region_refs[context.region_index.regions[0].key]

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


def test_search_results_conserve_bounded_regions_into_next_turn_read_capability() -> None:
    world = _many_region_world(count=16)
    task = TaskGoal("search-follow-up", "Inspect matching content")
    builder = ContextBuilder()
    first = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
    )
    first_delivery, first_catalog = catalog_for(first)
    target_region = first.region_index.region_for_target("content:15")
    assert target_region is not None
    target_region_ref = first.canonical_world.region_refs[target_region.key]
    initial_regions = next(
        item for item in first_catalog.specs if item.name == "read_region"
    ).input_schema["properties"]["region_ref"]["enum"]
    assert target_region_ref not in initial_regions

    search_resolution = resolve_catalog_call(
        first_catalog,
        ToolCall("search_page_content", {"query": "Needle"}),
        expected_context_id=first.context_id,
    )
    matching_item = next(
        item for item in search_resolution.decision.result["items"]
        if item["region_ref"] == target_region_ref
    )
    assert matching_item["follow_up"] == {
        "operation": "read_region",
        "region_ref": target_region_ref,
    }
    step = StepResult(
        search_resolution.decision,
        world,
        world,
        _evaluation(task, world.observation_id),
        feedback="local_tool_result",
    )
    transition = first.delivery_store.reduce(step, step_index=1)
    second = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        delivery_store=transition.next_store,
    )
    second_delivery, second_catalog = catalog_for(second)
    available_regions = next(
        item for item in second_catalog.specs if item.name == "read_region"
    ).input_schema["properties"]["region_ref"]["enum"]

    assert target_region_ref in available_regions
    assert len(second.delivery_store.search_follow_ups) == 16
    assert len({item.region_ref for item in second.delivery_store.search_follow_ups}) == 16
    assert f"follow_up=read_region({target_region_ref})" in second_delivery.view.text
    opened = resolve_catalog_call(
        second_catalog,
        ToolCall("read_region", {"region_ref": target_region_ref}),
        expected_context_id=second.context_id,
    )
    assert opened.decision.result["kind"] == "Opened"

    fresh_world = _many_region_world(count=16, suffix="fresh")
    fresh = builder.build(
        task,
        fresh_world,
        ActionSpace(fresh_world.observation_id, ()),
        _evaluation(task, fresh_world.observation_id),
        delivery_store=transition.next_store,
    )
    fresh_delivery, fresh_catalog = catalog_for(fresh)
    fresh_regions = next(
        item for item in fresh_catalog.specs if item.name == "read_region"
    ).input_schema["properties"]["region_ref"]["enum"]
    assert fresh.delivery_store.search_follow_ups == ()
    assert "SearchFollowUps" not in fresh_delivery.view.text
    assert target_region_ref not in fresh_regions


def test_paginated_search_keeps_every_latest_page_region_within_bounded_follow_ups() -> None:
    world = _many_region_world(count=40, suffix="paged")
    task = TaskGoal("search-follow-up-pages", "Inspect matching content")
    builder = ContextBuilder()
    context = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
    )
    _, catalog = catalog_for(context)
    first = resolve_catalog_call(
        catalog,
        ToolCall("search_page_content", {"query": "Needle"}),
        expected_context_id=context.context_id,
    )
    first_step = StepResult(
        first.decision,
        world,
        world,
        _evaluation(task, world.observation_id),
        feedback="local_tool_result",
    )
    first_store = context.delivery_store.reduce(first_step, step_index=1).next_store
    context = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        delivery_store=first_store,
    )
    _, catalog = catalog_for(context)
    second = resolve_catalog_call(
        catalog,
        ToolCall("read_next_page", {"scope": "active_read"}),
        expected_context_id=context.context_id,
    )
    latest_page_regions = {
        item["region_ref"] for item in second.decision.result["items"]
    }
    second_step = StepResult(
        second.decision,
        world,
        world,
        _evaluation(task, world.observation_id),
        feedback="local_tool_result",
    )
    second_store = context.delivery_store.reduce(second_step, step_index=2).next_store
    final = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        delivery_store=second_store,
    )
    _, final_catalog = catalog_for(final)
    available_regions = set(next(
        item for item in final_catalog.specs if item.name == "read_region"
    ).input_schema["properties"]["region_ref"]["enum"])

    assert latest_page_regions <= available_regions
    assert len(second_store.search_follow_ups) == 32
    assert len({item.region_ref for item in second_store.search_follow_ups}) == 32


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
    desired_region = max(first.region_index.regions, key=lambda region: len(region.member_target_ids))
    desired_region_ref = first.canonical_world.region_refs[desired_region.key]
    available = next(item for item in first_catalog.specs if item.name == "read_region").input_schema[
        "properties"
    ]["region_ref"]["enum"]
    while desired_region_ref not in available:
        continuation = next(item for item in first_catalog.specs if item.name == "read_next_page")
        arguments = {"scope": "page_directory"} if continuation.input_schema["properties"] else {}
        continuation_resolution = resolve_catalog_call(
            first_catalog,
            ToolCall("read_next_page", arguments),
            expected_context_id=first.context_id,
        )
        continuation_step = StepResult(
            continuation_resolution.decision,
            world,
            world,
            _evaluation(task, world.observation_id),
            feedback="local_tool_result",
        )
        continuation_store = first.delivery_store.reduce(
            continuation_step,
            step_index=1,
        ).next_store
        first = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            _evaluation(task, world.observation_id),
            delivery_store=continuation_store,
        )
        _, first_catalog = catalog_for(first)
        available = next(item for item in first_catalog.specs if item.name == "read_region").input_schema[
            "properties"
        ]["region_ref"]["enum"]

    opened_resolution = resolve_catalog_call(
        first_catalog,
        ToolCall("read_region", {"region_ref": desired_region_ref}),
        expected_context_id=first.context_id,
    )
    opened = opened_resolution.decision

    assert opened.result["has_more"] is True
    assert "cursor" not in opened.result
    assert first.delivery_store.active_read is None
    opened_step = StepResult(
        opened,
        world,
        world,
        _evaluation(task, world.observation_id),
        feedback="local_tool_result",
    )
    opened_store = first.delivery_store.reduce(opened_step, step_index=1).next_store
    assert opened_store.active_read.next_cursor
    second = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        region_index=first.region_index,
        delivery_store=opened_store,
    )
    _, second_catalog = catalog_for(second)
    continuation = next(item for item in second_catalog.specs if item.name == "read_next_page")
    arguments = {"scope": "active_read"} if continuation.input_schema["properties"] else {}

    continued = resolve_catalog_call(
        second_catalog,
        ToolCall("read_next_page", arguments),
        expected_context_id=second.context_id,
    ).decision
    assert continued.result["items"]
    assert "cursor" not in continued.arguments
    assert "cursor" not in continued.result


def test_byte_bounded_region_continuation_is_store_private_and_fresh_world_stale() -> None:
    world = _long_record_world((4000,) * 25, suffix="catalog-continuation")
    task = TaskGoal("catalog-byte-paging", "Inspect all reviews")
    builder = ContextBuilder()
    context = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
    )
    region = next(item for item in context.region_index.regions if item.role == "list")
    region_ref = context.canonical_world.region_refs[region.key]
    _, catalog = catalog_for(context)
    opened = resolve_catalog_call(
        catalog,
        ToolCall("read_region", {"region_ref": region_ref}),
        expected_context_id=context.context_id,
    )

    assert opened.decision.result["has_more"] is True
    assert "cursor" not in opened.decision.arguments
    assert "cursor" not in opened.decision.result
    opened_step = StepResult(
        opened.decision,
        world,
        world,
        _evaluation(task, world.observation_id),
        feedback="local_tool_result",
    )
    opened_transition = context.delivery_store.reduce(opened_step, step_index=1)
    assert opened_transition.next_store.active_read.next_cursor
    assert len(
        json.dumps(
            to_json_compatible(opened.decision.result),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ) <= 64 * 1024

    assert opened_transition.next_store.public_result_inventory is not None

    continued_context = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        delivery_store=opened_transition.next_store,
    )
    _, continued_catalog = catalog_for(continued_context)
    continuation = next(item for item in continued_catalog.specs if item.name == "read_next_page")
    assert "active_read" in continuation.input_schema["properties"]["scope"]["enum"]
    continued = resolve_catalog_call(
        continued_catalog,
        ToolCall("read_next_page", {"scope": "active_read"}),
        expected_context_id=continued_context.context_id,
    )
    continued_step = StepResult(
        continued.decision,
        world,
        world,
        _evaluation(task, world.observation_id),
        feedback="local_tool_result",
    )
    transition = continued_context.delivery_store.reduce(
        continued_step,
        step_index=2,
    )
    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    inventory = transition.next_store.public_result_inventory
    assert inventory is not None
    opened_values = tuple(opened.decision.result["items"])
    continued_values = tuple(continued.decision.result["items"])
    expected_values = tuple(
        value
        for index, value in enumerate((*opened_values, *continued_values))
        if value not in (*opened_values, *continued_values)[:index]
    )
    assert tuple(item.public_value for item in inventory.records) == expected_values
    assert len({item.digest for item in inventory.records}) == len(inventory.records)
    assert inventory.offset == 0

    packed_context = builder.build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        _evaluation(task, world.observation_id),
        delivery_store=transition.next_store,
    )
    result_obligation = packed_context.action_delivery_plan.obligation(
        DeliveryObligationKind.PUBLIC_RESULT
    )
    assert result_obligation is not None
    assert result_obligation.records == inventory.records

    fresh_world = _long_record_world((4000,) * 25, suffix="catalog-fresh")
    fresh_context = builder.build(
        task,
        fresh_world,
        ActionSpace(fresh_world.observation_id, ()),
        _evaluation(task, fresh_world.observation_id),
        delivery_store=transition.next_store,
    )
    assert fresh_context.delivery_store.active_read is None
    assert fresh_context.delivery_store.public_result_inventory is None
    _, fresh_catalog = catalog_for(fresh_context)
    fresh_continuation = next(
        (item for item in fresh_catalog.specs if item.name == "read_next_page"),
        None,
    )
    if fresh_continuation is not None and fresh_continuation.input_schema["properties"]:
        assert "active_read" not in fresh_continuation.input_schema["properties"]["scope"]["enum"]


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
        canonical_world=context.canonical_world,
        observation=small_world,
    )
    schemas = json.dumps([to_json_compatible(item.input_schema) for item in catalog.specs])

    assert '"enum": ["E' in schemas
    assert '"enum": ["F' in schemas
    assert '"enum": ["R' in schemas
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

    assert "ActionCandidates" in view.view.text
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
    assert catalog.delivery_index is context.region_index
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
    assert gap.value.code is GroundedToolResolutionCode.INVALID_ARGUMENTS

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
