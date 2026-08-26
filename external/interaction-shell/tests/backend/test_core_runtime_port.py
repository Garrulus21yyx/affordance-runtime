from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from typing import Any, cast

import pytest
from interaction_shell.contracts import (
    Capability,
    OptionalCommand,
    ResumeTask,
    ReviseTask,
    RunStatus,
    StartTask,
    ViewerState,
)
from interaction_shell.core_runtime_port import CoreRuntimeSessionPort
from interaction_shell.manager import RunSessionManager

from affordance_runtime.app.public_session import (
    PUBLIC_SESSION_CAPABILITIES,
    PublicCompletion,
    PublicControlOutcome,
    PublicPendingQuestion,
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionSnapshot,
    PublicSessionCapability,
    PublicSessionStatus,
)


class FakePublicHandle:
    def __init__(self, session_id: str, expires_at: datetime) -> None:
        self.current = PublicRuntimeSessionSnapshot(
            session_id,
            expires_at,
            PublicSessionStatus.IDLE,
            "fake-public-event-epoch",
            0,
            PUBLIC_SESSION_CAPABILITIES - {PublicSessionCapability.RESUME_TASK},
        )
        self.recorded: list[PublicRuntimeSessionEvent] = []
        self.release = asyncio.Event()
        self.cleanup_count = 0
        self.revise_calls: list[tuple[str, str | None, str]] = []

    async def snapshot(self):
        return self.current

    async def events(self, after: int):
        return tuple(event for event in self.recorded if event.cursor > after)

    async def start(self, instruction: str):
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.RUNNING,
                task_id=self.current.session_id,
                task_revision=1,
                task_text=instruction,
            ),
            "RUN_STARTED",
        )
        asyncio.create_task(self._finish_interrupt())
        return self.current

    async def _finish_interrupt(self):
        await self.release.wait()
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.WAITING_USER,
                pending_question=PublicPendingQuestion("ask:choice", "Which option?"),
            ),
            "RUN_FINISHED",
        )

    async def answer(self, interrupt_id: str, answer: str):
        raise AssertionError((interrupt_id, answer))

    async def confirm(self, interrupt_id: str, *, approved: bool):
        raise AssertionError((interrupt_id, approved))

    async def cancel(self, command_id: str):
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.CANCELLED,
                pending_question=None,
                completion=PublicCompletion(
                    "cancelled", "user_cancelled", "Cancelled at a safe boundary."
                ),
            ),
            "RUN_FINISHED",
        )
        return self.current

    async def pause(self, command_id: str):
        checkpoint_id = "runtime-checkpoint:" + "a" * 64
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.PAUSED,
                checkpoint_id=checkpoint_id,
                resume_eligible=True,
                capabilities=self.current.capabilities
                | {PublicSessionCapability.RESUME_TASK},
                last_control_outcome=PublicControlOutcome(
                    command_id,
                    "pause",
                    "paused",
                    "pause_checkpoint_committed",
                    checkpoint_id,
                ),
            ),
            "RUN_PAUSED",
        )
        return self.current

    async def resume(self, command_id: str, checkpoint_id: str):
        assert checkpoint_id == self.current.checkpoint_id
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.WAITING_USER,
                resume_eligible=False,
                capabilities=self.current.capabilities
                - {PublicSessionCapability.RESUME_TASK},
                pending_question=PublicPendingQuestion("ask:choice", "Which option?"),
            ),
            "RUN_RESUMED",
        )
        return self.current

    async def revise(
        self,
        command_id: str,
        expected_checkpoint_id: str | None,
        text: str,
    ):
        self.revise_calls.append((command_id, expected_checkpoint_id, text))
        if (
            self.current.last_control_outcome is not None
            and self.current.last_control_outcome.command_id == command_id
        ):
            return self.current
        checkpoint_id = "runtime-checkpoint:" + "b" * 64
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.PAUSED,
                task_revision=self.current.task_revision + 1,
                task_text=text,
                checkpoint_id=checkpoint_id,
                resume_eligible=True,
                capabilities=self.current.capabilities
                | {PublicSessionCapability.RESUME_TASK},
                pending_question=None,
                pending_confirmation=None,
                last_control_outcome=PublicControlOutcome(
                    command_id,
                    "revise",
                    "revised",
                    "revised",
                    checkpoint_id,
                ),
            ),
            "TASK_REVISED",
        )
        return self.current

    async def close(self):
        self.cleanup_count += 1

    def _emit(self, snapshot: PublicRuntimeSessionSnapshot, event_type: str) -> None:
        cursor = len(self.recorded) + 1
        self.current = replace(snapshot, event_cursor=cursor)
        self.recorded.append(
            PublicRuntimeSessionEvent(
                self.current.session_id,
                self.current.event_epoch,
                cursor,
                event_type,
                self.current,
            )
        )


