from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from affordance_runtime.agent import SelectAction
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.checkpoint import (
    RuntimeCheckpointCommandOutcome,
    RuntimeCheckpointError,
    RuntimeCheckpointResumeOutcome,
    RuntimeCheckpointRevisionOutcome,
    SQLiteRuntimeCheckpointStore,
)
from affordance_runtime.app.public_session import (
    PublicSessionCapability,
    PublicSessionConflict,
    PublicSessionOpenError,
    PublicSessionStatus,
    RuntimeEnvironmentLease,
    TargetRuntimeSessionFactory,
)
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequired, NotRequiredGoalCompiler
from affordance_runtime.task import (
    NaturalLanguageTaskRequest,
    RevisionNoChange,
    RevisionReady,
    RiskProfile,
    TaskBoundary,
    TaskRevisionProposal,
)
from tests.integration.agent.test_core_loop import (
    CoreActionOutcomeProjector,
    CoreTaskEvaluator,
)
from tests.integration.agent.test_core_loop import (
    _world as _action_world,
)
from tests.unit.agent.test_target_runtime_facade import AskForAccountPolicy, _runtime, _world


class RecoverableAskPolicy(AskForAccountPolicy):
    active_task_identity: tuple[str, int] | None = None
    restored: bool = False

    async def decide(self, context):
        self.active_task_identity = (
            context.task.task_id,
            context.goal_plan.task_revision,
        )
        return await super().decide(context)

    def export_checkpoint_history(self):
        return {
            "format": "pydantic-ai.messages.v1",
            "messages": [],
            "active_task_identity": list(self.active_task_identity or ()),
        }

    def restore_checkpoint_history(self, payload, *, task_id, task_revision):
        if payload.get("format") != "pydantic-ai.messages.v1":
            raise ValueError("history format mismatch")
        if tuple(payload.get("active_task_identity", ())) != (task_id, task_revision):
            raise ValueError("history task mismatch")
        self.active_task_identity = (task_id, task_revision)
        self.restored = True

    def rebind_checkpoint_history(
        self,
        *,
        task_id,
        current_revision,
        revised_revision,
    ):
        if revised_revision != current_revision + 1:
            raise ValueError("revision is not consecutive")
        if self.active_task_identity not in {None, (task_id, current_revision)}:
            raise ValueError("history identity mismatch")
        self.active_task_identity = (task_id, revised_revision)


@dataclass
class ReadyRevisionCompiler:
    calls: int = 0

    async def compile(self, request):
        self.calls += 1
        return RevisionReady(
            request.current_task.revision,
            TaskRevisionProposal(
                "Inspect the selected account and its owner",
                TaskBoundary(),
            ),
        )


@dataclass
class NoChangeRevisionCompiler:
    calls: int = 0

    async def compile(self, request):
        self.calls += 1
        return RevisionNoChange(request.current_task.revision, "already_equivalent")


@dataclass
class CountingGoalCompiler:
    revisions: list[int] = field(default_factory=list)

    async def compile(self, request):
        self.revisions.append(request.task.revision)
        return NotRequired(request.task.revision, "revision_test")


@dataclass
class RevisionEnvironment(ScriptedEnvironment):
    revised_tasks: list = field(default_factory=list, init=False)

    async def revise_task(self, task):
        self.revised_tasks.append(task)
        await super().revise_task(task)


@dataclass(frozen=True)
class FailingRevisionStore:
    delegate: SQLiteRuntimeCheckpointStore

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def commit_pause(self, checkpoint, outcome):
        await self.delegate.commit_pause(checkpoint, outcome)

    async def commit_revision(self, checkpoint, outcome):
        if outcome.outcome == "revised":
            raise RuntimeCheckpointError("injected_revision_commit_failure")
        await self.delegate.commit_revision(checkpoint, outcome)


