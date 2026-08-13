"""Typed identity and outcomes for one-shot user-input continuation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from affordance_runtime.agent.result import AgentResult
    from affordance_runtime.task.contracts import TaskGoal

_INPUT_REQUEST_ID = re.compile(r"user-input:[0-9a-f]{24}")
_TRANSITION_ID = re.compile(r"transition:[1-9][0-9]*(?::[0-9a-f]{20})?")


class UserInputResumeRejectionCode(StrEnum):
    ALREADY_SUBMITTED = "user_input_already_submitted"
    ENVIRONMENT_REVISION_FAILED = "environment_task_revision_failed"
    ENVIRONMENT_REVISION_UNSUPPORTED = "environment_task_revision_unsupported"
    NO_REQUEST_PENDING = "no_user_input_request_pending"
    REQUEST_ID_MISMATCH = "user_input_request_id_mismatch"
    SESSION_TASK_REVISION_STALE = "session_task_revision_stale"
    TASK_ID_MISMATCH = "user_input_task_id_mismatch"
    TASK_REVISION_NOT_CONSECUTIVE = "task_revision_not_consecutive"
    TERMINAL_SESSION = "terminal_session_is_immutable"


@dataclass(frozen=True)
class UserInputRequest:
    """Public pending question tied to one accepted AskUser root and task revision."""

    input_request_id: str
    task_id: str
    based_on_task_revision: int
    context_id: str
    source_transition_id: str
    question: str
    requested_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if _INPUT_REQUEST_ID.fullmatch(self.input_request_id) is None:
            raise ValueError("user input request identity is invalid")
        if not self.task_id.strip() or not self.context_id.strip() or not self.question.strip():
            raise ValueError("user input request requires task, context, and question")
        if type(self.based_on_task_revision) is not int or self.based_on_task_revision < 1:
            raise ValueError("user input request task revision is invalid")
        if _TRANSITION_ID.fullmatch(self.source_transition_id) is None:
            raise ValueError("user input request transition identity is invalid")
        values = tuple(self.requested_fields)
        if any(not item.strip() for item in values) or len(values) != len(set(values)):
            raise ValueError("user input requested fields must be nonblank and unique")
        object.__setattr__(self, "requested_fields", values)


@dataclass(frozen=True)
class UserInputContinuation:
    """Internal proof that one pending AskUser root received a consecutive revision."""

    input_request_id: str
    source_transition_id: str
    task_id: str
    previous_task_revision: int
    task_revision: int

    def __post_init__(self) -> None:
        if _INPUT_REQUEST_ID.fullmatch(self.input_request_id) is None:
            raise ValueError("user input continuation request identity is invalid")
        if _TRANSITION_ID.fullmatch(self.source_transition_id) is None:
            raise ValueError("user input continuation transition identity is invalid")
        if not self.task_id.strip():
            raise ValueError("user input continuation requires task identity")
        if (
            type(self.previous_task_revision) is not int
            or type(self.task_revision) is not int
            or self.previous_task_revision < 1
            or self.task_revision != self.previous_task_revision + 1
        ):
            raise ValueError("user input continuation requires one consecutive task revision")


@dataclass(frozen=True)
class UserInputResumeRejected:
    code: UserInputResumeRejectionCode
    pending_request: UserInputRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, UserInputResumeRejectionCode):
            raise TypeError("user input resume rejection code must be typed")


@dataclass(frozen=True)
class UserInputResumed:
    result: AgentResult


UserInputResumeOutcome: TypeAlias = UserInputResumed | UserInputResumeRejected


def build_user_input_request(
    *,
    task_id: str,
    task_revision: int,
    context_id: str,
    source_transition_id: str,
    question: str,
    requested_fields: tuple[str, ...],
) -> UserInputRequest:
    digest = hashlib.sha256(
        "\0".join((task_id, str(task_revision), context_id, source_transition_id)).encode()
    ).hexdigest()[:24]
    return UserInputRequest(
        f"user-input:{digest}",
        task_id,
        task_revision,
        context_id,
        source_transition_id,
        question,
        requested_fields,
    )


def user_input_revision_rejection(
    pending: UserInputRequest | None,
    *,
    submitted_request_id: str,
    current_task: TaskGoal,
    current_task_revision: int,
    proposed_task: TaskGoal,
) -> UserInputResumeRejectionCode | None:
    """Pure fail-closed validation before any environment or session mutation."""

    if pending is None:
        return UserInputResumeRejectionCode.NO_REQUEST_PENDING
    if submitted_request_id != pending.input_request_id:
        return UserInputResumeRejectionCode.REQUEST_ID_MISMATCH
    if (
        current_task.revision != current_task_revision
        or pending.task_id != current_task.task_id
        or pending.based_on_task_revision != current_task_revision
    ):
        return UserInputResumeRejectionCode.SESSION_TASK_REVISION_STALE
    if proposed_task.task_id != current_task.task_id:
        return UserInputResumeRejectionCode.TASK_ID_MISMATCH
    if proposed_task.revision != current_task_revision + 1:
        return UserInputResumeRejectionCode.TASK_REVISION_NOT_CONSECUTIVE
    return None
