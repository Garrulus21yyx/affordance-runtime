from __future__ import annotations

from affordance_runtime.actions import ActionSpace
from affordance_runtime.agent.context.compact_world_renderer import (
    Opened,
    _bounded_tool_record,
    inspect_actor_world,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.surfaces.browsergym.entity_identity import BrowserGymEntityIdentityMap
from affordance_runtime.task import TaskGoal
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    ax_node,
    raw_observation,
    reset_task_state,
)
from tests.support.surfaces.browsergym.projection_support import project_browsergym_observation


def test_browsergym_read_delivers_complete_records_with_text_beyond_control_label_limit() -> None:
    first_body = "introductory detail " * 20 + "the relevant phrase is near the end"
    second_body = "more introductory detail " * 45 + "another relevant phrase near the end"
    nodes = [ax_node("reviews", "list", "Reviews", child_ids=("row-1", "row-2"))]
    for ordinal, body in enumerate((first_body, second_body), start=1):
        nodes.extend((
            ax_node(
                f"row-{ordinal}",
                "listitem",
                "",
                parent_id="reviews",
                child_ids=(f"body-{ordinal}", f"author-{ordinal}"),
            ),
            ax_node(f"body-{ordinal}", "StaticText", body, parent_id=f"row-{ordinal}"),
            ax_node(
                f"author-{ordinal}",
                "StaticText",
                f"Review by Person {ordinal}",
                parent_id=f"row-{ordinal}",
            ),
        ))
    projection = project_browsergym_observation(
        raw_observation(*nodes),
        observation_id="observation:readable-text",
        source_revision="revision:readable-text",
        page_identity="page:readable-text",
        episode_identity="episode:readable-text",
        task_state=reset_task_state("observation:readable-text"),
        entity_identity=BrowserGymEntityIdentityMap(b"readable-text-integration-key-001"),
    )
    world = projection.world
    task = TaskGoal("read-complete-records", "Find the relevant review details")
    evaluation = TaskEvaluation(
        task.task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "integration fixture",
    )
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        evaluation,
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
    records = tuple(item for item in outcome.items if item.get("kind") == "complete_item")
    assert len(records) == 2
    assert tuple(tuple(field["text"] for field in item["content"]) for item in records) == (
        (first_body, "Review by Person 1"),
        (second_body, "Review by Person 2"),
    )
    assert all(item["shape"] == "record" and item["field_count"] == 2 for item in records)
    assert all(len(body) > 240 for body in (first_body, second_body))
    assert all(item.get("content_truncated") is not True for item in records)


def test_browsergym_table_rows_are_delivered_as_indivisible_records() -> None:
    projection = project_browsergym_observation(
        raw_observation(
            ax_node("orders", "table", "Orders", child_ids=("row-1", "row-2")),
            ax_node("row-1", "row", "", parent_id="orders", child_ids=("name-1", "price-1", "qty-1")),
            ax_node("name-1", "StaticText", "Notebook", parent_id="row-1"),
            ax_node("price-1", "StaticText", "$12.50", parent_id="row-1"),
            ax_node("qty-1", "StaticText", "2", parent_id="row-1"),
            ax_node("row-2", "row", "", parent_id="orders", child_ids=("name-2", "price-2", "qty-2")),
            ax_node("name-2", "StaticText", "Pen", parent_id="row-2"),
            ax_node("price-2", "StaticText", "$3.00", parent_id="row-2"),
            ax_node("qty-2", "StaticText", "1", parent_id="row-2"),
        ),
        observation_id="observation:table-records",
        source_revision="revision:table-records",
        page_identity="page:table-records",
        episode_identity="episode:table-records",
        task_state=reset_task_state("observation:table-records"),
        entity_identity=BrowserGymEntityIdentityMap(b"table-records-integration-key-0001"),
    )
    world = projection.world
    task = TaskGoal("read-table-records", "Read the order rows")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "fixture"),
    )
    region = next(item for item in context.region_index.regions if item.role == "table")
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
    records = tuple(item for item in outcome.items if item.get("shape") == "record")
    assert tuple(tuple(field["text"] for field in item["content"]) for item in records) == (
        ("Notebook", "$12.50", "2"),
        ("Pen", "$3.00", "1"),
    )


def test_browsergym_control_group_delivers_one_normalized_group_value() -> None:
    projection = project_browsergym_observation(
        raw_observation(
            ax_node("rating", "radiogroup", "Rating", child_ids=("one", "five")),
            ax_node("one", "radio", "1 star", parent_id="rating", properties=(("checked", False),)),
            ax_node("five", "radio", "5 stars", parent_id="rating", properties=(("checked", True),)),
        ),
        observation_id="observation:rating-group",
        source_revision="revision:rating-group",
        page_identity="page:rating-group",
        episode_identity="episode:rating-group",
        task_state=reset_task_state("observation:rating-group"),
        entity_identity=BrowserGymEntityIdentityMap(b"rating-group-integration-key-0001"),
    )
    world = projection.world
    task = TaskGoal("read-rating", "Read the selected rating")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "fixture"),
    )
    region = next(item for item in context.region_index.regions if item.role == "radiogroup")
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
    group = next(item for item in outcome.items if item.get("shape") == "control_group")
    assert group["member_count"] == 2
    assert group["selected_members"] == ("5 stars",)
    assert group["value_status"] == "known"


def test_semantic_unit_bounding_trims_detail_without_slicing_the_record_skeleton() -> None:
    fields = tuple(
        {"role": "cell", "text": f"field-{index}:" + "x" * 3_000}
        for index in range(80)
    )

    bounded = _bounded_tool_record(
        {
            "kind": "complete_item",
            "shape": "record",
            "field_count": len(fields),
            "content": fields,
        }
    )

    assert bounded["kind"] == "partial_item"
    assert bounded["field_count"] == 80
    assert len(bounded["content"]) == 80
    assert all(item["text"].endswith("…") for item in bounded["content"])
