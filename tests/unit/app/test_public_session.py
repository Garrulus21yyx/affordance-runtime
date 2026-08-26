from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from affordance_runtime.app import compose_target_runtime
from affordance_runtime.app.public_session import (
    PublicSessionConflict,
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
        runtime,
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
    assert tuple(event.cursor for event in events) == tuple(range(1, len(events) + 1))
    assert events[-1].snapshot == waiting
    assert events[-1].type == "RUN_FINISHED"

    with pytest.raises(PublicSessionConflict, match="interrupt_mismatch"):
        await handle.answer("ask:wrong", "primary")

    resumed = await handle.answer(waiting.pending_question.interrupt_id, "primary")
    assert resumed.status is PublicSessionStatus.RUNNING
    done = await _wait_for_status(handle, PublicSessionStatus.DONE)
    assert done.task_revision == 2
    assert done.pending_question is None
    assert done.completion is not None
    assert done.completion.outcome == "success"

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
        _runtime(),
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
