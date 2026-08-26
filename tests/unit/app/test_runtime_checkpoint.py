from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from affordance_runtime.app.checkpoint import (
    RuntimeCheckpointCommandOutcome,
    RuntimeCheckpointError,
    SQLiteRuntimeCheckpointStore,
)
from affordance_runtime.app.public_session import (
    PublicSessionCapability,
    PublicSessionStatus,
    RuntimeEnvironmentLease,
    TargetRuntimeSessionFactory,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from tests.unit.agent.test_target_runtime_facade import AskForAccountPolicy, _runtime, _world


async def _waiting_checkpoint_session(tmp_path, *, store=None):
    checkpoint_store = store or SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(
            ScriptedEnvironment(initial_observation=_world())
        ),
        checkpoint_store=checkpoint_store,
    )
    handle = await factory.open(
        "session:checkpoint",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        snapshot = await handle.snapshot()
        if snapshot.status is PublicSessionStatus.WAITING_USER:
            return handle, checkpoint_store
        await asyncio.sleep(0.01)
    raise AssertionError("fixture did not reach waiting boundary")


@pytest.mark.asyncio
async def test_pause_publishes_only_after_atomic_checkpoint_and_command_outcome(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    assert PublicSessionCapability.PAUSE_TASK in (await handle.snapshot()).capabilities

    paused = await handle.pause("pause:atomic")

    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.checkpoint_id is not None
    assert paused.resume_eligible is False
    assert paused.last_control_outcome is not None
    assert paused.last_control_outcome.outcome == "paused"
    assert paused.last_control_outcome.checkpoint_id == paused.checkpoint_id
    checkpoint = await store.load_latest("session:checkpoint")
    outcome = await store.command_outcome("session:checkpoint", "pause:atomic")
    assert checkpoint is not None
    assert checkpoint.checkpoint_id == paused.checkpoint_id
    assert outcome == RuntimeCheckpointCommandOutcome(
        "session:checkpoint",
        "pause:atomic",
        paused.checkpoint_id,
    )
    payload = json.loads(checkpoint.to_json())
    assert payload["run"]["status"] == "paused"
    assert payload["run"]["status_before_pause"] == "waiting_user"
    assert payload["last_step"]["pending_question"]["identity"]
    assert payload["model_history"] == {"format": "unavailable", "messages": []}
    assert "current_world" not in checkpoint.to_json()
    assert "full_world" not in checkpoint.to_json()
    assert tuple(event.type for event in await handle.events(0))[-2:] == (
        "CONTROL_REQUESTED",
        "RUN_PAUSED",
    )
    await handle.close()


@pytest.mark.asyncio
async def test_active_pause_does_not_write_before_runtime_reaches_boundary(tmp_path) -> None:
    release = asyncio.Event()
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")

    class BlockingEnvironment(ScriptedEnvironment):
        async def reset(self, task):
            await release.wait()
            return await super().reset(task)

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(
            BlockingEnvironment(initial_observation=_world())
        ),
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:active-checkpoint",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")

    requested = await handle.pause("pause:active")
    assert requested.status is PublicSessionStatus.RUNNING
    assert await store.load_latest("session:active-checkpoint") is None

    release.set()
    for _ in range(100):
        paused = await handle.snapshot()
        if paused.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"active pause did not reach its durable boundary: {paused!r}")

    checkpoint = await store.load_latest("session:active-checkpoint")
    assert checkpoint is not None
    assert checkpoint.pause_command_id == "pause:active"
    assert (await handle.snapshot()).checkpoint_id == checkpoint.checkpoint_id
    await handle.close()


@pytest.mark.asyncio
async def test_sqlite_rolls_back_checkpoint_when_command_outcome_cannot_commit(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    handle, _ = await _waiting_checkpoint_session(tmp_path, store=store)
    await store.load_latest("session:checkpoint")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_pause_outcome BEFORE INSERT ON runtime_command_outcomes "
            "BEGIN SELECT RAISE(ABORT, 'forced outcome failure'); END"
        )

    current = await handle.pause("pause:rollback")

    assert current.status is PublicSessionStatus.WAITING_USER
    assert current.checkpoint_id is None
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.outcome == "failed"
    assert current.last_control_outcome.code == "pause_persistence_failed"
    assert await store.load_latest("session:checkpoint") is None
    assert await store.command_outcome("session:checkpoint", "pause:rollback") is None
    assert tuple(event.type for event in await handle.events(0))[-2:] == (
        "CONTROL_REQUESTED",
        "CONTROL_FAILED",
    )
    await handle.close()


@pytest.mark.asyncio
async def test_failed_active_pause_refreshes_world_before_policy_continues(tmp_path) -> None:
    policy_release = asyncio.Event()
    policy_entered = asyncio.Event()

    class BlockingPolicy(AskForAccountPolicy):
        async def decide(self, context):
            if self.calls == 0:
                policy_entered.set()
                await policy_release.wait()
            return await super().decide(context)

    class FailingStore:
        async def commit_pause(self, checkpoint, outcome):
            del checkpoint, outcome
            raise RuntimeCheckpointError("checkpoint_persistence_failed")

        async def load_latest(self, session_id):
            del session_id
            return None

        async def command_outcome(self, session_id, command_id):
            del session_id, command_id
            return None

    policy = BlockingPolicy()
    environment = ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(policy),
        lambda _session_id: RuntimeEnvironmentLease(environment),
        checkpoint_store=FailingStore(),
    )
    handle = await factory.open(
        "session:persistence-recovery",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    await asyncio.wait_for(policy_entered.wait(), timeout=1)

    await handle.pause("pause:failed-active")
    policy_release.set()
    for _ in range(100):
        current = await handle.snapshot()
        if current.status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"failed pause did not continue from fresh currentness: {current!r}")

    assert current.checkpoint_id is None
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.code == "pause_persistence_failed"
    assert environment.capture_calls == 1
    assert policy.calls == 2
    assert any(
        request.reason == "fresh currentness after pause persistence failure"
        for request in environment.capture_requests
    )
    await handle.close()


@pytest.mark.asyncio
async def test_store_rejects_command_identity_conflict_without_second_checkpoint(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:one")
    checkpoint = await store.load_latest("session:checkpoint")
    assert checkpoint is not None and paused.checkpoint_id == checkpoint.checkpoint_id

    with pytest.raises(RuntimeCheckpointError, match="checkpoint_command_scope_mismatch"):
        await store.commit_pause(
            checkpoint,
            RuntimeCheckpointCommandOutcome(
                "session:checkpoint",
                "pause:other",
                checkpoint.checkpoint_id,
            ),
        )
    assert await store.command_outcome("session:checkpoint", "pause:other") is None
    await handle.close()


@pytest.mark.asyncio
async def test_cancel_from_durable_pause_is_terminal_and_not_resume_eligible(tmp_path) -> None:
    handle, _store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:before-cancel")
    assert paused.status is PublicSessionStatus.PAUSED

    cancelled = await handle.cancel("cancel:paused")

    assert cancelled.status is PublicSessionStatus.CANCELLED
    assert cancelled.resume_eligible is False
    assert cancelled.completion is not None
    assert cancelled.completion.outcome == "cancelled"
    await handle.close()
