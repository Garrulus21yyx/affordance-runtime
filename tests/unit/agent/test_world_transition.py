from __future__ import annotations

import pytest

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.context.world_region_index import RegionVersion, WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicChangeKind,
    WorldTransitionProjector,
)
from affordance_runtime.agent.decisions import ReadRegionResult
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.profile import AgentLoopProfile
from affordance_runtime.agent.run_state import RunStatus, StepResult
from affordance_runtime.agent.workspace import (
    ActivityFamily,
    ActivitySummary,
    AgentWorkspace,
    CurrentFinding,
    SemanticEvent,
    SemanticEventKind,
)
from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world import CoverageState, SemanticTarget, StateFact
from tests.support.world import fused_world


def _world(observation_id: str, values: dict[str, int]):
    targets = tuple(
        SemanticTarget(target_id, "status", target_id, {"value": value}) for target_id, value in sorted(values.items())
    )
    facts = tuple(
        StateFact(
            f"fact:{observation_id}:{target_id}",
            target_id,
            "value",
            value,
            observation_id,
        )
        for target_id, value in sorted(values.items())
    )
    return fused_world(observation_id, targets, facts, surface="dom")


def test_public_world_delta_is_complete_and_binds_exact_lineage() -> None:
    before = _world("source:before", {"kept": 1, "removed": 2})
    after = _world("source:after", {"kept": 3, "added": 4})

    delta = WorldTransitionProjector().project(before, after)

    assert delta.before_observation_id == before.observation_id
    assert delta.after_observation_id == after.observation_id
    assert delta.changed
    assert {(item.target_id, item.kind) for item in delta.target_changes} == {
        ("added", PublicChangeKind.ADDED),
        ("kept", PublicChangeKind.MODIFIED),
        ("removed", PublicChangeKind.REMOVED),
    }
    assert {(item.subject_id, item.kind) for item in delta.fact_changes} == {
        ("added", PublicChangeKind.ADDED),
        ("kept", PublicChangeKind.MODIFIED),
        ("removed", PublicChangeKind.REMOVED),
    }
    kept = next(item for item in delta.fact_changes if item.subject_id == "kept")
    assert kept.before is not None and kept.before.value == 1
    assert kept.after is not None and kept.after.value == 3
    assert kept.before_region_key == kept.after_region_key
    assert set(delta.changed_region_keys)


@pytest.mark.parametrize(
    ("before_values", "after_values", "expected_changes"),
    (
        ({}, {}, 0),
        ({}, {"a": 1}, 2),
        ({"a": 1}, {}, 2),
        ({"a": 1}, {"a": 1}, 0),
        ({"a": 1}, {"a": 2}, 2),
        ({"a": 1, "b": 2}, {"a": 1, "c": 3}, 4),
    ),
)
def test_public_world_delta_covers_supported_target_and_fact_changes(
    before_values: dict[str, int],
    after_values: dict[str, int],
    expected_changes: int,
) -> None:
    delta = WorldTransitionProjector().project(
        _world("source:before", before_values),
        _world("source:after", after_values),
    )

    assert len(delta.target_changes) + len(delta.fact_changes) == expected_changes
    assert delta.changed is bool(expected_changes)


def test_delivery_index_consumes_only_a_delta_ending_at_its_world() -> None:
    before = _world("source:before", {"a": 1})
    after = _world("source:after", {"a": 2})
    delta = WorldTransitionProjector().project(before, after)

    index = WorldDeliveryIndex.from_observation(after, public_world_delta=delta)

    assert index.public_world_delta is delta
    with pytest.raises(ValueError, match="terminate"):
        WorldDeliveryIndex.from_observation(before, public_world_delta=delta)


