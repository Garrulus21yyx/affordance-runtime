import asyncio
from dataclasses import FrozenInstanceError

import pytest

from affordance_runtime.agent import (
    Abort,
    AgentFailureCode,
    AgentLoop,
    AgentSessionStartError,
)
from affordance_runtime.agent.observation_control import capture_fresh, post_action_observation
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
    with pytest.raises(ValueError, match="WorldObservation"):
        ObservationAcquisition(
            AcquisitionStatus.ACQUIRED, AcquisitionOrigin.RESET, object(), "reset_acquired",
        )
    with pytest.raises(TypeError, match="status"):
        ObservationAcquisition(
            "failed", AcquisitionOrigin.RESET, None, "reset_failed",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="origin"):
        ObservationAcquisition(
            AcquisitionStatus.FAILED, "reset", None, "reset_failed",  # type: ignore[arg-type]
        )


def test_execution_result_and_outcome_algebras_reject_untyped_variants() -> None:
    with pytest.raises(TypeError, match="dispatch status"):
        ActionResult("request:1", "sent", "dom", True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="boolean"):
        ActionResult("request:1", DispatchStatus.SENT, "dom", 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="result"):
        ExecutionOutcome(  # type: ignore[arg-type]
            object(),
            ObservationAcquisition(
                AcquisitionStatus.FAILED,
                AcquisitionOrigin.POST_ACTION,
                None,
                "post_capture_failed",
            ),
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
        await (loop).run(runner_environment, _task())
        await loop.run(direct_environment, _task())
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
            await (loop).start(environment, _task())
        assert captured.value.status is AcquisitionStatus.FAILED
        assert captured.value.origin is AcquisitionOrigin.RESET
        assert captured.value.reason_code == "initial_capture_failed"
        assert captured.value.start_evidence.receipt.operation.value == "reset"
        assert captured.value.start_evidence.accounting.observation_attempts == 1
        assert captured.value.start_evidence.accounting.receipt_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", (RuntimeError("private reset detail"), asyncio.CancelledError()))
def test_thrown_reset_failure_carries_privacy_safe_attempt_truth(failure) -> None:
    class RaisingReset(StaticEnvironment):
        async def reset(self, task):
            self.reset_calls += 1
            raise failure

    async def scenario() -> None:
        environment = RaisingReset(initial_observation=_world("unused"))
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        expected = asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else AgentSessionStartError
        with pytest.raises(expected) as captured:
            await (loop).start(environment, _task())
        evidence = captured.value.start_evidence
        assert evidence.receipt.operation.value == "reset"
        assert evidence.receipt.disposition.value in {"threw", "cancelled"}
        assert evidence.accounting.observation_attempts == 1
        assert evidence.accounting.receipt_count == 1
        assert "private reset detail" not in repr(evidence)

    asyncio.run(scenario())


def test_immutable_foreign_reset_exception_is_normalized_without_losing_receipt() -> None:
    class ImmutableError(Exception):
        def __setattr__(self, name, value):
            raise AttributeError("immutable error")

    class RaisingReset(StaticEnvironment):
        async def reset(self, task):
            self.reset_calls += 1
            raise ImmutableError("private reset detail")

    async def scenario() -> None:
        environment = RaisingReset(initial_observation=_world("unused"))
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        with pytest.raises(AgentSessionStartError) as captured:
            await (loop).start(environment, _task())
        assert captured.value.exception_class == "ImmutableError"
        assert captured.value.start_evidence.accounting.receipt_count == 1
        assert isinstance(captured.value.__cause__, ImmutableError)

    asyncio.run(scenario())


def test_malformed_reset_return_is_one_failed_physical_attempt() -> None:
    class MalformedReset(StaticEnvironment):
        async def reset(self, task):
            self.reset_calls += 1
            return object()

    async def scenario() -> None:
        environment = MalformedReset(initial_observation=_world("unused"))
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        with pytest.raises(AgentSessionStartError) as captured:
            await (loop).start(environment, _task())
        evidence = captured.value.start_evidence
        assert environment.reset_calls == 1
        assert evidence.receipt.disposition.value == "malformed"
        assert evidence.accounting.observation_attempts == 1
        assert evidence.accounting.receipt_count == 1

    asyncio.run(scenario())


def test_foreign_reset_exception_name_cannot_break_physical_accounting() -> None:
    foreign_error = type("X" * 129, (Exception,), {})("private reset detail")

    class RaisingReset(StaticEnvironment):
        async def reset(self, task):
            self.reset_calls += 1
            raise foreign_error

    async def scenario() -> None:
        environment = RaisingReset(initial_observation=_world("unused"))
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        with pytest.raises(AgentSessionStartError) as captured:
            await (loop).start(environment, _task())
        evidence = captured.value.start_evidence
        assert environment.reset_calls == 1
        assert evidence.accounting.observation_attempts == 1
        assert evidence.accounting.receipt_count == 1
        assert evidence.receipt.exception_class.startswith("ExceptionClass_")

    asyncio.run(scenario())


@pytest.mark.parametrize("origin", (AcquisitionOrigin.RESET, AcquisitionOrigin.POST_ACTION))
def test_independent_capture_rejects_non_independent_origin(origin: AcquisitionOrigin) -> None:
    class WrongOriginEnvironment(StaticEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            return ObservationAcquisition(
                AcquisitionStatus.ACQUIRED,
                origin,
                _world("wrong-origin"),
                "static_capture_acquired",
            )

    async def scenario() -> None:
        environment = WrongOriginEnvironment(initial_observation=_world("initial"))
        await environment.reset(_task())
        acquired = await capture_fresh(
            environment,
            "initial",
            WorldObservationRequest(ObservationRequestKind.WAIT_REFRESH, "refresh"),
        )
        assert acquired.observation is None
        assert acquired.attempts == 1
        assert acquired.status is AcquisitionStatus.FAILED
        assert acquired.reason_code == "independent_capture_origin_invalid"
        assert acquired.failure_code is AgentFailureCode.OBSERVATION_ORIGIN_INVALID
        assert acquired.expected_origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
        assert acquired.actual_origin is origin
        assert acquired.request_kind is ObservationRequestKind.WAIT_REFRESH
        assert environment.capture_calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("primary_status", "independent", "expected_attempts", "expected_reason"),
    (
        (AcquisitionStatus.CAPABILITY_UNAVAILABLE, (_world("after"),), 1, "static_capture_acquired"),
        (AcquisitionStatus.CAPABILITY_UNAVAILABLE, (), 1, "static_capture_failed"),
        (AcquisitionStatus.FAILED, (), 2, "static_capture_failed"),
    ),
)
def test_post_action_fallback_reports_last_attempt_truth(
    primary_status: AcquisitionStatus,
    independent: tuple[WorldObservation, ...],
    expected_attempts: int,
    expected_reason: str,
) -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            initial_observation=_world("initial"),
            independent_observations=independent,
            repeat_last_observation=False,
        )
        await environment.reset(_task())
        primary = ObservationAcquisition(
            primary_status,
            AcquisitionOrigin.POST_ACTION,
            None,
            "post_action_observation_unavailable"
            if primary_status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
            else "post_action_projection_failed",
        )
        acquired = await post_action_observation(environment, "initial", primary, 2)
        assert acquired.attempts == expected_attempts
        assert acquired.reason_code == expected_reason
        assert acquired.expected_origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
        assert acquired.actual_origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
        assert acquired.request_kind is ObservationRequestKind.POST_ACTION_FALLBACK
        assert environment.capture_calls == 1
        if independent:
            assert acquired.status is AcquisitionStatus.ACQUIRED
            assert acquired.observation is independent[0]
            assert acquired.failure_code is None
        else:
            assert acquired.status is AcquisitionStatus.FAILED
            assert acquired.observation is None
            assert acquired.failure_code is AgentFailureCode.POST_ACTION_ACQUISITION_FAILED

    asyncio.run(scenario())


