from __future__ import annotations

from affordance_runtime.actions import ActionSpace
from affordance_runtime.agent.context.compact_world_renderer import (
    CapacityExceeded,
    Opened,
    inspect_actor_world,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.surfaces.browsergym.entity_identity import BrowserGymEntityIdentityMap
from affordance_runtime.task import TaskGoal
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    ax_node,
    dom_snapshot,
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

    cursor = ""
    paged_records = []
    while True:
        page = inspect_actor_world(
            context.actor_world,
            context.grounding,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            observation=world,
            action="read_region",
            region_ref=context.canonical_world.region_refs[region.key],
            cursor=cursor,
            page_size=1,
        )
        assert isinstance(page, Opened)
        assert len(page.items) == 1
        paged_records.extend(item for item in page.items if item.get("shape") == "record")
        if page.continuation is None:
            break
        cursor = page.continuation.cursor
    assert tuple(tuple(field["text"] for field in item["content"]) for item in paged_records) == (
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
    assert group["value_status"] == "known"
    assert group["selected_value"] == "5 stars"


def test_browsergym_native_same_name_radios_form_one_control_group_with_authored_value() -> None:
    raw = raw_observation(
        ax_node("review", "group", "Review", child_ids=("star-5", "star-4", "star-3")),
        ax_node("star-5", "radio", "★", parent_id="review", properties=(("checked", False),)),
        ax_node("star-4", "radio", "★", parent_id="review", properties=(("checked", False),)),
        ax_node("star-3", "radio", "★", parent_id="review", properties=(("checked", True),)),
    )
    raw["dom_object"] = dom_snapshot(
        ("input", "star-5", {"type": "radio", "name": "ratings[4]", "value": "5"}),
        ("input", "star-4", {"type": "radio", "name": "ratings[4]", "value": "4"}),
        ("input", "star-3", {"type": "radio", "name": "ratings[4]", "value": "3"}),
    )
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:native-rating-group",
        source_revision="revision:native-rating-group",
        page_identity="page:native-rating-group",
        episode_identity="episode:native-rating-group",
        task_state=reset_task_state("observation:native-rating-group"),
        entity_identity=BrowserGymEntityIdentityMap(b"native-rating-group-key-00000001"),
    )
    world = projection.world
    task = TaskGoal("read-native-rating", "Read the selected rating")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "fixture"),
    )
    groups = tuple(item for item in world.semantic_topology if item.role == "radiogroup")
    assert len(groups) == 1
    assert groups[0].semantic_shape.kind.value == "control_group"
    assert tuple(
        next(item for item in world.semantic_topology if item.structure_id == child).role
        for child in groups[0].child_structure_ids
    ) == ("radio", "radio", "radio")

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
    assert group["member_count"] == 3
    assert group["value_status"] == "known"
    assert group["selected_value"] == "3"
    assert tuple(item["state"]["semantic.control.value"] for item in group["content"]) == ("5", "4", "3")


def test_browsergym_native_radio_group_does_not_claim_value_from_identical_labels() -> None:
    raw = raw_observation(
        ax_node("review", "group", "Review", child_ids=("one", "two")),
        ax_node("one", "radio", "★", parent_id="review", properties=(("checked", True),)),
        ax_node("two", "radio", "★", parent_id="review", properties=(("checked", False),)),
    )
    raw["dom_object"] = dom_snapshot(
        ("input", "one", {"type": "radio", "name": "rating"}),
        ("input", "two", {"type": "radio", "name": "rating"}),
    )
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:incomplete-rating-group",
        source_revision="revision:incomplete-rating-group",
        page_identity="page:incomplete-rating-group",
        episode_identity="episode:incomplete-rating-group",
        task_state=reset_task_state("observation:incomplete-rating-group"),
        entity_identity=BrowserGymEntityIdentityMap(b"incomplete-rating-group-key-0001"),
    )
    group = next(item for item in projection.world.semantic_topology if item.role == "radiogroup")
    assert dict(group.state)["semantic.control.value_status"] == "incomplete"
    assert "semantic.control.selected_value" not in group.state


def test_browsergym_native_radio_groups_respect_html_form_ownership() -> None:
    raw = raw_observation(
        ax_node("root", "group", "Settings", child_ids=("a-yes", "a-no", "b-yes", "b-no")),
        ax_node("a-yes", "radio", "Yes", parent_id="root", properties=(("checked", True),)),
        ax_node("a-no", "radio", "No", parent_id="root", properties=(("checked", False),)),
        ax_node("b-yes", "radio", "Yes", parent_id="root", properties=(("checked", False),)),
        ax_node("b-no", "radio", "No", parent_id="root", properties=(("checked", True),)),
    )
    raw["dom_object"] = dom_snapshot(
        ("input", "a-yes", {"type": "radio", "form": "form-a", "name": "choice", "value": "yes"}),
        ("input", "a-no", {"type": "radio", "form": "form-a", "name": "choice", "value": "no"}),
        ("input", "b-yes", {"type": "radio", "form": "form-b", "name": "choice", "value": "yes"}),
        ("input", "b-no", {"type": "radio", "form": "form-b", "name": "choice", "value": "no"}),
    )
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:form-owned-radio-groups",
        source_revision="revision:form-owned-radio-groups",
        page_identity="page:form-owned-radio-groups",
        episode_identity="episode:form-owned-radio-groups",
        task_state=reset_task_state("observation:form-owned-radio-groups"),
        entity_identity=BrowserGymEntityIdentityMap(b"form-owned-radio-groups-key-0001"),
    )

    groups = tuple(item for item in projection.world.semantic_topology if item.role == "radiogroup")
    assert len(groups) == 2
    assert {dict(group.state)["semantic.control.selected_value"] for group in groups} == {"yes", "no"}
    assert all(len(group.child_structure_ids) == 2 for group in groups)


