"""Coordinator-facing current-state TaskPlan progress preparation and commit."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits, TaskPlanLifecycle
from affordance_runtime.task_plan_progress import (
    CurrentStateStepCompletionEvaluator,
    StepCompletionPreparation,
    TaskPlanProgressStateView,
    current_state_evidence_refs,
)
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import CriterionEvaluation, CriterionStatus


@dataclass(frozen=True)
class CurrentStateStepCompletionCommit:
    preparation: StepCompletionPreparation
    evidence_refs: tuple[str, ...]
    completed_step_ids: tuple[str, ...]
    task_plan_completed: bool

    @property
    def step_id(self) -> str:
        return self.preparation.step_id

    def completion_payload(self, state_phase: str) -> dict[str, object]:
        return {
            "state": state_phase,
            "plan_id": self.preparation.plan_id,
            "plan_version": self.preparation.plan_version,
            "step_id": self.preparation.step_id,
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
            "completed_step_ids": list(self.completed_step_ids),
        }


@dataclass(frozen=True)
class VerifiedTaskProgressCommit:
    parent: TraceNode
    step_completion_committed: bool
    task_plan_completed: bool
    task_completion_requested: bool


@dataclass(frozen=True)
class TaskSkillTerminalProgressCommit:
    parent: TraceNode
    task_completion_requested: bool
    task_skill_id: str = ""
    task_skill_version: str = ""
    completed_step_ids: tuple[str, ...] = ()

    def result_payload(self) -> dict[str, object]:
        return {
            "task_skill_id": self.task_skill_id,
            "task_skill_version": self.task_skill_version,
            "completed_step_ids": list(self.completed_step_ids),
        }


def prepare_current_state_step_completion(
    task_spec: TaskSpec | None,
    state: StateKernel,
    snapshot: UnifiedObservation,
    budget: TaskPlanBudgetLimits,
    *,
    evaluator: CurrentStateStepCompletionEvaluator | None = None,
) -> CurrentStateStepCompletionCommit | None:
    if task_spec is None or state.task_plan is None or state.task_progress is None:
        return None
    active_step_id = state.task_progress.active_step_id
    if not active_step_id:
        ready = state.task_progress.ready_step_ids(state.task_plan)
        active_step_id = ready[0] if ready else ""
    if not active_step_id:
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
        active_step_id=active_step_id,
        completed_step_ids=tuple(state.task_progress.completed_step_ids),
        failed_step_ids=tuple(state.task_progress.failed_step_ids),
    )
    preparation = (evaluator or CurrentStateStepCompletionEvaluator()).evaluate(
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
                *state.task_progress.completed_step_ids,
                preparation.step_id,
            )
        )
    )
    completed = set(completed_ids)
    return CurrentStateStepCompletionCommit(
        preparation=preparation,
        evidence_refs=current_state_evidence_refs(preparation.evidence),
        completed_step_ids=completed_ids,
        task_plan_completed=all(
            item.step_id in completed for item in state.task_plan.steps
        ),
    )


def commit_current_state_completion(
    task_spec: TaskSpec | None,
    state: StateKernel,
    snapshot: UnifiedObservation,
    budget: TaskPlanBudgetLimits,
    trace: TraceDag,
    parent: TraceNode,
) -> TraceNode | None:
    completion = prepare_current_state_step_completion(
        task_spec,
        state,
        snapshot,
        budget,
    )
    if completion is None:
        return None
    state.complete_step(
        completion.step_id,
        completion.evidence_refs,
        completion.preparation.criterion_ids,
    )
    parent = trace.add(
        "StepCompletedFromCurrentObservation",
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


def commit_verified_task_progress(
    *,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    step_completion: CriterionEvaluation | None,
    task_planner_is_router: bool,
    skill_complete: bool,
    skill_progress: TaskSkillRunState | None = None,
) -> VerifiedTaskProgressCommit:
    if state.task_plan is None or state.task_progress is None:
        return VerifiedTaskProgressCommit(parent, False, False, False)
    step = TaskPlanLifecycle.active_step_spec(state)
    if (
        step_completion is not None
        and step_completion.status == CriterionStatus.SATISFIED
        and step is not None
    ):
        state.complete_step(
            step.step_id,
            step_completion.evidence_refs,
            tuple(item.criterion_id for item in step.completion_criteria),
        )
        parent = trace.add(
            "StepCompleted",
            {
                "state": state.phase,
                "plan_id": state.task_plan.plan_id,
                "step_id": step.step_id,
                "evidence": list(step_completion.evidence_refs),
                "criterion_ids": [item.criterion_id for item in step.completion_criteria],
            },
            parents=[parent.id],
        )
        if not TaskPlanLifecycle.completed(state):
            return VerifiedTaskProgressCommit(parent, True, False, False)
        parent = trace.add(
            "TaskPlanCompleted",
            {
                "state": state.phase,
                "task_plan_id": state.task_plan.plan_id,
                "completed_step_ids": list(state.task_progress.completed_step_ids),
            },
            parents=[parent.id],
        )
        if not (
            len(state.task_plan.steps) > 1
            or not task_planner_is_router
            or skill_complete
        ):
            return VerifiedTaskProgressCommit(parent, True, True, False)
        if skill_complete and skill_progress is not None:
            state.final_result = {
                "task_skill_id": skill_progress.skill_id,
                "task_skill_version": skill_progress.version,
                "completed_step_ids": list(skill_progress.completed_step_ids),
            }
            parent = trace.add(
                "TaskSkillCompleted",
                {"state": state.phase, **state.final_result},
                parents=[parent.id],
            )
        else:
            state.final_result = {
                "task_plan_id": state.task_plan.plan_id,
                "completed_step_ids": list(state.task_progress.completed_step_ids),
            }
        return VerifiedTaskProgressCommit(parent, True, True, True)
    if step_completion is not None and step is not None:
        parent = trace.add(
            "StepEvidenceRejected",
            {
                "state": state.phase,
                "plan_id": state.task_plan.plan_id,
                "step_id": step.step_id,
                "status": step_completion.status.value,
                "reason_code": step_completion.reason_code,
            },
            parents=[parent.id],
        )
    return VerifiedTaskProgressCommit(parent, False, False, False)


def commit_task_skill_terminal_progress(
    *,
    state: StateKernel,
    progress: TaskSkillRunState | None,
    trace: TraceDag,
    parent: TraceNode,
) -> TaskSkillTerminalProgressCommit:
    """Record verified TaskSkill completion without committing Runtime done."""

    if state.task_plan is not None or progress is None:
        return TaskSkillTerminalProgressCommit(parent, False)
    completed_step_ids = tuple(progress.completed_step_ids)
    parent = trace.add(
        "TaskSkillCompleted",
        {
            "state": state.phase,
            "task_skill_id": progress.skill_id,
            "task_skill_version": progress.version,
            "completed_step_ids": list(completed_step_ids),
        },
        parents=[parent.id],
    )
    return TaskSkillTerminalProgressCommit(
        parent=parent,
        task_completion_requested=False,
        task_skill_id=progress.skill_id,
        task_skill_version=progress.version,
        completed_step_ids=completed_step_ids,
    )


def _still_current(
    preparation: StepCompletionPreparation,
    state: StateKernel,
) -> bool:
    return (
        state.task_plan is not None
        and preparation.plan_id == state.task_plan.plan_id
        and preparation.plan_version == state.task_plan.plan_version
        and preparation.evaluated_at_state_version == state.version
    )
