"""Coordinator-facing TaskSkill verification/progress seam for SAR-9."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_terminal import TaskCompletionVerifier, commit_task_terminal_success
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_plan_progress_flow import commit_task_skill_terminal_progress
from affordance_runtime.task_skill_phase import task_skill_progress
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class TaskSkillProgressTerminal:
    status: RuntimeStep


@dataclass(frozen=True)
class TaskSkillProgressPhaseResult:
    parent: TraceNode
    skill_complete: bool = False
    skill_progress: TaskSkillRunState | None = None
    terminal: TaskSkillProgressTerminal | None = None


class TaskSkillProgressPhase:
    """Commit TaskSkill step progress or fallthrough after verification."""

    def run(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        skill_step_id: str,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        verification: VerificationReport,
        post_snapshot: BrowserSnapshot,
        verification_ref_path: str,
    ) -> TaskSkillProgressPhaseResult:
        if not skill_step_id or task_skill_runtime is None:
            return TaskSkillProgressPhaseResult(parent=parent)
        if verification.passed:
            skill_report = task_skill_runtime.verify_active_step(
                state,
                step_id=skill_step_id,
                verification=verification,
                observation=post_snapshot.observation,
            )
            if not skill_report.passed:
                reason = skill_report.match.reason
                task_skill_runtime.fallthrough(state, reason)
                parent = trace.add(
                    "TaskSkillStepEvidenceRejected",
                    {
                        "state": state.phase,
                        "skill_id": skill_report.skill_id,
                        "version": skill_report.skill_version,
                        "step_id": skill_report.step_id,
                        "criteria_match": asdict(skill_report.match),
                    },
                    parents=[parent.id],
                )
                parent = _trace_task_skill_fallthrough(
                    trace,
                    parent,
                    state,
                    reason,
                    progress=task_skill_progress(task_skill_runtime, state),
                    step_id=skill_step_id,
                )
                return TaskSkillProgressPhaseResult(parent=parent)
            artifact_refs = (verification_ref_path,) if verification_ref_path else ()
            skill_complete = task_skill_runtime.checkpoint_verified(
                state,
                report=skill_report,
                artifact_refs=artifact_refs,
            )
            skill_progress = task_skill_progress(task_skill_runtime, state)
            parent = trace.add(
                "TaskSkillStepCompleted",
                {
                    "state": state.phase,
                    "skill_id": skill_progress.skill_id if skill_progress else "",
                    "version": skill_progress.version if skill_progress else "",
                    "step_id": skill_step_id,
                    "completed_step_ids": (
                        list(skill_progress.completed_step_ids)
                        if skill_progress is not None
                        else []
                    ),
                    "evidence": (
                        list(skill_progress.evidence) if skill_progress is not None else []
                    ),
                    "criterion_evidence_links": [
                        asdict(item) for item in skill_report.match.links
                    ],
                },
                parents=[parent.id],
            )
            if skill_complete and state.task_plan is None:
                if contract.grounding_candidate is not None:
                    state.complete_grounding_recovery(
                        contract.grounding_candidate.semantic_target_id
                    )
                skill_terminal_progress = commit_task_skill_terminal_progress(
                    state=state,
                    progress=task_skill_progress(task_skill_runtime, state),
                    trace=trace,
                    parent=parent,
                )
                parent = skill_terminal_progress.parent
                completion = TaskCompletionVerifier().verify(
                    task_spec=envelope.task_spec,
                    state=state,
                    verification=verification,
                    result=skill_terminal_progress.result_payload(),
                )
                terminal = commit_task_terminal_success(
                    state=state,
                    trace=trace,
                    parent=parent,
                    completion=completion,
                )
                return TaskSkillProgressPhaseResult(
                    parent=terminal.parent,
                    skill_complete=skill_complete,
                    skill_progress=skill_progress,
                    terminal=TaskSkillProgressTerminal(RuntimeStep.DONE),
                )
            return TaskSkillProgressPhaseResult(
                parent=parent,
                skill_complete=skill_complete,
                skill_progress=skill_progress,
            )

        reason = f"TaskSkill step verification {verification.status.value}"
        task_skill_runtime.fallthrough(state, reason)
        skill_progress = task_skill_progress(task_skill_runtime, state)
        parent = trace.add(
            "TaskSkillStepFailed",
            {
                "state": state.phase,
                "skill_id": skill_progress.skill_id if skill_progress else "",
                "version": skill_progress.version if skill_progress else "",
                "step_id": skill_step_id,
                "verification": verification.status.value,
                "preserved_completed_step_ids": (
                    list(skill_progress.completed_step_ids)
                    if skill_progress is not None
                    else []
                ),
            },
            parents=[parent.id],
        )
        parent = _trace_task_skill_fallthrough(
            trace,
            parent,
            state,
            reason,
            progress=skill_progress,
            step_id=skill_step_id,
        )
        return TaskSkillProgressPhaseResult(
            parent=parent,
            skill_progress=skill_progress,
        )


def _trace_task_skill_fallthrough(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
    reason: str,
    *,
    progress: TaskSkillRunState | None = None,
    step_id: str = "",
) -> TraceNode:
    return trace.add(
        "TaskSkillFellThrough",
        {
            "state": state.phase,
            "skill_id": progress.skill_id if progress else "",
            "version": progress.version if progress else "",
            "step_id": step_id,
            "reason": reason,
            "preserved_completed_step_ids": (
                list(progress.completed_step_ids) if progress else []
            ),
            "preserved_evidence": list(progress.evidence) if progress else [],
            "fallback": "system_2",
        },
        parents=[parent.id],
    )
