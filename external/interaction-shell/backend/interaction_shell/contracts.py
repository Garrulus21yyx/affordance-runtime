from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

SCHEMA_VERSION = "interaction-shell.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"
    BLOCKED = "blocked"


class Capability(StrEnum):
    START_TASK = "start_task"
    ANSWER_QUESTION = "answer_question"
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    CLOSE_SESSION = "close_session"
    CANCEL_TASK = "cancel_task"
    PAUSE_TASK = "pause_task"
    REVISE_TASK = "revise_task"
    START_NEW_TASK = "start_new_task"
    TAKE_OVER = "take_over"
    RETURN_CONTROL = "return_control"


class PendingQuestion(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=2000)


class PendingConfirmation(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)
    risk: str = Field(min_length=1, max_length=128)


class Completion(StrictModel):
    outcome: Literal["success", "failure", "blocked", "cancelled"]
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(max_length=4000)
    evidence_refs: tuple[str, ...] = ()


class ViewerState(StrictModel):
    status: Literal["available", "unavailable"] = "unavailable"
    provider: Literal["steel", "browserbase"] | None = None
    protected_path: str | None = None
    reason_code: str = "viewer_not_configured"
    read_only: bool = True

    @model_validator(mode="after")
    def require_protected_same_origin_path(self):
        if self.status == "available":
            if self.provider is None or self.protected_path is None:
                raise ValueError("available viewer requires provider and protected path")
            if not self.protected_path.startswith("/viewer/") or any(
                marker in self.protected_path for marker in ("?", "#", "://")
            ):
                raise ValueError("viewer must use a secret-free same-origin protected path")
        elif self.provider is not None or self.protected_path is not None:
            raise ValueError("unavailable viewer cannot publish provider routing")
        if not self.read_only:
            raise ValueError("v0 viewer must remain read-only")
        return self


class UsageSummary(StrictModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    model_latency_ms: float = Field(default=0, ge=0)
    runtime_latency_ms: float = Field(default=0, ge=0)


class PublicStep(StrictModel):
    step: int = Field(ge=1)
    stage: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=80)
    label: str = Field(max_length=500)
    attempt: int = Field(default=1, ge=1)
    retry_count: int = Field(default=0, ge=0)
    recovery_count: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    evidence_refs: tuple[str, ...] = ()


class ControlOutcome(StrictModel):
    command_id: str = Field(min_length=1, max_length=128)
    kind: Literal["pause"]
    outcome: Literal["paused", "failed"]
    code: str = Field(min_length=1, max_length=128)
    checkpoint_id: str | None = Field(default=None, max_length=200)


class RuntimeSessionSnapshot(StrictModel):
    schema_version: Literal["interaction-shell.v1"] = SCHEMA_VERSION
    session_id: str
    task_id: str | None = None
    task_revision: int = Field(default=0, ge=0)
    task_text: str | None = Field(default=None, max_length=8000)
    run_status: RunStatus = RunStatus.IDLE
    event_epoch: str = Field(min_length=16, max_length=128)
    event_cursor: int = Field(default=0, ge=0)
    pending_question: PendingQuestion | None = None
    pending_confirmation: PendingConfirmation | None = None
    completion: Completion | None = None
    capabilities: frozenset[Capability]
    viewer: ViewerState = ViewerState()
    usage: UsageSummary = UsageSummary()
    public_steps: tuple[PublicStep, ...] = ()
    checkpoint_id: str | None = Field(default=None, max_length=200)
    resume_eligible: bool = False
    last_control_outcome: ControlOutcome | None = None
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


class ShellEvent(StrictModel):
    schema_version: Literal["interaction-shell.v1"] = SCHEMA_VERSION
    session_id: str
    event_epoch: str = Field(min_length=16, max_length=128)
    cursor: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=120)
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, object] = Field(default_factory=dict)
    durable: bool = True

    @field_validator("data")
    @classmethod
    def exclude_private_fields(cls, value: dict[str, object]) -> dict[str, object]:
        forbidden = {
            "selector",
            "coordinate",
            "backend_handle",
            "accessibility_node_id",
            "private_binding",
            "credential",
            "viewer_reusable_secret",
            "full_world",
            "hidden_reasoning",
            "benchmark_hidden_state",
        }

        def inspect(node: object) -> None:
            if isinstance(node, dict):
                overlap = {str(key).lower() for key in node} & forbidden
                if overlap:
                    raise ValueError(f"private public-event fields are forbidden: {sorted(overlap)}")
                for child in node.values():
                    inspect(child)
            elif isinstance(node, (list, tuple)):
                for child in node:
                    inspect(child)

        inspect(value)
        return value


class CommandBase(StrictModel):
    command_id: str = Field(min_length=1, max_length=128)
    expected_task_revision: int = Field(ge=0)
    expected_run_status: RunStatus


class StartTask(CommandBase):
    kind: Literal["start_task"] = "start_task"
    task: str = Field(min_length=1, max_length=8000)


class AnswerQuestion(CommandBase):
    kind: Literal["answer_question"] = "answer_question"
    request_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=4000)


class ApproveAction(CommandBase):
    kind: Literal["approve_action"] = "approve_action"
    request_id: str = Field(min_length=1, max_length=128)


class RejectAction(CommandBase):
    kind: Literal["reject_action"] = "reject_action"
    request_id: str = Field(min_length=1, max_length=128)


class CloseSession(CommandBase):
    kind: Literal["close_session"] = "close_session"


class OptionalCommand(CommandBase):
    kind: Literal[
        "cancel_task",
        "pause_task",
        "revise_task",
        "start_new_task",
        "take_over",
        "return_control",
    ]
    message: str | None = Field(default=None, max_length=8000)


ShellCommand = Annotated[
    StartTask | AnswerQuestion | ApproveAction | RejectAction | CloseSession | OptionalCommand,
    Field(discriminator="kind"),
]
SHELL_COMMAND_ADAPTER = TypeAdapter(ShellCommand)


class Accepted(StrictModel):
    kind: Literal["accepted"] = "accepted"
    command_id: str
    snapshot: RuntimeSessionSnapshot


class Conflict(StrictModel):
    kind: Literal["conflict"] = "conflict"
    command_id: str
    code: Literal[
        "duplicate_command",
        "stale_command",
        "pending_request_mismatch",
        "session_closed",
        "runtime_conflict",
    ]
    snapshot: RuntimeSessionSnapshot


class Unsupported(StrictModel):
    kind: Literal["unsupported"] = "unsupported"
    command_id: str
    capability: Capability
    reason: str
    snapshot: RuntimeSessionSnapshot


class Rejected(StrictModel):
    kind: Literal["rejected"] = "rejected"
    command_id: str
    code: str
    message: str
    snapshot: RuntimeSessionSnapshot


CommandAdmission = Annotated[Accepted | Conflict | Unsupported | Rejected, Field(discriminator="kind")]


class CreateSessionRequest(StrictModel):
    ttl_seconds: int = Field(default=1800, ge=60, le=86400)


class CreateSessionResponse(StrictModel):
    session_key: str
    snapshot: RuntimeSessionSnapshot
