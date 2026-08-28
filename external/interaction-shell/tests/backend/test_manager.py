from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from interaction_shell.contracts import (
    Conflict,
    Recovered,
    RecoveryAttemptUnavailable,
    RunStatus,
    RuntimeSessionSnapshot,
    SnapshotUpdated,
    StartTask,
    UserTurnBlock,
)
from interaction_shell.conversation import BoundedConversation
from interaction_shell.manager import RunSessionManager
from interaction_shell.port import PortRecoverableCheckpoint, PortRecoveredHandle
from interaction_shell.session_registry import SQLiteSessionRecoveryRegistry


def snapshot(session_id: str, expires_at: datetime) -> RuntimeSessionSnapshot:
    return RuntimeSessionSnapshot(
        schema_version="interaction-shell.v4",
        session_id=session_id,
        event_epoch="manager-epoch-00001",
        expires_at=expires_at,
        command_offers=(),
    )


class FakePort:
    def __init__(self) -> None:
        self.handles: dict[str, object] = {}
        self.command_calls = 0
        self.viewer_input_calls = 0
        self.viewer_input_admitted = True
        self.active_calls = 0
        self.max_active_calls = 0
        self.inspection = PortRecoverableCheckpoint("recoverable_checkpoint", "checkpoint-1")
        self.absent_result = RecoveryAttemptUnavailable(
            kind="recovery_unavailable",
            reason_code="checkpoint_not_found",
        )
        self.feed_events = ()

    async def open(self, session_id, expires_at):
        handle = {"session_id": session_id, "expires_at": expires_at}
        self.handles[session_id] = handle
        return handle

    async def snapshot(self, handle):
        if self.feed_events:
            return self.feed_events[-1].snapshot
        return snapshot(handle["session_id"], handle["expires_at"])

    async def events(self, handle, after):
        del handle
        return tuple(event for event in self.feed_events if event.cursor > after)

    async def forward_viewer_input(self, handle, control_lease_id, forward):
        del handle, control_lease_id
        self.viewer_input_calls += 1
        if not self.viewer_input_admitted:
            return False
        await forward()
        return True

    async def command(self, handle, command, *, revision_conversation=None):
        del revision_conversation
        self.command_calls += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        await asyncio.sleep(0)
        self.active_calls -= 1
        projected = await self.snapshot(handle)
        return Conflict(
            kind="conflict",
            command_id=command.command_id,
            code="stale_command",
            snapshot=projected,
        )

    async def inspect(self, session_id):
        del session_id
        return self.inspection

    async def recover_absent(self, session_id, checkpoint_id, expires_at):
        del session_id, checkpoint_id, expires_at
        return self.absent_result

    async def recover_live(self, handle, checkpoint_id):
        del handle, checkpoint_id
        return RecoveryAttemptUnavailable(kind="recovery_unavailable", reason_code="checkpoint_unavailable")

    async def close(self, handle):
        del handle


def command(command_id: str) -> StartTask:
    return StartTask(
        kind="start_task",
        command_id=command_id,
        expected_task_revision=99,
        expected_run_status=RunStatus.DONE,
        task="Task",
    )


@pytest.mark.asyncio
async def test_manager_serializes_calls_but_does_not_recompute_runtime_legality():
    port = FakePort()
    manager = RunSessionManager(port)
    created = await manager.create()
    results = await asyncio.gather(
        *(
            manager.admit(created.snapshot.session_id, created.session_key, command(f"command-{index}"))
            for index in range(4)
        )
    )
    assert port.command_calls == 4
    assert port.max_active_calls == 1
    assert {result.code for result in results} == {"stale_command"}


