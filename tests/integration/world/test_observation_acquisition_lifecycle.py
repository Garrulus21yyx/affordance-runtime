import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest

from affordance_runtime.actions import ActionBinder, ActionSpaceBuilder
from affordance_runtime.agent import (
    Abort,
    AgentFailureCode,
    AgentLoop,
    AgentSessionStartError,
)
from affordance_runtime.agent.context.acquisition_projection import project_acquisition_offers
from affordance_runtime.agent.observation_control import (
    capture_fresh,
    post_action_fallback_result,
    validate_fresh_acquisition,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus, ExecutionOutcome
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionReason,
    AcquisitionReasonKind,
    AcquisitionStage,
    AcquisitionStatus,
    ObservationAssurance,
    ObservationCapabilities,
    ObservationModality,
    ObservationNeed,
    ObservationOffer,
    ObservationPurpose,
    ObservationRequestKind,
    WorldObservation,
    WorldObservationRequest,
)
from tests.integration.agent.test_agent_loop import _task as _action_task
from tests.integration.agent.test_agent_loop import _world as _action_world
from tests.support.observation_acquisition import acquired_acquisition, failed_acquisition
from tests.support.world import fused_world


def _world(identity: str) -> WorldObservation:
    return fused_world(identity, surface="static")


def _task() -> TaskGoal:
    return TaskGoal("task", "Inspect", risk_profile=RiskProfile.READ_ONLY)


def _request():
    world = _action_world("bound", False)
    builder = ActionSpaceBuilder()
    option = builder.build(_action_task(), world).options[0]
    admission = builder.try_admit(option, {}, "")
    assert admission.admitted is not None
    return ActionBinder().bind(admission.admitted, world, "context:test")


def test_acquisition_values_are_frozen_and_enforce_observation_invariant() -> None:
    acquired = acquired_acquisition(_world("one"), AcquisitionOrigin.RESET)
    with pytest.raises(FrozenInstanceError):
        acquired.reason_code = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError):
        replace(acquired, fusion_outcome=None)
    with pytest.raises(ValueError):
        replace(acquired, status=AcquisitionStatus.FAILED)
    with pytest.raises(TypeError, match="status"):
        replace(acquired, status="failed")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="origin"):
        replace(acquired, origin="reset")  # type: ignore[arg-type]


def test_execution_result_and_outcome_algebras_reject_untyped_variants() -> None:
    with pytest.raises(TypeError, match="dispatch status"):
        ActionResult("request:1", "sent", "dom", True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="boolean"):
        ActionResult("request:1", DispatchStatus.SENT, "dom", 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="result"):
        ExecutionOutcome(  # type: ignore[arg-type]
            _request(),
            object(),
            failed_acquisition(AcquisitionOrigin.POST_ACTION, "post_capture_failed"),
        )


@pytest.mark.parametrize(
    "reason",
    ["", "Not_Snake", "contains-url", "selector_failed", "token_exposed", "x" * 65],
)
def test_reason_code_is_bounded_stable_and_private_marker_free(reason: str) -> None:
    with pytest.raises(ValueError):
        AcquisitionReason(
            AcquisitionReasonKind.SOURCE_FAILURE,
            reason,
            AcquisitionStage.SOURCE_ACQUISITION_FAILED,
        )


def test_sent_unknown_and_failed_post_acquisition_preserve_both_truths() -> None:
    request = _request()
    result = ActionResult(
        request.request_id,
        DispatchStatus.SENT_UNKNOWN,
        request.binding.executor_id,
        False,
        ActionError.EXECUTION_FAILED,
    )
    post = failed_acquisition(AcquisitionOrigin.POST_ACTION, "post_capture_failed")
    outcome = ExecutionOutcome(request, result, post)
    assert outcome.result.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert outcome.post_acquisition.status is AcquisitionStatus.FAILED


