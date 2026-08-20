from __future__ import annotations

import json

import pytest

from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.evaluation.contracts import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.goals import Failed, GoalPlan, GoalPlanItem, NotRequired, Ready, Unsupported
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
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
        recent_steps,
        goal_resolution=resolution,
    )


def _public(context):
    delivery = build_model_turn_delivery(context, include_images=False)
    catalog = compile_grounded_action_catalog(context, delivery)
    messages = GroundedPolicyContextBinder().action_messages(
        ModelDecisionRequest("model-request:g2", context),
        catalog.specs,
        delivery,
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        include_tool_menu=True,
    )
    return json.loads(messages[1].content)


def test_ready_goal_plan_is_direct_static_context_without_progress_projection() -> None:
    world = _world("world:before", False)
    plan = _plan()
    public = _public(_context(world, Ready(1, plan)))
    assert tuple(public) == ("task", "observation", "goal_plan", "recent_steps", "tools")
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


def test_action_prompt_requires_fresh_reassessment_toggle_preservation_and_dependency_order() -> None:
    system = GroundedPolicyContextBinder().prompts.actor
    assert "Reassess progress from task, fresh observation, and semantic recent_steps on every turn" in system
    assert "Only refs in the current observation and current" in system
    assert "Preserve outcomes already supported by evidence" in system
    assert "Treat final=true only as an ordering hint" in system
    assert "dependencies express semantic order, not an action gate" in system
    assert "Outcomes need not remain simultaneously visible" in system
    assert "earliest dependency-ready" not in system
    assert "visibly satisfied" not in system
    assert "exactly one" in system