@pytest.mark.asyncio
async def test_manager_materializes_bounded_feed_once_across_snapshot_resync() -> None:
    port = FakePort()
    manager = RunSessionManager(port)
    created = await manager.create()
    occurred_at = datetime.now(UTC)
    event_snapshot = created.snapshot.model_copy(update={"event_cursor": 1})
    block = UserTurnBlock(
        kind="user_turn",
        block_id=f"feed:{created.snapshot.event_epoch}:1:0",
        occurred_at=occurred_at,
        content="Inspect the current page",
    )
    port.feed_events = (
        SnapshotUpdated(
            schema_version="interaction-shell.v4",
            type="snapshot.updated",
            session_id=created.snapshot.session_id,
            event_epoch=created.snapshot.event_epoch,
            cursor=1,
            emitted_at=occurred_at,
            snapshot=event_snapshot,
            feed_delta=(block,),
        ),
    )

    first = await manager.snapshot(created.snapshot.session_id, created.session_key)
    replay = await manager.snapshot(created.snapshot.session_id, created.session_key)

    assert first.feed == (block,)
    assert replay.feed == first.feed


@pytest.mark.asyncio
async def test_manager_holds_session_lock_but_delegates_viewer_input_admission_to_port():
    port = FakePort()
    manager = RunSessionManager(port)
    created = await manager.create()
    forwarded = 0

    async def forward():
        nonlocal forwarded
        forwarded += 1

    await manager.forward_viewer_input(
        created.snapshot.session_id,
        created.session_key,
        "opaque-lease",
        forward,
    )
    assert port.viewer_input_calls == 1
    assert forwarded == 1


@pytest.mark.asyncio
async def test_manager_maps_recoverable_inspection_one_to_one_without_checkpoint_read(tmp_path):
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "registry.sqlite3")
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    await registry.register("session-1", "secret", expires_at)
    result = await RunSessionManager(FakePort(), registry).lookup("session-1", "secret")
    assert result.kind == "recovery_required"
    assert result.checkpoint_id == "checkpoint-1"


@pytest.mark.asyncio
async def test_absent_recovery_installs_exactly_one_handle_only_for_recovered(tmp_path):
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "registry.sqlite3")
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    await registry.register("session-1", "secret", expires_at)
    port = FakePort()
    manager = RunSessionManager(port, registry)
    unavailable = await manager.recover("session-1", "secret", "checkpoint-1")
    assert unavailable.kind == "recovery_unavailable"
    assert "session-1" not in manager._sessions

    handle = {"session_id": "session-1", "expires_at": expires_at}
    recovered = Recovered(kind="recovered", snapshot=snapshot("session-1", expires_at))
    port.absent_result = PortRecoveredHandle(handle, recovered)
    result = await manager.recover("session-1", "secret", "checkpoint-1")
    assert result.kind == "recovered"
    assert manager.authenticate("session-1", "secret").runtime_handle is handle


@pytest.mark.asyncio
async def test_live_handle_recovery_delegates_exact_checkpoint_to_port():
    port = FakePort()
    manager = RunSessionManager(port)
    created = await manager.create()
    result = await manager.recover(created.snapshot.session_id, created.session_key, "checkpoint-exact")
    assert result.kind == "recovery_unavailable"


@pytest.mark.asyncio
async def test_registry_schema_contains_only_auth_ttl_and_conversation_not_checkpoint_truth(tmp_path):
    path = tmp_path / "registry.sqlite3"
    registry = SQLiteSessionRecoveryRegistry(path)
    await registry.register("session-1", "secret", datetime.now(UTC) + timedelta(hours=1))
    connection = sqlite3.connect(path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(shell_session_recovery)")}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        connection.close()
    assert columns == {"session_id", "salt", "verifier", "expires_at", "projection_json"}
    assert not any("checkpoint" in name or "resume" in name for name in tables | columns)


@pytest.mark.asyncio
async def test_registry_round_trips_bounded_feed_projection(tmp_path) -> None:
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "registry.sqlite3")
    await registry.register(
        "session-feed",
        "secret",
        datetime.now(UTC) + timedelta(hours=1),
    )
    occurred_at = datetime.now(UTC)
    block = UserTurnBlock(
        kind="user_turn",
        block_id="feed:event-epoch-0001:1:0",
        occurred_at=occurred_at,
        content="Inspect the current page",
    )
    conversation = BoundedConversation()
    conversation.ingest_feed(
        event_epoch="event-epoch-0001",
        event_cursor=1,
        blocks=(block,),
    )

    await registry.save_projection("session-feed", conversation.projection())
    restored = await registry.load_projection("session-feed")

    assert restored.feed == (block,)
    assert restored.source_event_cursor == 1
