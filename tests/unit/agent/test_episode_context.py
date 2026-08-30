from __future__ import annotations

import json
import re
from collections import Counter
from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView
from affordance_runtime.agent.context.contracts import (
    AgentTurnView,
    history_operational_refs,
    sanitize_history_arguments,
    sanitize_history_prose,
)
from affordance_runtime.agent.context.observation_delivery import (
    ObservationDeliveryStore,
)
from affordance_runtime.agent.context.step_projection import _historical_target, project_step_result
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.decisions import (
    ReadRegionResult,
    SearchPageContentResult,
    ToolRejectedResult,
)
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.workspace import (
    ActivityFamily,
    ActivitySummary,
    AgentWorkspace,
    DefaultWorkspaceReducer,
    SemanticEventKind,
    render_agent_workspace,
    render_current_activities,
    render_recent_trajectory,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest
from tests.support.agent.core_loop_support import shared_world


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

    assert len(workspace.recent_steps) == 8
    assert tuple(item.semantic_summary["query"] for item in workspace.recent_steps) == tuple(
        f"query-{index}" for index in range(992, 1_000)
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
            decision=SimpleNamespace(),
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
    assert len(workspace.recent_steps) == min(8, len(operations))
    assert tuple(item.semantic_action for item in workspace.recent_steps) == tuple(operations[-8:])
    assert workspace.semantic_events == ()


def test_workspace_keeps_gui_effect_summary_without_copying_exact_values() -> None:
    before = shared_world("observation:before", False)
    after = shared_world("observation:after", True)
    delta = WorldTransitionProjector().project(before, after)
    reducer = DefaultWorkspaceReducer()
    effect = SimpleNamespace(
        public_world_delta=delta,
        execution_receipts=SimpleNamespace(receipts=(object(),)),
        decision=SimpleNamespace(),
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
    )
    ordinary = SimpleNamespace(
        public_world_delta=WorldTransitionProjector().project(after, after),
        execution_receipts=None,
        decision=SimpleNamespace(),
        recovery_signal=None,
        status_after="running",
        failure_code=None,
        runtime_failure=None,
        feedback="local_tool_result",
    )
    for index in range(2, 9):
        workspace = reducer.reduce(
            workspace,
            ordinary,
            AgentTurnView(
                "read_region",
                "read_region",
                reason=f"read-{index}",
                semantic_summary={
                    "scope": {"role": "main", "heading": f"section-{index}"},
                    "result_page": "1/1",
                },
            ),
            index,
        )

    assert workspace.recent_steps[0].semantic_action == "activate"
    assert tuple(item.semantic_summary["scope"]["heading"] for item in workspace.recent_steps[1:]) == tuple(
        f"section-{index}" for index in range(2, 9)
    )
    workspace = reducer.reduce(
        workspace,
        ordinary,
        AgentTurnView(
            "read_region",
            "read_region",
            reason="read-9",
            semantic_summary={"scope": {"role": "main", "heading": "section-9"}, "result_page": "1/1"},
        ),
        9,
    )
    assert all(item.semantic_action != "activate" for item in workspace.recent_steps)
    rendered = json.dumps(to_json_compatible(render_agent_workspace(workspace, total_step_count=9)))
    assert tuple(item.kind for item in workspace.semantic_events) == (SemanticEventKind.GUI_EFFECT,)
    assert workspace.semantic_events[0].summary == "activate"
    assert '"value": true' not in rendered


def test_projected_workspace_removes_generation_local_entity_and_fact_refs() -> None:
    world = shared_world("observation:refs", False)
    decision = ReadRegionResult(
        "context:test",
        "count_children",
        {"containers": ("E1",), "evidence_ref": "F2"},
        {"counts": {"E1": 2}, "evidence_ref": "F2", "total": 2},
        "provider-call:refs",
    )
    result = StepResult(decision, world, world, _evaluation(world.observation_id), feedback="used E1 and F2")
    projected = project_step_result(result)
    rendered = render_agent_workspace(AgentWorkspace((projected,)), total_step_count=1)
    encoded = json.dumps(to_json_compatible(rendered))

    assert not re.search(r"\b[EF][1-9][0-9]{0,2}\b", encoded)
    assert "expired-ref" not in encoded


def test_history_contract_distinguishes_typed_refs_from_ref_shaped_business_values() -> None:
    value = {
        "target": "E1",
        "region_ref": "R4",
        "text": "E6",
        "query": "R2",
        "label": "F3",
    }

    assert history_operational_refs(value, include_selectors=True) == frozenset({"E1", "R4"})
    assert sanitize_history_arguments(value) == {
        "text": "E6",
        "query": "R2",
        "label": "F3",
    }
    prose = sanitize_history_prose(
        "Used E1 to enter business code E6; next query R2.",
        expired_refs={"E1"},
    )
    assert "E1" not in prose
    assert "E6" in prose
    assert "R2" in prose


def test_recent_trajectory_uses_the_same_model_state_allowlist_as_fresh_world() -> None:
    transition = {
        "role": "textbox",
        "label": "",
        "observed_change": "changed",
        "before_state": {
            "active": False,
            "semantic.dom.attribute.type": "text",
            "semantic.dom.attribute.title": "Product filter",
            "semantic.dom.attribute.id": "implementation-filter-id",
            "semantic.dom.attribute.name": "implementation_filter_name",
            "semantic.dom.attribute.class_tokens": ("private-class",),
            "semantic.dom.tag": "input",
            "semantic.name_status": "unknown",
            "appearance.color_family": "gray",
        },
        "after_state": {
            "active": True,
            "semantic.dom.attribute.type": "text",
            "semantic.dom.attribute.title": "Product filter",
            "semantic.dom.attribute.id": "implementation-filter-id",
        },
    }
    rendered = render_recent_trajectory(
        AgentWorkspace((AgentTurnView("select_action", "type_text", transition=transition),))
    )
    encoded = json.dumps(to_json_compatible(rendered))

    assert rendered[0]["result"]["transition"]["before_state"] == {
        "active": False,
        "semantic.dom.attribute.type": "text",
        "semantic.dom.attribute.title": "Product filter",
    }
    assert rendered[0]["result"]["transition"]["after_state"] == {
        "active": True,
        "semantic.dom.attribute.type": "text",
        "semantic.dom.attribute.title": "Product filter",
    }
    assert "implementation-filter-id" not in encoded
    assert "implementation_filter_name" not in encoded
    assert "private-class" not in encoded


def test_recent_trajectory_never_uses_dom_class_as_a_target_label() -> None:
    target = ActorWorldNodeView(
        "E1",
        "textbox",
        "",
        {"semantic.dom.attribute.class_tokens": ("implementation-filter",)},
    )
    result = SimpleNamespace(
        policy_observation=SimpleNamespace(documents=(SimpleNamespace(roots=(target,)),)),
        policy_target_refs={"target:filter": "E1"},
    )

    projected = _historical_target(result, "target:filter")

    assert projected is not None
    assert projected.role == "textbox"
    assert projected.label == ""
    assert "implementation-filter" not in json.dumps(to_json_compatible(projected))


def test_read_region_workspace_keeps_ref_free_scope_without_copying_result_body() -> None:
    world = shared_world("observation:read-scope", False)
    decision = ReadRegionResult(
        "context:test",
        "read_region",
        {"region_ref": "R7", "cursor": "opaque"},
        {
            "kind": "Opened",
            "items": ({"kind": "complete_item", "content": ({"text": "private body"},)},),
            "has_more": True,
            "result_page": "1/3",
            "source_coverage": "complete",
            "region_membership": "complete",
            "scope": {
                "role": "main",
                "heading": "Results",
                "context": ("Account", "Results"),
            },
        },
    )
    projected = project_step_result(
        StepResult(decision, world, world, _evaluation(world.observation_id), feedback="local_tool_result")
    )
    encoded = json.dumps(
        to_json_compatible(render_agent_workspace(AgentWorkspace((projected,)), total_step_count=1))
    )

    assert to_json_compatible(projected.semantic_summary["scope"]) == {
        "role": "main",
        "heading": "Results",
        "context": ["Account", "Results"],
    }
    assert projected.semantic_summary["has_more"] is True
    assert projected.semantic_summary["result_page"] == "1/3"
    assert "private body" not in encoded
    assert "R7" not in encoded
    assert "opaque" not in encoded


def test_rejected_action_workspace_keeps_receipt_not_result_body_or_ref_identity() -> None:
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

    assert "result" not in projected.semantic_summary
    assert projected.semantic_summary["operation"] == "activate"
    assert projected.semantic_summary["feedback_code"] == "tool_rejected"
    assert "press_key" not in encoded
    assert "REPORTS" not in encoded
    assert "E59" not in encoded


def test_local_delivery_records_stay_in_store_and_workspace_keeps_only_lineage() -> None:
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
    assert workspace.semantic_events[-1].operation == "search_page_content"
    assert workspace.semantic_events[-1].result_lineage == first.information_delta.inventory_digest
    receipt = first.next_store.local_deliveries[-1]
    assert len(receipt.item_digests) == len(decision.result["items"])
    assert not hasattr(receipt, "records")
    assert "Airport" not in repr(receipt)
    assert "exact_public_values" not in vars(workspace.semantic_events[-1])
    assert workspace.activities[-1].new_finding_count == 2
    assert workspace.activities[-1].last_outcome == "new_information"
    assert replay_view.semantic_summary["information_delta"] == "exact_replay"
    assert "result" not in replay_view.semantic_summary


def test_current_activity_projection_is_bounded_ref_free_and_fresh_world_only() -> None:
    world = shared_world("observation:current-activity", False)
    current_digest = public_world_semantic_digest(world)
    workspace = AgentWorkspace(
        activities=(
            ActivitySummary(ActivityFamily.SEARCH_PAGE_CONTENT, "stale-digest", 7, 0, "exact_replay E9"),
            ActivitySummary(ActivityFamily.READ_REGION, current_digest, 3, 0, "no_new_information"),
        ),
    )

    rendered = render_current_activities(
        workspace,
        current_world_digest=current_digest,
    )

    assert rendered == (
        {
            "family": "read_region",
            "attempt_count": 3,
            "last_new_information_count": 0,
            "last_outcome": "no_new_information",
        },
    )
    assert current_digest not in json.dumps(rendered)
    assert "E9" not in json.dumps(rendered)


def test_typed_failure_is_retained_as_a_bounded_semantic_event() -> None:
    world = shared_world("observation:failure", False)
    step = SimpleNamespace(
        public_world_delta=WorldTransitionProjector().project(world, world),
        execution_receipts=None,
        decision=SimpleNamespace(),
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
