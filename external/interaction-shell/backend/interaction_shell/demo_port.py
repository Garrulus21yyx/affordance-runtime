"""Contract demo for local UI/E2E only. It is not a GUI agent or Runtime adapter."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime

from .contracts import (
    Accepted,
    AnswerQuestion,
    ApproveAction,
    Capability,
    Completion,
    PendingConfirmation,
    PendingQuestion,
    PublicStep,
    RejectAction,
    RunStatus,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
    StartTask,
    UsageSummary,
)


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
    capabilities = frozenset(
        {
            Capability.START_TASK,
            Capability.ANSWER_QUESTION,
            Capability.APPROVE_ACTION,
            Capability.REJECT_ACTION,
            Capability.CLOSE_SESSION,
        }
    )

    async def open(self, session_id: str, expires_at: datetime) -> DemoHandle:
        event_epoch = secrets.token_urlsafe(18)
        return DemoHandle(
            session_id,
            expires_at,
            event_epoch,
            RuntimeSessionSnapshot(
                session_id=session_id,
                expires_at=expires_at,
                event_epoch=event_epoch,
                capabilities=self.capabilities,
            ),
        )

    async def snapshot(self, handle: DemoHandle) -> RuntimeSessionSnapshot:
        return handle.snapshot

    async def events(self, handle: DemoHandle, after: int) -> tuple[ShellEvent, ...]:
        return tuple(event for event in handle.events if event.cursor > after)

    async def command(self, handle: DemoHandle, command: ShellCommand):
        old = handle.snapshot
        cursor = old.event_cursor
        events: list[ShellEvent] = []
        if isinstance(command, StartTask):
            snapshot = old.model_copy(
                update={
                    "task_id": "demo-task",
                    "task_revision": 1,
                    "task_text": command.task,
                    "run_status": RunStatus.WAITING_USER,
                    "pending_question": PendingQuestion(
                        request_id="demo-question", prompt="Which option should the task use?"
                    ),
                    "public_steps": (PublicStep(step=1, stage="intake", status="finished", label="Task admitted"),),
                    "usage": UsageSummary(prompt_tokens=328, runtime_latency_ms=42),
                }
            )
            event_types = ("RUN_STARTED", "STEP_FINISHED", "user_input.required")
        elif isinstance(command, AnswerQuestion):
            snapshot = old.model_copy(
                update={
                    "task_revision": old.task_revision + 1,
                    "run_status": RunStatus.WAITING_CONFIRMATION,
                    "pending_question": None,
                    "pending_confirmation": PendingConfirmation(
                        request_id="demo-confirmation",
                        summary="Submit the selected option",
                        risk="external_effect",
                    ),
                    "public_steps": old.public_steps
                    + (PublicStep(step=2, stage="policy", status="finished", label="Option selected"),),
                }
            )
            event_types = ("task.revised", "confirmation.required")
        elif isinstance(command, ApproveAction):
            snapshot = old.model_copy(
                update={
                    "run_status": RunStatus.DONE,
                    "pending_confirmation": None,
                    "completion": Completion(
                        outcome="success",
                        code="demo_owner_completion",
                        message="Contract demo completed.",
                        evidence_refs=("demo:completion",),
                    ),
                    "public_steps": old.public_steps
                    + (PublicStep(step=3, stage="evaluation", status="finished", label="Owner completion"),),
                }
            )
            event_types = ("STEP_FINISHED", "RUN_FINISHED")
        elif isinstance(command, RejectAction):
            snapshot = old.model_copy(
                update={
                    "run_status": RunStatus.BLOCKED,
                    "pending_confirmation": None,
                    "completion": Completion(
                        outcome="blocked", code="user_rejected", message="Action rejected by user."
                    ),
                }
            )
            event_types = ("RUN_FINISHED",)
        else:
            raise TypeError("demo port received unsupported command")
        for event_type in event_types:
            cursor += 1
            event_snapshot = snapshot.model_copy(update={"event_cursor": cursor})
            event = ShellEvent(
                session_id=handle.session_id,
                event_epoch=handle.event_epoch,
                cursor=cursor,
                type=event_type,
                data={"snapshot": event_snapshot.model_dump(mode="json")},
            )
            events.append(event)
            handle.events.append(event)
        handle.snapshot = snapshot.model_copy(update={"event_cursor": cursor})
        return Accepted(command_id=command.command_id, snapshot=handle.snapshot), tuple(events)

    async def close(self, handle: DemoHandle) -> None:
        if handle.closed:
            return
        handle.cleanup_count += 1
        handle.closed = True
