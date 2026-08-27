"""Synthetic v3 contract demo for local UI/E2E only; never a Runtime implementation."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime

from .contracts import (
    Accepted,
    AnswerQuestion,
    AnswerQuestionOffer,
    ApproveAction,
    CloseSession,
    CloseSessionOffer,
    Completion,
    ConfirmActionOffer,
    RecoveryAttempt,
    RecoveryAttemptUnavailable,
    RejectAction,
    RevisionConversationContext,
    RunStatus,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
    SnapshotUpdated,
    StartTask,
    StartTaskOffer,
    Unsupported,
    PublicStep,
    SCHEMA_VERSION,
)
from .port import PortRecoveryInspectionUnsupported


@dataclass
class DemoHandle:
    session_id: str
    expires_at: datetime
    event_epoch: str
    snapshot: RuntimeSessionSnapshot
    events: list[ShellEvent] = field(default_factory=list)
    closed: bool = False
    cleanup_count: int = 0


class ContractDemoPort:
    async def open(self, session_id: str, expires_at: datetime) -> DemoHandle:
        event_epoch = secrets.token_urlsafe(18)
        return DemoHandle(
            session_id,
            expires_at,
            event_epoch,
            RuntimeSessionSnapshot(
                schema_version=SCHEMA_VERSION,
                session_id=session_id,
                expires_at=expires_at,
                event_epoch=event_epoch,
                command_offers=(
                    StartTaskOffer(kind="start_task"),
                    CloseSessionOffer(kind="close_session"),
                ),
            ),
        )

    async def inspect(self, session_id: str):
        del session_id
        return PortRecoveryInspectionUnsupported(
            "recovery_inspection_unsupported",
            "checkpoint_store_unavailable",
        )

    async def recover_absent(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> RecoveryAttempt:
        del session_id, checkpoint_id, expires_at
        return RecoveryAttemptUnavailable(
            kind="recovery_unavailable", reason_code="recovery_unsupported"
        )

    async def recover_live(self, handle: DemoHandle, checkpoint_id: str) -> RecoveryAttempt:
        del handle, checkpoint_id
        return RecoveryAttemptUnavailable(
            kind="recovery_unavailable", reason_code="checkpoint_unavailable"
        )

    async def snapshot(self, handle: DemoHandle) -> RuntimeSessionSnapshot:
        return handle.snapshot

    async def events(self, handle: DemoHandle, after: int) -> tuple[ShellEvent, ...]:
        return tuple(event for event in handle.events if event.cursor > after)

    async def forward_viewer_input(self, handle, control_lease_id, forward) -> bool:
        del handle, control_lease_id, forward
        return False

    async def command(
        self,
        handle: DemoHandle,
        command: ShellCommand,
        *,
        revision_conversation: RevisionConversationContext | None = None,
    ):
        del revision_conversation
        old = handle.snapshot
        cursor = old.event_cursor
        if isinstance(command, StartTask):
            snapshot = old.model_copy(
                update={
                    "task_id": "demo-task",
                    "task_revision": 1,
                    "task_text": command.task,
                    "run_status": RunStatus.WAITING_USER,
                    "command_offers": (
                        AnswerQuestionOffer(
                            kind="answer_question",
                            request_id="demo-question",
                            prompt="Which option should the task use?",
                        ),
                        CloseSessionOffer(kind="close_session"),
                    ),
                    "public_steps": (
                        PublicStep(
                            step=1, stage="intake", status="finished", label="Task admitted"
                        ),
                    ),
                }
            )
            event_count = 3
        elif isinstance(command, AnswerQuestion):
            snapshot = old.model_copy(
                update={
                    "task_revision": old.task_revision + 1,
                    "run_status": RunStatus.WAITING_CONFIRMATION,
                    "command_offers": (
                        ConfirmActionOffer(
                            kind="confirm_action",
                            request_id="demo-confirmation",
                            summary="Submit the selected option",
                            risk="external_effect",
                        ),
                        CloseSessionOffer(kind="close_session"),
                    ),
                    "public_steps": old.public_steps
                    + (
                        PublicStep(
                            step=2, stage="policy", status="finished", label="Option selected"
                        ),
                    ),
                }
            )
            event_count = 2
        elif isinstance(command, ApproveAction):
            snapshot = old.model_copy(
                update={
                    "run_status": RunStatus.DONE,
                    "command_offers": (CloseSessionOffer(kind="close_session"),),
                    "completion": Completion(
                        outcome="success",
                        code="demo_owner_completion",
                        message="Contract demo completed.",
                        evidence_refs=("demo:completion",),
                    ),
                    "public_steps": old.public_steps
                    + (
                        PublicStep(
                            step=3, stage="evaluation", status="finished", label="Owner completion"
                        ),
                    ),
                }
            )
            event_count = 2
        elif isinstance(command, RejectAction):
            snapshot = old.model_copy(
                update={
                    "run_status": RunStatus.BLOCKED,
                    "command_offers": (CloseSessionOffer(kind="close_session"),),
                    "completion": Completion(
                        outcome="blocked",
                        code="user_rejected",
                        message="Action rejected by user.",
                    ),
                }
            )
            event_count = 1
        elif isinstance(command, CloseSession):
            await self.close(handle)
            return Accepted(kind="accepted", command_id=command.command_id, snapshot=old)
        else:
            return Unsupported(
                kind="unsupported",
                command_id=command.command_id,
                code="command_not_supported",
                snapshot=old,
            )
        for _ in range(event_count):
            cursor += 1
            event_snapshot = snapshot.model_copy(update={"event_cursor": cursor})
            event = SnapshotUpdated(
                schema_version=SCHEMA_VERSION,
                type="snapshot.updated",
                session_id=handle.session_id,
                event_epoch=handle.event_epoch,
                cursor=cursor,
                snapshot=event_snapshot,
            )
            handle.events.append(event)
        handle.snapshot = snapshot.model_copy(update={"event_cursor": cursor})
        return Accepted(kind="accepted", command_id=command.command_id, snapshot=handle.snapshot)

    async def close(self, handle: DemoHandle) -> None:
        if handle.closed:
            return
        handle.cleanup_count += 1
        handle.closed = True
