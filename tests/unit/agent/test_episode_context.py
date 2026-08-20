from __future__ import annotations

import json
import re

import pytest

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.episode_history import render_episode_history
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.decisions import LocalToolResult
from affordance_runtime.agent.run_state import (
    EpisodeYieldReason,
    RunState,
    RunStatus,
    StepResult,
)
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus, WorldEvidenceIndex
from affordance_runtime.immutable import to_json_compatible
from tests.support.agent.core_loop_support import shared_world


def _evaluation(observation_id: str) -> TaskEvaluation:
    return TaskEvaluation("task", observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing")


def test_episode_history_retains_all_steps_and_never_repeats_the_latest_four() -> None:
    steps = tuple(AgentTurnView("wait", "wait", reason=f"step-{index}") for index in range(12))

    rendered = render_episode_history(steps)

    assert rendered["retained_count"] == 12
    assert tuple(item["outcome"] for item in rendered["earlier_actions"]) == tuple(
        f"step-{index}" for index in range(8)
    )
    assert tuple(item["result"]["reason"] for item in rendered["recent_trajectory"]) == tuple(
        f"step-{index}" for index in range(8, 12)
    )


def test_fifty_step_history_keeps_semantic_trace_without_refs_ids_or_screenshots() -> None:
    steps = tuple(
            AgentTurnView(
                "selectaction",
                "activate",
                reason="unchanged",
            transition={
                "observed_change": "unchanged",
                "before_world_fingerprint": f"fingerprint-before-{index}",
                "after_world_fingerprint": f"fingerprint-after-{index}",
                "screenshot_changed": False,
                "fact_changes": tuple({"predicate": f"p{inner}", "before": "a", "after": "b"} for inner in range(6)),
            },
        )
        for index in range(50)
    )

    rendered = render_episode_history(steps, max_bytes=3_000)
    encoded = json.dumps(to_json_compatible(rendered))

    assert rendered["retained_count"] == 50
    assert len(rendered["recent_trajectory"]) == 4
    assert len(rendered["earlier_actions"]) < 46
    assert "activate" in encoded
    assert "fingerprint" not in encoded
    assert "screenshot" not in encoded
    assert not re.search(r"\b[EFNR][1-9][0-9]{0,3}\b", encoded)


def test_projected_history_removes_generation_local_entity_and_fact_refs() -> None:
    world = shared_world("observation:refs", False)
    decision = LocalToolResult(
        "context:test",
        "count_children",
        {"containers": ("E1",), "evidence_ref": "F2"},
        {"counts": {"E1": 2}, "source": "F2"},
        "provider-call:refs",
    )
    result = StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        feedback="local result used E1 and F2",
    )

    projected = project_step_result(result)
    encoded = json.dumps(to_json_compatible({
        "summary": projected.semantic_summary,
        "reason": projected.reason,
    }))

    assert not re.search(r"\b[EF][1-9][0-9]{0,2}\b", encoded)
    assert "expired-ref" not in encoded


def test_rejected_action_history_keeps_semantics_and_capability_not_ref_identity() -> None:
    world = shared_world("observation:rejected", False)
    decision = LocalToolResult(
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
    projected = project_step_result(StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        feedback="tool_rejected",
    ))
    encoded = json.dumps(to_json_compatible(render_episode_history((projected,))))

    assert projected.semantic_summary["result"]["target"] == {
        "role": "focused_context",
        "label": "REPORTS",
    }
    assert projected.semantic_summary["result"]["available_operations"] == ("press_key",)
    assert "E59" not in encoded
    assert "expired-ref" not in encoded


def test_history_sanitizer_removes_legacy_expired_ref_aliases() -> None:
    decision = LocalToolResult(
        "context:test",
        "tool_rejected",
        {"summary": "activate <expired-ref-1>"},
        {
            "failure_reason": "<expired-ref-2> is not actionable",
            "available_operations": ("press_key",),
        },
    )
    world = shared_world("observation:legacy-alias", False)

    projected = project_step_result(StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        feedback="tool_rejected",
    ))
    encoded = json.dumps(to_json_compatible(render_episode_history((projected,))))

    assert "expired-ref" not in encoded
    assert "activate" in encoded
    assert "press_key" in encoded


def test_irreducible_history_overflow_yields_with_typed_reason() -> None:
    world = shared_world("observation:capacity", False)
    state = RunState(world, _evaluation(world.observation_id), 10)

    state.remember_step(AgentTurnView("abort", "abort", reason="x" * 240), max_bytes=32)

    assert state.status is RunStatus.YIELDED
    assert state.yield_reason is EpisodeYieldReason.CONTEXT_CAPACITY
    assert state.recent_steps == ()


def test_working_fact_is_runtime_value_and_local_tool_has_zero_gui_execution() -> None:
    world = shared_world("observation:pin", False)
    record = WorldEvidenceIndex.from_observation(world).records[0]
    fact = WorkingFact("saved_enabled", record, 0, "reuse later")
    decision = LocalToolResult(
        "context:test",
        "pin_fact",
        {"key": "saved_enabled", "evidence_ref": "F1", "purpose": "reuse later"},
        {"status": "pinned", "key": "saved_enabled"},
        "provider-call:pin",
        working_fact=fact,
    )
    state = RunState(world, _evaluation(world.observation_id), 3)

    state.apply(StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        feedback="local_tool_result",
    ))

    assert state.working_facts == (fact,)
    assert state.execution_count == 0
    state.remember_working_fact(fact)
    assert state.working_facts == (fact,)


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


def test_working_fact_collection_has_a_serialized_byte_budget() -> None:
    world = shared_world("observation:working-capacity", False)
    record = WorldEvidenceIndex.from_observation(world).records[0]
    large = type(record)(
        record.evidence_ref,
        record.observation_id,
        record.kind,
        record.source_id,
        record.source_observation_id,
        record.source_modality,
        record.source_assurance,
        record.subject_id,
        record.predicate,
        "x" * 2_000,
    )
    facts = tuple(WorkingFact(f"value_{index}", large, index, "later") for index in range(3))

    with pytest.raises(ValueError, match="serialized byte budget"):
        RunState(world, _evaluation(world.observation_id), 5, working_facts=facts)
