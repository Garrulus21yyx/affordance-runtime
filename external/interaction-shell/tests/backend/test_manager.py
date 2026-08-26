from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from interaction_shell.contracts import (
    AnswerQuestion,
    ApproveAction,
    CloseSession,
    OptionalCommand,
    RunStatus,
    StartTask,
)
from interaction_shell.demo_port import ContractDemoPort
from interaction_shell.manager import RunSessionManager


@pytest.mark.asyncio
async def test_command_idempotency_stale_conflict_and_unsupported_capability():
    manager = RunSessionManager(ContractDemoPort())
    created = await manager.create()
    snapshot = created.snapshot
    start = StartTask(
        command_id="start-1",
        expected_task_revision=0,
        expected_run_status=RunStatus.IDLE,
        task="Choose an option",
    )
    accepted = await manager.admit(snapshot.session_id, created.session_key, start)
    assert accepted.kind == "accepted"
    duplicate = await manager.admit(snapshot.session_id, created.session_key, start)
    assert duplicate.kind == "conflict" and duplicate.code == "duplicate_command"
    stale = await manager.admit(
        snapshot.session_id,
        created.session_key,
        ApproveAction(
            command_id="approve-stale",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            request_id="wrong",
        ),
    )
    assert stale.kind == "conflict" and stale.code == "stale_command"
    current = await manager.snapshot(snapshot.session_id, created.session_key)
    unsupported = await manager.admit(
        snapshot.session_id,
        created.session_key,
        OptionalCommand(
            command_id="takeover-1",
            kind="take_over",
            expected_task_revision=current.task_revision,
            expected_run_status=current.run_status,
        ),
    )
    assert unsupported.kind == "unsupported"


@pytest.mark.asyncio
async def test_snapshot_event_consistency_and_reconnect_cursor():
    manager = RunSessionManager(ContractDemoPort())
    created = await manager.create()
    session_id = created.snapshot.session_id
    await manager.admit(
        session_id,
        created.session_key,
        StartTask(
            command_id="start",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="Ask first",
        ),
    )
    snapshot = await manager.snapshot(session_id, created.session_key)
    events = await manager.events(session_id, created.session_key, 0)
    managed = manager.authenticate(session_id, created.session_key)
    assert not hasattr(managed, "events")
    assert events == tuple(managed.runtime_handle.events)
    assert tuple(event.cursor for event in events) == tuple(range(1, len(events) + 1))
    assert all(event.event_epoch == snapshot.event_epoch for event in events)
    assert snapshot.event_cursor == events[-1].cursor
    assert await manager.events(session_id, created.session_key, events[-2].cursor) == (events[-1],)
    assert events[-1].data["snapshot"]["run_status"] == snapshot.run_status.value


@pytest.mark.asyncio
async def test_external_cleanup_exactly_once_on_close_and_expiry():
    port = ContractDemoPort()
    manager = RunSessionManager(port)
    created = await manager.create(ttl_seconds=60)
    session = manager.authenticate(created.snapshot.session_id, created.session_key)
    close = CloseSession(
        command_id="close",
        expected_task_revision=0,
        expected_run_status=RunStatus.IDLE,
    )
    assert (await manager.admit(session.session_id, session.session_key, close)).kind == "accepted"
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await manager.expire()
    assert session.runtime_handle.cleanup_count == 1


@pytest.mark.asyncio
async def test_session_create_snapshot_failure_cleans_opaque_handle_once():
    class SnapshotFailurePort(ContractDemoPort):
        handle = None

        async def open(self, session_id, expires_at):
            self.handle = await super().open(session_id, expires_at)
            return self.handle

        async def snapshot(self, handle):
            raise RuntimeError("snapshot unavailable after open")

    port = SnapshotFailurePort()
    manager = RunSessionManager(port)
    with pytest.raises(RuntimeError, match="snapshot unavailable"):
        await manager.create()
    assert port.handle is not None
    assert port.handle.cleanup_count == 1
    assert port.handle.closed is True
    assert manager._sessions == {}


@pytest.mark.asyncio
async def test_terminal_owner_snapshot_triggers_external_cleanup_once():
    port = ContractDemoPort()
    manager = RunSessionManager(port)
    created = await manager.create()
    session_id, key = created.snapshot.session_id, created.session_key
    await manager.admit(
        session_id,
        key,
        StartTask(
            command_id="s",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="task",
        ),
    )
    await manager.admit(
        session_id,
        key,
        AnswerQuestion(
            command_id="a",
            expected_task_revision=1,
            expected_run_status=RunStatus.WAITING_USER,
            request_id="demo-question",
            answer="second",
        ),
    )
    finished = await manager.admit(
        session_id,
        key,
        ApproveAction(
            command_id="c",
            expected_task_revision=2,
            expected_run_status=RunStatus.WAITING_CONFIRMATION,
            request_id="demo-confirmation",
        ),
    )
    session = manager.authenticate(session_id, key)
    assert finished.snapshot.run_status is RunStatus.DONE
    assert session.runtime_handle.cleanup_count == 1
    await manager.expire()
    assert session.runtime_handle.cleanup_count == 1
