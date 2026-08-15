"""Exceptional-path witnesses for the canonical control-transition contract."""

from __future__ import annotations

import asyncio
import math
from dataclasses import replace

import pytest

from affordance_runtime.agent import AgentLoop, AgentLoopStatus, RequestObservation
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    EvaluationInterruption,
    EvaluationInterruptionReason,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import (
    ActionDispatchCancelled,
    ActionError,
    ActionResult,
    DispatchStatus,
)
from affordance_runtime.world import WorldFusion
from tests.integration.agent.test_agent_loop import (
    ScriptedPolicy,
    SharedActionEvaluator,
    SharedTaskEvaluator,
    _loop,
    _sent,
    _task,
    _world,
)


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
            if stage == "action"
            else SharedActionEvaluator()
        )
        task_evaluator = (
            SecondCallTaskEvaluator(RuntimeError("private evaluator detail"))
            if stage == "task"
            else SharedTaskEvaluator()
        )
        session = await (AgentLoop(ScriptedPolicy(["first"]), action_evaluator, task_evaluator)).start(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[_sent()],
            ),
            _task(),
        )

        with pytest.raises(RuntimeError, match="private evaluator detail"):
            await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert root.resulting_status is AgentLoopStatus.FAILED
        assert root.reason_code == "runtime_exception"
        assert root.execution is not None
        assert root.execution.result.dispatch_status is DispatchStatus.SENT
        if stage == "task":
            assert root.action_evaluation is not None
            assert root.action_evaluation.after_observation_id == "after"
        assert root.after_observation_id == "after"
        assert len(root.acquisition_attempts) == 1
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
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[_sent()],
            ),
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


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("invalid task evaluation"),
        RuntimeError("task evaluator failed"),
        asyncio.CancelledError(),
    ],
)
def test_observation_evaluation_interruption_retains_exact_trigger(exc: BaseException) -> None:
    async def scenario() -> None:
        decision = RequestObservation(
            "context:test",
            "criterion_verification",
            "current_world",
            "",
            "refresh",
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(_world("fresh", False),),
        )
        session = await (
            AgentLoop(
                ScriptedPolicy([decision]),
                SharedActionEvaluator(),
                SecondCallTaskEvaluator(exc),
            )
        ).start(environment, _task())

        if isinstance(exc, ValueError):
            await session.run_until_pause()
        else:
            with pytest.raises(type(exc)):
                await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert isinstance(root.evaluation, EvaluationInterruption)
        assert root.evaluation.execution is None
        assert root.evaluation.observation_trigger is root.evaluation.consumed_acquisition
        assert root.evaluation.observation_trigger in root.acquisition_attempts
        assert root.evaluation.after_observation is root.after_observation
        assert root.evaluation.action_evaluation is None
        assert root.evaluation.reason_code in {
            EvaluationInterruptionReason.TASK_CANCELLED,
            EvaluationInterruptionReason.TASK_INVALID,
            EvaluationInterruptionReason.TASK_CALL_FAILED,
        }
        with pytest.raises(TypeError, match="reason must be typed"):
            replace(root.evaluation, reason_code="not_actually_cancelled")
        with pytest.raises(ValueError, match="task trigger"):
            replace(root.evaluation, reason_code=EvaluationInterruptionReason.ACTION_INVALID)

    asyncio.run(scenario())


def test_execute_exception_latches_terminal_session_without_duplicate_dispatch() -> None:
    exc = RuntimeError("execute failed")

    class RaisingEnvironment(ScriptedEnvironment):
        async def execute(self, request):
            self.execute_calls += 1
            self.executed_requests.append(request)
            raise exc

    async def scenario() -> None:
        policy = ScriptedPolicy(["first"])
        environment = RaisingEnvironment(initial_observation=_world("before", False))
        session = await (_loop(policy)).start(environment, _task())
        with pytest.raises(type(exc)):
            await session.run_until_pause()

        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal is session.last_result
        assert terminal.status is AgentLoopStatus.FAILED
        assert root.reason_code == "runtime_exception"
        assert policy.decisions == []
        assert environment.execute_calls == 1
        assert session.state.control_transition_total_count == 1
        assert terminal.runtime_failure is not None
        assert terminal.runtime_failure.stage is FailureStage.EXECUTION
        assert terminal.runtime_failure.root_id == root.transition_id
        assert terminal.runtime_failure.attempt_id == root.attempt_receipts[-1].attempt_id

    asyncio.run(scenario())


