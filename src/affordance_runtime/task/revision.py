"""Bounded task-revision compiler contract; never a second execution loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import TaskBoundary

REVISION_CONVERSATION_MAX_TURNS = 6
REVISION_CONVERSATION_MAX_TEXT_BYTES = 16 * 1024


@dataclass(frozen=True)
class RevisionConversationTurn:
    """One Shell-owned language turn; it carries no Runtime authority."""

    turn_id: str
    role: Literal["user", "assistant"]
    text: str

    def __post_init__(self) -> None:
        if not self.turn_id.strip() or len(self.turn_id) > 128:
            raise ValueError("revision conversation turn identity is invalid")
        if self.role not in {"user", "assistant"}:
            raise ValueError("revision conversation turn role is invalid")
        if not self.text.strip() or len(self.text) > 8_000:
            raise ValueError("revision conversation turn text is invalid")


@dataclass(frozen=True)
class RevisionConversationContext:
    """Bounded immutable language context ending at the command's latest turn."""

    turns: tuple[RevisionConversationTurn, ...]
    latest_turn_id: str

    def __post_init__(self) -> None:
        turns = tuple(self.turns)
        object.__setattr__(self, "turns", turns)
        if not 1 <= len(turns) <= REVISION_CONVERSATION_MAX_TURNS:
            raise ValueError("revision conversation must contain 1..6 turns")
        if len({turn.turn_id for turn in turns}) != len(turns):
            raise ValueError("revision conversation turn identities must be unique")
        latest = tuple(turn for turn in turns if turn.turn_id == self.latest_turn_id)
        if len(latest) != 1 or turns[-1] is not latest[0] or latest[0].role != "user":
            raise ValueError("revision conversation must end at one identified user turn")
        if sum(len(turn.text.encode("utf-8")) for turn in turns) > REVISION_CONVERSATION_MAX_TEXT_BYTES:
            raise ValueError("revision conversation exceeds its total text-byte bound")

    @property
    def latest_turn(self) -> RevisionConversationTurn:
        return self.turns[-1]


@dataclass(frozen=True)
class TaskRevisionRuntimeContext:
    """Runtime-owned interruption facts available to language interpretation."""

    pending_question_id: str = ""
    pending_question: str = ""
    pending_question_fields: tuple[str, ...] = ()
    pending_confirmation_id: str = ""
    pending_confirmation_summary: str = ""
    pending_confirmation_risk: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "pending_question_fields", tuple(self.pending_question_fields))
        question_values = (self.pending_question_id, self.pending_question)
        confirmation_values = (
            self.pending_confirmation_id,
            self.pending_confirmation_summary,
            self.pending_confirmation_risk,
        )
        if any(question_values) != all(question_values):
            raise ValueError("pending question Runtime context is incomplete")
        if self.pending_question_fields and not self.pending_question_id:
            raise ValueError("pending question fields require a pending question")
        if any(confirmation_values) != all(confirmation_values):
            raise ValueError("pending confirmation Runtime context is incomplete")
        if self.pending_question and self.pending_confirmation_id:
            raise ValueError("revision Runtime context cannot contain two pending interruptions")
        if len(self.pending_question_fields) > 32 or any(
            not field.strip() or len(field) > 120 for field in self.pending_question_fields
        ):
            raise ValueError("pending question fields exceed their bound")
        if any(
            len(value) > limit
            for value, limit in (
                (self.pending_question_id, 256),
                (self.pending_question, 2_000),
                (self.pending_confirmation_id, 256),
                (self.pending_confirmation_summary, 2_000),
                (self.pending_confirmation_risk, 128),
            )
        ):
            raise ValueError("revision Runtime context exceeds a field bound")


@dataclass(frozen=True)
class TaskRevisionRequest:
    current_task: TaskGoal
    conversation: RevisionConversationContext
    runtime_context: TaskRevisionRuntimeContext = TaskRevisionRuntimeContext()

    def __post_init__(self) -> None:
        if not isinstance(self.current_task, TaskGoal):
            raise TypeError("task revision requires the current TaskGoal")
        if not isinstance(self.conversation, RevisionConversationContext):
            raise TypeError("task revision requires bounded conversation context")
        if not isinstance(self.runtime_context, TaskRevisionRuntimeContext):
            raise TypeError("task revision requires typed Runtime context")

    @property
    def text(self) -> str:
        """Compatibility accessor for the single latest turn, never a second copy."""

        return self.conversation.latest_turn.text


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
        conversation: RevisionConversationContext,
        runtime_context: TaskRevisionRuntimeContext = TaskRevisionRuntimeContext(),
    ) -> TaskRevisionCompilerOutcome:
        try:
            outcome = await compiler.compile(TaskRevisionRequest(current_task, conversation, runtime_context))
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
    "REVISION_CONVERSATION_MAX_TEXT_BYTES",
    "REVISION_CONVERSATION_MAX_TURNS",
    "RevisionConversationContext",
    "RevisionConversationTurn",
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
    "TaskRevisionRuntimeContext",
    "UnavailableTaskRevisionCompiler",
    "revision_outcome_code",
]