async def _revisable_checkpoint_session(
    tmp_path,
    *,
    store=None,
    compiler=None,
    pause_source=True,
):
    checkpoint_store = store or SQLiteRuntimeCheckpointStore(
        tmp_path / "revision-checkpoints.sqlite3"
    )
    policy = RecoverableAskPolicy()
    revision_compiler = compiler or ReadyRevisionCompiler()
    goal_compiler = CountingGoalCompiler()
    environment = RevisionEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(), _world(), _world()),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: replace(
            _runtime(policy),
            goal_compiler=goal_compiler,
            task_revision_compiler=revision_compiler,
        ),
        lambda _session_id: RuntimeEnvironmentLease(
            environment,
            reconnect_reference="browser-lease:revision",
        ),
        checkpoint_store=checkpoint_store,
    )
    handle = await factory.open(
        "session:revision",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        if (await handle.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("revision fixture did not reach waiting-user")
    paused = await handle.pause("pause:revision-source") if pause_source else await handle.snapshot()
    assert paused.status is (
        PublicSessionStatus.PAUSED if pause_source else PublicSessionStatus.WAITING_USER
    )
    return (
        handle,
        checkpoint_store,
        policy,
        revision_compiler,
        goal_compiler,
        environment,
        paused,
    )


class RecoverableSelectPolicy(RecoverableAskPolicy):
    async def decide(self, context):
        self.active_task_identity = (
            context.task.task_id,
            context.goal_plan.task_revision,
        )
        self.calls += 1
        return SelectAction(
            context.context_id,
            context.actions.options[0].action_id,
            tool_call_id="provider-call:recover-confirmation",
        )


def _confirmation_runtime(policy: RecoverableSelectPolicy) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(policy),
        CoreActionOutcomeProjector(),
        CoreTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("checkpoint_confirmation_test"),
    )


def _confirmation_request(session_id: str, instruction: str):
    return NaturalLanguageTaskRequest(
        session_id,
        instruction,
        TaskBoundary(
            allowed_effects=("shared_state_enabled",),
            success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
            risk_profile=RiskProfile.MEDIUM,
        ),
    )


def _action_request(session_id: str, instruction: str):
    return NaturalLanguageTaskRequest(
        session_id,
        instruction,
        TaskBoundary(
            allowed_effects=("shared_state_enabled",),
            success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
            risk_profile=RiskProfile.LOW,
        ),
    )


async def _waiting_checkpoint_session(tmp_path, *, store=None):
    checkpoint_store = store or SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
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
    restored_task = checkpoint.restore_task()
    restored_facts = checkpoint.restore_run_facts()
    assert restored_task.task_id == "session:checkpoint"
    assert restored_task.revision == 1
    assert restored_facts.status_before_pause.value == "waiting_user"
    assert restored_facts.last_decision is not None
    assert restored_facts.last_decision.question == "Which account should I use?"
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
        lambda _session_id: RuntimeEnvironmentLease(BlockingEnvironment(initial_observation=_world())),
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


@pytest.mark.asyncio
async def test_process_restart_restores_same_environment_fresh_world_and_new_epoch(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    first_policy = RecoverableAskPolicy()
    first_environment = ScriptedEnvironment(initial_observation=_world())
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            first_environment,
            reconnect_reference="browser-lease:session:restart",
        ),
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:restart", expires_at)
    await first.start("Inspect the selected account")
    for _ in range(100):
        if (await first.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    paused = await first.pause("pause:restart")
    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.resume_eligible is True
    assert paused.checkpoint_id is not None
    first_epoch = paused.event_epoch
    await first.close()

    normal_open_calls = 0
    reconnect_calls: list[tuple[str, str]] = []
    recovered_environment = ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    recovered_policy = RecoverableAskPolicy()

    def must_not_open_replacement(_session_id: str):
        nonlocal normal_open_calls
        normal_open_calls += 1
        raise AssertionError("restart recovery must not open a replacement environment")

    def reconnect(session_id: str, reference: str):
        reconnect_calls.append((session_id, reference))
        return RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        )

    recovered_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(recovered_policy),
        must_not_open_replacement,
        checkpoint_store=store,
        environment_reconnector=reconnect,
    )
    recovered = await recovered_factory.recover("session:restart", paused.checkpoint_id, expires_at)
    baseline = await recovered.snapshot()

    assert baseline.status is PublicSessionStatus.PAUSED
    assert baseline.event_epoch != first_epoch
    assert baseline.event_cursor == 1
    assert tuple(event.type for event in await recovered.events(0)) == ("SESSION_RECOVERED",)
    assert baseline.checkpoint_id == paused.checkpoint_id
    assert baseline.resume_eligible is True
    assert normal_open_calls == 0
    assert reconnect_calls == [("session:restart", "browser-lease:session:restart")]
    assert recovered_environment.reset_calls == 0
    assert recovered_environment.capture_calls == 1
    assert recovered_policy.restored is True
    assert recovered_policy.calls == 0

    resumed = await recovered.resume("resume:restart", paused.checkpoint_id)
    assert resumed.status is PublicSessionStatus.WAITING_USER
    assert resumed.pending_question is not None
    assert resumed.resume_eligible is False
    assert recovered_policy.calls == 0
    assert await store.resume_outcome("session:restart", "resume:restart") == (
        RuntimeCheckpointResumeOutcome("session:restart", "resume:restart", paused.checkpoint_id)
    )
    duplicate = await recovered.resume("resume:restart", paused.checkpoint_id)
    assert duplicate == resumed

    with pytest.raises(PublicSessionOpenError, match="checkpoint_already_resumed"):
        await recovered_factory.recover("session:restart", paused.checkpoint_id, expires_at)
    assert len(reconnect_calls) == 1
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_refuses_nonreconnectable_checkpoint_without_opening_environment(tmp_path) -> None:
    handle, _store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:not-reconnectable")
    assert paused.checkpoint_id is not None
    await handle.close()
    open_calls = 0

    def environment_factory(_session_id: str):
        nonlocal open_calls
        open_calls += 1
        raise AssertionError("failed recovery must not create a new environment")

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        environment_factory,
        checkpoint_store=SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3"),
    )
    with pytest.raises(PublicSessionOpenError, match="environment_not_reconnectable"):
        await factory.recover(
            "session:checkpoint",
            paused.checkpoint_id,
            datetime.now(UTC) + timedelta(minutes=5),
        )
    assert open_calls == 0


