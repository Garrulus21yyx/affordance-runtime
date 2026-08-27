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
    ReturnControl,
    ReviseTask,
    RunStatus,
    StartTask,
    TakeOver,
    ViewerState,
)
from interaction_shell.core_runtime_port import CoreRuntimeSessionPort
from interaction_shell.manager import RunSessionManager
from interaction_shell.port import RuntimeSessionUnavailable
from interaction_shell.session_registry import SQLiteSessionRecoveryRegistry

from affordance_runtime.app.public_session import (
    PUBLIC_SESSION_CAPABILITIES,
    PublicCompletion,
    PublicControlOutcome,
    PublicEffectReconciliation,
    PublicPendingQuestion,
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionSnapshot,
    PublicSessionCapability,
    PublicSessionConflict,
    PublicSessionControlOwner,
    PublicSessionStatus,
    PublicTaskRevisionCommand,
)


class FakePublicHandle:
    def __init__(self, session_id: str, expires_at: datetime) -> None:
        self.current = PublicRuntimeSessionSnapshot(
            session_id,
            expires_at,
            PublicSessionStatus.IDLE,
            "fake-public-event-epoch",
            0,
            PUBLIC_SESSION_CAPABILITIES
            - {
                PublicSessionCapability.RESUME_TASK,
                PublicSessionCapability.TAKE_OVER,
                PublicSessionCapability.RETURN_CONTROL,
            },
        )
        self.recorded: list[PublicRuntimeSessionEvent] = []
        self.release = asyncio.Event()
        self.cleanup_count = 0
        self.revise_calls: list[
            tuple[
                str,
                int,
                PublicSessionStatus,
                str | None,
                str,
                tuple[str, ...],
                str,
            ]
        ] = []
        self.revision_digests: dict[str, str] = {}
        self.takeover_calls: list[tuple[str, str]] = []
        self.return_control_calls: list[tuple[str, str]] = []

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
                completion=PublicCompletion("cancelled", "user_cancelled", "Cancelled at a safe boundary."),
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
                | {
                    PublicSessionCapability.RESUME_TASK,
                    PublicSessionCapability.TAKE_OVER,
                },
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

    async def take_over(self, command_id: str, checkpoint_id: str):
        assert checkpoint_id == self.current.checkpoint_id
        self.takeover_calls.append((command_id, checkpoint_id))
        lease_id = "user-control-lease:" + "u" * 32
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.PAUSED,
                resume_eligible=False,
                capabilities=frozenset(
                    {
                        PublicSessionCapability.CLOSE_SESSION,
                        PublicSessionCapability.RETURN_CONTROL,
                    }
                ),
                pending_question=None,
                pending_confirmation=None,
                control_owner=PublicSessionControlOwner.USER,
                control_lease_id=lease_id,
                last_control_outcome=PublicControlOutcome(
                    command_id,
                    "take_over",
                    "user_control_granted",
                    "user_control_granted",
                    checkpoint_id,
                ),
            ),
            "USER_CONTROL_GRANTED",
        )
        return self.current

    async def return_control(self, command_id: str, control_lease_id: str):
        assert control_lease_id == self.current.control_lease_id
        self.return_control_calls.append((command_id, control_lease_id))
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.WAITING_USER,
                checkpoint_id=None,
                capabilities=(
                    self.current.capabilities
                    | {
                        PublicSessionCapability.ANSWER_QUESTION,
                        PublicSessionCapability.PAUSE_TASK,
                        PublicSessionCapability.REVISE_TASK,
                    }
                )
                - {PublicSessionCapability.RETURN_CONTROL},
                pending_question=PublicPendingQuestion("ask:fresh", "Which fresh option?"),
                control_owner=PublicSessionControlOwner.AGENT,
                control_lease_id=None,
                last_control_outcome=PublicControlOutcome(
                    command_id,
                    "return_control",
                    "user_control_returned",
                    "user_control_currentness_refreshed",
                ),
            ),
            "USER_CONTROL_RETURNED",
        )
        return self.current

    async def resume(self, command_id: str, checkpoint_id: str):
        assert checkpoint_id == self.current.checkpoint_id
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.WAITING_USER,
                resume_eligible=False,
                capabilities=self.current.capabilities - {PublicSessionCapability.RESUME_TASK},
                pending_question=PublicPendingQuestion("ask:choice", "Which option?"),
            ),
            "RUN_RESUMED",
        )
        return self.current

    async def revise(self, command: PublicTaskRevisionCommand):
        self.revise_calls.append(
            (
                command.command_id,
                command.expected_task_revision,
                command.expected_run_status,
                command.expected_checkpoint_id,
                command.text,
                tuple(turn.text for turn in command.conversation.turns),
                command.conversation.latest_turn_id,
            )
        )
        existing_digest = self.revision_digests.get(command.command_id)
        if existing_digest is not None:
            if existing_digest != command.payload_digest:
                raise PublicSessionConflict("command_identity_reused", self.current)
            return self.current
        if (
            command.expected_task_revision != self.current.task_revision
            or command.expected_run_status is not self.current.status
        ):
            raise PublicSessionConflict("stale_command", self.current)
        if command.expected_checkpoint_id != self.current.checkpoint_id:
            raise PublicSessionConflict("checkpoint_mismatch", self.current)
        self.revision_digests[command.command_id] = command.payload_digest
        checkpoint_id = "runtime-checkpoint:" + "b" * 64
        self._emit(
            replace(
                self.current,
                status=PublicSessionStatus.PAUSED,
                task_revision=self.current.task_revision + 1,
                task_text=command.text,
                checkpoint_id=checkpoint_id,
                resume_eligible=True,
                capabilities=self.current.capabilities
                | {
                    PublicSessionCapability.RESUME_TASK,
                    PublicSessionCapability.TAKE_OVER,
                },
                pending_question=None,
                pending_confirmation=None,
                last_control_outcome=PublicControlOutcome(
                    command.command_id,
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
            | {
                PublicSessionCapability.RESUME_TASK,
                PublicSessionCapability.TAKE_OVER,
            },
        )
        return self.handle


class RestartingFakePublicHandle(FakePublicHandle):
    def __init__(self, session_id: str, expires_at: datetime, factory: Any) -> None:
        super().__init__(session_id, expires_at)
        self._factory = factory

    async def revise(self, command: PublicTaskRevisionCommand):
        was_committed = command.command_id in self.revision_digests
        result = await super().revise(command)
        if not was_committed:
            self._factory.revision_compile_count += 1
        return result


class RestartingFakePublicFactory:
    """One fake Runtime authority exposed through process-local replacement handles."""

    handle: RestartingFakePublicHandle | None = None

    def __init__(self) -> None:
        self.revision_compile_count = 0
        self.recovery_count = 0

    async def open(self, session_id: str, expires_at: datetime):
        self.handle = RestartingFakePublicHandle(session_id, expires_at, self)
        return self.handle

    async def recover(self, session_id: str, checkpoint_id: str, expires_at: datetime):
        prior = self.handle
        assert prior is not None
        assert prior.current.checkpoint_id == checkpoint_id
        recovered = RestartingFakePublicHandle(session_id, expires_at, self)
        recovered.current = replace(
            prior.current,
            expires_at=expires_at,
            event_epoch=f"recovered-event-epoch:{self.recovery_count}",
            event_cursor=0,
        )
        recovered.revision_digests = prior.revision_digests
        self.recovery_count += 1
        self.handle = recovered
        return recovered


@pytest.mark.asyncio
async def test_core_adapter_projects_effect_reconciliation_without_private_binding() -> None:
    factory = FakePublicFactory()
    port = CoreRuntimeSessionPort(cast(Any, factory))
    expires_at = datetime.now().astimezone()
    handle = await port.open("session:effect-projection", expires_at)
    assert factory.handle is not None
    factory.handle.current = replace(
        factory.handle.current,
        status=PublicSessionStatus.PAUSED,
        task_id="session:effect-projection",
        task_revision=2,
        effect_reconciliation=PublicEffectReconciliation(
            "pending",
            "effect_compensation_required",
            "effect:" + "a" * 32,
            "set_state",
            "account:second",
            "reversible",
        ),
    )

    snapshot = await port.snapshot(handle)

    assert snapshot.schema_version == "interaction-shell.v2"
    assert snapshot.effect_reconciliation is not None
    assert snapshot.effect_reconciliation.status == "pending"
    assert snapshot.effect_reconciliation.resource_ref == "account:second"
    assert "selector" not in snapshot.model_dump_json()


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
async def test_takeover_requires_viewer_and_return_projects_fresh_agent_control() -> None:
    factory = FakePublicFactory()
    port = CoreRuntimeSessionPort(
        cast(Any, factory),
        lambda _handle: ViewerState(
            status="available",
            provider="steel",
            protected_path="/viewer/takeover-session",
        ),
    )
    manager = RunSessionManager(port)
    created = await manager.create()
    started = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        StartTask(
            command_id="start:takeover",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="Inspect the account",
        ),
    )
    paused = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        OptionalCommand(
            kind="pause_task",
            command_id="pause:takeover",
            expected_task_revision=1,
            expected_run_status=started.snapshot.run_status,
        ),
    )
    assert paused.snapshot.checkpoint_id is not None
    assert Capability.TAKE_OVER in paused.snapshot.capabilities
    assert paused.snapshot.viewer.read_only is True

    controlled = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        TakeOver(
            command_id="takeover:one",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
            checkpoint_id=paused.snapshot.checkpoint_id,
        ),
    )

    assert controlled.kind == "accepted"
    assert controlled.snapshot.control_owner.value == "user"
    assert controlled.snapshot.control_lease_id is not None
    assert controlled.snapshot.viewer.read_only is False
    assert Capability.RETURN_CONTROL in controlled.snapshot.capabilities
    assert Capability.RESUME_TASK not in controlled.snapshot.capabilities
    assert Capability.REVISE_TASK not in controlled.snapshot.capabilities
    assert factory.handle is not None
    assert factory.handle.takeover_calls == [
        ("takeover:one", paused.snapshot.checkpoint_id)
    ]

    returned = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReturnControl(
            command_id="return:one",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
            control_lease_id=controlled.snapshot.control_lease_id,
        ),
    )

    assert returned.kind == "accepted"
    assert returned.snapshot.control_owner.value == "agent"
    assert returned.snapshot.control_lease_id is None
    assert returned.snapshot.viewer.read_only is True
    assert returned.snapshot.pending_question is not None
    assert returned.snapshot.pending_question.request_id == "ask:fresh"
    assert Capability.RETURN_CONTROL not in returned.snapshot.capabilities
    assert factory.handle.return_control_calls == [
        ("return:one", "user-control-lease:" + "u" * 32)
    ]


