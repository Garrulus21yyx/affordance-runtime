from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from affordance_runtime.goals import (
    Failed,
    GoalCompileTrigger,
    GoalPlanBoundary,
    GoalPlanProposal,
    InvalidGoalProposal,
    NeedsInput,
    NotRequired,
    Ready,
    Unsupported,
)
from tests.support.agent.core_loop_support import _task, _world


def _proposal(*items, revision: int = 1):
    return GoalPlanProposal(
        revision,
        tuple(items) or (
            {
                "id": "complete_requested_changes",
                "objective": "Complete every requested visible change.",
                "done_when": "Every relevant item visibly has the requested state.",
                "depends_on": (),
                "final": False,
            },
            {
                "id": "finalize_task",
                "objective": "Finalize the task.",
                "done_when": "Finalization occurs after requested changes are complete.",
                "depends_on": ("complete_requested_changes",),
                "final": True,
            },
        ),
    )


@dataclass
class SequenceCompiler:
    outcomes: list[object]
    requests: list[object] = field(default_factory=list)

    async def compile(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        return outcome(request) if callable(outcome) else outcome


def test_boundary_accepts_only_five_fields_and_ignores_descriptive_surplus() -> None:
    raw = dict(_proposal().items[0])
    raw.update({"label": "harmless", "kind": "ignored", "edge_path": ["ignored"]})
    plan = GoalPlanBoundary().accept(_proposal(raw), _task(), plan_version=3)
    assert plan.plan_version == 3
    assert plan.items[0].id == "complete_requested_changes"
    assert vars(plan.items[0]).keys() == {"id", "objective", "done_when", "depends_on", "final"}


def test_boundary_rejects_duplicate_dangling_cycle_and_multiple_final() -> None:
    valid = dict(_proposal().items[0])
    cases = (
        (valid, dict(valid)),
        (dict(valid, depends_on=("missing",)),),
        (dict(valid, id="a", depends_on=("b",)), dict(valid, id="b", depends_on=("a",))),
        (dict(valid, id="a", final=True), dict(valid, id="b", final=True)),
    )
    for items in cases:
        with pytest.raises(InvalidGoalProposal):
            GoalPlanBoundary().accept(_proposal(*items), _task(), plan_version=1)


def test_boundary_contract_repair_is_one_bounded_compiler_call() -> None:
    invalid = _proposal({"id": "broken"})
    compiler = SequenceCompiler([invalid, _proposal()])
    resolution = asyncio.run(GoalPlanBoundary().resolve(
        compiler, _task(), _world("initial", False), next_plan_version=1,
    ))
    assert isinstance(resolution, Ready)
    assert [request.attempt for request in compiler.requests] == [0, 1]
    assert compiler.requests[1].repair_errors == ("goal_plan_item_invalid",)


def test_start_revision_and_advisory_dispositions_preserve_typed_contract() -> None:
    for outcome in (NotRequired(1, "atomic"), Unsupported(1, "unsupported"), Failed(1, "failed")):
        compiler = SequenceCompiler([outcome])
        result = asyncio.run(GoalPlanBoundary().resolve(
            compiler, _task(), _world("initial", False), next_plan_version=1,
            trigger=GoalCompileTrigger.TASK_START,
        ))
        assert result == outcome
        assert compiler.requests[0].trigger is GoalCompileTrigger.TASK_START


def test_needs_input_remains_only_user_fact_pause() -> None:
    compiler = SequenceCompiler([NeedsInput(1, "Which account?", ("account",))])
    result = asyncio.run(GoalPlanBoundary().resolve(
        compiler, _task(), _world("initial", False), next_plan_version=1,
    ))
    assert isinstance(result, NeedsInput)
