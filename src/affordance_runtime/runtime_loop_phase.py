"""Runtime loop lifecycle seam for Coordinator phase extraction.

This module owns loop-start and phase-entry lifecycle commits that are not
domain planning, execution, verification, progress, or recovery decisions.
"""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class RuntimeLoopStartResult:
    state: StateKernel
    trace: TraceDag
    parent: TraceNode


@dataclass(frozen=True)
class RuntimeLoopTerminalResult:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None
    parent: TraceNode


class RuntimeLoopPhase:
    """Coordinator-facing owner for loop lifecycle state and trace commits."""

    def start(
        self,
        *,
        envelope: TaskEnvelope,
        upstream_trace: TraceDag | None,
        runtime_profile_digest: str,
        loaded_profile_artifact_ids: tuple[str, ...],
    ) -> RuntimeLoopStartResult:
        state = StateKernel(
            task_id=envelope.task_id,
            goal=envelope.goal,
            constraints=dict(envelope.constraints),
        )
        if upstream_trace is not None and upstream_trace.run_id != envelope.task_id:
            raise ValueError("upstream trace run_id does not match task")
        trace = upstream_trace or TraceDag(run_id=envelope.task_id)
        upstream_parent = trace.nodes[-1] if trace.nodes else None
        parent = trace.add(
            "TaskCreated",
            {
                "state": RuntimeStep.CREATED.value,
                "goal": envelope.goal,
                "constraints": envelope.constraints,
                "task_spec_identity": (
                    envelope.task_spec.identity if envelope.task_spec is not None else ""
                ),
                "runtime_profile_digest": runtime_profile_digest,
                "loaded_profile_artifact_ids": list(loaded_profile_artifact_ids),
            },
            parents=[upstream_parent.id] if upstream_parent else None,
        )
        return RuntimeLoopStartResult(state=state, trace=trace, parent=parent)

    def check_budget(
        self,
        *,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        budget_error: RuntimeErrorCode | None,
    ) -> RuntimeLoopTerminalResult | None:
        if budget_error is None:
            return None
        state.transition(RuntimeStep.FAILED.value)
        parent = trace.add(
            "TaskFailed",
            {
                "state": state.phase,
                "error_code": budget_error.value,
                "reason": "runtime budget exhausted",
            },
            parents=[parent.id],
        )
        return RuntimeLoopTerminalResult(
            status=RuntimeStep.FAILED,
            error_code=budget_error,
            parent=parent,
        )

    def enter_planning(self, *, state: StateKernel) -> None:
        state.transition(RuntimeStep.PLANNING.value)
        if state.task_plan is not None:
            state.activate_next_subgoal()

    def enter_verifying(self, *, state: StateKernel) -> None:
        state.transition(RuntimeStep.VERIFYING.value)