@pytest.mark.asyncio
async def test_unavailable_viewer_hides_takeover_but_not_active_return() -> None:
    factory = FakePublicFactory()
    port = CoreRuntimeSessionPort(cast(Any, factory))
    handle = await port.open("session:no-viewer", datetime.now().astimezone())
    assert factory.handle is not None
    checkpoint_id = "runtime-checkpoint:" + "c" * 64
    factory.handle.current = replace(
        factory.handle.current,
        status=PublicSessionStatus.PAUSED,
        task_id="session:no-viewer",
        task_revision=1,
        checkpoint_id=checkpoint_id,
        capabilities=frozenset(
            {
                PublicSessionCapability.CLOSE_SESSION,
                PublicSessionCapability.TAKE_OVER,
            }
        ),
    )
    paused = await port.snapshot(handle)
    assert Capability.TAKE_OVER not in paused.capabilities

    factory.handle.current = replace(
        factory.handle.current,
        capabilities=frozenset(
            {
                PublicSessionCapability.CLOSE_SESSION,
                PublicSessionCapability.RETURN_CONTROL,
            }
        ),
        control_owner=PublicSessionControlOwner.USER,
        control_lease_id="user-control-lease:" + "x" * 32,
    )
    controlled = await port.snapshot(handle)
    assert Capability.RETURN_CONTROL in controlled.capabilities
    assert controlled.viewer.status == "unavailable"
    assert controlled.viewer.read_only is True


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

    stale = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:stale",
            expected_task_revision=0,
            expected_run_status=RunStatus.RUNNING,
            expected_checkpoint_id=None,
            text="This stale command must be rejected by Runtime",
        ),
    )
    assert stale.kind == "conflict"
    assert stale.code == "stale_command"
    assert factory.handle is not None
    assert factory.handle.revise_calls == [
        (
            "revise:stale",
            0,
            PublicSessionStatus.RUNNING,
            None,
            "This stale command must be rejected by Runtime",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
            ),
            "revise:stale",
        )
    ]

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
    assert factory.handle.revise_calls == [
        (
            "revise:stale",
            0,
            PublicSessionStatus.RUNNING,
            None,
            "This stale command must be rejected by Runtime",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
            ),
            "revise:stale",
        ),
        (
            "revise:1",
            1,
            PublicSessionStatus.RUNNING,
            None,
            "Inspect the account and its owner",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
                "Inspect the account and its owner",
            ),
            "revise:1",
        ),
    ]
    reused = await manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:1",
            expected_task_revision=1,
            expected_run_status=RunStatus.RUNNING,
            expected_checkpoint_id=None,
            text="Reuse the identity for a different revision",
        ),
    )
    assert reused.kind == "conflict"
    assert reused.code == "command_identity_reused"
    assert factory.handle.revise_calls[-1] == (
        "revise:1",
        1,
        PublicSessionStatus.RUNNING,
        None,
        "Reuse the identity for a different revision",
        (
            "Inspect the account",
            "This stale command must be rejected by Runtime",
            "Reuse the identity for a different revision",
        ),
        "revise:1",
    )

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
        (
            "revise:stale",
            0,
            PublicSessionStatus.RUNNING,
            None,
            "This stale command must be rejected by Runtime",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
            ),
            "revise:stale",
        ),
        (
            "revise:1",
            1,
            PublicSessionStatus.RUNNING,
            None,
            "Inspect the account and its owner",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
                "Inspect the account and its owner",
            ),
            "revise:1",
        ),
        (
            "revise:1",
            1,
            PublicSessionStatus.RUNNING,
            None,
            "Reuse the identity for a different revision",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
                "Reuse the identity for a different revision",
            ),
            "revise:1",
        ),
        (
            "revise:1",
            1,
            PublicSessionStatus.RUNNING,
            None,
            "Inspect the account and its owner",
            (
                "Inspect the account",
                "This stale command must be rejected by Runtime",
                "Inspect the account and its owner",
            ),
            "revise:1",
        ),
    ]
    conversation = manager.authenticate(
        created.snapshot.session_id,
        created.session_key,
    ).conversation.view()
    assert tuple(turn.text for turn in conversation.turns) == (
        "Inspect the account",
        "This stale command must be rejected by Runtime",
        "Inspect the account and its owner",
    )