@pytest.mark.parametrize("crossed_dispatch", [False, True])
def test_execute_cancellation_closes_exact_outcome_before_propagation(
    crossed_dispatch: bool,
) -> None:
    def cancel(request, observation):
        del observation
        if not crossed_dispatch:
            raise asyncio.CancelledError
        raise ActionDispatchCancelled(
            ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                request.binding.executor_id,
                False,
                ActionError.CANCELLED,
            )
        )

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            execute_fn=cancel,
        )
        session = await (_loop(ScriptedPolicy(["first"]))).start(environment, _task())

        with pytest.raises(asyncio.CancelledError):
            await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert root.resulting_status is AgentLoopStatus.CANCELLED
        assert root.execution is not None
        assert root.execution.request is environment.adapter.executed_requests[0]
        assert root.execution.result.error is ActionError.CANCELLED
        assert root.execution.result.dispatch_status is (
            DispatchStatus.SENT_UNKNOWN if crossed_dispatch else DispatchStatus.NOT_SENT
        )
        if crossed_dispatch:
            assert root.execution.post_acquisition is not None
            assert root.execution.post_acquisition in root.acquisition_attempts
        else:
            assert root.execution.post_acquisition is None
            assert root.acquisition_attempts == ()
        assert root.attempt_receipts[-1].disposition.value == "cancelled"

    asyncio.run(scenario())


def test_foreign_execute_exception_name_cannot_break_physical_accounting() -> None:
    foreign_error = type("Execute.Error!" * 12, (Exception,), {})("private execute detail")

    class RaisingEnvironment(ScriptedEnvironment):
        async def execute(self, request):
            self.execute_calls += 1
            self.executed_requests.append(request)
            raise foreign_error

    async def scenario() -> None:
        environment = RaisingEnvironment(initial_observation=_world("before", False))
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            environment,
            _task(),
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
        session = await (
            AgentLoop(
                RaisingPolicy() if component == "policy" else ScriptedPolicy(["first"]),
                SharedActionEvaluator(),
                RaisingInitialTaskEvaluator() if component == "initial_task_evaluator" else SharedTaskEvaluator(),
            )
        ).start(ScriptedEnvironment(initial_observation=_world("before", False)), _task())
        with pytest.raises(TimeoutError if component == "policy" else RuntimeError):
            await session.run_until_pause()
        assert session.last_result is not None
        failure = session.last_result.runtime_failure
        assert failure is not None
        assert failure.stage is (FailureStage.POLICY if component == "policy" else FailureStage.EVALUATION)
        assert failure.kind is FailureKind.CALL_FAILED
        assert not failure.root_id and not failure.attempt_id
        assert failure.exception_class in {"TimeoutError", "RuntimeError"}

    asyncio.run(scenario())


def test_malformed_execute_return_is_one_failed_physical_attempt() -> None:
    class MalformedEnvironment(ScriptedEnvironment):
        async def execute(self, request):
            self.execute_calls += 1
            self.executed_requests.append(request)
            return object()

    async def scenario() -> None:
        environment = MalformedEnvironment(initial_observation=_world("before", False))
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            environment,
            _task(),
        )
        with pytest.raises(TypeError, match="malformed contract"):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert environment.execute_calls == 1
        assert session.execution_count == 1
        assert len(root.attempt_receipts) == 1
        assert root.attempt_receipts[0].disposition.value == "malformed"

    asyncio.run(scenario())


