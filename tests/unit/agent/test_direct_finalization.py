from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from affordance_runtime.agent.decisions import (
    FinalResponse,
    PublicArtifactDraft,
    PublicArtifactItemDraft,
)
from affordance_runtime.agent.finalization import FinalizationProtocolResult
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.benchmarks.target_loop.outcome_checkpoint import (
    OfficialOutcomeCheckpointRecorder,
    PersistenceStatus,
)
from affordance_runtime.benchmarks.target_loop.result_store import SQLiteRunResultStore
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.invocation import (
    TaskEvaluationStage,
    TaskEvaluationUnavailableError,
    Unavailable,
    task_evaluation_diagnostic_from_exception,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import AcquisitionOrigin
from affordance_runtime.world.finalization import (
    PLAIN_TEXT_FINAL_RESPONSE_CODEC,
    EnvironmentFinalization,
    FinalResponseCodec,
)
from tests.support.agent.core_loop_support import SharedActionOutcomeProjector, shared_world
from tests.support.observation_acquisition import acquired_acquisition


@dataclass
class FinalResponsePolicy:
    content: str
    artifact: PublicArtifactDraft | None = None
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        return FinalResponse(context.context_id, self.content, artifact=self.artifact)


@dataclass
class TerminalEvaluator:
    terminal_observation_id: str
    calls: list[str] = field(default_factory=list)

    async def evaluate(self, task, observation):
        self.calls.append(observation.observation_id)
        status = (
            TaskEvaluationStatus.COMPLETE
            if observation.observation_id == self.terminal_observation_id
            else TaskEvaluationStatus.INCOMPLETE
        )
        refs = (observation.facts[0].fact_id,) if status is TaskEvaluationStatus.COMPLETE else ()
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            status.value,
            completion_evidence_refs=refs,
        )


@dataclass
class BlockedAfterStopEvaluator:
    terminal_observation_id: str
    calls: list[str] = field(default_factory=list)

    async def evaluate(self, task, observation):
        self.calls.append(observation.observation_id)
        status = (
            TaskEvaluationStatus.BLOCKED
            if observation.observation_id == self.terminal_observation_id
            else TaskEvaluationStatus.INCOMPLETE
        )
        return TaskEvaluation(task.task_id, observation.observation_id, status, status.value)


@dataclass
class OutcomeSink:
    evaluations: list[TaskEvaluation] = field(default_factory=list)

    def native_evaluator_returned(self, evaluation):
        self.evaluations.append(evaluation)


@dataclass
class FinalizingEnvironment:
    wrapped: ScriptedEnvironment
    post_world: object
    dispatch_status: DispatchStatus
    finalize_calls: list[str] = field(default_factory=list)
    final_response_codec: FinalResponseCodec = PLAIN_TEXT_FINAL_RESPONSE_CODEC

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    @property
    def supports_finalization(self) -> bool:
        return True

    async def finalize(self, content: str) -> EnvironmentFinalization:
        self.finalize_calls.append(content)
        return EnvironmentFinalization(
            ActionResult(
                "final-response",
                self.dispatch_status,
                "fixture",
                self.dispatch_status is DispatchStatus.SENT,
                None if self.dispatch_status is DispatchStatus.SENT else ActionError.EXECUTION_FAILED,
            ),
            acquired_acquisition(self.post_world, AcquisitionOrigin.POST_ACTION),
        )


@pytest.mark.parametrize("dispatch_status", [DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN])
def test_final_response_sends_once_then_uses_one_fresh_native_evaluation(dispatch_status) -> None:
    before = shared_world("final-before", False)
    after = shared_world("final-after", True)
    policy = FinalResponsePolicy("done")
    evaluator = TerminalEvaluator(after.observation_id)
    sink = OutcomeSink()
    environment = FinalizingEnvironment(ScriptedEnvironment(before), after, dispatch_status)
    runtime = TargetRuntime(
        AgentDecisionPorts(policy),
        SharedActionOutcomeProjector(),
        evaluator,
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
        official_outcome_sink=sink,
    )

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:final", "Return the answer.")))

    assert state.status is RunStatus.DONE
    assert state.current_world.observation_id == after.observation_id
    assert policy.calls == 1
    assert environment.finalize_calls == ["done"]
    assert evaluator.calls == [before.observation_id, after.observation_id]
    assert sink.evaluations == [state.current_task_evaluation]
    assert state.execution_count == 0
    assert state.finalization is not None
    assert state.finalization.stop_send_count == 1
    assert state.finalization.post_stop_capture_count == 1
    assert state.finalization.native_evaluator_count == 1


