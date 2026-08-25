from __future__ import annotations

import pytest

from affordance_runtime.agent.decisions import (
    Abort,
    AskUser,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.tool_result_projection import (
    committed_tool_call_id,
    project_committed_tool_return,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import (
    ActionError,
    ActionResult,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceiptBatch,
)
from affordance_runtime.world.observation_needs import ObservationPurpose
from tests.support.agent.core_loop_support import _world


def _evaluation(observation_id: str) -> TaskEvaluation:
    return TaskEvaluation("task:projection", observation_id, TaskEvaluationStatus.INCOMPLETE, "fixture")


def _step(decision, *, waited_ms: int = 0) -> StepResult:
    world = _world("tool-result-projection", False)
    return StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        waited_ms=waited_ms,
        feedback="committed fixture",
    )


@pytest.mark.parametrize(
    "decision",
    (
        RequestObservation(
            "context:fixture",
            ObservationPurpose.ENTITY_DISCOVERY.value,
            "subject",
            "",
            "inspect",
            tool_call_id="call:observe",
        ),
        RequestActionPage("context:fixture", "query", tool_call_id="call:discover"),
        AskUser("context:fixture", "Which value?", ("value",), "call:ask"),
        Wait("context:fixture", "settle", 100, "call:wait"),
        Abort("context:fixture", "stop", "user_request", "call:abort"),
    ),
)
def test_supported_nonlocal_decisions_have_one_call_correlated_public_projection(decision) -> None:
    step = _step(decision, waited_ms=100 if isinstance(decision, Wait) else 0)

    assert committed_tool_call_id(step) == decision.tool_call_id
    assert project_committed_tool_return(step) is not None


@pytest.mark.parametrize(
    "result_type",
    (ReadRegionResult, SearchPageContentResult, ToolRejectedResult),
)
def test_closed_local_result_algebra_projects_the_owner_mapping_unchanged(result_type) -> None:
    result = {
        "kind": "Evidence",
        "items": (
            {"nested": {"text": "完整🙂", "ordinal": 1}},
            {"nested": {"text": "suffix", "ordinal": 2}},
        ),
        "next_cursor": "2",
    }
    decision = result_type(
        "context:fixture",
        "future_operation",
        {"public": "argument"},
        result,
        "call:local",
    )

    projected = project_committed_tool_return(_step(decision))

    assert projected == decision.result
    assert projected["items"] == decision.result["items"]
    assert projected["next_cursor"] == "2"


def test_projection_has_no_prefix_selection_api() -> None:
    decision = SearchPageContentResult(
        "context:fixture",
        "search_page_content",
        {},
        {"items": ({"value": "一"}, {"value": "二"}), "next_cursor": None},
        "call:direct",
    )
    with pytest.raises(TypeError):
        project_committed_tool_return(  # type: ignore[call-arg]
            _step(decision), admitted_evidence_records=()
        )


def test_non_dispatched_terminal_failure_is_not_hidden_from_same_call_tool_return() -> None:
    world = _world("tool-result-terminal-failure", False)
    decision = SelectAction(
        "context:fixture",
        "action:fixture",
        tool_call_id="call:action",
    )
    result = ActionResult(
        "request:fixture",
        DispatchStatus.NOT_SENT,
        "browsergym",
        False,
        ActionError.STALE_BINDING,
        adapter_evidence={
            "currentness_status": "stale",
            "currentness_reason": "task_done",
            "private_backend_detail": "must-not-project",
        },
    )
    step = StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        execution_receipts=ExecutionReceiptBatch(
            (),
            ExecutionCompletion.PARTIAL,
            terminal_failure=result,
        ),
        feedback="binding rejected before dispatch",
    )

    projected = project_committed_tool_return(step)

    assert projected == {
        "status": "running",
        "failed": True,
        "kind": "execution_receipt",
        "completion": "partial",
        "receipts": [],
        "terminal_failure": {
            "dispatch_status": "not_sent",
            "transport_success": False,
            "error": "stale_binding",
            "currentness": {"status": "stale", "reason": "task_done"},
        },
    }
    assert "private_backend_detail" not in repr(projected)
