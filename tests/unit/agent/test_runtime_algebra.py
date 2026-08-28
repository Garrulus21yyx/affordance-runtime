from __future__ import annotations

import pytest

from affordance_runtime.agent import (
    Abort,
    DecisionKind,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    RunState,
    RunStatus,
    SearchPageContentResult,
    SelectAction,
    StandaloneRunBudget,
    StepResult,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.episode_snapshot import snapshot_episode
from affordance_runtime.agent.interactions import legacy_interaction_request
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from tests.support.world import fused_world


def _evaluation(observation_id: str) -> TaskEvaluation:
    return TaskEvaluation(
        "task:algebra",
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )


def test_every_control_decision_uses_the_single_decision_kind_algebra() -> None:
    decisions = (
        legacy_interaction_request(
            context_id="context:test",
            prompt="Which value?",
            requested_fields=(),
        ),
        Abort("context:test", "stop", "user_request"),
    )
    assert tuple(item.kind for item in decisions) == (
        DecisionKind.ASK_USER,
        DecisionKind.ABORT,
    )


def test_decision_algebra_is_exhaustive_through_step_history_trace_and_snapshot(tmp_path) -> None:
    decisions = (
        SelectAction("context:test", "action:one"),
        RequestObservation(
            context_id="context:test",
            query_id="observation-query:test",
            purpose="entity_discovery",
            atomic_query="inspect",
        ),
        RequestActionPage("context:test", query="controls"),
        legacy_interaction_request(
            context_id="context:test",
            prompt="Which value?",
            requested_fields=(),
        ),
        ReadRegionResult("context:test", "read_region", {}, {"items": ()}),
        SearchPageContentResult("context:test", "search_page_content", {}, {"items": ()}),
        ToolRejectedResult("context:test", "tool_rejected", {}, {"rejected": True}),
        FinalResponse("context:test", "done", ("evidence:test",)),
        Wait("context:test", "settle", 1),
        Abort("context:test", "stop", "user_request"),
    )
    assert {item.kind for item in decisions} == set(DecisionKind)

    for index, decision in enumerate(decisions):
        world = fused_world(f"observation:decision:{index}")
        status = (
            RunStatus.WAITING_USER
            if decision.kind is DecisionKind.ASK_USER
            else RunStatus.DONE
            if decision.kind is DecisionKind.SUBMIT_FINAL_RESPONSE
            else RunStatus.CANCELLED
            if decision.kind is DecisionKind.ABORT
            else RunStatus.RUNNING
        )
        step = StepResult(
            decision,
            world,
            world,
            _evaluation(world.observation_id),
            status,
            feedback=f"decision:{decision.kind.value}",
        )
        state = RunState(world, _evaluation(world.observation_id), 2)
        state.apply(step)
        recorder = RunTraceRecorder(tmp_path / str(index))
        recorder.step_completed(index + 1, step)

        assert project_step_result(step).decision_kind == decision.kind.value
        assert snapshot_episode(state).last_decision_kind == decision.kind.value
        traced = recorder.events[-1]["result"]["decision"]
        assert traced["kind"] == decision.kind.value


def test_step_result_rejects_values_outside_the_closed_decision_algebra() -> None:
    world = fused_world("observation:invalid-decision")
    with pytest.raises(TypeError, match="closed decision algebra"):
        StepResult(
            object(),  # type: ignore[arg-type]
            world,
            world,
            _evaluation(world.observation_id),
            feedback="invalid decision",
        )


def test_single_run_budget_is_positive_and_not_an_episode_authority() -> None:
    assert StandaloneRunBudget(16).turns == 16
    with pytest.raises(ValueError, match="positive"):
        StandaloneRunBudget(0)
