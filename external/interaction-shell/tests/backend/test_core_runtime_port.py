from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from typing import Any, cast

import pytest
from interaction_shell.contracts import RunStatus, StartTask, ViewerState
from interaction_shell.core_runtime_port import CoreRuntimeSessionPort
from interaction_shell.manager import RunSessionManager

from affordance_runtime.app.public_session import (
    PUBLIC_SESSION_CAPABILITIES,
    PublicCompletion,
    PublicPendingQuestion,
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionSnapshot,
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
            PUBLIC_SESSION_CAPABILITIES,
        )
        self.recorded: list[PublicRuntimeSessionEvent] = []
        self.release = asyncio.Event()
        self.cleanup_count = 0

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
