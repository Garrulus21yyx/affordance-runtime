"""Bounded task-revision compiler contract; never a second execution loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import TaskBoundary


@dataclass(frozen=True)
class TaskRevisionRequest:
    current_task: TaskGoal
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.current_task, TaskGoal):
            raise TypeError("task revision requires the current TaskGoal")
        if not self.text.strip() or len(self.text) > 8_000:
            raise ValueError("task revision text must be within (0, 8000]")


@dataclass(frozen=True)
class TaskRevisionProposal:
    """A complete candidate meaning boundary, without task identity or authority."""

    instruction: str
    boundary: TaskBoundary

    def __post_init__(self) -> None:
        if not self.instruction.strip() or len(self.instruction) > 16_384:
            raise ValueError("task revision proposal instruction is invalid")
        if not isinstance(self.boundary, TaskBoundary):
            raise TypeError("task revision proposal requires a typed boundary")


@dataclass(frozen=True)
class RevisionReady:
    task_revision: int
    proposal: TaskRevisionProposal


@dataclass(frozen=True)
class RevisionNeedsInput:
    task_revision: int
    question: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.question.strip() or not self.fields:
            raise ValueError("revision needs-input outcome is incomplete")
        object.__setattr__(self, "fields", tuple(self.fields))


@dataclass(frozen=True)
class RevisionNoChange:
    task_revision: int
    reason: str


@dataclass(frozen=True)
class RevisionNewTaskSuggested:
    task_revision: int
    reason: str


@dataclass(frozen=True)
class RevisionUnsupported:
    task_revision: int
    reason: str


@dataclass(frozen=True)
class RevisionFailed:
    task_revision: int
    reason: str


TaskRevisionCompilerOutcome: TypeAlias = (
    RevisionReady
    | RevisionNeedsInput
    | RevisionNoChange
    | RevisionNewTaskSuggested
    | RevisionUnsupported
    | RevisionFailed
)


class TaskRevisionCompiler(Protocol):
    async def compile(self, request: TaskRevisionRequest) -> TaskRevisionCompilerOutcome: ...


@dataclass(frozen=True)
class UnavailableTaskRevisionCompiler:
    async def compile(self, request: TaskRevisionRequest) -> TaskRevisionCompilerOutcome:
        return RevisionUnsupported(
            request.current_task.revision,
            "task_revision_compiler_not_configured",
        )


@dataclass(frozen=True)
class TaskRevisionBoundary:
    """Admit exactly one typed compiler result for the current revision."""

    async def resolve(
        self,
        compiler: TaskRevisionCompiler,
        current_task: TaskGoal,
        text: str,
    ) -> TaskRevisionCompilerOutcome:
        try:
            outcome = await compiler.compile(TaskRevisionRequest(current_task, text))
        except Exception:
            return RevisionFailed(current_task.revision, "task_revision_compiler_call_failed")
        if not isinstance(
            outcome,
            RevisionReady
            | RevisionNeedsInput
            | RevisionNoChange
            | RevisionNewTaskSuggested
            | RevisionUnsupported
            | RevisionFailed,
        ):
            return RevisionFailed(current_task.revision, "invalid_task_revision_compiler_outcome")
        if outcome.task_revision != current_task.revision:
            return RevisionFailed(current_task.revision, "task_revision_compiler_revision_mismatch")
        return outcome


def revision_outcome_code(outcome: TaskRevisionCompilerOutcome) -> str:
    return {
        RevisionReady: "revision_ready",
        RevisionNeedsInput: "revision_needs_input",
        RevisionNoChange: "revision_no_change",
        RevisionNewTaskSuggested: "revision_new_task_suggested",
        RevisionUnsupported: "revision_unsupported",
        RevisionFailed: "revision_failed",
    }[type(outcome)]


__all__ = [
    "RevisionFailed",
    "RevisionNeedsInput",
    "RevisionNewTaskSuggested",
    "RevisionNoChange",
    "RevisionReady",
    "RevisionUnsupported",
    "TaskRevisionBoundary",
    "TaskRevisionCompiler",
    "TaskRevisionCompilerOutcome",
    "TaskRevisionProposal",
    "TaskRevisionRequest",
    "UnavailableTaskRevisionCompiler",
    "revision_outcome_code",
]
