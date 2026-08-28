from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from affordance_runtime.agent.interactions import StructuredFieldsResponse, TextFieldValue
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.app.public_session import (
    PublicCommandAccepted,
    PublicCommandConflict,
    PublicCommandRejected,
    PublicSessionCapability,
    PublicSessionCommand,
    PublicSessionCommandKind,
    PublicSessionConflict,
    PublicSessionOpenError,
    PublicSessionOpenStage,
    PublicSessionStatus,
    RuntimeEnvironmentLease,
    TargetRuntimeSessionFactory,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.goals import NotRequiredGoalCompiler
from tests.unit.agent.test_target_runtime_facade import (
    AskForAccountPolicy,
    UnusedActionOutcomeProjector,
    _runtime,
    _world,
)


async def _wait_for_status(handle, expected: PublicSessionStatus):
    for _ in range(100):
        snapshot = await handle.snapshot()
        if snapshot.status is expected:
            return snapshot
        await asyncio.sleep(0)
    raise AssertionError(f"public session did not reach {expected}")


@pytest.mark.asyncio
async def test_public_session_owns_resumable_state_and_projects_ordered_interrupt() -> None:
    cleanup_count = 0

    def cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    class UserResponseEvaluator:
        async def evaluate(self, task, observation):
            complete = bool(task.inputs.get("user_responses"))
            evidence = ("fact:page:available",) if complete else ()
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE,
                "public session fixture evaluation",
                completion_evidence_refs=evidence,
                outcome=(
                    TaskOutcomeFact(TaskOutcomeKind.TERMINAL_SUCCESS, "fixture_complete", evidence)
                    if complete
                    else TaskOutcomeFact(TaskOutcomeKind.RUNNING_INCOMPLETE, "fixture_incomplete")
                ),
            )

    runtime = compose_target_runtime(
        AskForAccountPolicy(),
        UnusedActionOutcomeProjector(),
        UserResponseEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("public_session_test"),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: runtime,
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world()), cleanup),
    )
    handle = await factory.open("session:public", datetime.now(UTC) + timedelta(minutes=5))

    admitted = await handle.start("Inspect the selected account")
    assert admitted.status is PublicSessionStatus.RUNNING
    waiting = await _wait_for_status(handle, PublicSessionStatus.WAITING_USER)

    assert waiting.pending_question is not None
    assert waiting.pending_question.prompt == "Which account should I use?"
    assert waiting.pending_question.requested_fields == ("inputs.account",)
    assert waiting.pending_confirmation is None
    events = await handle.events(0)
    assert waiting.event_epoch
    assert all(event.event_epoch == waiting.event_epoch for event in events)
    assert tuple(event.cursor for event in events) == tuple(range(1, len(events) + 1))
    assert events[-1].snapshot == waiting
    assert events[-1].type == "RUN_FINISHED"
    waiting_feed = tuple(source for event in events for source in event.feed_sources)
    assert tuple(source.kind for source in waiting_feed) == (
        "user_turn",
        "goal_accepted",
        "interaction_request",
    )
    assert len({source.source_id for source in waiting_feed}) == len(waiting_feed)

    with pytest.raises(PublicSessionConflict, match="interrupt_mismatch"):
        await handle.answer("ask:wrong", "primary")

    resumed = await handle.answer(waiting.pending_question.interrupt_id, "primary")
    assert resumed.status is PublicSessionStatus.RUNNING
    done = await _wait_for_status(handle, PublicSessionStatus.DONE)
    assert done.task_revision == 2
    assert done.pending_question is None
    assert done.completion is not None
    assert done.completion.outcome == "success"
    completed_feed = tuple(
        source
        for event in await handle.events(0)
        for source in event.feed_sources
    )
    assert tuple(source.kind for source in completed_feed)[-2:] == (
        "user_turn",
        "completion",
    )

    await handle.close()
    await handle.close()
    assert cleanup_count == 1


@pytest.mark.asyncio
async def test_public_session_cleanup_waits_for_active_run_and_executes_once() -> None:
    release = asyncio.Event()
    cleanup_count = 0

    class BlockingEnvironment(ScriptedEnvironment):
        async def reset(self, task):
            await release.wait()
            return await super().reset(task)

    def cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(BlockingEnvironment(initial_observation=_world()), cleanup),
    )
    handle = await factory.open("session:cleanup", datetime.now(UTC) + timedelta(minutes=5))
    await handle.start("Inspect the selected account")
    await handle.close()
    assert cleanup_count == 0

    release.set()
    await _wait_for_status(handle, PublicSessionStatus.WAITING_USER)
    for _ in range(100):
        if cleanup_count:
            break
        await asyncio.sleep(0)
    await handle.close()
    assert cleanup_count == 1