async def _start_and_pause_for_restart(
    manager: RunSessionManager,
    session_id: str,
    session_key: str,
):
    started = await manager.admit(
        session_id,
        session_key,
        StartTask(
            command_id="start:accounts",
            expected_task_revision=0,
            expected_run_status=RunStatus.IDLE,
            task="检查两个账号",
        ),
    )
    return await manager.admit(
        session_id,
        session_key,
        OptionalCommand(
            kind="pause_task",
            command_id="pause:accounts",
            expected_task_revision=1,
            expected_run_status=started.snapshot.run_status,
        ),
    )


@pytest.mark.asyncio
async def test_restart_restores_preexisting_turns_for_first_new_revision(tmp_path) -> None:
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3")
    factory = RestartingFakePublicFactory()
    port = CoreRuntimeSessionPort(cast(Any, factory))
    first_manager = RunSessionManager(port, registry)
    created = await first_manager.create()
    paused = await _start_and_pause_for_restart(
        first_manager,
        created.snapshot.session_id,
        created.session_key,
    )
    assert paused.snapshot.checkpoint_id is not None
    assert await first_manager.close_all() == ()

    second_manager = RunSessionManager(port, registry)
    recovered = await second_manager.recover(
        created.snapshot.session_id,
        created.session_key,
        paused.snapshot.checkpoint_id,
    )
    revised = await second_manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:second",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
            expected_checkpoint_id=recovered.snapshot.checkpoint_id,
            text="用第二个",
        ),
    )

    assert revised.kind == "accepted"
    assert factory.handle is not None
    assert factory.handle.revise_calls[-1][5] == ("检查两个账号", "用第二个")
    assert factory.revision_compile_count == 1


