"""Coordinator-facing progress phase seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits
from affordance_runtime.task_plan_progress_flow import (
    commit_current_state_completion,
    commit_post_observation_progress,
)
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class ProgressPhaseResult:
    parent: TraceNode
    completion_committed: bool = False


class ProgressPhase:
    """Application seam for progress commits during SAR-9 extraction.

    This phase delegates to the existing progress-flow writers. It does not
    create a new progress authority; it removes low-level progress-flow calls
    from Coordinator and TaskPlanPhase so later SAR-9 work can pure-ify the
    phase boundary.
    """

    def commit_post_observation(
        self,
        task_spec: TaskSpec | None,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        budget: TaskPlanBudgetLimits,
        trace: TraceDag,
        parent: TraceNode,
    ) -> ProgressPhaseResult:
        progress_commit = commit_post_observation_progress(
            task_spec,
            state,
            snapshot,
            budget,
            trace,
            parent,
        )
        return ProgressPhaseResult(
            parent=progress_commit.parent,
            completion_committed=progress_commit.legacy_completion_committed,
        )

    def commit_current_state(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        budget: TaskPlanBudgetLimits,
        trace: TraceDag,
        parent: TraceNode,
    ) -> ProgressPhaseResult:
        current_state_parent = commit_current_state_completion(
            task_spec,
            state,
            snapshot,
            budget,
            trace,
            parent,
        )
        if current_state_parent is None:
            return ProgressPhaseResult(parent=parent)
        return ProgressPhaseResult(
            parent=current_state_parent,
            completion_committed=True,
        )
