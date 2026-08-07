"""Coordinator-facing commit of already verified TaskPlan progress."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.criteria import criterion_ids
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.contracts import CriterionEvaluation, CriterionStatus


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


def commit_verified_task_progress(
    *,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    step_completion: CriterionEvaluation | None,
    task_planner_is_router: bool,
    task_spec: TaskSpec | None = None,
    skill_complete: bool,
    skill_progress: TaskSkillRunState | None = None,
) -> VerifiedTaskProgressCommit:
    if state.task_plan is None or state.task_progress is None:
        return VerifiedTaskProgressCommit(parent, False, False, False)
    step = TaskPlanLifecycle.active_step_spec(state)
    if step_completion is not None and step_completion.status == CriterionStatus.SATISFIED and step is not None:
        state.complete_step(
            step.step_id,
            step_completion.evidence_refs,
            criterion_ids(step.completion_criteria),
        )
        parent = trace.add(
            "StepCompleted",
            {
                "state": state.phase,
                "plan_id": state.task_plan.plan_id,
                "step_id": step.step_id,
                "evidence": list(step_completion.evidence_refs),
                "criterion_ids": list(criterion_ids(step.completion_criteria)),
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
        if not (len(state.task_plan.steps) > 1 or not task_planner_is_router or skill_complete):
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