@pytest.mark.asyncio
async def test_restart_replays_committed_revision_with_exact_original_payload(tmp_path) -> None:
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3")
    factory = RestartingFakePublicFactory()
    port = CoreRuntimeSessionPort(cast(Any, factory))
    first_manager = RunSessionManager(port, registry)
    created = await first_manager.create()
    paused = await _start_and_pause_for_restart(
        first_manager,
        created.snapshot.session_id,
        created.session_key,
    )
    command = ReviseTask(
        command_id="revise:lost-response",
        expected_task_revision=1,
        expected_run_status=RunStatus.PAUSED,
        expected_checkpoint_id=paused.snapshot.checkpoint_id,
        text="用第二个",
    )
    committed = await first_manager.admit(
        created.snapshot.session_id,
        created.session_key,
        command,
    )
    assert committed.kind == "accepted"
    assert committed.snapshot.checkpoint_id is not None
    assert factory.revision_compile_count == 1
    assert await first_manager.close_all() == ()

    second_manager = RunSessionManager(port, registry)
    await second_manager.recover(
        created.snapshot.session_id,
        created.session_key,
        committed.snapshot.checkpoint_id,
    )
    replayed = await second_manager.admit(
        created.snapshot.session_id,
        created.session_key,
        command,
    )

    assert replayed.kind == "accepted"
    assert replayed.snapshot.task_revision == 2
    assert factory.revision_compile_count == 1
    assert factory.handle is not None
    assert factory.handle.revise_calls[-1][5] == ("检查两个账号", "用第二个")