def test_execute_boundary_rejects_substituted_request_authority() -> None:
    class SubstitutingEnvironment(ScriptedEnvironment):
        async def execute(self, request):
            outcome = await super().execute(request)
            return replace(
                outcome,
                request=replace(outcome.request, timeout_ms=outcome.request.timeout_ms + 1),
            )

    async def scenario() -> None:
        environment = SubstitutingEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=[_sent()],
        )
        session = await (_loop(ScriptedPolicy(["first"]))).start(environment, _task())

        with pytest.raises(TypeError, match="malformed contract"):
            await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert environment.execute_calls == 1
        assert root.execution is None
        assert root.attempt_receipts[-1].disposition.value == "malformed"

    asyncio.run(scenario())


def test_capture_boundary_rejects_substituted_request_authority() -> None:
    class SubstitutingEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            acquisition = await super().capture(request)
            return replace(
                acquisition,
                request=replace(request, reason=f"{request.reason} substituted"),
            )

    async def scenario() -> None:
        decision = RequestObservation(
            "context:test",
            "criterion_verification",
            "current_world",
            "",
            "refresh",
        )
        environment = SubstitutingEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(_world("fresh", False),),
        )
        session = await (_loop(ScriptedPolicy([decision]))).start(environment, _task())

        with pytest.raises(TypeError, match="malformed contract"):
            await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert environment.capture_calls == 1
        assert root.acquisition_attempts == ()
        assert root.attempt_receipts[-1].disposition.value == "malformed"

    asyncio.run(scenario())


def test_lineage_mismatch_preserves_truth_without_foreign_identity_material() -> None:
    async def scenario() -> None:
        result = ActionResult("request:wrong", DispatchStatus.SENT, "dom", True)
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[result],
            ),
            _task(),
        )
        with pytest.raises(ValueError, match="lineage"):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert root.execution is None
        assert root.attempt_receipts[0].disposition.value == "threw"
        assert "request:wrong" not in repr(root)
        assert session.execution_count == 1
        assert session.observation_count == 1
        assert root.acquisition_attempts == ()

    asyncio.run(scenario())


def test_foreign_execution_identity_is_private_across_transition_and_turn() -> None:
    marker = "PRIVATE_CREDENTIAL_SELECTOR"

    async def scenario() -> None:
        result = ActionResult(marker, DispatchStatus.SENT, marker, True)
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[result],
            ),
            _task(),
        )
        with pytest.raises(ValueError, match="lineage"):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert marker not in repr(root)
        assert marker not in repr(session.snapshot_partial_episode())
        assert root.execution is None

    asyncio.run(scenario())


def test_matching_private_backend_identity_is_always_opaque_in_transition() -> None:
    marker = "PRIVATE_CREDENTIAL_SELECTOR"

    async def scenario() -> None:
        before = _world("before", False)
        after = _world("after", True)
        binding = replace(before.bindings[0], executor_id=marker)
        source = replace(before.sources[0], bindings=(binding,))
        fused = WorldFusion().fuse((source,))
        assert fused.observation is not None
        before = fused.observation
        result = ActionResult("*", DispatchStatus.SENT, marker, True)
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            ScriptedEnvironment(initial_observation=before, post_observations=(after,), results=[result]),
            _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.status is AgentLoopStatus.DONE
        assert marker not in repr(root)
        assert root.execution is not None
        assert root.execution.request.binding.executor_id == marker
        assert root.execution.result.backend == marker

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", (True, -1, 1.5, float("nan"), float("inf"), "1"))
def test_invalid_probe_metadata_fails_closed_without_polluting_counts(invalid) -> None:
    async def scenario() -> None:
        result = ActionResult(
            "*",
            DispatchStatus.SENT,
            "dom",
            True,
            adapter_evidence={"currentness_probe_count": invalid},
        )
        session = await (_loop(ScriptedPolicy(["first"]))).start(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[result],
            ),
            _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.status is AgentLoopStatus.FAILED
        assert terminal.reason_code == "invalid_currentness_probe_count"
        assert session.currentness_probe_count == 0
        assert root.execution is not None
        retained = root.execution.result.adapter_evidence["currentness_probe_count"]
        assert math.isnan(retained) if isinstance(invalid, float) and math.isnan(invalid) else retained == invalid
        assert root.attempt_receipts[0].currentness_probe_count == 0

    asyncio.run(scenario())