def test_public_artifact_sidecar_does_not_change_stop_bytes_or_native_evaluation_order() -> None:
    before = shared_world("artifact-before", False)
    after = shared_world("artifact-after", True)
    artifact = PublicArtifactDraft(
        "Result",
        items=(
            PublicArtifactItemDraft(
                "Current state",
                evidence_refs=("fact:artifact-before:enabled",),
            ),
        ),
        evidence_refs=("fact:artifact-before:enabled",),
    )

    def run(draft):
        evaluator = TerminalEvaluator(after.observation_id)
        environment = FinalizingEnvironment(
            ScriptedEnvironment(before),
            after,
            DispatchStatus.SENT,
        )
        runtime = TargetRuntime(
            AgentDecisionPorts(FinalResponsePolicy("same evaluator bytes", draft)),
            SharedActionOutcomeProjector(),
            evaluator,
            goal_compiler=NotRequiredGoalCompiler("artifact_parity_test"),
        )
        state = asyncio.run(
            runtime.run_task(environment, TaskGoal("task:artifact-parity", "Return the answer."))
        )
        return state, environment.finalize_calls, evaluator.calls

    plain_state, plain_bytes, plain_order = run(None)
    artifact_state, artifact_bytes, artifact_order = run(artifact)

    assert plain_state.status is artifact_state.status is RunStatus.DONE
    assert plain_bytes == artifact_bytes == ["same evaluator bytes"]
    assert plain_order == artifact_order == [before.observation_id, after.observation_id]
    assert plain_state.last_step is not None and plain_state.last_step.public_artifact is None
    assert artifact_state.last_step is not None
    assert artifact_state.last_step.public_artifact is not None
    assert artifact_state.last_step.public_artifact.links == ()


def test_invalid_final_response_representation_never_sends_stop() -> None:
    class InvalidCodec:
        def normalize(self, content: str) -> str:
            del content
            raise ValueError("invalid native response")

    before = shared_world("invalid-final-before", False)
    after = shared_world("invalid-final-after", True)
    environment = FinalizingEnvironment(
        ScriptedEnvironment(before),
        after,
        DispatchStatus.SENT,
        final_response_codec=InvalidCodec(),
    )
    task = TaskGoal("task:invalid-final", "Return a number.")
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("not-a-number")),
        SharedActionOutcomeProjector(),
        TerminalEvaluator(after.observation_id),
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
    )

    state = asyncio.run(runtime.run_task(environment, task))

    assert state.status is RunStatus.FAILED
    assert state.last_step is not None
    assert state.last_step.feedback == "final_response_invalid"
    assert environment.finalize_calls == []
    assert state.finalization is None


def test_final_response_codec_canonical_content_is_the_only_content_sent() -> None:
    class CanonicalCodec:
        def normalize(self, content: str) -> str:
            assert content == "raw"
            return '{"canonical":true}'

    before = shared_world("canonical-final-before", False)
    after = shared_world("canonical-final-after", True)
    environment = FinalizingEnvironment(
        ScriptedEnvironment(before),
        after,
        DispatchStatus.SENT,
        final_response_codec=CanonicalCodec(),
    )
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("raw")),
        SharedActionOutcomeProjector(),
        TerminalEvaluator(after.observation_id),
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
    )

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:canonical-final", "Answer.")))

    assert state.status is RunStatus.DONE
    assert environment.finalize_calls == ['{"canonical":true}']


def test_native_incomplete_after_stop_is_terminal_failure_and_durable_official_outcome() -> None:
    before = shared_world("incomplete-before", False)
    after = shared_world("incomplete-after", False)
    evaluator = TerminalEvaluator("some-other-observation")
    sink = OutcomeSink()
    environment = FinalizingEnvironment(ScriptedEnvironment(before), after, DispatchStatus.SENT)
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("done")),
        SharedActionOutcomeProjector(),
        evaluator,
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
        official_outcome_sink=sink,
    )

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:incomplete-final", "Answer.")))

    assert state.status is RunStatus.FAILED
    assert environment.finalize_calls == ["done"]
    assert evaluator.calls == [before.observation_id, after.observation_id]
    assert sink.evaluations == [state.current_task_evaluation]
    assert state.finalization is not None
    assert state.finalization.native_evaluation_status is TaskEvaluationStatus.INCOMPLETE


