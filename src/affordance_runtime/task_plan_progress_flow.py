"""Coordinator-facing current-state TaskPlan progress preparation and commit."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.obligation_progress_shadow_flow import (
    prepare_obligation_progress_shadow_trace,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits, TaskPlanLifecycle
from affordance_runtime.task_plan_progress import (
    CurrentStateSubgoalCompletionEvaluator,
    SubgoalCompletionPreparation,
    TaskPlanProgressStateView,
    current_state_evidence_refs,
)
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class CurrentStateSubgoalCompletionCommit:
    preparation: SubgoalCompletionPreparation
    evidence_refs: tuple[str, ...]
    completed_subgoal_ids: tuple[str, ...]
    task_plan_completed: bool

    @property
    def subgoal_id(self) -> str:
        return self.preparation.subgoal_id

    def completion_payload(self, state_phase: str) -> dict[str, object]:
        return {
            "state": state_phase,
            "plan_id": self.preparation.plan_id,
            "plan_version": self.preparation.plan_version,
            "subgoal_id": self.preparation.subgoal_id,
            "evidence": list(self.evidence_refs),
            "criterion_ids": list(self.preparation.criterion_ids),
            "requirement_ids": list(self.preparation.requirement_ids),
            "current_state_evidence": [
                asdict(item) for item in self.preparation.evidence
            ],
        }

    def plan_completed_payload(self, state_phase: str) -> dict[str, object]:
        return {
            "state": state_phase,
            "task_plan_id": self.preparation.plan_id,
            "completed_subgoal_ids": list(self.completed_subgoal_ids),
        }


@dataclass(frozen=True)
class PostObservationProgressCommit:
    parent: TraceNode
    legacy_completion_committed: bool


def prepare_current_state_subgoal_completion(
    task_spec: TaskSpec | None,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    budget: TaskPlanBudgetLimits,
    *,
    evaluator: CurrentStateSubgoalCompletionEvaluator | None = None,
) -> CurrentStateSubgoalCompletionCommit | None:
    if task_spec is None or state.task_plan is None or state.plan_progress is None:
        return None
    active_subgoal_id = state.plan_progress.active_subgoal_id
    if not active_subgoal_id:
        ready = state.plan_progress.ready_subgoal_ids(state.task_plan)
        active_subgoal_id = ready[0] if ready else ""
    if not active_subgoal_id:
        return None
    context = TaskPlanLifecycle.build_context(
        task_spec,
        state,
        snapshot,
        budget,
        reason="current_state_progress",
    )
    progress = TaskPlanProgressStateView(
        plan_id=state.task_plan.plan_id,
        plan_version=state.task_plan.plan_version,
        plan_based_on_state_version=state.task_plan.based_on_state_version,
        evaluated_at_state_version=state.version,
        active_subgoal_id=active_subgoal_id,
        completed_subgoal_ids=tuple(state.plan_progress.completed_subgoal_ids),
        failed_subgoal_ids=tuple(state.plan_progress.failed_subgoal_ids),
    )
    preparation = (evaluator or CurrentStateSubgoalCompletionEvaluator()).evaluate(
        plan=state.task_plan,
        progress=progress,
        environment=context.environment,
        evaluated_at_state_version=state.version,
        snapshot_id=state.current_snapshot_id,
        page_revision=state.current_page_revision(),
        environment_revision=state.current_revision(),
    )
    if preparation is None or not _still_current(preparation, state):
        return None
    completed_ids = tuple(
        dict.fromkeys(
            (
                *state.plan_progress.completed_subgoal_ids,
                preparation.subgoal_id,
            )
        )
    )
    completed = set(completed_ids)
    return CurrentStateSubgoalCompletionCommit(
        preparation=preparation,
        evidence_refs=current_state_evidence_refs(preparation.evidence),
        completed_subgoal_ids=completed_ids,
        task_plan_completed=all(
            item.subgoal_id in completed for item in state.task_plan.subgoals
        ),
    )


def commit_current_state_completion(
    task_spec: TaskSpec | None,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    budget: TaskPlanBudgetLimits,
    trace: TraceDag,
    parent: TraceNode,
) -> TraceNode | None:
    completion = prepare_current_state_subgoal_completion(
        task_spec,
        state,
        snapshot,
        budget,
    )
    if completion is None:
        return None
    state.complete_subgoal(completion.subgoal_id, completion.evidence_refs)
    parent = trace.add(
        "SubgoalCompletedFromCurrentObservation",
        completion.completion_payload(state.phase),
        parents=[parent.id],
    )
    if completion.task_plan_completed:
        parent = trace.add(
            "TaskPlanCompleted",
            completion.plan_completed_payload(state.phase),
            parents=[parent.id],
        )
    return parent


def commit_post_observation_progress(
    task_spec: TaskSpec | None,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    budget: TaskPlanBudgetLimits,
    trace: TraceDag,
    parent: TraceNode,
) -> PostObservationProgressCommit:
    current_state_parent = commit_current_state_completion(
        task_spec,
        state,
        snapshot,
        budget,
        trace,
        parent,
    )
    legacy_completion_committed = current_state_parent is not None
    parent = current_state_parent or parent
    try:
        projection = prepare_obligation_progress_shadow_trace(
            task_spec,
            state,
            snapshot,
        )
    except Exception as exc:
        parent = trace.add(
            "ObligationProgressShadowFailed",
            {
                "state": state.phase,
                "error_type": type(exc).__name__,
                "reason": str(exc)[:500],
                "task_id": state.task_id,
                "state_version": state.version,
                "snapshot_id": snapshot.observation.snapshot_id,
                "page_revision": snapshot.observation.page_revision,
                "environment_revision": snapshot.observation.environment_revision,
            },
            parents=[parent.id],
        )
        return PostObservationProgressCommit(
            parent=parent,
            legacy_completion_committed=legacy_completion_committed,
        )
    if projection is None:
        return PostObservationProgressCommit(
            parent=parent,
            legacy_completion_committed=legacy_completion_committed,
        )
    payload = {"state": state.phase, **projection.to_trace_payload()}
    parent = trace.add(
        "ObligationProgressShadowCompared",
        payload,
        parents=[parent.id],
    )
    return PostObservationProgressCommit(
        parent=parent,
        legacy_completion_committed=legacy_completion_committed,
    )


def _still_current(
    preparation: SubgoalCompletionPreparation,
    state: StateKernel,
) -> bool:
    return (
        state.task_plan is not None
        and preparation.plan_id == state.task_plan.plan_id
        and preparation.plan_version == state.task_plan.plan_version
        and preparation.evaluated_at_state_version == state.version
    )