def test_post_action_fallback_reused_identity_reports_final_freshness_failure() -> None:
    async def scenario() -> None:
        initial = _world("initial")
        environment = StaticEnvironment(
            initial_observation=initial,
            independent_observations=(initial,),
        )
        await environment.reset(_task())
        primary = ObservationAcquisition(
            AcquisitionStatus.CAPABILITY_UNAVAILABLE,
            AcquisitionOrigin.POST_ACTION,
            None,
            "post_action_observation_unavailable",
        )
        acquired = await post_action_observation(environment, "initial", primary, 2)
        assert acquired.observation is None
        assert acquired.attempts == 1
        assert acquired.status is AcquisitionStatus.FAILED
        assert acquired.reason_code == "observation_identity_reused"
        assert acquired.failure_code is AgentFailureCode.POST_ACTION_FRESHNESS_INVALID

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "kind",
    tuple(kind for kind in ObservationRequestKind if kind is not ObservationRequestKind.POLICY_REQUEST),
)
def test_internal_refresh_uses_aggregate_capability_without_offer(kind: ObservationRequestKind) -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            initial_observation=_world("initial"),
            independent_observations=(_world("after"),),
            observation_capabilities=ObservationCapabilities(True, True, ()),
        )
        await environment.reset(_task())
        acquired = await capture_fresh(
            environment,
            "initial",
            WorldObservationRequest(kind, "internal refresh"),
        )
        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert environment.capture_calls == 1

    asyncio.run(scenario())


def test_policy_request_requires_explicit_offer_even_when_projection_is_misleading() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            initial_observation=_world("initial"),
            independent_observations=(_world("after"),),
            observation_capabilities=ObservationCapabilities(True, True, ()),
        )
        await environment.reset(_task())
        acquired = await capture_fresh(
            environment,
            "initial",
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "policy refresh",
                modality="structural",
                required_assurance="structural",
            ),
        )
        assert acquired.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
        assert acquired.reason_code == "observation_capability_not_offered"
        assert environment.capture_calls == 0

    asyncio.run(scenario())


def test_forged_model_offer_cannot_override_environment_capture_authority() -> None:
    forged_projection = project_acquisition_offers(ObservationCapabilities(
        True,
        True,
        (ObservationOffer("forged", "structural", "structural", "low"),),
    ))
    assert forged_projection

    async def scenario() -> None:
        environment = StaticEnvironment(
            initial_observation=_world("initial"),
            independent_observations=(_world("after"),),
            observation_capabilities=ObservationCapabilities(
                False,
                True,
                (ObservationOffer("environment", "structural", "structural", "low"),),
            ),
        )
        await environment.reset(_task())
        acquired = await capture_fresh(
            environment,
            "initial",
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "policy refresh",
                modality=forged_projection[0].modality,
                required_assurance=forged_projection[0].assurance,
            ),
        )
        assert acquired.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
        assert acquired.reason_code == "independent_capture_unsupported"
        assert environment.capture_calls == 0

    asyncio.run(scenario())