def test_native_blocked_after_stop_enters_durable_official_sink_exactly_once(tmp_path) -> None:
    before = shared_world("blocked-before", False)
    after = shared_world("blocked-after", False)
    evaluator = BlockedAfterStopEvaluator(after.observation_id)
    trace = RunTraceRecorder(tmp_path / "trace")
    sink = OfficialOutcomeCheckpointRecorder(
        "case:blocked-final",
        SQLiteRunResultStore(tmp_path / "results.sqlite3"),
        trace,
    )
    environment = FinalizingEnvironment(ScriptedEnvironment(before), after, DispatchStatus.SENT)
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("done")),
        SharedActionOutcomeProjector(),
        evaluator,
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
        official_outcome_sink=sink,
    )

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:blocked-final", "Answer.")))

    assert state.status is RunStatus.BLOCKED
    assert evaluator.calls == [before.observation_id, after.observation_id]
    assert sink.persistence_status is PersistenceStatus.COMMITTED
    assert sink.durable_checkpoint is not None
    assert sink.durable_checkpoint.evaluation_status is TaskEvaluationStatus.BLOCKED
    assert [event["event"] for event in trace.events].count("native_evaluator_returned") == 1
    assert state.finalization is not None
    assert state.finalization.native_evaluation_status is TaskEvaluationStatus.BLOCKED


def test_native_evaluator_exception_is_typed_and_durably_traced_without_unknown(tmp_path) -> None:
    before = shared_world("evaluator-failure-before", False)
    after = shared_world("evaluator-failure-after", False)

    class FailingAfterStopEvaluator(TerminalEvaluator):
        async def evaluate(self, task, observation):
            if observation.observation_id == after.observation_id:
                raise ValueError("projection failed for token=secret-value")
            return await super().evaluate(task, observation)

    trace = RunTraceRecorder(tmp_path / "trace")
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("done")),
        SharedActionOutcomeProjector(),
        FailingAfterStopEvaluator("never"),
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
        trace_sink=trace,
    )
    environment = FinalizingEnvironment(ScriptedEnvironment(before), after, DispatchStatus.SENT)

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:evaluator-failure", "Answer.")))

    assert state.status is RunStatus.FAILED
    assert state.current_task_evaluation is None
    assert state.runtime_failure is not None
    assert state.runtime_failure.stage.value == "evaluation"
    assert state.runtime_failure.kind.value == "internal"
    events = [event for event in trace.events if event["event"] == "native_evaluator_failed"]
    assert len(events) == 1
    assert events[0]["phase"] == "evaluator_call"
    assert events[0]["exception_type"] == "ValueError"
    assert events[0]["observation_id"] == after.observation_id
    assert "secret-value" not in events[0]["safe_message"]
    assert not [event for event in trace.events if event["event"] == "native_evaluator_returned"]


def test_native_evaluator_unavailable_is_typed_and_never_enters_official_sink(tmp_path) -> None:
    before = shared_world("evaluator-unavailable-before", False)
    after = shared_world("evaluator-unavailable-after", False)

    class UnavailableAfterStopEvaluator(TerminalEvaluator):
        async def evaluate(self, task, observation):
            if observation.observation_id == after.observation_id:
                error = RuntimeError("native evaluator dependency unavailable")
                raise TaskEvaluationUnavailableError(
                    Unavailable(
                        "native_evaluator_unavailable",
                        task_evaluation_diagnostic_from_exception(
                            error,
                            stage=TaskEvaluationStage.EVALUATOR_CALL,
                            observation_id=observation.observation_id,
                        ),
                    )
                )
            return await super().evaluate(task, observation)

    trace = RunTraceRecorder(tmp_path / "trace")
    sink = OutcomeSink()
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("done")),
        SharedActionOutcomeProjector(),
        UnavailableAfterStopEvaluator("never"),
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
        official_outcome_sink=sink,
        trace_sink=trace,
    )
    environment = FinalizingEnvironment(ScriptedEnvironment(before), after, DispatchStatus.SENT)

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:evaluator-unavailable", "Answer.")))

    assert state.status is RunStatus.FAILED
    assert state.current_task_evaluation is None
    assert state.runtime_failure is not None
    assert state.runtime_failure.kind.value == "capability_unavailable"
    assert sink.evaluations == []
    failures = [event for event in trace.events if event["event"] == "native_evaluator_failed"]
    assert len(failures) == 1
    assert failures[0]["outcome"] == "unavailable"
    assert failures[0]["code"] == "native_evaluator_unavailable"


def test_finalization_protocol_rejects_facts_after_unsent_stop() -> None:
    with pytest.raises(ValueError, match="unsent STOP"):
        FinalizationProtocolResult(
            DispatchStatus.NOT_SENT,
            post_stop_observation_id="post-stop",
        )
    with pytest.raises(ValueError, match="unsent STOP"):
        FinalizationProtocolResult(
            DispatchStatus.NOT_SENT,
            native_evaluator_invoked=True,
            native_evaluation_status=TaskEvaluationStatus.INCOMPLETE,
        )