@pytest.mark.asyncio
async def test_cancel_run_is_cooperative_terminal_and_close_remains_idempotent() -> None:
    release = asyncio.Event()
    cleanup_count = 0

    class BlockingEnvironment(ScriptedEnvironment):
        async def reset(self, task):
            await release.wait()
            return await super().reset(task)

    def cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(BlockingEnvironment(initial_observation=_world()), cleanup),
    )
    handle = await factory.open("session:cancel", datetime.now(UTC) + timedelta(minutes=5))
    initial = await handle.snapshot()
    assert PublicSessionCapability.CANCEL_TASK in initial.capabilities
    await handle.start("Inspect the selected account")

    requested = await handle.cancel("cancel:active")
    assert requested.status is PublicSessionStatus.RUNNING
    assert cleanup_count == 0
    release.set()
    cancelled = await _wait_for_status(handle, PublicSessionStatus.CANCELLED)

    assert cancelled.completion is not None
    assert cancelled.completion.outcome == "cancelled"
    assert cancelled.completion.code == "user_cancelled"
    assert tuple(event.type for event in await handle.events(0)) == (
        "RUN_STARTED",
        "CONTROL_REQUESTED",
        "RUN_FINISHED",
    )
    assert cleanup_count == 1

    await handle.close()
    await handle.close()
    assert cleanup_count == 1


@pytest.mark.asyncio
async def test_cancel_at_waiting_boundary_does_not_resume_policy_or_dispatch() -> None:
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
    )
    handle = await factory.open("session:cancel-waiting", datetime.now(UTC) + timedelta(minutes=5))
    await handle.start("Inspect the selected account")
    await _wait_for_status(handle, PublicSessionStatus.WAITING_USER)

    cancelled = await handle.cancel("cancel:waiting")

    assert cancelled.status is PublicSessionStatus.CANCELLED
    assert cancelled.pending_question is None
    assert cancelled.completion is not None
    assert cancelled.completion.outcome == "cancelled"
    await handle.close()


@pytest.mark.asyncio
async def test_runtime_factory_isolates_policy_history_world_events_and_cleanup() -> None:
    policies: dict[str, SessionHistoryPolicy] = {}
    environments: dict[str, ScriptedEnvironment] = {}
    cleanup_counts: dict[str, int] = {}

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            complete = bool(task.inputs.get("user_responses"))
            evidence = ("fact:page:available",) if complete else ()
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE,
                "session-isolation evaluation",
                completion_evidence_refs=evidence,
                outcome=(
                    TaskOutcomeFact(TaskOutcomeKind.TERMINAL_SUCCESS, "isolated_complete", evidence)
                    if complete
                    else TaskOutcomeFact(TaskOutcomeKind.RUNNING_INCOMPLETE, "isolated_incomplete")
                ),
            )

    def runtime_factory(session_id: str):
        policy = SessionHistoryPolicy()
        policies[session_id] = policy
        return compose_target_runtime(
            policy,
            UnusedActionOutcomeProjector(),
            IncompleteEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("session_isolation_test"),
        )

    def environment_factory(session_id: str):
        environment = ScriptedEnvironment(initial_observation=_world())
        environments[session_id] = environment
        cleanup_counts[session_id] = 0

        def cleanup() -> None:
            cleanup_counts[session_id] += 1

        return RuntimeEnvironmentLease(environment, cleanup)

    factory = TargetRuntimeSessionFactory(runtime_factory, environment_factory)
    expiry = datetime.now(UTC) + timedelta(minutes=5)
    first, second = await asyncio.gather(
        factory.open("session:first", expiry),
        factory.open("session:second", expiry),
    )
    await asyncio.gather(first.start("Inspect first"), second.start("Inspect second"))
    first_waiting, second_waiting = await asyncio.gather(
        _wait_for_status(first, PublicSessionStatus.WAITING_USER),
        _wait_for_status(second, PublicSessionStatus.WAITING_USER),
    )

    assert policies["session:first"] is not policies["session:second"]
    assert policies["session:first"].message_history == ["session:first"]
    assert policies["session:second"].message_history == ["session:second"]
    assert environments["session:first"] is not environments["session:second"]
    assert first_waiting.task_id == "session:first"
    assert second_waiting.task_id == "session:second"
    assert first_waiting.event_epoch != second_waiting.event_epoch
    assert {event.session_id for event in await first.events(0)} == {"session:first"}
    assert {event.session_id for event in await second.events(0)} == {"session:second"}

    first_cancelled = await first.cancel("cancel:first")
    assert first_cancelled.status is PublicSessionStatus.CANCELLED
    assert (await second.snapshot()).status is PublicSessionStatus.WAITING_USER
    await first.close()
    assert cleanup_counts == {"session:first": 1, "session:second": 0}
    assert (await second.snapshot()).status is PublicSessionStatus.WAITING_USER
    assert second_waiting.pending_question is not None
    await second.answer(second_waiting.pending_question.interrupt_id, "primary")
    await _wait_for_status(second, PublicSessionStatus.DONE)
    await second.close()
    assert cleanup_counts == {"session:first": 1, "session:second": 1}


