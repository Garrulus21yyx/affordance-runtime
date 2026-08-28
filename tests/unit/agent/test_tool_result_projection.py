from __future__ import annotations

import pytest

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent.context import ContextBuilder
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
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationObservedItem,
    ObservationQueryDisposition,
    ObservationQueryOutcome,
    ObservationUnknownItem,
    QueryScopeLocator,
    VisualUnknownReason,
)
from tests.support.agent.core_loop_support import _task, _world


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
            context_id="context:fixture",
            query_id="observation-query:fixture",
            purpose=ObservationPurpose.ENTITY_DISCOVERY,
            atomic_query="inspect",
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


def test_observation_outcome_projects_current_public_ref_without_private_subject_id() -> None:
    world = _world("tool-result-observed", False)
    task = _task()
    evaluation = TaskEvaluation(
        task.task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "fixture",
    )
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        evaluation,
    )
    decision = RequestObservation(
        context_id=context.context_id,
        query_id="observation-query:observed",
        purpose=ObservationPurpose.VISUAL_PROPERTY,
        subject_ids=("shared-toggle",),
        predicate="selected",
        tool_call_id="call:observed",
    )
    outcome = ObservationQueryOutcome(
        decision.query_id,
        decision.purpose,
        ObservationQueryDisposition.OBSERVED,
        (
            ObservationObservedItem(
                InputLocator((0,)),
                ("shared-toggle",),
                (world.facts[0].fact_id,),
            ),
        ),
    )
    step = StepResult(
        decision,
        world,
        world,
        evaluation,
        feedback="observation_acquired",
        before_public_world=context.canonical_world,
        after_public_world=context.canonical_world,
        after_delivery_index=context.region_index,
        observation_outcome=outcome,
    )

    projected = project_committed_tool_return(step)

    assert projected is not None
    assert projected["status"] == "observed"
    assert projected["query_id"] == decision.query_id
    assert projected["executable_grounding"] == "attached_to_returned_readable_targets"
    assert projected["observed_items"][0]["target_ref"].startswith("E")
    assert "activate" in projected["observed_items"][0]["verbs"]
    assert "shared-toggle" not in repr(projected)


def test_scope_unknown_projects_no_ref_or_executable_grounding() -> None:
    decision = RequestObservation(
        context_id="context:fixture",
        query_id="observation-query:unknown",
        purpose=ObservationPurpose.ENTITY_DISCOVERY,
        atomic_query="find the visible chart legend",
        tool_call_id="call:unknown",
    )
    outcome = ObservationQueryOutcome(
        decision.query_id,
        decision.purpose,
        ObservationQueryDisposition.UNKNOWN,
        unknown_items=(
            ObservationUnknownItem(
                QueryScopeLocator(),
                VisualUnknownReason.TARGET_NOT_VISIBLE,
            ),
        ),
    )
    base = _step(decision)
    step = StepResult(
        decision,
        base.before_world,
        base.after_world,
        base.task_evaluation,
        feedback="observation_unknown",
        observation_outcome=outcome,
    )

    projected = project_committed_tool_return(step)

    assert projected is not None
    assert projected["status"] == "unknown"
    assert projected["unknown_items"] == (
        {"locator": {"kind": "query_scope"}, "reason": "target_not_visible"},
    )
    assert "target_ref" not in repr(projected)
    assert "executable_grounding" not in projected


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