@pytest.mark.asyncio
async def test_restart_from_running_boundary_reselects_only_after_explicit_resume(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "running-checkpoints.sqlite3")
    release = asyncio.Event()

    class BlockingEnvironment(ScriptedEnvironment):
        async def reset(self, task):
            await release.wait()
            return await super().reset(task)

    first_policy = RecoverableAskPolicy()
    first_policy.active_task_identity = ("session:running-restart", 1)
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            BlockingEnvironment(initial_observation=_world()),
            reconnect_reference="browser-lease:running",
        ),
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:running-restart", expires_at)
    await first.start("Inspect the selected account")
    await first.pause("pause:running-restart")
    release.set()
    for _ in range(100):
        paused = await first.snapshot()
        if paused.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("running checkpoint did not commit")
    assert paused.checkpoint_id is not None
    await first.close()

    recovered_policy = RecoverableAskPolicy()
    recovered_environment = ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(recovered_policy),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await factory.recover("session:running-restart", paused.checkpoint_id, expires_at)
    assert recovered_policy.calls == 0
    assert recovered_environment.execute_calls == 0

    resumed = await recovered.resume("resume:running-restart", paused.checkpoint_id)
    assert resumed.status is PublicSessionStatus.RUNNING
    for _ in range(100):
        waiting = await recovered.snapshot()
        if waiting.status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("resumed running checkpoint did not return to policy")
    assert recovered_policy.calls == 1
    assert recovered_environment.execute_calls == 0
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_confirmation_keeps_exact_interrupt_and_never_dispatches_before_resume(
    tmp_path,
) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "confirmation-checkpoints.sqlite3")
    first_policy = RecoverableSelectPolicy()
    first_environment = ScriptedEnvironment(initial_observation=_action_world("confirmation-before", False))
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            first_environment,
            reconnect_reference="browser-lease:confirmation",
        ),
        request_factory=_confirmation_request,
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:confirmation-restart", expires_at)
    await first.start("Enable shared state")
    for _ in range(100):
        waiting = await first.snapshot()
        if waiting.status is PublicSessionStatus.WAITING_CONFIRMATION:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("confirmation fixture did not reach its interrupt")
    original_interrupt = waiting.pending_confirmation
    paused = await first.pause("pause:confirmation-restart")
    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.checkpoint_id is not None
    assert first_environment.execute_calls == 0
    await first.close()

    recovered_policy = RecoverableSelectPolicy()
    recovered_environment = ScriptedEnvironment(
        initial_observation=_action_world("confirmation-reconnected", False),
        independent_observations=(_action_world("confirmation-reconnected", False),),
        post_observations=(_action_world("confirmation-after", True),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )
    recovered_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(recovered_policy),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        request_factory=_confirmation_request,
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await recovered_factory.recover("session:confirmation-restart", paused.checkpoint_id, expires_at)
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0

    resumed = await recovered.resume("resume:confirmation-restart", paused.checkpoint_id)
    assert resumed.status is PublicSessionStatus.WAITING_CONFIRMATION
    assert resumed.pending_confirmation == original_interrupt
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0

    assert resumed.pending_confirmation is not None
    await recovered.confirm(
        resumed.pending_confirmation.interrupt_id,
        approved=True,
    )
    for _ in range(100):
        done = await recovered.snapshot()
        if done.status is PublicSessionStatus.DONE:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"restored confirmation did not execute after approval: {done!r}")
    assert recovered_environment.execute_calls == 1
    assert recovered_policy.calls == 0
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_after_sent_receipt_observes_effect_without_replaying_action(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "sent-checkpoints.sqlite3")
    dispatch_entered = asyncio.Event()
    dispatch_release = asyncio.Event()

    class BlockingDispatchEnvironment(ScriptedEnvironment):
        async def execute(self, request):
            dispatch_entered.set()
            await dispatch_release.wait()
            return await super().execute(request)

    first_policy = RecoverableSelectPolicy()
    first_environment = BlockingDispatchEnvironment(
        initial_observation=_action_world("sent-before", False),
        post_observations=(_action_world("sent-after", False),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            first_environment,
            reconnect_reference="browser-lease:sent",
        ),
        request_factory=_action_request,
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:sent-restart", expires_at)
    await first.start("Enable shared state")
    await asyncio.wait_for(dispatch_entered.wait(), timeout=1)
    requested = await first.pause("pause:sent-restart")
    assert requested.status is PublicSessionStatus.RUNNING
    dispatch_release.set()
    for _ in range(100):
        paused = await first.snapshot()
        if paused.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("sent checkpoint did not commit")
    assert paused.checkpoint_id is not None
    checkpoint = await store.load(
        "session:sent-restart",
        paused.checkpoint_id,
    )
    assert checkpoint is not None and checkpoint.last_step is not None
    receipts = checkpoint.last_step["receipts"]
    assert receipts[0]["dispatch_status"] == "sent"
    assert first_environment.execute_calls == 1
    await first.close()

    recovered_policy = RecoverableSelectPolicy()
    recovered_environment = ScriptedEnvironment(
        initial_observation=_action_world("sent-reconnected", True),
        independent_observations=(_action_world("sent-reconnected", True),),
    )
    recovered_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(recovered_policy),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        request_factory=_action_request,
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await recovered_factory.recover("session:sent-restart", paused.checkpoint_id, expires_at)
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0
    await recovered.resume("resume:sent-restart", paused.checkpoint_id)
    for _ in range(100):
        done = await recovered.snapshot()
        if done.status is PublicSessionStatus.DONE:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"sent checkpoint did not finish from fresh truth: {done!r}")
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_rejects_corrupted_checkpoint_before_environment_reconnect(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:corrupt")
    assert paused.checkpoint_id is not None
    await handle.close()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE runtime_checkpoints SET payload_json = replace(payload_json, "
            "'Inspect the selected account', 'Inspect a corrupted account') "
            "WHERE session_id = ? AND checkpoint_id = ?",
            ("session:checkpoint", paused.checkpoint_id),
        )
        connection.commit()
    reconnect_calls = 0

    def reconnect(_session_id: str, reference: str):
        nonlocal reconnect_calls
        reconnect_calls += 1
        return RuntimeEnvironmentLease(
            ScriptedEnvironment(initial_observation=_world()),
            reconnect_reference=reference,
        )

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        checkpoint_store=store,
        environment_reconnector=reconnect,
    )
    with pytest.raises(PublicSessionOpenError, match="checkpoint_invalid"):
        await factory.recover(
            "session:checkpoint",
            paused.checkpoint_id,
            datetime.now(UTC) + timedelta(minutes=5),
        )
    assert reconnect_calls == 0