@pytest.mark.asyncio
async def test_session_factory_reports_typed_stage_and_cleans_invalid_environment_once() -> None:
    environment_calls = 0

    def failed_runtime(_session_id: str):
        raise RuntimeError("provider configuration failed")

    def unused_environment(_session_id: str):
        nonlocal environment_calls
        environment_calls += 1
        raise AssertionError("environment must not open after Runtime failure")

    factory = TargetRuntimeSessionFactory(failed_runtime, unused_environment)
    with pytest.raises(PublicSessionOpenError) as runtime_error:
        await factory.open("session:runtime-failure", datetime.now(UTC) + timedelta(minutes=5))
    assert runtime_error.value.stage is PublicSessionOpenStage.RUNTIME
    assert environment_calls == 0

    cleanup_count = 0

    def cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    invalid_environment_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(object(), cleanup),  # type: ignore[arg-type]
    )
    with pytest.raises(PublicSessionOpenError) as session_error:
        await invalid_environment_factory.open(
            "session:invalid-environment",
            datetime.now(UTC) + timedelta(minutes=5),
        )
    assert session_error.value.stage is PublicSessionOpenStage.SESSION
    assert cleanup_count == 1


@pytest.mark.asyncio
async def test_v3_runtime_command_capabilities_are_state_correct_unique_and_ref_owned() -> None:
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
    )
    handle = await factory.open("session:v3-capabilities", datetime.now(UTC) + timedelta(minutes=5))
    initial = await handle.snapshot()
    initial_kinds = tuple(capability.kind for capability in initial.command_capabilities)
    assert initial_kinds == (
        PublicSessionCommandKind.START_TASK,
        PublicSessionCommandKind.CLOSE_SESSION,
    )
    assert len(initial_kinds) == len(set(initial_kinds))

    admitted = await handle.admit(
        PublicSessionCommand(
            command_id="start:v3",
            kind=PublicSessionCommandKind.START_TASK,
            expected_task_revision=0,
            expected_run_status=PublicSessionStatus.IDLE,
            task="Inspect the selected account",
        )
    )
    assert isinstance(admitted, PublicCommandAccepted)
    waiting = await _wait_for_status(handle, PublicSessionStatus.WAITING_USER)
    answer = next(
        capability
        for capability in waiting.command_capabilities
        if capability.kind is PublicSessionCommandKind.RESPOND_INTERACTION
    )
    assert waiting.pending_interaction is not None
    assert answer.interaction_ref == waiting.pending_interaction.request_id
    assert answer.prompt == waiting.pending_interaction.prompt
    assert len({capability.kind for capability in waiting.command_capabilities}) == len(waiting.command_capabilities)
    await handle.close()


@pytest.mark.asyncio
async def test_interaction_response_is_admitted_against_exact_pending_contract_before_resume() -> None:
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
    )
    handle = await factory.open("session:typed-response", datetime.now(UTC) + timedelta(minutes=5))
    await handle.start("Inspect the selected account")
    waiting = await _wait_for_status(handle, PublicSessionStatus.WAITING_USER)
    assert waiting.pending_interaction is not None

    before = waiting
    admission = await handle.admit(
        PublicSessionCommand(
            command_id="response:invalid-field",
            kind=PublicSessionCommandKind.RESPOND_INTERACTION,
            expected_task_revision=waiting.task_revision,
            expected_run_status=waiting.status,
            interaction_ref=waiting.pending_interaction.request_id,
            response=StructuredFieldsResponse(
                waiting.pending_interaction.request_id,
                (TextFieldValue("field:00000000000000000000000000000000", "primary"),),
            ),
        )
    )

    assert isinstance(admission, PublicCommandRejected)
    assert admission.code == "interaction_response_invalid"
    assert admission.snapshot == before
    assert (await handle.snapshot()).status is PublicSessionStatus.WAITING_USER
    await handle.close()


@pytest.mark.asyncio
async def test_v3_runtime_admission_owns_currentness_and_command_identity() -> None:
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
    )
    handle = await factory.open("session:v3-admission", datetime.now(UTC) + timedelta(minutes=5))
    command = PublicSessionCommand(
        command_id="start:stable",
        kind=PublicSessionCommandKind.START_TASK,
        expected_task_revision=0,
        expected_run_status=PublicSessionStatus.IDLE,
        task="Inspect the selected account",
    )
    first = await handle.admit(command)
    replay = await handle.admit(command)
    reused = await handle.admit(
        PublicSessionCommand(
            command_id="start:stable",
            kind=PublicSessionCommandKind.START_TASK,
            expected_task_revision=0,
            expected_run_status=PublicSessionStatus.IDLE,
            task="A different task",
        )
    )
    stale = await handle.admit(
        PublicSessionCommand(
            command_id="start:stale",
            kind=PublicSessionCommandKind.START_TASK,
            expected_task_revision=99,
            expected_run_status=PublicSessionStatus.IDLE,
            task="Inspect",
        )
    )
    assert first is replay
    assert isinstance(reused, PublicCommandConflict)
    assert reused.code == "command_identity_reused"
    assert isinstance(stale, PublicCommandConflict)
    assert stale.code == "stale_command"
    await handle.close()


@dataclass
class SessionHistoryPolicy:
    message_history: list[str] = field(default_factory=list)

    async def decide(self, context):
        self.message_history.append(context.task.task_id)
        return await AskForAccountPolicy().decide(context)