def test_finalization_protocol_requires_capture_before_native_evaluation() -> None:
    with pytest.raises(ValueError, match="requires one evaluator invocation"):
        FinalizationProtocolResult(
            DispatchStatus.SENT,
            post_stop_observation_id="post-stop",
        )
    with pytest.raises(ValueError, match="captured post-STOP World"):
        FinalizationProtocolResult(
            DispatchStatus.SENT,
            native_evaluator_invoked=True,
            native_evaluation_status=TaskEvaluationStatus.COMPLETE,
        )
    with pytest.raises(ValueError, match="requires one evaluator invocation"):
        FinalizationProtocolResult(
            DispatchStatus.SENT,
            post_stop_observation_id="post-stop",
            native_evaluation_status=TaskEvaluationStatus.COMPLETE,
        )


def test_finalization_protocol_rejects_untyped_and_contradictory_owner_facts() -> None:
    for invalid_invoked in (1, "yes"):
        with pytest.raises(TypeError, match="must be boolean"):
            FinalizationProtocolResult(
                DispatchStatus.SENT,
                post_stop_observation_id="post-stop",
                native_evaluator_invoked=invalid_invoked,  # type: ignore[arg-type]
            )
    with pytest.raises(TypeError, match="observation id"):
        FinalizationProtocolResult(
            DispatchStatus.SENT,
            post_stop_observation_id=42,  # type: ignore[arg-type]
            native_evaluator_invoked=True,
        )
    with pytest.raises(TypeError, match="status must be typed"):
        FinalizationProtocolResult(
            DispatchStatus.SENT,
            post_stop_observation_id="post-stop",
            native_evaluator_invoked=True,
            native_evaluation_status="bogus",  # type: ignore[arg-type]
        )

    before = shared_world("lineage-before", False)
    after = shared_world("lineage-after", False)
    evaluation = TaskEvaluation(
        "task:lineage",
        after.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "incomplete",
    )
    with pytest.raises(ValueError, match="after-world"):
        StepResult(
            FinalResponse("context:lineage", "done"),
            before,
            after,
            evaluation,
            RunStatus.FAILED,
            feedback="lineage",
            finalization=FinalizationProtocolResult(
                DispatchStatus.SENT,
                "different-world",
                native_evaluator_invoked=True,
                native_evaluation_status=TaskEvaluationStatus.INCOMPLETE,
            ),
        )
    with pytest.raises(ValueError, match="cannot advance"):
        StepResult(
            FinalResponse("context:lineage", "done"),
            before,
            after,
            evaluation,
            RunStatus.FAILED,
            feedback="missing capture",
            finalization=FinalizationProtocolResult(DispatchStatus.SENT),
        )
    with pytest.raises(ValueError, match="contradicts run status"):
        StepResult(
            FinalResponse("context:lineage", "done"),
            before,
            after,
            evaluation,
            RunStatus.DONE,
            feedback="wrong terminal status",
            finalization=FinalizationProtocolResult(
                DispatchStatus.SENT,
                after.observation_id,
                native_evaluator_invoked=True,
                native_evaluation_status=TaskEvaluationStatus.INCOMPLETE,
            ),
        )
    with pytest.raises(ValueError, match="current task evaluation"):
        RunState(
            after,
            evaluation,
            0,
            status=RunStatus.FAILED,
            finalization=FinalizationProtocolResult(
                DispatchStatus.SENT,
                after.observation_id,
                native_evaluator_invoked=True,
                native_evaluation_status=TaskEvaluationStatus.COMPLETE,
            ),
        )
    with pytest.raises(ValueError, match="contradicts run status"):
        RunState(
            after,
            evaluation,
            0,
            status=RunStatus.DONE,
            finalization=FinalizationProtocolResult(
                DispatchStatus.SENT,
                after.observation_id,
                native_evaluator_invoked=True,
                native_evaluation_status=TaskEvaluationStatus.INCOMPLETE,
            ),
        )


def test_final_response_transport_exception_fails_without_retry() -> None:
    before = shared_world("send-failure-before", False)

    class FailingEnvironment(FinalizingEnvironment):
        async def finalize(self, content: str) -> EnvironmentFinalization:
            self.finalize_calls.append(content)
            raise RuntimeError("transport failed")

    environment = FailingEnvironment(ScriptedEnvironment(before), before, DispatchStatus.NOT_SENT)
    runtime = TargetRuntime(
        AgentDecisionPorts(FinalResponsePolicy("done")),
        SharedActionOutcomeProjector(),
        TerminalEvaluator("never"),
        goal_compiler=NotRequiredGoalCompiler("direct_finalization_test"),
    )

    state = asyncio.run(runtime.run_task(environment, TaskGoal("task:send-failure", "Answer.")))

    assert state.status is RunStatus.FAILED
    assert state.last_step is not None
    assert state.last_step.feedback == "final_response_send_failed"
    assert environment.finalize_calls == ["done"]
    assert state.finalization is not None
    assert state.finalization.stop_send_count == 0
