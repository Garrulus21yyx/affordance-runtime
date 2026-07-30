"""Coordinator-facing verified progress seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_terminal import TaskCompletionVerifier, commit_task_terminal_success
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_plan_progress_flow import commit_verified_task_progress
from affordance_runtime.task_planning import SubgoalVerifierPort
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class VerifiedProgressTerminal:
    status: RuntimeStep


@dataclass(frozen=True)
class VerifiedProgressPhaseResult:
    parent: TraceNode
    terminal: VerifiedProgressTerminal | None = None
    continue_observing: bool = False


class VerifiedProgressPhase:
    """Commit verifier-backed task progress after a passed verification."""

    def run(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        subgoal_verifier: SubgoalVerifierPort,
        verification: VerificationReport,
        post_snapshot: BrowserSnapshot,
        task_planner_is_router: bool,
        skill_complete: bool,
        skill_progress: TaskSkillRunState | None,
    ) -> VerifiedProgressPhaseResult:
        if contract.grounding_candidate is not None:
            state.complete_grounding_recovery(
                contract.grounding_candidate.semantic_target_id
            )
        verified_progress_commit = commit_verified_task_progress(
            state=state,
            trace=trace,
            parent=parent,
            subgoal_verifier=subgoal_verifier,
            verification=verification,
            observation=post_snapshot.observation,
            task_planner_is_router=task_planner_is_router,
            skill_complete=skill_complete,
            skill_progress=skill_progress,
        )
        parent = verified_progress_commit.parent
        if verified_progress_commit.task_completion_requested:
            completion = TaskCompletionVerifier().verify(
                task_spec=envelope.task_spec,
                state=state,
                verification=verification,
                result=state.final_result,
            )
            terminal = commit_task_terminal_success(
                state=state,
                trace=trace,
                parent=parent,
                completion=completion,
            )
            return VerifiedProgressPhaseResult(
                parent=terminal.parent,
                terminal=VerifiedProgressTerminal(RuntimeStep.DONE),
            )
        state.replan_count += 1
        state.transition(RuntimeStep.OBSERVING.value)
        return VerifiedProgressPhaseResult(parent=parent, continue_observing=True)
