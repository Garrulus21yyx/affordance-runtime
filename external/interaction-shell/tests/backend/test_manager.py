from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from interaction_shell.contracts import (
    AnswerQuestion,
    ApproveAction,
    Capability,
    CloseSession,
    OptionalCommand,
    RunStatus,
    StartTask,
)
from interaction_shell.demo_port import ContractDemoPort
from interaction_shell.manager import RunSessionManager, SessionUnauthorized
from interaction_shell.session_registry import SQLiteSessionRecoveryRegistry


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
async def test_manager_shutdown_closes_all_session_handles_once():
    port = ContractDemoPort()
    manager = RunSessionManager(port)
    first = await manager.create()
    second = await manager.create()
    first_handle = manager.authenticate(first.snapshot.session_id, first.session_key).runtime_handle
    second_handle = manager.authenticate(second.snapshot.session_id, second.session_key).runtime_handle

    await manager.close_all()
    await manager.close_all()

    assert first_handle.cleanup_count == 1
    assert second_handle.cleanup_count == 1


@pytest.mark.asyncio
async def test_manager_shutdown_attempts_every_handle_when_one_cleanup_fails():
    class OneFailurePort(ContractDemoPort):
        failed_handle = None

        async def close(self, handle):
            if handle is self.failed_handle:
                raise RuntimeError("first cleanup failed")
            await super().close(handle)

    port = OneFailurePort()
    manager = RunSessionManager(port)
    first = await manager.create()
    second = await manager.create()
    port.failed_handle = manager.authenticate(first.snapshot.session_id, first.session_key).runtime_handle
    second_handle = manager.authenticate(second.snapshot.session_id, second.session_key).runtime_handle

    errors = await manager.close_all()

    assert [str(error) for error in errors] == ["first cleanup failed"]
    assert second_handle.cleanup_count == 1


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


@pytest.mark.asyncio
async def test_restart_authenticates_same_session_without_persisting_reusable_key(tmp_path):
    checkpoint_id = "runtime-checkpoint:" + "b" * 64
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3")
    first_port = ContractDemoPort()
    first_manager = RunSessionManager(first_port, registry)
    created = await first_manager.create()
    original = first_manager.authenticate(
        created.snapshot.session_id,
        created.session_key,
    )
    original.runtime_handle.snapshot = original.runtime_handle.snapshot.model_copy(
        update={
            "task_id": created.snapshot.session_id,
            "task_revision": 1,
            "task_text": "Paused task",
            "run_status": RunStatus.PAUSED,
            "checkpoint_id": checkpoint_id,
            "resume_eligible": True,
            "capabilities": frozenset({Capability.RESUME_TASK, Capability.CLOSE_SESSION}),
        }
    )
    original_epoch = original.runtime_handle.snapshot.event_epoch

    assert await first_manager.close_all() == ()
    assert original.runtime_handle.cleanup_count == 1
    with sqlite3.connect(registry.path) as connection:
        persisted = " ".join(
            str(value)
            for row in connection.execute("SELECT session_id, salt, verifier, expires_at FROM shell_session_recovery")
            for value in row
        )
    assert created.session_key not in persisted

    class RecoveringDemoPort(ContractDemoPort):
        recover_calls = []

        async def recover(self, session_id, supplied_checkpoint_id, expires_at):
            self.recover_calls.append((session_id, supplied_checkpoint_id, expires_at))
            handle = await self.open(session_id, expires_at)
            handle.snapshot = handle.snapshot.model_copy(
                update={
                    "task_id": session_id,
                    "task_revision": 1,
                    "task_text": "Paused task",
                    "run_status": RunStatus.PAUSED,
                    "checkpoint_id": supplied_checkpoint_id,
                    "resume_eligible": True,
                    "capabilities": frozenset({Capability.RESUME_TASK, Capability.CLOSE_SESSION}),
                }
            )
            return handle

    second_port = RecoveringDemoPort()
    second_manager = RunSessionManager(second_port, registry)
    with pytest.raises(SessionUnauthorized):
        await second_manager.recover(
            created.snapshot.session_id,
            "wrong-session-key",
            checkpoint_id,
        )

    recovered = await second_manager.recover(
        created.snapshot.session_id,
        created.session_key,
        checkpoint_id,
    )
    assert recovered.snapshot.session_id == created.snapshot.session_id
    assert recovered.snapshot.event_epoch != original_epoch
    assert recovered.snapshot.run_status is RunStatus.PAUSED
    assert recovered.snapshot.checkpoint_id == checkpoint_id
    assert second_port.recover_calls == [
        (
            created.snapshot.session_id,
            checkpoint_id,
            created.snapshot.expires_at,
        )
    ]

    closed = await second_manager.admit(
        created.snapshot.session_id,
        created.session_key,
        CloseSession(
            command_id="close:recovered",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
        ),
    )
    assert closed.kind == "accepted"
    assert (
        await registry.authenticate(
            created.snapshot.session_id,
            created.session_key,
        )
        is None
    )
    with pytest.raises(LookupError, match="projection is unavailable"):
        await registry.load_projection(created.snapshot.session_id)


