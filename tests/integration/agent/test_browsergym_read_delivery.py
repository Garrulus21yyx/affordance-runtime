from __future__ import annotations

from affordance_runtime.actions import ActionSpace
from affordance_runtime.agent.context.compact_world_renderer import Opened, inspect_actor_world
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
    assert tuple(item["content"][0]["text"] for item in records) == (
        f"{first_body}\nReview by Person 1",
        f"{second_body}\nReview by Person 2",
    )
    assert all(len(body) > 240 for body in (first_body, second_body))
    assert all(item.get("content_truncated") is not True for item in records)
