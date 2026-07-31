"""Runtime-facing ODG shadow projection without runtime authority.

This migration seam reads the current legacy TaskPlan progress and canonical
TaskSpec, then prepares a diagnostic shadow trace projection. It does not
mutate ``StateKernel``, write trace events, initialize the obligation ledger,
invoke planners, or decide task completion.
"""

from __future__ import annotations

from typing import Literal

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.obligation_progress import (
    ObligationEvidenceLedgerEntry,
    ObligationProgressStateView,
    decide_obligation_execution_roles,
    project_ready_obligations,
)
from affordance_runtime.obligation_progress_shadow import (
    ObligationProgressShadowTraceProjection,
    TaskPlanShadowProjection,
    compare_obligation_progress_shadow,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec

LEGACY_VERIFIED_PROJECTION: Literal["legacy_verified_projection"] = (
    "legacy_verified_projection"
)


def prepare_obligation_progress_shadow_trace(
    task_spec: TaskSpec | None,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> ObligationProgressShadowTraceProjection | None:
    """Prepare an ODG shadow trace payload from read-only runtime state."""

    if task_spec is None or state.task_plan is None or state.task_progress is None:
        return None
    progress = project_verified_legacy_progress(task_spec, state)
    ready_projection = project_ready_obligations(
        task_spec,
        progress,
        decide_obligation_execution_roles(task_spec),
    )
    comparison = compare_obligation_progress_shadow(
        legacy=_project_legacy_task_plan(state),
        obligation_projection=ready_projection,
        satisfied_obligation_ids=progress.satisfied_obligation_ids,
    )
    return ObligationProgressShadowTraceProjection(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        page_revision=snapshot.observation.page_revision,
        environment_revision=snapshot.observation.environment_revision,
        task_plan_id=state.task_plan.plan_id,
        task_plan_version=state.task_plan.plan_version,
        obligation_progress_source=LEGACY_VERIFIED_PROJECTION,
        comparison=comparison,
    )


def project_verified_legacy_progress(
    task_spec: TaskSpec,
    state: StateKernel,
) -> ObligationProgressStateView:
    """Project verifier-backed legacy TaskPlan progress into obligation state."""

    known_obligation_ids = tuple(
        obligation.obligation_id for obligation in task_spec.obligations
    )
    if state.task_progress is None:
        return ObligationProgressStateView(
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            evaluated_at_state_version=state.version,
            known_obligation_ids=known_obligation_ids,
        )
    known = set(known_obligation_ids)
    evidence_by_obligation = tuple(
        ObligationEvidenceLedgerEntry(
            obligation_id=subgoal_id,
            evidence_refs=tuple(state.task_progress.evidence_by_subgoal[subgoal_id]),
        )
        for subgoal_id in known_obligation_ids
        if subgoal_id in state.task_progress.completed_subgoal_ids
        and subgoal_id in known
        and state.task_progress.evidence_by_subgoal.get(subgoal_id)
    )
    satisfied_ids = tuple(item.obligation_id for item in evidence_by_obligation)
    failed_ids = tuple(
        subgoal_id
        for subgoal_id in known_obligation_ids
        if subgoal_id in state.task_progress.failed_subgoal_ids and subgoal_id in known
    )
    return ObligationProgressStateView(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=state.version,
        known_obligation_ids=known_obligation_ids,
        satisfied_obligation_ids=satisfied_ids,
        failed_obligation_ids=failed_ids,
        evidence_by_obligation=evidence_by_obligation,
    )


def _project_legacy_task_plan(state: StateKernel) -> TaskPlanShadowProjection:
    assert state.task_plan is not None
    assert state.task_progress is not None
    active_subgoal_id = state.task_progress.active_subgoal_id
    if not active_subgoal_id:
        ready = state.task_progress.ready_subgoal_ids(state.task_plan)
        active_subgoal_id = ready[0] if ready else ""
    return TaskPlanShadowProjection(
        active_subgoal_id=active_subgoal_id,
        ready_subgoal_ids=state.task_progress.ready_subgoal_ids(state.task_plan),
        completed_subgoal_ids=tuple(state.task_progress.completed_subgoal_ids),
        subgoal_obligation_ids=tuple(
            (subgoal.subgoal_id, subgoal.subgoal_id)
            for subgoal in state.task_plan.subgoals
        ),
    )