class FakePublicFactory:
    handle: FakePublicHandle | None = None

    async def open(self, session_id: str, expires_at: datetime):
        self.handle = FakePublicHandle(session_id, expires_at)
        return self.handle

    async def recover(self, session_id: str, checkpoint_id: str, expires_at: datetime):
        self.handle = FakePublicHandle(session_id, expires_at)
        self.handle.current = replace(
            self.handle.current,
            status=PublicSessionStatus.PAUSED,
            checkpoint_id=checkpoint_id,
            resume_eligible=True,
            capabilities=self.handle.current.capabilities
            | {PublicSessionCapability.RESUME_TASK},
        )
        return self.handle


@pytest.mark.asyncio
async def test_core_adapter_drains_background_owner_events_in_cursor_order() -> None:
    factory = FakePublicFactory()
    port = CoreRuntimeSessionPort(
        cast(Any, factory),
        lambda _handle: ViewerState(
            status="available",
            provider="steel",
            protected_path="/viewer/protected-session",
        ),
    )
    manager = RunSessionManager(port)
    created = await manager.create()
    session_id = created.snapshot.session_id

    admitted = await manager.admit(
        session_id,
        created.session_key,
        StartTask(
            command_id="start",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="Choose an option",
        ),
    )
    assert admitted.kind == "accepted"
    assert admitted.snapshot.run_status is RunStatus.RUNNING
    assert admitted.snapshot.viewer.protected_path == "/viewer/protected-session"
    assert factory.handle is not None
    factory.handle.release.set()
    await asyncio.sleep(0)

    events, concurrent_events = await asyncio.gather(
        manager.events(session_id, created.session_key, 0),
        manager.events(session_id, created.session_key, 0),
    )
    snapshot = await manager.snapshot(session_id, created.session_key)
    assert tuple(event.cursor for event in events) == (1, 2)
    assert all(event.event_epoch == snapshot.event_epoch for event in events)
    assert concurrent_events == events
    assert tuple(event.type for event in events) == ("RUN_STARTED", "RUN_FINISHED")
    assert snapshot.run_status is RunStatus.WAITING_USER
    assert snapshot.pending_question is not None
    assert snapshot.pending_question.request_id == "ask:choice"
    assert events[-1].data["snapshot"]["run_status"] == "waiting_user"
    assert snapshot.event_cursor == events[-1].cursor

    factory.handle._emit(
        replace(
            factory.handle.current,
            status=PublicSessionStatus.DONE,
            pending_question=None,
            completion=PublicCompletion("success", "owner_complete", "Completed."),
        ),
        "RUN_FINISHED",
    )
    terminal_events = await manager.events(session_id, created.session_key, 2)
    assert tuple(event.cursor for event in terminal_events) == (3,)
    assert factory.handle.cleanup_count == 1
    await manager.snapshot(session_id, created.session_key)
    assert factory.handle.cleanup_count == 1