def test_multifield_record_detail_cursor_recovers_every_omitted_field() -> None:
    values = tuple(f"field-{index}:" + chr(65 + index) * 5_000 for index in range(5))
    field_ids = tuple(f"field-{index}" for index in range(len(values)))
    projection = project_browsergym_observation(
        raw_observation(
            ax_node("table", "table", "Large record", child_ids=("row",)),
            ax_node("row", "row", "", parent_id="table", child_ids=field_ids),
            *(ax_node(field_id, "StaticText", value, parent_id="row") for field_id, value in zip(field_ids, values)),
        ),
        observation_id="observation:continued-record",
        source_revision="revision:continued-record",
        page_identity="page:continued-record",
        episode_identity="episode:continued-record",
        task_state=reset_task_state("observation:continued-record"),
        entity_identity=BrowserGymEntityIdentityMap(b"continued-record-integration-key-01"),
    )
    world = projection.world
    task = TaskGoal("continued-record", "Read every field")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "fixture"),
    )
    region = next(item for item in context.region_index.regions if item.role == "table")
    region_ref = context.canonical_world.region_refs[region.key]
    cursor = ""
    chunks: dict[tuple[object, ...], list[str]] = {}
    skeleton = None
    while True:
        outcome = inspect_actor_world(
            context.actor_world,
            context.grounding,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            observation=world,
            action="read_region",
            region_ref=region_ref,
            cursor=cursor,
            hard_limit=4_096,
        )
        assert isinstance(outcome, Opened)
        assert bool(outcome.next_cursor) is (outcome.continuation is not None)
        for item in outcome.items:
            if item.get("kind") == "detail_page":
                chunks.setdefault(tuple(item["path"]), []).append(item["text"])
            else:
                skeleton = item
                for omission in item.get("delivery_omissions", ()):
                    path = tuple(omission["path"])
                    field = item
                    for segment in path:
                        field = field[segment]
                    chunks.setdefault(path, []).append(field)
        if not outcome.next_cursor:
            break
        cursor = outcome.next_cursor

    assert skeleton is not None
    assert skeleton["field_count"] == 5
    assert len(skeleton["content"]) == 5
    assert skeleton["delivery_coverage"] == "continued"
    for index, expected in enumerate(values):
        assert "".join(chunks[("content", index, "text")]) == expected


def test_record_skeleton_is_never_sliced_to_fit_the_byte_gate() -> None:
    values = tuple(f"field-{index}:" + "x" * 3_000 for index in range(80))
    field_ids = tuple(f"field-{index}" for index in range(len(values)))
    projection = project_browsergym_observation(
        raw_observation(
            ax_node("table", "table", "Wide record", child_ids=("row",)),
            ax_node("row", "row", "", parent_id="table", child_ids=field_ids),
            *(ax_node(field_id, "StaticText", value, parent_id="row") for field_id, value in zip(field_ids, values)),
        ),
        observation_id="observation:wide-record",
        source_revision="revision:wide-record",
        page_identity="page:wide-record",
        episode_identity="episode:wide-record",
        task_state=reset_task_state("observation:wide-record"),
        entity_identity=BrowserGymEntityIdentityMap(b"wide-record-integration-key-0000001"),
    )
    world = projection.world
    task = TaskGoal("wide-record", "Read the wide record")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "fixture"),
    )
    region = next(item for item in context.region_index.regions if item.role == "table")
    arguments = {
        "snapshot": context.actor_world,
        "grounding": context.grounding,
        "region_index": context.region_index,
        "canonical_world": context.canonical_world,
        "observation": world,
        "action": "read_region",
        "region_ref": context.canonical_world.region_refs[region.key],
    }

    admitted = inspect_actor_world(**arguments, hard_limit=64 * 1024)
    assert isinstance(admitted, Opened)
    if not any(item.get("shape") == "record" for item in admitted.items):
        admitted = inspect_actor_world(
            **arguments,
            cursor=admitted.next_cursor,
            hard_limit=64 * 1024,
        )
    rejected = inspect_actor_world(**arguments, hard_limit=4_096)
    assert isinstance(rejected, Opened)
    if rejected.next_cursor:
        rejected = inspect_actor_world(
            **arguments,
            cursor=rejected.next_cursor,
            hard_limit=4_096,
        )

    assert isinstance(admitted, Opened)
    skeleton = next(item for item in admitted.items if item.get("shape") == "record")
    assert skeleton["field_count"] == 80
    assert len(skeleton["content"]) == 80
    assert len(skeleton["delivery_omissions"]) == 80
    assert admitted.continuation is not None
    assert admitted.continuation.kind == "detail"
    assert isinstance(rejected, CapacityExceeded)
