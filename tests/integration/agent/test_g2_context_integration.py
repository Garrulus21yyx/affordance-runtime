from __future__ import annotations

import json

import pytest

from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.evaluation.contracts import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.goals import Failed, GoalPlan, GoalPlanItem, NotRequired, Ready, Unsupported
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.task.contracts import TaskGoal
from tests.support.agent.core_loop_support import _world


def _task(revision: int = 1):
    return TaskGoal("task:g2", "Complete all requested visible changes, then finalize.", revision=revision)


def _plan(revision: int = 1, version: int = 1):
    return GoalPlan(revision, version, (
        GoalPlanItem(
            "complete_requested_changes",
            "Ensure every requested item has the desired visible state without changing unrelated controls.",
            "Every relevant item visibly has the requested state.",
        ),
        GoalPlanItem(
            "finalize_task",
            "Finalize the completed task.",
            "The final effect occurs after all requested changes are visibly complete.",
            ("complete_requested_changes",),
            True,
        ),
    ))


def _context(world, resolution=None, recent_steps: tuple[AgentTurnView, ...] = ()):
    task = _task()
    return ContextBuilder().build(
        task,
        world,
        ActionSpace(world.observation_id, ()),
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "incomplete"),
        AgentWorkspace(recent_steps[-8:]),
        current_step_index=len(recent_steps),
        goal_resolution=resolution,
    )


def _public(context):
    delivery = build_model_turn_delivery(context, include_images=False)
    catalog = compile_grounded_action_catalog(context, delivery)
    public = dict(GroundedPolicyContextBinder()._public_context_sections(  # noqa: SLF001 - projection gate
        context,
        False,
        delivery,
    )["public"])
    public["tools"] = tuple(
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in catalog.specs
    )
    return json.loads(json.dumps(public))


def test_ready_goal_plan_is_direct_static_context_without_progress_projection() -> None:
    world = _world("world:before", False)
    plan = _plan()
    public = _public(_context(world, Ready(1, plan)))
    assert tuple(public) == ("task", "observation", "goal_plan", "tools")
    assert "progress" not in public
    goal_plan = public["goal_plan"]
    assert goal_plan["resolution"] == "ready"
    assert goal_plan["plan_version"] == 1
    assert goal_plan["plan_digest"] == plan.digest
    assert goal_plan["items"] == [
        {
            "id": item.id,
            "objective": item.objective,
            "done_when": item.done_when,
            "depends_on": list(item.depends_on),
            "final": item.final,
        }
        for item in plan.items
    ]
    assert "obligations" not in goal_plan
    assert "frontier_refs" not in goal_plan
    assert "snapshot_digest" not in goal_plan


@pytest.mark.parametrize("resolution, expected", (
    (NotRequired(1, "atomic"), "not_required"),
    (Failed(1, "private provider diagnostic"), "unavailable"),
    (Unsupported(1, "private unsupported diagnostic"), "unavailable"),
))
def test_empty_plan_dispositions_do_not_expose_private_diagnostics(resolution, expected) -> None:
    public = _public(_context(_world("world", False), resolution))
    assert public["goal_plan"] == {
        "resolution": expected, "plan_version": None, "plan_digest": "", "items": [],
    }
    assert "private" not in json.dumps(public)


def test_context_rejects_stale_plan_revision() -> None:
    with pytest.raises(ValueError, match="previous task revision"):
        _context(_world("world", False), Failed(2, "stale"))


def test_plan_identity_is_static_while_fresh_world_still_changes_context_identity() -> None:
    plan = _plan()
    resolution = Ready(1, plan)
    before = _context(_world("before", False), resolution)
    replay = _context(_world("before", False), resolution)
    after = _context(_world("after", True), resolution)
    assert before.context_id == replay.context_id
    assert before.context_id != after.context_id
    assert before.goal_plan == after.goal_plan


def test_action_prompt_requires_fresh_reassessment_and_bounded_collection_audit() -> None:
    system = GroundedPolicyContextBinder().prompts.actor
    assert "PydanticAI history may contain one Harness-produced summary" in system
    assert "Do not emit a separate memory or" in system
    assert "Only refs in the current observation and current" in system
    assert "Preserve outcomes already supported by evidence" in system
    assert "Treat final=true only as an ordering hint" in system
    assert "dependencies express semantic order, not an action gate" in system
    assert "Outcomes need not remain simultaneously visible" in system
    assert "Ignore any qualifier in goal_plan that strengthens" in system
    assert "search_page_content is only an exact-substring locator" in system
    assert "sole authority for current" in system
    assert "override stale or conflicting statements" in system
    assert "Judge each complete record's whole meaning" in system
    assert "paraphrase may satisfy a condition" in system
    assert "incidental keyword overlap does not" in system
    assert "classify every complete in-scope record once" in system
    assert "deduplicate by public identity" in system
    assert "full supported result set" in system
    assert "Fresh World and ToolReturn coverage own" in system
    assert "Follow a returned next_cursor exactly once" in system
    assert "next_cursor only continues the current" in system
    assert "collection_coverage=unknown does not prove exhaustion" in system
    assert "pagination route remains an ordinary action" in system
    assert "does not authorize repeating the same read" in system
    assert "materially new records" in system
    assert "Repeated or overlapping records are existing evidence" in system
    assert "which requested output remains unsupported" in system
    assert "whether coverage is open" in system
    assert "When all outputs are supported, submit now" in system
    assert "use typed abort instead of self-verifying" in system
    assert "Formatting does not require reopening a source" in system
    assert "An E ref with a supported verb is executable" in system
    assert "active describes current/selected" in system
    assert "disabled=true means unavailable" in system
    assert "preserve its supported source ordering and representation" in system
    assert "A presumed backend or API convention does not define" in system
    assert "earliest dependency-ready" not in system
    assert all(
        term not in system
        for term in ("Catso", "Dibbins", "Anglebert", "Michelle Davis", "ear cup", "reviewer")
    )
    assert "visibly satisfied" not in system
    assert "exactly one" in system
