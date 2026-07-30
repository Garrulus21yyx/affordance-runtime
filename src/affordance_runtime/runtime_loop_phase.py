"""Runtime loop lifecycle seam for Coordinator phase extraction.

This module owns loop-start and phase-entry lifecycle commits that are not
domain planning, execution, verification, progress, or recovery decisions.
"""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag


@dataclass(frozen=True)
class RuntimeLoopEvent:
    kind: str
    payload: dict[str, object]
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeLoopTransition:
    phase: RuntimeStep
    activate_next_subgoal: bool = False


@dataclass(frozen=True)
class RuntimeLoopStartResult:
    state: StateKernel
    trace: TraceDag
    event: RuntimeLoopEvent


@dataclass(frozen=True)
class RuntimeLoopTerminalResult:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None
    transition: RuntimeLoopTransition
    event: RuntimeLoopEvent


class RuntimeLoopPhase:
    """Prepare loop lifecycle transitions and events without committing them."""

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
        event = RuntimeLoopEvent(
            kind="TaskCreated",
            payload={
                "state": RuntimeStep.CREATED.value,
                "goal": envelope.goal,
                "constraints": envelope.constraints,
                "task_spec_identity": (
                    envelope.task_spec.identity if envelope.task_spec is not None else ""
                ),
                "runtime_profile_digest": runtime_profile_digest,
                "loaded_profile_artifact_ids": list(loaded_profile_artifact_ids),
            },
            parent_ids=(upstream_parent.id,) if upstream_parent else (),
        )
        return RuntimeLoopStartResult(state=state, trace=trace, event=event)

    def check_budget(
        self,
        *,
        state: StateKernel,
        budget_error: RuntimeErrorCode | None,
    ) -> RuntimeLoopTerminalResult | None:
        if budget_error is None:
            return None
        return RuntimeLoopTerminalResult(
            status=RuntimeStep.FAILED,
            error_code=budget_error,
            transition=RuntimeLoopTransition(RuntimeStep.FAILED),
            event=RuntimeLoopEvent(
                kind="TaskFailed",
                payload={
                    "state": RuntimeStep.FAILED.value,
                    "error_code": budget_error.value,
                    "reason": "runtime budget exhausted",
                },
            ),
        )

    def enter_planning(self, *, has_task_plan: bool) -> RuntimeLoopTransition:
        return RuntimeLoopTransition(
            RuntimeStep.PLANNING,
            activate_next_subgoal=has_task_plan,
        )

    def enter_verifying(self) -> RuntimeLoopTransition:
        return RuntimeLoopTransition(RuntimeStep.VERIFYING)