@pytest.mark.asyncio
async def test_checkpoint_load_rejects_row_and_payload_scope_mismatch(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:scope")
    assert paused.checkpoint_id is not None
    await handle.close()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "INSERT INTO runtime_checkpoints "
            "(session_id, checkpoint_id, schema_version, digest, created_at, payload_json) "
            "SELECT ?, checkpoint_id, schema_version, digest, created_at, payload_json "
            "FROM runtime_checkpoints WHERE session_id = ? AND checkpoint_id = ?",
            ("session:wrong-scope", "session:checkpoint", paused.checkpoint_id),
        )
        connection.commit()

    with pytest.raises(RuntimeCheckpointError, match="checkpoint_scope_mismatch"):
        await store.load("session:wrong-scope", paused.checkpoint_id)
    with pytest.raises(RuntimeCheckpointError, match="checkpoint_scope_mismatch"):
        await store.load_latest("session:wrong-scope")


@pytest.mark.asyncio
async def test_revision_commits_new_checkpoint_and_remains_paused(tmp_path) -> None:
    (
        handle,
        store,
        policy,
        revision_compiler,
        goal_compiler,
        environment,
        source,
    ) = await _revisable_checkpoint_session(tmp_path)
    assert source.checkpoint_id is not None
    policy_calls = policy.calls

    revised = await handle.revise(
        "revise:ready",
        source.checkpoint_id,
        "Also include the owner",
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.task_text == "Inspect the selected account and its owner"
    assert revised.checkpoint_id is not None
    assert revised.checkpoint_id != source.checkpoint_id
    assert revised.resume_eligible is True
    assert revised.pending_question is None
    assert revised.pending_confirmation is None
    assert revised.last_control_outcome is not None
    assert revised.last_control_outcome.kind == "revise"
    assert revised.last_control_outcome.outcome == "revised"
    assert policy.calls == policy_calls
    assert revision_compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert [task.revision for task in environment.revised_tasks] == [2]
    checkpoint = await store.load("session:revision", revised.checkpoint_id)
    assert checkpoint is not None
    assert checkpoint.restore_task().revision == 2
    assert checkpoint.model_history["active_task_identity"] == (
        "session:revision",
        2,
    )
    assert await store.revision_outcome("session:revision", "revise:ready") == (
        RuntimeCheckpointRevisionOutcome(
            "session:revision",
            "revise:ready",
            source.checkpoint_id,
            revised.checkpoint_id,
            2,
            "revised",
        )
    )
    assert await store.checkpoint_revision_outcome(
        "session:revision",
        source.checkpoint_id,
    ) == RuntimeCheckpointRevisionOutcome(
        "session:revision",
        "revise:ready",
        source.checkpoint_id,
        revised.checkpoint_id,
        2,
        "revised",
    )
    duplicate = await handle.revise(
        "revise:ready",
        source.checkpoint_id,
        "ignored duplicate text",
    )
    assert duplicate == revised
    assert revision_compiler.calls == 1
    await handle.close()


@pytest.mark.asyncio
async def test_revision_command_reuses_cooperative_pause_without_separate_shell_command(
    tmp_path,
) -> None:
    handle, store, policy, compiler, goal_compiler, environment, before = (
        await _revisable_checkpoint_session(tmp_path, pause_source=False)
    )
    assert before.checkpoint_id is None
    policy_calls = policy.calls

    revised = await handle.revise(
        "revise:single-command",
        None,
        "Also include the owner",
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.checkpoint_id is not None
    assert policy.calls == policy_calls
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert [task.revision for task in environment.revised_tasks] == [2]
    outcome = await store.revision_outcome(
        "session:revision",
        "revise:single-command",
    )
    assert outcome is not None
    assert outcome.source_checkpoint_id != outcome.result_checkpoint_id
    events = tuple(event.type for event in await handle.events(before.event_cursor))
    assert events[-3:] == ("CONTROL_REQUESTED", "RUN_PAUSED", "TASK_REVISED")
    await handle.close()


@pytest.mark.asyncio
async def test_revision_nonready_outcome_is_durable_and_keeps_old_checkpoint(tmp_path) -> None:
    compiler = NoChangeRevisionCompiler()
    handle, store, _policy, _, goal_compiler, environment, source = (
        await _revisable_checkpoint_session(tmp_path, compiler=compiler)
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match="revision_no_change"):
        await handle.revise(
            "revise:no-change",
            source.checkpoint_id,
            "Keep the existing task",
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.outcome == "no_change"
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1]
    assert environment.revised_tasks == []
    outcome = await store.revision_outcome("session:revision", "revise:no-change")
    assert outcome is not None and outcome.outcome == "revision_no_change"

    with pytest.raises(PublicSessionConflict, match="revision_no_change"):
        await handle.revise(
            "revise:no-change",
            source.checkpoint_id,
            "Do not call the compiler twice",
        )
    assert compiler.calls == 1
    await handle.close()


@pytest.mark.asyncio
async def test_revision_requires_phase7_when_any_gui_effect_was_committed(tmp_path) -> None:
    handle, store, _policy, compiler, goal_compiler, environment, source = (
        await _revisable_checkpoint_session(tmp_path)
    )
    assert source.checkpoint_id is not None
    assert handle._state is not None
    handle._state.execution_count = 1

    with pytest.raises(PublicSessionConflict, match="effect_reconciliation_required"):
        await handle.revise(
            "revise:effect",
            source.checkpoint_id,
            "Change the goal after an effect",
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.outcome == "effect_reconciliation_required"
    assert compiler.calls == 0
    assert goal_compiler.revisions == [1]
    assert environment.revised_tasks == []
    outcome = await store.revision_outcome("session:revision", "revise:effect")
    assert outcome is not None and outcome.outcome == "effect_reconciliation_required"
    await handle.close()


@pytest.mark.asyncio
async def test_revision_commit_failure_restores_old_history_environment_and_pause(tmp_path) -> None:
    delegate = SQLiteRuntimeCheckpointStore(tmp_path / "revision-failure.sqlite3")
    store = FailingRevisionStore(delegate)
    handle, _, policy, compiler, goal_compiler, environment, source = (
        await _revisable_checkpoint_session(tmp_path, store=store)
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match="revision_persistence_failed"):
        await handle.revise(
            "revise:persistence-failure",
            source.checkpoint_id,
            "Also include the owner",
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.code == "revision_persistence_failed"
    assert policy.active_task_identity == ("session:revision", 1)
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert [task.revision for task in environment.revised_tasks] == [2, 1]
    assert await delegate.revision_outcome(
        "session:revision",
        "revise:persistence-failure",
    ) is None
    await handle.close()
