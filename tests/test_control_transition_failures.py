"""Exceptional-path witnesses for the canonical control-transition contract."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from test_agent_loop import (
    ScriptedPolicy,
    SharedActionEvaluator,
    SharedTaskEvaluator,
    _loop,
    _sent,
    _task,
    _world,
)

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import AcquisitionOrigin


class RaisingActionEvaluator:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def evaluate(self, *args):
        del args
        raise self.exc


class SecondCallTaskEvaluator:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        if self.calls == 2:
            raise self.exc
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "incomplete",
        )


@pytest.mark.parametrize("stage", ("action", "task"))
def test_evaluator_runtime_error_preserves_incremental_execution_truth(stage: str) -> None:
    async def scenario() -> None:
        action_evaluator = (
            RaisingActionEvaluator(RuntimeError("private evaluator detail"))
            if stage == "action" else SharedActionEvaluator()
        )
        task_evaluator = (
            SecondCallTaskEvaluator(RuntimeError("private evaluator detail"))
            if stage == "task" else SharedTaskEvaluator()
        )
        session = await (
            AgentLoop(ScriptedPolicy(["first"]), action_evaluator, task_evaluator)
        ).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [_sent()]),
            _task(),
        )

        with pytest.raises(RuntimeError, match="private evaluator detail"):
            await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert root.resulting_status is AgentLoopStatus.FAILED
        assert root.reason_code == "runtime_exception"
        assert root.execution is not None
        assert root.execution.dispatch_status is DispatchStatus.SENT
        if stage == "task":
            assert root.action_evaluation is not None
            assert root.action_evaluation.after_observation_id == "after"
        assert root.after_observation_id == "after"
        assert root.acquisition is not None and root.acquisition.attempts == 1
        assert session.state.current_observation.observation_id == "after"
        assert session.execution_count == 1
        assert session.observation_count == 2
        terminal = await session.run_until_pause()
        assert terminal is session.last_result
        assert terminal.status is AgentLoopStatus.FAILED
        assert terminal.reason_code == "runtime_exception"
        assert terminal.runtime_failure is not None
        assert terminal.runtime_failure.stage is FailureStage.EVALUATION
        assert terminal.runtime_failure.kind is FailureKind.CALL_FAILED
        assert terminal.runtime_failure.root_id == root.transition_id
        assert terminal.runtime_failure.attempt_id == root.attempt_receipts[-1].attempt_id
        assert terminal.execution_count == 1
        assert session.state.control_transition_total_count == 1

    asyncio.run(scenario())


def test_evaluator_cancellation_preserves_facts_and_propagates() -> None:
    async def scenario() -> None:
        session = await (
            AgentLoop(
                ScriptedPolicy(["first"]),
                RaisingActionEvaluator(asyncio.CancelledError()),
                SharedTaskEvaluator(),
            )
        ).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [_sent()]),
            _task(),
        )
        with pytest.raises(asyncio.CancelledError):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert root.resulting_status is AgentLoopStatus.CANCELLED
        assert root.reason_code == "runtime_cancelled"
        assert root.after_observation_id == "after"
        assert session.execution_count == 1
        assert session.observation_count == 2
        terminal = await session.run_until_pause()
        assert terminal is session.last_result
        assert terminal.status is AgentLoopStatus.CANCELLED
        assert terminal.reason_code == "runtime_cancelled"
        assert session.state.control_transition_total_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("exc", (RuntimeError("execute failed"), asyncio.CancelledError()))
def test_execute_exception_latches_terminal_session_without_duplicate_dispatch(exc) -> None:
    class RaisingEnvironment(StaticEnvironment):
        async def execute(self, request):
            self.execute_calls += 1
            self.executed_requests.append(request)
            raise exc

    async def scenario() -> None:
        policy = ScriptedPolicy(["first"])
        environment = RaisingEnvironment([_world("before", False)])
        session = await (_loop(policy)).start(environment, _task())
        with pytest.raises(type(exc)):
            await session.run_until_pause()

        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal is session.last_result
        assert terminal.status is (
            AgentLoopStatus.CANCELLED
            if isinstance(exc, asyncio.CancelledError)
            else AgentLoopStatus.FAILED
        )
        assert root.reason_code == (
            "runtime_cancelled"
            if isinstance(exc, asyncio.CancelledError)
            else "runtime_exception"
        )
        assert policy.decisions == []
        assert environment.execute_calls == 1
        assert session.state.control_transition_total_count == 1
        assert terminal.runtime_failure is not None
        assert terminal.runtime_failure.stage is (
            FailureStage.SESSION
            if isinstance(exc, asyncio.CancelledError)
            else FailureStage.EXECUTION
        )
        assert terminal.runtime_failure.root_id == root.transition_id
        assert terminal.runtime_failure.attempt_id == root.attempt_receipts[-1].attempt_id

    asyncio.run(scenario())


def test_foreign_execute_exception_name_cannot_break_physical_accounting() -> None:
    foreign_error = type("Execute.Error!" * 12, (Exception,), {})("private execute detail")

    class RaisingEnvironment(StaticEnvironment):
        async def execute(self, request):
            self.execute_calls += 1
            self.executed_requests.append(request)
            raise foreign_error

    async def scenario() -> None:
        environment = RaisingEnvironment([_world("before", False)])
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            environment, _task(),
        )
        with pytest.raises(type(foreign_error)):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert environment.execute_calls == 1
        assert session.execution_count == 1
        assert len(root.attempt_receipts) == 1
        assert root.attempt_receipts[0].exception_class.startswith("ExceptionClass_")

    asyncio.run(scenario())


@pytest.mark.parametrize("component", ("policy", "initial_task_evaluator"))
def test_predecision_component_exception_keeps_typed_stage_without_root(component) -> None:
    class RaisingPolicy:
        async def decide(self, context):
            del context
            raise TimeoutError("private policy detail")

    class RaisingInitialTaskEvaluator:
        async def evaluate(self, task, observation):
            del task, observation
            raise RuntimeError("private evaluation detail")

    async def scenario() -> None:
        session = await (AgentLoop(
            RaisingPolicy() if component == "policy" else ScriptedPolicy(["first"]),
            SharedActionEvaluator(),
            RaisingInitialTaskEvaluator()
            if component == "initial_task_evaluator"
            else SharedTaskEvaluator(),
        )).start(StaticEnvironment([_world("before", False)]), _task())
        with pytest.raises(TimeoutError if component == "policy" else RuntimeError):
            await session.run_until_pause()
        assert session.last_result is not None
        failure = session.last_result.runtime_failure
        assert failure is not None
        assert failure.stage is (
            FailureStage.POLICY
            if component == "policy"
            else FailureStage.EVALUATION
        )
        assert failure.kind is FailureKind.CALL_FAILED
        assert not failure.root_id and not failure.attempt_id
        assert failure.exception_class in {"TimeoutError", "RuntimeError"}

    asyncio.run(scenario())


def test_malformed_execute_return_is_one_failed_physical_attempt() -> None:
    class MalformedEnvironment(StaticEnvironment):
        async def execute(self, request):
            self.execute_calls += 1
            self.executed_requests.append(request)
            return object()

    async def scenario() -> None:
        environment = MalformedEnvironment([_world("before", False)])
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            environment, _task(),
        )
        with pytest.raises(TypeError, match="malformed contract"):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert environment.execute_calls == 1
        assert session.execution_count == 1
        assert len(root.attempt_receipts) == 1
        assert root.attempt_receipts[0].disposition.value == "malformed"

    asyncio.run(scenario())


def test_lineage_mismatch_preserves_truth_without_foreign_identity_material() -> None:
    async def scenario() -> None:
        result = ActionResult("request:wrong", DispatchStatus.SENT, "dom", True)
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [result]),
            _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.reason_code == "action_result_lineage_mismatch"
        assert root.execution is not None
        assert root.execution.expected_request_id == root.request_id
        assert root.execution.request_id.startswith("request_sha256_")
        assert root.execution.backend.startswith("backend_sha256_")
        assert root.attempt_receipts[0].request_lineage_valid is False
        assert "request:wrong" not in repr(root)
        assert root.acquisition is not None and root.acquisition.attempts == 1
        assert session.execution_count == 1
        assert session.observation_count == 2
        assert tuple(item.origin for item in root.acquisition_attempts) == (
            AcquisitionOrigin.POST_ACTION,
        )

    asyncio.run(scenario())


def test_foreign_execution_identity_is_private_across_transition_and_turn() -> None:
    marker = "PRIVATE_CREDENTIAL_SELECTOR"

    async def scenario() -> None:
        result = ActionResult(marker, DispatchStatus.SENT, marker, True)
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [result]),
            _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.reason_code == "action_result_lineage_mismatch"
        assert marker not in repr(root)
        assert marker not in repr(root.as_turn())
        assert marker not in repr(session.snapshot_partial_episode())
        assert root.execution is not None
        assert root.execution.request_id.startswith("request_sha256_")
        assert root.execution.backend.startswith("backend_sha256_")

    asyncio.run(scenario())


def test_matching_private_backend_identity_is_always_opaque_in_transition() -> None:
    marker = "PRIVATE_CREDENTIAL_SELECTOR"

    async def scenario() -> None:
        before = _world("before", False)
        after = _world("after", True)
        binding = replace(before.bindings[0], executor_id=marker)
        source = replace(before.sources[0], bindings=(binding,))
        before = replace(before, bindings=(binding,), sources=(source,))
        result = ActionResult("*", DispatchStatus.SENT, marker, True)
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            StaticEnvironment([before, after], [result]), _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.status is AgentLoopStatus.DONE
        assert marker not in repr(root)
        assert marker not in repr(root.as_turn())
        assert root.execution is not None
        assert root.execution.backend.startswith("backend_sha256_")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid", (True, -1, 1.5, float("nan"), float("inf"), "1")
)
def test_invalid_probe_metadata_fails_closed_without_polluting_counts(invalid) -> None:
    async def scenario() -> None:
        result = ActionResult(
            "*", DispatchStatus.SENT, "dom", True,
            adapter_evidence={"currentness_probe_count": invalid},
        )
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [result]),
            _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.status is AgentLoopStatus.FAILED
        assert terminal.reason_code == "invalid_currentness_probe_count"
        assert session.currentness_probe_count == 0
        assert root.execution is not None
        assert root.execution.currentness_probe_count == 0

    asyncio.run(scenario())