@pytest.mark.asyncio
async def test_recovery_registry_migrates_existing_credential_rows_to_empty_projection(
    tmp_path,
) -> None:
    path = tmp_path / "shell-recovery.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE shell_session_recovery ("
            "session_id TEXT PRIMARY KEY, salt TEXT NOT NULL, verifier TEXT NOT NULL, "
            "expires_at TEXT NOT NULL)"
        )
    registry = SQLiteSessionRecoveryRegistry(path)

    await registry.register(
        "new-session",
        "new-session-key",
        datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    projection = await registry.load_projection("new-session")
    assert projection.turns == ()
    assert projection.revision_contexts == ()
    with sqlite3.connect(path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(shell_session_recovery)")
        }
    assert "projection_json" in columns


@pytest.mark.asyncio
async def test_concurrent_recovery_installs_only_one_runtime_handle(tmp_path):
    checkpoint_id = "runtime-checkpoint:" + "c" * 64
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3")
    first_manager = RunSessionManager(ContractDemoPort(), registry)
    created = await first_manager.create()
    original = first_manager.authenticate(created.snapshot.session_id, created.session_key)
    original.runtime_handle.snapshot = original.runtime_handle.snapshot.model_copy(
        update={
            "task_id": created.snapshot.session_id,
            "task_revision": 1,
            "task_text": "Paused task",
            "run_status": RunStatus.PAUSED,
            "checkpoint_id": checkpoint_id,
            "resume_eligible": True,
            "capabilities": frozenset({Capability.RESUME_TASK, Capability.CLOSE_SESSION}),
        }
    )
    assert await first_manager.close_all() == ()

    class BlockingRecoveryPort(ContractDemoPort):
        def __init__(self):
            super().__init__()
            self.recover_started = asyncio.Event()
            self.release_recovery = asyncio.Event()
            self.recover_calls = 0

        async def recover(self, session_id, supplied_checkpoint_id, expires_at):
            self.recover_calls += 1
            self.recover_started.set()
            await self.release_recovery.wait()
            handle = await self.open(session_id, expires_at)
            handle.snapshot = handle.snapshot.model_copy(
                update={
                    "task_id": session_id,
                    "task_revision": 1,
                    "task_text": "Paused task",
                    "run_status": RunStatus.PAUSED,
                    "checkpoint_id": supplied_checkpoint_id,
                    "resume_eligible": True,
                    "capabilities": frozenset(
                        {Capability.RESUME_TASK, Capability.CLOSE_SESSION}
                    ),
                }
            )
            return handle

    port = BlockingRecoveryPort()
    manager = RunSessionManager(port, registry)
    first = asyncio.create_task(
        manager.recover(created.snapshot.session_id, created.session_key, checkpoint_id)
    )
    await port.recover_started.wait()
    second = asyncio.create_task(
        manager.recover(created.snapshot.session_id, created.session_key, checkpoint_id)
    )
    await asyncio.sleep(0)
    assert port.recover_calls == 1
    port.release_recovery.set()

    first_result, second_result = await asyncio.gather(first, second)
    assert first_result == second_result
    assert port.recover_calls == 1
    await manager.close_all()