def test_region_versions_reuse_unchanged_cache_and_advance_changed_content() -> None:
    first_world = _world("source:first", {"a": 1, "b": 2})
    unchanged_world = _world("source:unchanged", {"a": 1, "b": 2})
    changed_world = _world("source:changed", {"a": 3, "b": 2})
    first = WorldDeliveryIndex.from_observation(first_world)
    unchanged = WorldDeliveryIndex.from_observation(unchanged_world, previous_index=first)
    changed = WorldDeliveryIndex.from_observation(changed_world, previous_index=unchanged)

    assert first.document_lineage == unchanged.document_lineage == changed.document_lineage
    assert len(first.region_versions) == 1
    initial = first.region_versions[0]
    reused = unchanged.version_for(initial.region_key)
    advanced = changed.version_for(initial.region_key)
    assert reused is not None and advanced is not None
    assert reused.version == initial.version
    assert reused.cached_outline is initial.cached_outline
    assert advanced.version == initial.version + 1
    assert advanced.content_digest != reused.content_digest
    assert advanced.member_target_ids == changed.regions[0].member_target_ids
    assert advanced.member_fact_ids == changed.regions[0].member_fact_ids


def test_document_route_change_invalidates_prior_region_cache() -> None:
    before = fused_world(
        "source:before",
        (SemanticTarget("viewport", "viewport", "Current page", {"page.route": "/before"}),),
        surface="dom",
    )
    after = fused_world(
        "source:after",
        (SemanticTarget("viewport", "viewport", "Current page", {"page.route": "/after"}),),
        surface="dom",
    )
    first = WorldDeliveryIndex.from_observation(before)
    navigated = WorldDeliveryIndex.from_observation(after, previous_index=first)

    assert first.document_lineage != navigated.document_lineage
    assert navigated.region_versions
    assert {item.version for item in navigated.region_versions} == {1}
    assert all(item.document_lineage == navigated.document_lineage for item in navigated.region_versions)


def test_runtime_consumers_share_one_delta_instance_or_exact_serialization() -> None:
    before = _world("source:before", {"a": 1})
    after = _world("source:after", {"a": 2})
    delta = WorldTransitionProjector().project(before, after)
    action = ActionOutcome(
        "request:test",
        before.observation_id,
        after.observation_id,
        ObservedChange.UNKNOWN,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.NONE,
        "not mechanically resolved",
        public_world_delta=delta,
    )
    decision = ReadRegionResult("context:test", "read_region", {}, {"items": ()})
    evaluation = TaskEvaluation(
        "task:test",
        after.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )
    step = StepResult(
        decision,
        before,
        after,
        evaluation,
        RunStatus.RUNNING,
        feedback="local_tool_result",
        public_world_delta=delta,
    )
    delivery = WorldDeliveryIndex.from_observation(after, public_world_delta=delta)
    turn = project_step_result(step)
    trace = RunTraceRecorder()
    trace.step_completed(1, step)

    assert action.public_world_delta is delta
    assert step.public_world_delta is delta
    assert delivery.public_world_delta is delta
    assert turn.transition == {}
    assert trace.events[-1]["result"]["public_world_delta"] == to_json_compatible(delta)
    assert trace.events[-1]["lineage"]["before_world_digest"] == delta.before_world_digest
    assert trace.events[-1]["lineage"]["after_world_digest"] == delta.after_world_digest


def test_frozen_later_stage_contracts_close_types_and_lifecycle_bounds() -> None:
    finding = CurrentFinding("fact:a", "value", "exact", "Results", CoverageState.COMPLETE)
    event = SemanticEvent(
        1,
        SemanticEventKind.PUBLIC_RESULT,
        "public result appeared",
        ({"predicate": finding.predicate, "value": finding.exact_value},),
    )
    activity = ActivitySummary(ActivityFamily.READ_REGION, "digest", 3, 0, "unchanged")
    workspace = AgentWorkspace(
        tuple(AgentTurnView(f"turn:{index}") for index in range(4)),
        (event,),
        (activity,),
    )
    version = RegionVersion(
        "region:test",
        "document:test",
        "content:digest",
        "structure:digest",
        1,
        ("Results",),
        ("a",),
        ("fact:a",),
    )
    profile = AgentLoopProfile(30, 8, 1)

    assert len(workspace.recent_steps) == 4
    assert version.version == 1
    assert profile.max_policy_decisions == 30
    with pytest.raises(ValueError, match="at most four"):
        AgentWorkspace(tuple(AgentTurnView(str(index)) for index in range(5)))
    with pytest.raises(ValueError, match="positive"):
        AgentLoopProfile(30, 8, 0)
