from __future__ import annotations

import json
import re
from collections import Counter
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.observation_delivery import (
    ObservationDeliveryStore,
    PublicEffectProjector,
)
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.decisions import (
    ReadRegionResult,
    RememberFactResult,
    SearchPageContentResult,
    ToolRejectedResult,
)
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.agent.workspace import (
    ActivityFamily,
    AgentWorkspace,
    DefaultWorkspaceReducer,
    SemanticEventKind,
    render_agent_workspace,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus, WorldEvidenceIndex
from affordance_runtime.immutable import to_json_compatible
from tests.support.agent.core_loop_support import shared_world
from tests.support.canonical_world import canonical_world


def _evaluation(observation_id: str) -> TaskEvaluation:
    return TaskEvaluation("task", observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing")


def test_workspace_reducer_is_total_for_one_thousand_ordinary_reads() -> None:
    world = shared_world("observation:reads", False)
    reducer = DefaultWorkspaceReducer()
    workspace = AgentWorkspace()
    trace = RunTraceRecorder()

    for index in range(1_000):
        decision = ReadRegionResult(
            f"context:{index}",
            "read_region",
            {"region_ref": "R1", "query": f"query-{index}"},
            {"items": ()},
        )
        step = StepResult(decision, world, world, _evaluation(world.observation_id), feedback="local_tool_result")
        workspace = reducer.reduce(workspace, step, project_step_result(step), index + 1)
        trace.step_completed(index + 1, step)

    assert len(workspace.recent_steps) == 4
    assert tuple(item.semantic_summary["query"] for item in workspace.recent_steps) == tuple(
        f"query-{index}" for index in range(996, 1_000)
    )
    activity = next(item for item in workspace.activities if item.family is ActivityFamily.READ_REGION)
    assert activity.attempt_count == 1_000
    assert workspace.semantic_events == ()
    assert sum(item["event"] == "step_completed" for item in trace.events) == 1_000


@given(
    st.lists(
        st.sampled_from(("read_region", "search_page_content", "find_controls", "wait")),
        max_size=200,
    )
)
def test_workspace_reducer_folds_generated_observation_activity_sequences(
    operations: list[str],
) -> None:
    world = shared_world("observation:generated-activity", False)
    unchanged = WorldTransitionProjector().project(world, world)
    reducer = DefaultWorkspaceReducer()
    workspace = AgentWorkspace()

    for step_index, operation in enumerate(operations, 1):
        step = SimpleNamespace(
            public_world_delta=unchanged,
            execution_receipts=None,
            decision=SimpleNamespace(working_fact=None),
            recovery_signal=None,
            status_after="running",
            failure_code=None,
            runtime_failure=None,
            feedback="local_tool_result",
        )
        workspace = reducer.reduce(
            workspace,
            step,
            AgentTurnView(operation, operation, reason="unchanged"),
            step_index,
        )

    expected = Counter(operations)
    actual = {item.family.value: item.attempt_count for item in workspace.activities}
    assert actual == expected
    assert len(workspace.recent_steps) == min(4, len(operations))
    assert tuple(item.semantic_action for item in workspace.recent_steps) == tuple(operations[-4:])
    assert workspace.semantic_events == ()


def test_exact_gui_result_survives_after_it_leaves_latest_four_steps() -> None:
    before = shared_world("observation:before", False)
    after = shared_world("observation:after", True)
    delta = WorldTransitionProjector().project(before, after)
    reducer = DefaultWorkspaceReducer()
    effect = SimpleNamespace(
        public_world_delta=delta,
        execution_receipts=SimpleNamespace(receipts=(object(),)),
        decision=SimpleNamespace(working_fact=None),
        recovery_signal=None,
        status_after="running",
        failure_code=None,
        runtime_failure=None,
        feedback="action_changed",
    )
    workspace = reducer.reduce(
        AgentWorkspace(),
        effect,
        AgentTurnView("select_action", "activate", reason="changed"),
        1,
        public_effect=PublicEffectProjector().project(
            delta,
            canonical_world(before),
            canonical_world(after),
        ),
    )
    ordinary = SimpleNamespace(
        public_world_delta=WorldTransitionProjector().project(after, after),
        execution_receipts=None,
        decision=SimpleNamespace(working_fact=None),
        recovery_signal=None,
        status_after="running",
        failure_code=None,
        runtime_failure=None,
        feedback="local_tool_result",
    )
    for index in range(2, 10):
        workspace = reducer.reduce(
            workspace,
            ordinary,
            AgentTurnView("read_region", "read_region", reason=f"read-{index}"),
            index,
        )

    assert all(item.semantic_action != "activate" for item in workspace.recent_steps)
    event = next(item for item in workspace.semantic_events if item.kind is SemanticEventKind.PUBLIC_RESULT)
    assert any(item["predicate"] == "enabled" and item["value"] is True for item in event.exact_public_values)
    rendered = json.dumps(to_json_compatible(render_agent_workspace(workspace, total_step_count=9)))
    assert '"value": true' in rendered


def test_projected_workspace_removes_generation_local_entity_and_fact_refs() -> None:
    world = shared_world("observation:refs", False)
    decision = ReadRegionResult(
        "context:test",
        "count_children",
        {"containers": ("E1",), "evidence_ref": "F2"},
        {"counts": {"E1": 2}, "source": "F2"},
        "provider-call:refs",
    )
    result = StepResult(decision, world, world, _evaluation(world.observation_id), feedback="used E1 and F2")
    projected = project_step_result(result)
    rendered = render_agent_workspace(AgentWorkspace((projected,)), total_step_count=1)
    encoded = json.dumps(to_json_compatible(rendered))

    assert not re.search(r"\b[EF][1-9][0-9]{0,2}\b", encoded)
    assert "expired-ref" not in encoded


def test_rejected_action_workspace_keeps_semantics_not_ref_identity() -> None:
    world = shared_world("observation:rejected", False)
    decision = ToolRejectedResult(
        "context:test",
        "tool_rejected",
        {"operation": "activate", "arguments": {"target": "E59"}},
        {
            "attempted_operation": "activate",
            "target": {"role": "focused_context", "label": "REPORTS"},
            "failure_reason": "operation is not offered for the current target",
            "available_operations": ("press_key",),
            "dispatch": "not_sent",
            "world_changed": False,
        },
    )
    projected = project_step_result(
        StepResult(decision, world, world, _evaluation(world.observation_id), feedback="tool_rejected")
    )
    encoded = json.dumps(
        to_json_compatible(render_agent_workspace(AgentWorkspace((projected,)), total_step_count=1))
    )

    assert projected.semantic_summary["result"]["target"] == {
        "role": "focused_context",
        "label": "REPORTS",
    }
    assert "press_key" in encoded
    assert "E59" not in encoded


def test_working_fact_moves_into_workspace_without_gui_execution() -> None:
    world = shared_world("observation:pin", False)
    record = WorldEvidenceIndex.from_observation(world).records[0]
    fact = WorkingFact("saved_enabled", record, 0, "reuse later")
    decision = RememberFactResult(
        "context:test",
        "remember_fact",
        {"key": "saved_enabled", "evidence_ref": "F1", "purpose": "reuse later"},
        {"status": "pinned", "key": "saved_enabled"},
        "provider-call:pin",
        working_fact=fact,
    )
    step = StepResult(decision, world, world, _evaluation(world.observation_id), feedback="local_tool_result")
    workspace = DefaultWorkspaceReducer().reduce(AgentWorkspace(), step, project_step_result(step), 1)

    assert workspace.working_facts == (fact,)
    assert workspace.semantic_events[-1].kind is SemanticEventKind.WORKING_FACT


def test_local_delivery_new_items_enter_workspace_and_replay_is_compact() -> None:
    world = shared_world("observation:local-delivery", False)
    decision = SearchPageContentResult(
        "context:test",
        "search_page_content",
        {"query": "airport"},
        {
            "kind": "Matches",
            "items": (
                {"label": "Airport", "value": "33 km"},
                {"label": "postcode", "value": "15231"},
            ),
        },
    )
    step = StepResult(decision, world, world, _evaluation(world.observation_id), feedback="local_tool_result")
    first = ObservationDeliveryStore().reduce(step, step_index=1)
    reducer = DefaultWorkspaceReducer()
    workspace = reducer.reduce(
        AgentWorkspace(),
        step,
        project_step_result(step, information_delta=first.information_delta),
        1,
        information_delta=first.information_delta,
    )
    replay = first.next_store.reduce(step, step_index=2)
    replay_view = project_step_result(step, information_delta=replay.information_delta)

    assert workspace.semantic_events[-1].kind is SemanticEventKind.PUBLIC_RESULT
    assert len(workspace.semantic_events[-1].exact_public_values) == 2
    assert workspace.activities[-1].new_finding_count == 2
    assert workspace.activities[-1].last_outcome == "new_information"
    assert replay_view.semantic_summary["information_delta"] == "exact_replay"
    assert "result" not in replay_view.semantic_summary


def test_typed_failure_is_retained_as_a_bounded_semantic_event() -> None:
    world = shared_world("observation:failure", False)
    step = SimpleNamespace(
        public_world_delta=WorldTransitionProjector().project(world, world),
        execution_receipts=None,
        decision=SimpleNamespace(working_fact=None),
        recovery_signal=None,
        status_after="failed",
        failure_code="internal_error",
        runtime_failure=object(),
        feedback="unexpected runtime failure",
    )

    workspace = DefaultWorkspaceReducer().reduce(AgentWorkspace(), step, None, 7)

    assert len(workspace.semantic_events) == 1
    assert workspace.semantic_events[0].kind is SemanticEventKind.TYPED_FAILURE
    assert workspace.semantic_events[0].step_index == 7


def test_working_fact_rejects_non_scalar_evidence() -> None:
    world = shared_world("observation:non-scalar", False)
    record = WorldEvidenceIndex.from_observation(world).records[0]
    non_scalar = type(record)(
        record.evidence_ref,
        record.observation_id,
        record.kind,
        record.source_id,
        record.source_observation_id,
        record.source_modality,
        record.source_assurance,
        record.subject_id,
        record.predicate,
        ("not", "scalar"),
    )

    with pytest.raises(ValueError, match="scalar"):
        WorkingFact("invalid", non_scalar, 0, "later")