@pytest.mark.asyncio
async def test_restart_rejects_reused_revision_identity_with_changed_payload(tmp_path) -> None:
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3")
    factory = RestartingFakePublicFactory()
    port = CoreRuntimeSessionPort(cast(Any, factory))
    first_manager = RunSessionManager(port, registry)
    created = await first_manager.create()
    paused = await _start_and_pause_for_restart(
        first_manager,
        created.snapshot.session_id,
        created.session_key,
    )
    committed = await first_manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:fixed-identity",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
            expected_checkpoint_id=paused.snapshot.checkpoint_id,
            text="用第二个",
        ),
    )
    assert committed.snapshot.checkpoint_id is not None
    assert await first_manager.close_all() == ()

    second_manager = RunSessionManager(port, registry)
    await second_manager.recover(
        created.snapshot.session_id,
        created.session_key,
        committed.snapshot.checkpoint_id,
    )
    conflict = await second_manager.admit(
        created.snapshot.session_id,
        created.session_key,
        ReviseTask(
            command_id="revise:fixed-identity",
            expected_task_revision=1,
            expected_run_status=RunStatus.PAUSED,
            expected_checkpoint_id=paused.snapshot.checkpoint_id,
            text="改用第一个",
        ),
    )

    assert conflict.kind == "conflict"
    assert conflict.code == "command_identity_reused"
    assert factory.revision_compile_count == 1
    assert factory.handle is not None
    assert factory.handle.revise_calls[-1][5] == ("检查两个账号", "改用第一个")


@pytest.mark.asyncio
async def test_revision_is_not_sent_when_projection_persistence_fails(tmp_path) -> None:
    class FailingProjectionRegistry:
        def __init__(self, delegate) -> None:
            self.delegate = delegate
            self.fail_saves = False

        async def register(self, *args):
            return await self.delegate.register(*args)

        async def authenticate(self, *args):
            return await self.delegate.authenticate(*args)

        async def load_projection(self, *args):
            return await self.delegate.load_projection(*args)

        async def save_projection(self, *args):
            if self.fail_saves:
                raise OSError("simulated durable projection failure")
            return await self.delegate.save_projection(*args)

        async def revoke(self, *args):
            return await self.delegate.revoke(*args)

    registry = FailingProjectionRegistry(SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3"))
    factory = RestartingFakePublicFactory()
    manager = RunSessionManager(
        CoreRuntimeSessionPort(cast(Any, factory)),
        cast(Any, registry),
    )
    created = await manager.create()
    paused = await _start_and_pause_for_restart(
        manager,
        created.snapshot.session_id,
        created.session_key,
    )
    registry.fail_saves = True

    with pytest.raises(
        RuntimeSessionUnavailable,
        match="shell_recovery_projection_persistence_failed",
    ):
        await manager.admit(
            created.snapshot.session_id,
            created.session_key,
            ReviseTask(
                command_id="revise:not-admitted",
                expected_task_revision=1,
                expected_run_status=RunStatus.PAUSED,
                expected_checkpoint_id=paused.snapshot.checkpoint_id,
                text="用第二个",
            ),
        )

    assert factory.handle is not None
    assert factory.handle.revise_calls == []
    assert factory.revision_compile_count == 0
