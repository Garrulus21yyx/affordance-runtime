from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.context import observation_delivery as observation_delivery_module
from affordance_runtime.agent.context import world_transition as world_transition_module
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.observation_delivery import current_findings_digest
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
from affordance_runtime.world import SemanticTarget, StateFact
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


def _rekeyed_world(observation_id: str, prefix: str, values: dict[str, int]):
    targets = tuple(
        SemanticTarget(
            f"{prefix}:{key}",
            "status",
            f"item {key}",
            {"value": value},
        )
        for key, value in sorted(values.items())
    )
    facts = tuple(
        StateFact(
            f"fact:{observation_id}:{key}",
            f"{prefix}:{key}",
            "value",
            value,
            observation_id,
        )
        for key, value in sorted(values.items())
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


def test_current_findings_digest_orders_nested_subject_semantics_canonically() -> None:
    observation_id = "source:nested-semantics"
    world = fused_world(
        observation_id,
        (
            SemanticTarget("a", "status", "same", {"nested": {"z": 1}}),
            SemanticTarget("b", "status", "same", {"nested": {"a": 2}}),
        ),
        (
            StateFact("fact:a", "a", "value", 1, observation_id),
            StateFact("fact:b", "b", "value", 2, observation_id),
        ),
        surface="dom",
    )

    assert current_findings_digest(world) == current_findings_digest(world)


def test_current_findings_digest_builds_each_subject_semantics_once(monkeypatch) -> None:
    world = _world("source:linear-findings", {f"target:{index}": index for index in range(24)})
    original = observation_delivery_module.target_semantics
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(observation_delivery_module, "target_semantics", counted)

    assert current_findings_digest(world)
    assert calls == len(world.targets)


def test_same_world_transition_does_not_rebuild_region_indexes(monkeypatch) -> None:
    world = _world("source:same-object", {"target": 1})

    def forbidden(*_args, **_kwargs):
        raise AssertionError("an unchanged authoritative World has no region changes to resolve")

    monkeypatch.setattr(
        world_transition_module.WorldDeliveryIndex,
        "from_observation",
        forbidden,
    )

    delta = WorldTransitionProjector().project(world, world)

    assert delta.before_observation_id == delta.after_observation_id == world.observation_id
    assert delta.before_world_digest == delta.after_world_digest
    assert not delta.changed


@given(
    st.dictionaries(
        st.text(alphabet="abcde", min_size=1, max_size=4),
        st.integers(),
        min_size=1,
        max_size=12,
    )
)
def test_public_identity_churn_is_not_a_semantic_world_change(values: dict[str, int]) -> None:
    delta = WorldTransitionProjector().project(
        _rekeyed_world("source:before-rekey", "before", values),
        _rekeyed_world("source:after-rekey", "after", values),
    )

    assert delta.changed
    assert delta.target_changes
    assert delta.fact_changes
    assert delta.before_world_digest == delta.after_world_digest
    assert not delta.semantic_changed


def test_fresh_world_transition_reuses_supplied_region_indexes(monkeypatch) -> None:
    before = _world("source:indexed-before", {"target": 1})
    after = _world("source:indexed-after", {"target": 2})
    before_index = WorldDeliveryIndex.from_observation(before)
    after_index = WorldDeliveryIndex.from_observation(after)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("transition projection cannot rebuild supplied World indexes")

    monkeypatch.setattr(
        world_transition_module.WorldDeliveryIndex,
        "from_observation",
        forbidden,
    )

    delta = WorldTransitionProjector().project(
        before,
        after,
        before_index=before_index,
        after_index=after_index,
    )

    assert delta.changed
    assert delta.before_observation_id == before.observation_id
    assert delta.after_observation_id == after.observation_id


def test_same_world_transition_rejects_a_foreign_supplied_index() -> None:
    world = _world("source:current", {"target": 1})
    foreign = _world("source:foreign", {"target": 1})

    with pytest.raises(ValueError, match="before-World delivery index belongs to another World"):
        WorldTransitionProjector().project(
            world,
            world,
            before_index=WorldDeliveryIndex.from_observation(foreign),
        )


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


@given(
    st.dictionaries(st.text(alphabet="abcde", min_size=1, max_size=4), st.integers(), max_size=12),
    st.dictionaries(st.text(alphabet="abcde", min_size=1, max_size=4), st.integers(), max_size=12),
)
def test_public_world_delta_classifies_every_generated_supported_transition(
    before_values: dict[str, int],
    after_values: dict[str, int],
) -> None:
    projector = WorldTransitionProjector()
    delta = projector.project(
        _world("source:before", before_values),
        _world("source:after", after_values),
    )
    target_kinds = {item.target_id: item.kind for item in delta.target_changes}
    fact_kinds = {item.subject_id: item.kind for item in delta.fact_changes}
    expected = {
        key: (
            PublicChangeKind.ADDED
            if key not in before_values
            else PublicChangeKind.REMOVED
            if key not in after_values
            else PublicChangeKind.MODIFIED
        )
        for key in before_values.keys() | after_values.keys()
        if before_values.get(key) != after_values.get(key) or key not in before_values or key not in after_values
    }

    assert target_kinds == expected
    assert fact_kinds == expected
    assert delta == projector.project(
        _world("source:before", before_values),
        _world("source:after", after_values),
    )
    assert delta.changed is bool(expected)


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
    assert trace.events[-1]["result"]["public_world_delta"] == {
        "before_observation_id": delta.before_observation_id,
        "after_observation_id": delta.after_observation_id,
        "before_world_digest": delta.before_world_digest,
        "after_world_digest": delta.after_world_digest,
        "changed": delta.changed,
        "semantic_changed": delta.semantic_changed,
        "changed_target_count": len(delta.target_changes),
        "changed_fact_count": len(delta.fact_changes),
        "changed_region_keys": delta.changed_region_keys,
        "changed_region_total_count": len(delta.changed_region_keys),
        "changed_regions_truncated": False,
    }
    assert trace.events[-1]["lineage"]["before_world_digest"] == delta.before_world_digest
    assert trace.events[-1]["lineage"]["after_world_digest"] == delta.after_world_digest


def test_frozen_later_stage_contracts_close_types_and_lifecycle_bounds() -> None:
    event = SemanticEvent(
        1,
        SemanticEventKind.PUBLIC_RESULT,
        "public result appeared",
        "read_region",
        "sha256:result",
    )
    activity = ActivitySummary(ActivityFamily.READ_REGION, "digest", 3, 0, "unchanged")
    workspace = AgentWorkspace(
        tuple(AgentTurnView(f"turn:{index}") for index in range(8)),
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
    profile = AgentLoopProfile(8, 1)

    assert len(workspace.recent_steps) == 8
    assert version.version == 1
    assert profile.max_consecutive_observation_only == 8
    assert profile.max_recovery_retries == 1
    with pytest.raises(ValueError, match="at most eight"):
        AgentWorkspace(tuple(AgentTurnView(str(index)) for index in range(9)))
    with pytest.raises(ValueError, match="positive"):
        AgentLoopProfile(8, 0)
