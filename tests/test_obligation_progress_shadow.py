from affordance_runtime.obligation_progress import (
    ObligationExecutionRole,
    ReadyObligationProjection,
    ReadyObligationView,
)
from affordance_runtime.obligation_progress_shadow import (
    ObligationProgressShadowClassification,
    ObligationProgressShadowTraceProjection,
    TaskPlanShadowProjection,
    compare_obligation_progress_shadow,
)


def _ready_view(obligation_id: str) -> ReadyObligationView:
    return ReadyObligationView(
        obligation_id=obligation_id,
        role=ObligationExecutionRole.PROGRESS_EFFECT,
        subject="field",
        relation="has_changed",
        expected_value="Alice",
        evidence_requirements=("evidence:field",),
        dependency_ids=(),
        terminal=False,
    )


def test_shadow_comparison_aligns_active_taskplan_subgoal_with_ready_obligation() -> None:
    legacy = TaskPlanShadowProjection(
        active_subgoal_id="subgoal:type-name",
        ready_subgoal_ids=("subgoal:type-name",),
        completed_subgoal_ids=(),
        subgoal_obligation_ids=(("subgoal:type-name", "obligation:type-name"),),
    )
    projection = ReadyObligationProjection(
        status="ready",
        ready_obligations=(_ready_view("obligation:type-name"),),
        pending_role_obligation_ids=(),
    )

    comparison = compare_obligation_progress_shadow(
        legacy=legacy,
        obligation_projection=projection,
        satisfied_obligation_ids=(),
    )

    assert comparison.classification == ObligationProgressShadowClassification.ALIGNED
    assert comparison.active_subgoal_obligation_id == "obligation:type-name"
    assert comparison.ready_obligation_ids == ("obligation:type-name",)
    assert comparison.to_trace_payload()["classification"] == "aligned"


def test_shadow_comparison_reports_ready_obligation_missing_from_taskplan() -> None:
    legacy = TaskPlanShadowProjection(
        active_subgoal_id="subgoal:type-name",
        ready_subgoal_ids=("subgoal:type-name",),
        completed_subgoal_ids=(),
        subgoal_obligation_ids=(("subgoal:type-name", "obligation:type-name"),),
    )
    projection = ReadyObligationProjection(
        status="ready",
        ready_obligations=(
            _ready_view("obligation:type-name"),
            _ready_view("obligation:submit"),
        ),
        pending_role_obligation_ids=(),
    )

    comparison = compare_obligation_progress_shadow(
        legacy=legacy,
        obligation_projection=projection,
        satisfied_obligation_ids=(),
    )

    assert (
        comparison.classification
        == ObligationProgressShadowClassification.OBLIGATION_READY_WITHOUT_SUBGOAL
    )
    assert comparison.divergent_obligation_ids == ("obligation:submit",)


def test_shadow_comparison_reports_active_non_progress_predicate() -> None:
    legacy = TaskPlanShadowProjection(
        active_subgoal_id="subgoal:submit-available",
        ready_subgoal_ids=("subgoal:submit-available",),
        completed_subgoal_ids=(),
        subgoal_obligation_ids=(
            ("subgoal:submit-available", "obligation:submit-available"),
        ),
    )
    projection = ReadyObligationProjection(
        status="role_pending",
        ready_obligations=(),
        pending_role_obligation_ids=("obligation:submit-available",),
        reason="blocking_availability_predicate_pending",
    )

    comparison = compare_obligation_progress_shadow(
        legacy=legacy,
        obligation_projection=projection,
        satisfied_obligation_ids=(),
    )

    assert (
        comparison.classification
        == ObligationProgressShadowClassification.LEGACY_ACTIVE_NON_PROGRESS_PREDICATE
    )
    assert comparison.pending_role_obligation_ids == ("obligation:submit-available",)
    assert comparison.reason == "blocking_availability_predicate_pending"