def test_fallback_keeps_two_linked_exact_acquisitions() -> None:
    primary = acquired_acquisition(
        _world("same"),
        AcquisitionOrigin.POST_ACTION,
        kind=ObservationRequestKind.POST_ACTION_FALLBACK,
        acquisition_id="acquisition:primary",
    )
    fallback = acquired_acquisition(
        _world("fresh"),
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        kind=ObservationRequestKind.POST_ACTION_FALLBACK,
        acquisition_id="acquisition:fallback",
    )
    linked = post_action_fallback_result(
        validate_fresh_acquisition(
            primary,
            "same",
            expected_origin=AcquisitionOrigin.POST_ACTION,
            post_action=True,
        ),
        validate_fresh_acquisition(
            fallback,
            "same",
            expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
        ),
    )

    assert linked.acquisition is primary
    assert linked.linked_fallback is not None
    assert linked.linked_fallback.primary_acquisition_id == primary.acquisition_id
    assert linked.linked_fallback.acquisition is fallback
    assert linked.consumed_acquisition is fallback


def test_offers_are_empty_when_independent_capture_is_false() -> None:
    capabilities = ObservationCapabilities(
        False,
        True,
        (ObservationOffer("dom", "structural", "structural", "low"),),
    )
    assert project_acquisition_offers(capabilities) == ()


def test_static_environment_uses_distinct_reset_capture_and_post_queues() -> None:
    initial, captured, after = _world("initial"), _world("captured"), _world("after")
    environment = ScriptedEnvironment(
        initial_observation=initial,
        independent_observations=(captured,),
        post_observations=(after,),
    )

    async def scenario() -> None:
        reset = await environment.reset(_task())
        capture = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.WAIT_REFRESH,
                "wait refresh",
            )
        )
        assert reset.observation == initial and capture.observation == captured
        assert environment.reset_calls == 1 and environment.capture_calls == 1

    asyncio.run(scenario())


class _NeverActionEvaluator:
    async def evaluate(self, *args):
        raise AssertionError("no action should be evaluated")


class _IncompleteTaskEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "incomplete",
        )


class _AbortPolicy:
    async def decide(self, context):
        return Abort(context.context_id, "stop", "policy")


def test_agent_loop_start_is_the_only_logical_reset_owner() -> None:
    async def scenario() -> None:
        loop = AgentLoop(_AbortPolicy(), _NeverActionEvaluator(), _IncompleteTaskEvaluator())
        runner_environment = ScriptedEnvironment(initial_observation=_world("runner"))
        direct_environment = ScriptedEnvironment(initial_observation=_world("direct"))
        await (loop).run(runner_environment, _task())
        await loop.run(direct_environment, _task())
        assert runner_environment.reset_calls == 1
        assert direct_environment.reset_calls == 1
        assert runner_environment.capture_calls == direct_environment.capture_calls == 0

    asyncio.run(scenario())


def test_non_acquired_initial_result_raises_typed_start_error() -> None:
    class FailedReset(ScriptedEnvironment):
        async def reset(self, task):
            await super().reset(task)
            return failed_acquisition(AcquisitionOrigin.RESET, "initial_capture_failed")

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
    class RaisingReset(ScriptedEnvironment):
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

    class RaisingReset(ScriptedEnvironment):
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
    class MalformedReset(ScriptedEnvironment):
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

    class RaisingReset(ScriptedEnvironment):
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
    class WrongOriginEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            return acquired_acquisition(
                _world("wrong-origin"),
                origin,
                kind=request.kind,
                request=request,
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
    "kind",
    tuple(kind for kind in ObservationRequestKind if kind is not ObservationRequestKind.POLICY_REQUEST),
)
def test_internal_refresh_uses_aggregate_capability_without_offer(kind: ObservationRequestKind) -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(
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


def test_forged_model_offer_cannot_override_environment_capture_authority() -> None:
    forged_projection = project_acquisition_offers(
        ObservationCapabilities(
            True,
            True,
            (ObservationOffer("forged", "structural", "structural", "low"),),
        )
    )
    assert forged_projection

    async def scenario() -> None:
        environment = ScriptedEnvironment(
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
                (
                    ObservationNeed(
                        "test:forged-projection",
                        ObservationPurpose.CURRENTNESS_REFRESH,
                        required_modality=ObservationModality(forged_projection[0].modality),
                        required_assurance=ObservationAssurance(forged_projection[0].assurance),
                    ),
                ),
            ),
        )
        assert acquired.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
        assert acquired.reason_code == "independent_capture_unsupported"
        assert environment.capture_calls == 0

    asyncio.run(scenario())
