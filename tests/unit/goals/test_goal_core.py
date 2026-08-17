from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime.goals import (
    Failed,
    GoalPlan,
    GoalPlanItem,
    NotRequired,
    Ready,
    Unsupported,
    project_agent_goal_plan,
)


def _items():
    return (
        GoalPlanItem(
            "complete_requested_changes",
            "Ensure every requested item has the desired visible state without changing unrelated controls.",
            "Every relevant item visibly has the requested state.",
        ),
        GoalPlanItem(
            "finalize_task",
            "Finalize the completed task.",
            "The final effect is performed after all requested changes are visibly complete.",
            ("complete_requested_changes",),
            True,
        ),
    )


def _plan(revision: int = 1, version: int = 1) -> GoalPlan:
    return GoalPlan(revision, version, _items())


def test_goal_plan_is_bounded_versioned_and_digest_stable() -> None:
    first = _plan()
    replay = _plan()
    changed = GoalPlan(1, 2, _items())
    assert first.digest == replay.digest
    assert first.digest != changed.digest
    assert len(first.digest) == 64


@pytest.mark.parametrize(
    "items, match",
    (
        ((_items()[0], replace(_items()[0], objective="changed")), "ids"),
        ((replace(_items()[0], depends_on=("missing",)),), "dangling"),
        ((replace(_items()[0], depends_on=("finalize_task",)), _items()[1]), "DAG"),
        ((replace(_items()[1], depends_on=()), replace(_items()[1], id="another_final", depends_on=())), "at most one"),
    ),
)
def test_goal_plan_rejects_invalid_global_shape(items, match) -> None:
    with pytest.raises(ValueError, match=match):
        GoalPlan(1, 1, items)


def test_goal_plan_view_is_direct_and_contains_no_runtime_progress() -> None:
    plan = _plan()
    view = project_agent_goal_plan(Ready(1, plan))
    assert view.resolution == "ready"
    assert view.plan_version == 1
    assert view.plan_digest == plan.digest
    assert view.items == plan.items
    assert not hasattr(view, "frontier_refs")
    assert not hasattr(view, "obligations")
    assert not hasattr(view, "snapshot_digest")


@pytest.mark.parametrize(
    "resolution, expected",
    (
        (NotRequired(1, "atomic"), "not_required"),
        (Failed(1, "provider_failed"), "unavailable"),
        (Unsupported(1, "unsupported"), "unavailable"),
    ),
)
def test_empty_plan_dispositions_are_explicit(resolution, expected) -> None:
    view = project_agent_goal_plan(resolution)
    assert view.resolution == expected
    assert view.items == ()
    assert view.plan_version is None
    assert view.plan_digest == ""
