"""Terminal decision helpers for Coordinator-controlled runtime stops."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from affordance_runtime.immutable import freeze_json, thaw_json_at_external_boundary
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class TaskTerminalCommit:
    parent: TraceNode


@dataclass(frozen=True)
class TaskCompletionResult:
    status: Literal["passed", "failed"]
    result: Mapping[str, object]
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", freeze_json(dict(self.result)))

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @classmethod
    def passed_with(cls, result: Mapping[str, object]) -> "TaskCompletionResult":
        return cls("passed", dict(result))

    @classmethod
    def failed(cls, reason: str) -> "TaskCompletionResult":
        return cls("failed", {}, reason)


class TaskCompletionVerifier:
    """Compatibility task-level completion verifier.

    For TaskSpec-backed tasks, completion requires an independent passed
    verification report. Legacy envelope-only tasks remain compatibility
    completions until their callers provide TaskSpec completion criteria.
    """

    def verify(
        self,
        *,
        task_spec: TaskSpec | None,
        state: StateKernel,
        verification: VerificationReport | None,
        result: Mapping[str, object],
    ) -> TaskCompletionResult:
        if task_spec is None:
            return TaskCompletionResult.passed_with(result)
        if verification is None and state.last_receipt is None and state.effectful_action_count == 0:
            return TaskCompletionResult.passed_with(result)
        if verification is None or not verification.passed:
            return TaskCompletionResult.failed(
                "task completion requires an independent passed verification"
            )
        return TaskCompletionResult.passed_with(result)


def commit_task_terminal_success(
    *,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    completion: TaskCompletionResult,
) -> TaskTerminalCommit:
    """Commit the single terminal success transition and TaskCompleted event."""

    if not completion.passed:
        raise ValueError("task completion verification did not pass")
    state.final_result = thaw_json_at_external_boundary(completion.result)
    state.transition("done")
    parent = trace.add(
        "TaskCompleted",
        {"state": state.phase, "result": state.final_result},
        parents=[parent.id],
    )
    return TaskTerminalCommit(parent)