@pytest.mark.asyncio
async def test_core_adapter_advertises_cancel_and_projects_distinct_terminal_status() -> None:
    factory = FakePublicFactory()
    manager = RunSessionManager(CoreRuntimeSessionPort(cast(Any, factory)))
    created = await manager.create()
    session_id = created.snapshot.session_id
    assert Capability.CANCEL_TASK in created.snapshot.capabilities
    started = await manager.admit(
        session_id,
        created.session_key,
        StartTask(
            command_id="start:cancel",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="Choose an option",
        ),
    )

    cancelled = await manager.admit(
        session_id,
        created.session_key,
        OptionalCommand(
            kind="cancel_task",
            command_id="cancel:1",
            expected_task_revision=1,
            expected_run_status=started.snapshot.run_status,
        ),
    )

    assert cancelled.kind == "accepted"
    assert cancelled.snapshot.run_status is RunStatus.CANCELLED
    assert cancelled.snapshot.completion is not None
    assert cancelled.snapshot.completion.outcome == "cancelled"
    assert factory.handle is not None
    assert factory.handle.cleanup_count == 1


@pytest.mark.asyncio
async def test_core_adapter_projects_durable_pause_without_terminal_cleanup() -> None:
    factory = FakePublicFactory()
    manager = RunSessionManager(CoreRuntimeSessionPort(cast(Any, factory)))
    created = await manager.create()
    session_id = created.snapshot.session_id
    assert Capability.PAUSE_TASK in created.snapshot.capabilities
    started = await manager.admit(
        session_id,
        created.session_key,
        StartTask(
            command_id="start:pause",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="Choose an option",
        ),
    )

    paused = await manager.admit(
        session_id,
        created.session_key,
        OptionalCommand(
            kind="pause_task",
            command_id="pause:1",
            expected_task_revision=1,
            expected_run_status=started.snapshot.run_status,
        ),
    )

    assert paused.kind == "accepted"
    assert paused.snapshot.run_status is RunStatus.PAUSED
    assert paused.snapshot.checkpoint_id == "runtime-checkpoint:" + "a" * 64
    assert paused.snapshot.resume_eligible is True
    assert paused.snapshot.last_control_outcome is not None
    assert paused.snapshot.last_control_outcome.outcome == "paused"
    assert factory.handle is not None
    assert factory.handle.cleanup_count == 0

    resumed = await manager.admit(
        session_id,
        created.session_key,
        ResumeTask(
            command_id="resume:1",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
            checkpoint_id=paused.snapshot.checkpoint_id,
        ),
    )

    assert resumed.kind == "accepted"
    assert resumed.snapshot.run_status is RunStatus.WAITING_USER
    assert resumed.snapshot.resume_eligible is False
    assert Capability.RESUME_TASK not in resumed.snapshot.capabilities


@pytest.mark.asyncio
async def test_shell_calls_dedicated_revision_port_once_and_keeps_paused() -> None:
    factory = FakePublicFactory()
    manager = RunSessionManager(CoreRuntimeSessionPort(cast(Any, factory)))
    created = await manager.create()
    started = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        StartTask(
            command_id="start:revise",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="Inspect the account",
        ),
    )
    assert Capability.REVISE_TASK in started.snapshot.capabilities

    revised = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:1",
            expected_task_revision=1,
            expected_run_status=RunStatus.RUNNING,
            expected_checkpoint_id=None,
            text="Inspect the account and its owner",
        ),
    )

    assert revised.kind == "accepted"
    assert revised.snapshot.run_status is RunStatus.PAUSED
    assert revised.snapshot.task_revision == 2
    assert revised.snapshot.last_control_outcome is not None
    assert revised.snapshot.last_control_outcome.kind == "revise"
    assert factory.handle is not None
    assert factory.handle.revise_calls == [
        ("revise:1", None, "Inspect the account and its owner")
    ]

    duplicate = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:1",
            expected_task_revision=1,
            expected_run_status=RunStatus.RUNNING,
            expected_checkpoint_id=None,
            text="Inspect the account and its owner",
        ),
    )

    assert duplicate.kind == "accepted"
    assert duplicate.snapshot.task_revision == 2
    assert factory.handle.revise_calls == [
        ("revise:1", None, "Inspect the account and its owner"),
        ("revise:1", None, "Inspect the account and its owner"),
    ]
