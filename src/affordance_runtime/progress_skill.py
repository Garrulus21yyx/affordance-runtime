"""Task-skill progress collaborator used by the Progress façade."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast

from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.progress_evaluation import (
    ActiveStepEvaluationStatus,
    ProgressEvaluationService,
    TaskCompletionEvaluationStatus,
)
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.stage_protocol import RuntimeEventBuffer, TerminalResult
from affordance_runtime.task_plan_progress_flow import commit_task_skill_terminal_progress
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.verification.contracts import TaskCompletionEvaluation
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class TaskSkillProgressResult:
    complete: bool = False
    progress: TaskSkillRunState | None = None
    terminal: TerminalResult | None = None
    task_completion: TaskCompletionEvaluation | None = None


@dataclass(frozen=True)
class TaskSkillProgressService:
    runtime: AcceptedTaskSkillRuntime | None
    evaluation: ProgressEvaluationService

    def evaluate(
        self,
        *,
        action: Any,
        task_spec: object | None,
        state: Any,
        events: RuntimeEventBuffer,
        report: VerificationReport,
        observation: Any,
        verification_ref: ArtifactRef | None,
    ) -> TaskSkillProgressResult:
        runtime = self.runtime
        if not action.skill_step_id or runtime is None:
            return TaskSkillProgressResult()
        if not report.passed:
            reason = f"TaskSkill step verification {report.status.value}"
            runtime.fallthrough(state, reason)
            progress = _skill_progress(runtime, state)
            events.add(
                "TaskSkillStepFailed",
                {
                    "state": state.phase,
                    "skill_id": progress.skill_id if progress else "",
                    "step_id": action.skill_step_id,
                    "verification": report.status.value,
                },
            )
            self._trace_fallthrough(
                events, state, runtime, reason, action.skill_step_id
            )
            return TaskSkillProgressResult(progress=progress)

        skill_report = runtime.verify_active_step(
            state,
            step_id=action.skill_step_id,
            verification=report,
            observation=observation,
        )
        if not skill_report.passed:
            runtime.fallthrough(state, skill_report.match.reason)
            events.add(
                "TaskSkillStepEvidenceRejected",
                {
                    "state": state.phase,
                    "skill_id": skill_report.skill_id,
                    "version": skill_report.skill_version,
                    "step_id": skill_report.step_id,
                    "criteria_match": asdict(skill_report.match),
                },
            )
            self._trace_fallthrough(
                events,
                state,
                runtime,
                skill_report.match.reason,
                action.skill_step_id,
            )
            return TaskSkillProgressResult(progress=_skill_progress(runtime, state))

        complete = runtime.checkpoint_verified(
            state,
            report=skill_report,
            artifact_refs=((verification_ref.path,) if verification_ref else ()),
        )
        progress = _skill_progress(runtime, state)
        events.add(
            "TaskSkillStepCompleted",
            {
                "state": state.phase,
                "skill_id": progress.skill_id if progress else "",
                "version": progress.version if progress else "",
                "step_id": action.skill_step_id,
                "completed_step_ids": list(progress.completed_step_ids)
                if progress
                else [],
                "evidence": list(progress.evidence) if progress else [],
                "criterion_evidence_links": [
                    asdict(item) for item in skill_report.match.links
                ],
            },
        )
        if not complete or state.task_plan is not None:
            return TaskSkillProgressResult(complete=complete, progress=progress)

        if action.contract.grounding_candidate is not None:
            state.complete_grounding_recovery(
                action.contract.grounding_candidate.semantic_target_id
            )
        commit = commit_task_skill_terminal_progress(
            state=state,
            progress=progress,
            trace=cast(Any, events),
            parent=cast(Any, events.root()),
        )
        completion = self.evaluation.evaluate_task_completion(
            task_spec=task_spec,
            state=state,
            observation=observation,
            report=report,
            result=commit.result_payload(),
        )
        if completion is None:
            raise ValueError("task completion requires an admitted TaskSpec")
        self.evaluation.record_task_completion(events, state, completion)
        self.evaluation.record_post_action(
            events,
            state,
            report,
            contract_id=action.contract.id,
            active_step_status=ActiveStepEvaluationStatus.COMPLETED,
            task_completion_status=(
                TaskCompletionEvaluationStatus.COMPLETED
                if completion.completed
                else TaskCompletionEvaluationStatus.INCOMPLETE
            ),
            progress_committed=True,
            liveness_decision="terminal" if completion.completed else "replan",
        )
        return TaskSkillProgressResult(
            complete=complete,
            progress=progress,
            terminal=(
                TerminalResult("", "task_completed", RuntimeStep.DONE)
                if completion.completed
                else None
            ),
            task_completion=completion,
        )

    @staticmethod
    def _trace_fallthrough(
        events: RuntimeEventBuffer,
        state: Any,
        runtime: object,
        reason: str,
        step_id: str,
    ) -> None:
        progress = _skill_progress(runtime, state)
        events.add(
            "TaskSkillFellThrough",
            {
                "state": state.phase,
                "skill_id": progress.skill_id if progress else "",
                "version": progress.version if progress else "",
                "step_id": step_id,
                "reason": reason,
                "preserved_completed_step_ids": list(progress.completed_step_ids)
                if progress
                else [],
                "preserved_evidence": list(progress.evidence) if progress else [],
                "fallback": "system_2",
            },
        )


def _skill_progress(runtime: object | None, state: object) -> TaskSkillRunState | None:
    progress_for = getattr(runtime, "progress_for", None)
    progress = progress_for(state) if callable(progress_for) else None
    return progress if isinstance(progress, TaskSkillRunState) else None