def test_shadow_comparison_reports_subgoal_without_obligation_mapping() -> None:
    legacy = TaskPlanShadowProjection(
        active_subgoal_id="subgoal:legacy-only",
        ready_subgoal_ids=("subgoal:legacy-only",),
        completed_subgoal_ids=(),
        subgoal_obligation_ids=(("subgoal:type-name", "obligation:type-name"),),
    )
    projection = ReadyObligationProjection(
        status="ready",
        ready_obligations=(_ready_view("obligation:type-name"),),
        pending_role_obligation_ids=(),
    )

    comparison = compare_obligation_progress_shadow(
        legacy=legacy,
        obligation_projection=projection,
        satisfied_obligation_ids=(),
    )

    assert (
        comparison.classification
        == ObligationProgressShadowClassification.SUBGOAL_WITHOUT_OBLIGATION
    )
    assert comparison.divergent_subgoal_ids == ("subgoal:legacy-only",)


def test_shadow_comparison_reports_dependency_divergence_when_active_is_not_ready() -> None:
    legacy = TaskPlanShadowProjection(
        active_subgoal_id="subgoal:submit",
        ready_subgoal_ids=("subgoal:submit",),
        completed_subgoal_ids=(),
        subgoal_obligation_ids=(
            ("subgoal:type-name", "obligation:type-name"),
            ("subgoal:submit", "obligation:submit"),
        ),
    )
    projection = ReadyObligationProjection(
        status="ready",
        ready_obligations=(_ready_view("obligation:type-name"),),
        pending_role_obligation_ids=(),
    )

    comparison = compare_obligation_progress_shadow(
        legacy=legacy,
        obligation_projection=projection,
        satisfied_obligation_ids=(),
    )

    assert (
        comparison.classification
        == ObligationProgressShadowClassification.DEPENDENCY_DIVERGENCE
    )
    assert comparison.active_subgoal_obligation_id == "obligation:submit"
    assert comparison.ready_obligation_ids == ("obligation:type-name",)


def test_shadow_projection_allows_many_strategy_steps_for_one_obligation() -> None:
    projection = TaskPlanShadowProjection(
        active_subgoal_id="subgoal:type-part-one",
        ready_subgoal_ids=("subgoal:type-part-one", "subgoal:type-part-two"),
        completed_subgoal_ids=(),
        subgoal_obligation_ids=(
            ("subgoal:type-part-one", "obligation:type-name"),
            ("subgoal:type-part-two", "obligation:type-name"),
        ),
    )

    assert projection.subgoal_obligation_ids == (
        ("subgoal:type-part-one", "obligation:type-name"),
        ("subgoal:type-part-two", "obligation:type-name"),
    )


def test_shadow_trace_projection_wraps_comparison_with_runtime_identity() -> None:
    comparison = compare_obligation_progress_shadow(
        legacy=TaskPlanShadowProjection(
            active_subgoal_id="subgoal:type-name",
            ready_subgoal_ids=("subgoal:type-name",),
            completed_subgoal_ids=(),
            subgoal_obligation_ids=(("subgoal:type-name", "obligation:type-name"),),
        ),
        obligation_projection=ReadyObligationProjection(
            status="ready",
            ready_obligations=(_ready_view("obligation:type-name"),),
            pending_role_obligation_ids=(),
        ),
        satisfied_obligation_ids=(),
    )

    trace_projection = ObligationProgressShadowTraceProjection(
        task_spec_identity="sha256:task",
        task_revision=3,
        evaluated_at_state_version=8,
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
        task_plan_id="plan-1",
        task_plan_version=2,
        obligation_progress_source="legacy_verified_projection",
        comparison=comparison,
    )

    assert trace_projection.to_trace_payload() == {
        "schema_version": "1.0",
        "task_spec_identity": "sha256:task",
        "task_revision": 3,
        "evaluated_at_state_version": 8,
        "snapshot": {
            "snapshot_id": "snapshot-1",
            "page_revision": "page-1",
            "environment_revision": "env-1",
        },
        "task_plan": {
            "plan_id": "plan-1",
            "plan_version": 2,
        },
        "obligation_progress_source": "legacy_verified_projection",
        "comparison": comparison.to_trace_payload(),
    }
