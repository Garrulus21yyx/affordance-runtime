from __future__ import annotations

import pytest

from affordance_runtime.agent.decisions import (
    Abort,
    AskUser,
    ContinueDeliveryResult,
    PublicEvidenceResult,
    ReadRegionResult,
    RememberFactResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.tool_result_projection import (
    committed_public_evidence,
    committed_tool_call_id,
    project_committed_tool_return,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
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
    assert committed_public_evidence(step) is None


@pytest.mark.parametrize(
    "result_type",
    (
        ReadRegionResult,
        SearchPageContentResult,
        ContinueDeliveryResult,
        RememberFactResult,
        ToolRejectedResult,
    ),
)
def test_closed_local_result_algebra_projects_without_operation_name_classification(result_type) -> None:
    evidence = PublicEvidenceResult.from_value(
        {
            "kind": "Evidence",
            "items": (
                {"nested": {"text": "完整🙂", "ordinal": 1}},
                {"nested": {"text": "suffix", "ordinal": 2}},
            ),
        },
        source_scope="current",
    )
    decision = result_type(
        "context:fixture",
        "future_operation",
        {"public": "argument"},
        evidence,
        "call:local",
    )
    step = _step(decision)

    assert committed_public_evidence(step) is evidence
    assert project_committed_tool_return(
        step,
        admitted_evidence_records=(evidence.records[0],),
    )["items"] == (evidence.records[0],)
    assert project_committed_tool_return(step, admitted_evidence_records=())["items"] == ()


def test_public_result_prefix_selection_never_mutates_the_committed_result() -> None:
    evidence = PublicEvidenceResult.from_value(
        {"items": ({"value": "一"}, {"value": "二"})},
        source_scope="generated",
    )
    decision = SearchPageContentResult(
        "context:fixture", "future_reader", {}, evidence, "call:prefix"
    )
    step = _step(decision)
    original = decision.result

    projected = project_committed_tool_return(
        step,
        admitted_evidence_records=(evidence.records[0],),
    )

    assert projected["items"] == (evidence.records[0],)
    assert decision.result is original
    assert decision.result["items"] == evidence.value["items"]
