import asyncio
from dataclasses import FrozenInstanceError

import pytest

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentLoop,
    AgentSessionStartError,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.model_boundary.acquisition_projection import project_acquisition_offers
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    CoverageState,
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationOffer,
    ObservationRequestKind,
    WorldObservation,
    WorldObservationRequest,
)


def _world(identity: str) -> WorldObservation:
    return WorldObservation(identity, (), (), (), {"static": CoverageState.COMPLETE})


def _task() -> TaskGoal:
    return TaskGoal("task", "Inspect", risk_profile=RiskProfile.READ_ONLY)


def test_acquisition_values_are_frozen_and_enforce_observation_invariant() -> None:
    acquired = ObservationAcquisition(
        AcquisitionStatus.ACQUIRED, AcquisitionOrigin.RESET, _world("one"), "reset_acquired",
    )
    with pytest.raises(FrozenInstanceError):
        acquired.reason_code = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ObservationAcquisition(
            AcquisitionStatus.ACQUIRED, AcquisitionOrigin.RESET, None, "reset_failed",
        )
    with pytest.raises(ValueError):
        ObservationAcquisition(
            AcquisitionStatus.FAILED, AcquisitionOrigin.RESET, _world("one"), "reset_failed",
        )


@pytest.mark.parametrize(
    "reason",
    ["", "Not_Snake", "contains-url", "selector_failed", "token_exposed", "x" * 65],
)
def test_reason_code_is_bounded_stable_and_private_marker_free(reason: str) -> None:
    with pytest.raises(ValueError):
        ObservationAcquisition(
            AcquisitionStatus.FAILED, AcquisitionOrigin.INDEPENDENT_CAPTURE, None, reason,
        )


def test_sent_unknown_and_failed_post_acquisition_preserve_both_truths() -> None:
    result = ActionResult(
        "request:1", DispatchStatus.SENT_UNKNOWN, "static", False, ActionError.EXECUTION_FAILED,
    )
    post = ObservationAcquisition(
        AcquisitionStatus.FAILED, AcquisitionOrigin.POST_ACTION, None, "post_capture_failed",
    )
    outcome = ExecutionOutcome(result, post)
    assert outcome.result.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert outcome.post_acquisition.status is AcquisitionStatus.FAILED


def test_offers_are_empty_when_independent_capture_is_false() -> None:
    capabilities = ObservationCapabilities(
        False,
        True,
        (ObservationOffer("dom", "structural", "structural", "low"),),
    )
    assert project_acquisition_offers(capabilities) == ()


def test_static_environment_uses_distinct_reset_capture_and_post_queues() -> None:
    initial, captured, after = _world("initial"), _world("captured"), _world("after")
    environment = StaticEnvironment(
        initial_observation=initial,
        independent_observations=(captured,),
        post_observations=(after,),
    )

    async def scenario() -> None:
        reset = await environment.reset(_task())
        capture = await environment.capture(WorldObservationRequest(
            ObservationRequestKind.WAIT_REFRESH, "wait refresh",
        ))
        assert reset.observation is initial and capture.observation is captured
        assert environment.reset_calls == 1 and environment.capture_calls == 1

    asyncio.run(scenario())


class _NeverActionEvaluator:
    async def evaluate(self, *args):
        raise AssertionError("no action should be evaluated")


class _IncompleteTaskEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id, observation.observation_id, TaskEvaluationStatus.INCOMPLETE,
            "incomplete",
        )


class _AbortPolicy:
    async def decide(self, context):
        return Abort(context.context_id, "stop", "policy")


def test_agent_loop_start_is_the_only_logical_reset_owner() -> None:
    async def scenario() -> None:
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        runner_environment = StaticEnvironment(initial_observation=_world("runner"))
        direct_environment = StaticEnvironment(initial_observation=_world("direct"))
        await AgentEpisodeRunner(loop).run(runner_environment, _task())
        await loop.run(_task(), direct_environment)
        assert runner_environment.reset_calls == 1
        assert direct_environment.reset_calls == 1
        assert runner_environment.capture_calls == direct_environment.capture_calls == 0

    asyncio.run(scenario())


def test_non_acquired_initial_result_raises_typed_start_error() -> None:
    class FailedReset(StaticEnvironment):
        async def reset(self, task):
            await super().reset(task)
            return ObservationAcquisition(
                AcquisitionStatus.FAILED, AcquisitionOrigin.RESET, None, "initial_capture_failed",
            )

    async def scenario() -> None:
        environment = FailedReset(initial_observation=_world("unused"))
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        with pytest.raises(AgentSessionStartError) as captured:
            await AgentEpisodeRunner(loop).start(environment, _task())
        assert captured.value.status is AcquisitionStatus.FAILED
        assert captured.value.origin is AcquisitionOrigin.RESET
        assert captured.value.reason_code == "initial_capture_failed"

    asyncio.run(scenario())
