import asyncio
from dataclasses import dataclass, replace

import pytest

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.agent import AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.risk import RiskDecisionKind, RiskPolicy
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.world import (
    AcquisitionOrigin,
    ObservationCapabilities,
    ObservationRequestKind,
    SemanticTarget,
    StateFact,
    WorldObservation,
)
from tests.support.observation_acquisition import acquired_acquisition
from tests.support.world import fused_world


def _world(identity: str, enabled: bool, selector: str, *, risk: ActionRisk = ActionRisk.MEDIUM) -> WorldObservation:
    target = SemanticTarget("shared", "button", "Shared state", {"enabled": enabled})
    binding = ActionBinding(
        f"binding:{identity}",
        identity,
        identity,
        f"revision:{identity}",
        f"fingerprint:{identity}",
        target.target_id,
        target.target_id,
        "dom",
        "dom",
        "activate",
        "click",
        "local_reversible",
        ("shared_state_enabled",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"selector": selector},
        risk=risk,
    )
    fact = StateFact(f"fact:{identity}:enabled", target.target_id, "enabled", enabled, identity)
    return fused_world(identity, (target,), (fact,), (binding,), surface="dom")


def _task() -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.MEDIUM,
    )


@dataclass
class FirstPolicy:
    calls: int = 0

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns = context.history.items
        del task, world, recent_turns
        self.calls += 1
        return SelectAction(context.context_id, action_space.options[0].action_id)


class TaskEvaluator:
    async def evaluate(self, task, observation):
        done = bool(observation.targets[0].state.get("enabled"))
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if done else TaskEvaluationStatus.INCOMPLETE,
            "done" if done else "not done",
            completion_evidence_refs=(observation.facts[0].fact_id,) if done else (),
        )


class ActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        changed = before.targets[0].state.get("enabled") != after.targets[0].state.get("enabled")
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED if changed else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "changed" if changed else "authoritatively unchanged",
            (after.facts[0].fact_id,),
        )


def _loop() -> AgentLoop:
    return AgentLoop(FirstPolicy(), ActionEvaluator(), TaskEvaluator())


def _decision(result, kind=ConfirmationDecisionKind.CONFIRM) -> ConfirmationDecision:
    request = result.confirmation_request
    assert request is not None
    return ConfirmationDecision(request.confirmation_id, request.subject_id, kind)


def test_confirmation_freshly_rebinds_selector_and_executes_once() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("old", False, "#old"),
            independent_observations=(_world("fresh", False, "#fresh"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        policy = FirstPolicy()
        loop = AgentLoop(policy, ActionEvaluator(), TaskEvaluator())
        session = await loop.start(environment, _task())
        paused = await session.run_until_pause()

        assert paused.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert paused.execution_count == 0
        assert paused.confirmation_request is not None
        assert session.state.control_transition_total_count == 1
        root_id = session.state.recent_control_transitions[0].transition_id

        completed = await session.resolve_confirmation(_decision(paused))

        assert completed.status == AgentLoopStatus.DONE
        assert completed.execution_count == 1
        assert len(environment.executed_requests) == 1
        assert environment.executed_requests[0].binding.payload["selector"] == "#fresh"
        assert policy.calls == 1
        assert "#old" not in repr(paused.confirmation_request)
        assert "#fresh" not in repr(paused.confirmation_request)
        assert session.state.control_transition_total_count == 1
        continuation = session.state.latest_control_continuation
        assert continuation is not None
        assert continuation.source_transition_id == root_id
        assert session.state.recent_control_transitions[0].transition_id == root_id

    asyncio.run(scenario())


def test_confirmation_wrong_identity_and_deny_fail_closed_without_execution() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("old", False, "#old"))
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        request = paused.confirmation_request
        assert request is not None

        wrong = await session.resolve_confirmation(
            ConfirmationDecision("confirmation:wrong", request.subject_id, ConfirmationDecisionKind.CONFIRM)
        )
        assert wrong.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert session.state.pending_confirmation is not None
        assert environment.executed_requests == []

        denied_environment = ScriptedEnvironment(initial_observation=_world("old", False, "#old"))
        denied_session = await (_loop()).start(denied_environment, _task())
        denied_pause = await denied_session.run_until_pause()
        denied = await denied_session.resolve_confirmation(_decision(denied_pause, ConfirmationDecisionKind.DENY))
        assert denied.status == AgentLoopStatus.CANCELLED
        assert denied_environment.executed_requests == []
        assert denied_session.state.pending_confirmation is None

    asyncio.run(scenario())


def test_confirmation_observation_budget_exhaustion_closes_original_root() -> None:
    async def scenario() -> None:
        task = replace(_task(), loop_budget=LoopBudget(max_turns=1, max_observations=1))
        environment = ScriptedEnvironment(initial_observation=_world("old", False, "#old"))
        session = await (_loop()).start(environment, task)
        paused = await session.run_until_pause()
        root_id = session.state.recent_control_transitions[0].transition_id

        failed = await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert failed.status is AgentLoopStatus.FAILED
        assert failed.reason_code == "observation_budget_exhausted"
        assert root.transition_id == root_id
        assert root.resulting_status is AgentLoopStatus.FAILED
        assert root.reason_code == "observation_budget_exhausted"
        assert root.pending_kind.value == "none"
        assert session.state.control_transition_total_count == 1
        assert environment.capture_calls == 0
        assert session.approved_confirmation is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failure_kind", "reason_code", "capture_calls"),
    (
        ("unavailable", "independent_capture_unsupported", 0),
        ("failed", "required_source_exhausted", 1),
        ("wrong_origin", "independent_capture_origin_invalid", 1),
        ("stale", "observation_identity_reused", 1),
    ),
)
def test_confirmation_refresh_failure_closes_original_root(
    failure_kind: str,
    reason_code: str,
    capture_calls: int,
) -> None:
    class WrongOriginEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            return acquired_acquisition(
                _world("fresh", False, "#fresh"),
                AcquisitionOrigin.RESET,
                kind=request.kind,
            )

    async def scenario() -> None:
        old = _world("old", False, "#old")
        if failure_kind == "unavailable":
            environment = ScriptedEnvironment(
                initial_observation=old, observation_capabilities=ObservationCapabilities(False, True)
            )
        elif failure_kind == "wrong_origin":
            environment = WrongOriginEnvironment(initial_observation=old)
        elif failure_kind == "stale":
            environment = ScriptedEnvironment(initial_observation=old, independent_observations=(old,))
        else:
            environment = ScriptedEnvironment(initial_observation=old)
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        root_id = session.state.recent_control_transitions[0].transition_id

        failed = await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert failed.status is AgentLoopStatus.FAILED
        assert failed.reason_code == reason_code
        assert root.transition_id == root_id
        assert root.reason_code == reason_code
        assert root.resulting_status is AgentLoopStatus.FAILED
        assert root.after_observation_id == "old"
        assert root.acquisition is not None
        assert root.acquisition.reason_code == reason_code
        assert environment.capture_calls == capture_calls
        assert session.state.control_transition_total_count == 1
        assert session.approved_confirmation is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("fresh_status", "expected_loop_status"),
    (
        (TaskEvaluationStatus.COMPLETE, AgentLoopStatus.DONE),
        (TaskEvaluationStatus.UNKNOWN, AgentLoopStatus.WAITING_USER),
        (TaskEvaluationStatus.BLOCKED, AgentLoopStatus.BLOCKED),
    ),
)
def test_confirmation_fresh_task_terminal_closes_root_without_execution(
    fresh_status: TaskEvaluationStatus,
    expected_loop_status: AgentLoopStatus,
) -> None:
    class FreshStatusEvaluator:
        calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            status = TaskEvaluationStatus.INCOMPLETE if self.calls == 1 else fresh_status
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                status,
                str(status),
                completion_evidence_refs=(observation.facts[0].fact_id,)
                if status is TaskEvaluationStatus.COMPLETE
                else (),
            )

    async def scenario() -> None:
        evaluator = FreshStatusEvaluator()
        environment = ScriptedEnvironment(
            initial_observation=_world("old", False, "#old"),
            independent_observations=(_world("fresh", True, "#fresh"),),
        )
        session = await (AgentLoop(FirstPolicy(), ActionEvaluator(), evaluator)).start(environment, _task())
        paused = await session.run_until_pause()
        root_id = session.state.recent_control_transitions[0].transition_id

        terminal = await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert terminal.status is expected_loop_status
        assert root.transition_id == root_id
        assert root.after_observation_id == "fresh"
        assert root.resulting_status is expected_loop_status
        assert root.reason_code == f"task_{fresh_status}"
        assert root.pending_kind.value == "none"
        assert session.state.control_transition_total_count == 1
        assert environment.execute_calls == 0
        assert session.approved_confirmation is None

    asyncio.run(scenario())


def test_confirmation_subject_change_requires_new_confirmation() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("old", False, "#old"),
            independent_observations=(_world("fresh", False, "#fresh", risk=ActionRisk.HIGH),),
        )
        policy = FirstPolicy()
        loop = AgentLoop(policy, ActionEvaluator(), TaskEvaluator())
        session = await (loop).start(environment, _task())
        paused = await session.run_until_pause()

        changed = await session.resolve_confirmation(_decision(paused))

        assert changed.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert changed.confirmation_request is not None
        assert changed.confirmation_request.subject_id != paused.confirmation_request.subject_id
        assert environment.executed_requests == []
        assert policy.calls == 2

    asyncio.run(scenario())


def test_not_sent_does_not_consume_confirmation_and_freshly_rebinds() -> None:
    async def scenario() -> None:
        attempts = 0

        def execute(request, observation):
            del observation
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return ActionResult(
                    request.request_id,
                    DispatchStatus.NOT_SENT,
                    "dom",
                    False,
                    ActionError.STALE_BINDING,
                )
            return ActionResult(request.request_id, DispatchStatus.SENT, "dom", True)

        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("confirmed", False, "#confirmed"), _world("rebound", False, "#rebound")),
            post_observations=(_world("after", True, "#after"),),
            execute_fn=execute,
        )
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()

        completed = await session.resolve_confirmation(_decision(paused))

        assert completed.status == AgentLoopStatus.DONE
        assert completed.execution_count == 2
        assert attempts == 2
        assert [item.binding.payload["selector"] for item in environment.executed_requests] == [
            "#confirmed",
            "#rebound",
        ]
        root = session.state.recent_control_transitions[0]
        assert [item.dispatch_status for item in root.execution_attempts] == [
            DispatchStatus.NOT_SENT,
            DispatchStatus.SENT,
        ]
        assert len(root.acquisition_attempts) == 3
        assert [item.reason_code for item in root.acquisition_attempts] == [
            "world_acquired",
            "world_acquired",
            "world_acquired",
        ]

    asyncio.run(scenario())


def test_sent_unknown_no_effect_consumes_confirmation_and_waits_without_replay() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("confirmed", False, "#confirmed"),),
            post_observations=(_world("after", False, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT_UNKNOWN, "dom", False, ActionError.EXECUTION_FAILED)],
        )
        session = await (_loop()).start(environment, _task())
        first = await session.run_until_pause()

        second = await session.resolve_confirmation(_decision(first))

        assert second.status == AgentLoopStatus.WAITING_USER
        assert second.execution_count == 1
        assert second.confirmation_request is None
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "exc",
    (RuntimeError("private evaluator error"), asyncio.CancelledError()),
)
def test_confirmed_execution_exception_closes_root_and_propagates(
    exc: BaseException,
) -> None:
    class RaisingEvaluator:
        async def evaluate(self, *args):
            del args
            raise exc

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("confirmed", False, "#confirmed"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await (AgentLoop(FirstPolicy(), RaisingEvaluator(), TaskEvaluator())).start(environment, _task())
        paused = await session.run_until_pause()
        root_id = session.state.recent_control_transitions[0].transition_id

        with pytest.raises(type(exc)):
            await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert root.transition_id == root_id
        assert root.execution is not None
        assert root.execution.dispatch_status is DispatchStatus.SENT
        assert root.after_observation_id == "after"
        assert root.reason_code == (
            "runtime_cancelled" if isinstance(exc, asyncio.CancelledError) else "runtime_exception"
        )
        assert root.pending_kind.value == "none"
        assert session.execution_count == 1
        assert session.observation_count == 3
        assert session.approved_confirmation is None

    asyncio.run(scenario())


def test_sent_unknown_unknown_waits_for_user_and_never_replays() -> None:
    class UnknownEvaluator:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.UNKNOWN,
                "coverage is insufficient",
            )

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("confirmed", False, "#confirmed"),),
            post_observations=(_world("after", False, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT_UNKNOWN, "dom", False, ActionError.EXECUTION_FAILED)],
        )
        loop = AgentLoop(FirstPolicy(), UnknownEvaluator(), TaskEvaluator())
        session = await (loop).start(environment, _task())
        paused = await session.run_until_pause()

        waiting = await session.resolve_confirmation(_decision(paused))

        assert waiting.status == AgentLoopStatus.WAITING_USER
        assert waiting.execution_count == 1
        assert session.state.pending_unknown_request is not None
        assert len(environment.executed_requests) == 1
        assert await session.run_until_pause() == waiting

    asyncio.run(scenario())


def test_confirmation_decision_cannot_be_reused_after_effectful_send() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("fresh", False, "#fresh"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        decision = _decision(paused)
        completed = await session.resolve_confirmation(decision)
        assert completed.status == AgentLoopStatus.DONE

        reused = await session.resolve_confirmation(decision)

        assert reused is completed
        assert reused.status == AgentLoopStatus.DONE
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_confirmation_requires_a_fresh_observation_identity() -> None:
    async def scenario() -> None:
        repeated = _world("same", False, "#same")
        environment = ScriptedEnvironment(initial_observation=repeated, independent_observations=(repeated,))
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()

        result = await session.resolve_confirmation(_decision(paused))

        assert result.status == AgentLoopStatus.FAILED
        assert "identity" in result.message
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_confirmation_continues_after_last_policy_turn_and_executes_once() -> None:
    async def scenario() -> None:
        task = replace(_task(), loop_budget=LoopBudget(max_turns=1, max_observations=3))
        policy = FirstPolicy()
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("confirmed", False, "#confirmed"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await (AgentLoop(policy, ActionEvaluator(), TaskEvaluator())).start(environment, task)
        paused = await session.run_until_pause()

        completed = await session.resolve_confirmation(_decision(paused))

        assert completed.status is AgentLoopStatus.DONE
        assert policy.calls == 1
        assert environment.execute_calls == 1
        assert session.state.control_transition_total_count == 1

    asyncio.run(scenario())


def test_wrong_origin_confirmation_records_expected_and_actual_origin() -> None:
    class WrongOriginEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            return acquired_acquisition(
                _world("fresh", False, "#fresh"),
                AcquisitionOrigin.RESET,
                kind=request.kind,
            )

    async def scenario() -> None:
        environment = WrongOriginEnvironment(
            initial_observation=_world("old", False, "#old"),
        )
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        await session.resolve_confirmation(_decision(paused))

        attempt = session.state.recent_control_transitions[0].acquisition_attempts[0]
        assert attempt.expected_origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
        assert attempt.origin is AcquisitionOrigin.RESET
        assert attempt.request_kind == str(ObservationRequestKind.CONFIRMATION_REFRESH)

    asyncio.run(scenario())


def test_confirmed_already_satisfied_closes_root_before_new_policy_decision() -> None:
    from tests.integration.agent.test_agent_progress_loop import (
        CountingBinder,
        IncompleteTaskEvaluator,
        RepeatedFillPolicy,
        ValueActionEvaluator,
    )
    from tests.integration.agent.test_agent_progress_loop import (
        _task as fill_task,
    )
    from tests.integration.agent.test_agent_progress_loop import (
        _world as fill_world,
    )

    async def scenario() -> None:
        policy = RepeatedFillPolicy()
        binder = CountingBinder()
        loop = AgentLoop(policy, ValueActionEvaluator(), IncompleteTaskEvaluator())
        loop.binder = binder
        task = replace(fill_task(), risk_profile=RiskProfile.MEDIUM)
        environment = ScriptedEnvironment(
            initial_observation=fill_world("initial", ""),
            independent_observations=(fill_world("confirmed", "desired"),),
        )
        session = await (loop).start(environment, task)
        paused = await session.run_until_pause()
        root_id = session.state.recent_control_transitions[0].transition_id

        terminal = await session.resolve_confirmation(_decision(paused))

        first = session.state.recent_control_transitions[0]
        assert terminal.status is AgentLoopStatus.WAITING_CONFIRMATION
        assert first.transition_id == root_id
        assert first.reason_code == "already_satisfied"
        assert first.progress.event_count == 1
        assert first.execution_attempts == ()
        assert first.pending_kind.value == "none"
        assert session.state.control_transition_total_count == 2
        assert policy.calls == 2
        assert binder.calls == environment.execute_calls == 0
        assert session.approved_confirmation is None
        assert session.confirmation_continuation_scope is None
        assert session.state.pending_confirmation is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("exc", (RuntimeError("capture failed"), asyncio.CancelledError()))
def test_confirmation_capture_exception_is_counted_and_closes_root(exc) -> None:
    class RaisingCaptureEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            raise exc

    async def scenario() -> None:
        environment = RaisingCaptureEnvironment(initial_observation=_world("old", False, "#old"))
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        with pytest.raises(type(exc)):
            await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        attempt = root.acquisition_attempts[0]
        assert attempt.attempts == 1
        assert attempt.origin is None
        assert attempt.expected_origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
        assert session.observation_count == 2
        assert session.state.control_transition_total_count == 1
        assert root.reason_code == (
            "runtime_cancelled" if isinstance(exc, asyncio.CancelledError) else "runtime_exception"
        )
        assert session.approved_confirmation is None
        assert session.confirmation_continuation_scope is None
        assert session.last_result is not None
        assert session.last_result.runtime_failure is not None
        assert session.last_result.runtime_failure.stage is (
            FailureStage.SESSION if isinstance(exc, asyncio.CancelledError) else FailureStage.ACQUISITION
        )
        assert session.last_result.runtime_failure.root_id == root.transition_id
        assert session.last_result.runtime_failure.attempt_id == root.attempt_receipts[-1].attempt_id

    asyncio.run(scenario())


def test_malformed_confirmation_capture_still_has_one_physical_receipt() -> None:
    class MalformedCaptureEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            return object()

    async def scenario() -> None:
        environment = MalformedCaptureEnvironment(initial_observation=_world("old", False, "#old"))
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        with pytest.raises(TypeError, match="malformed contract"):
            await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert environment.capture_calls == 1
        assert session.observation_count == 2
        assert len(root.attempt_receipts) == 1
        assert root.attempt_receipts[0].disposition.value == "malformed"
        assert root.acquisition_attempts[0].attempts == 1
        assert session.last_result is not None
        assert session.last_result.runtime_failure is not None
        assert session.last_result.runtime_failure.stage is FailureStage.ACQUISITION
        assert session.last_result.runtime_failure.kind is FailureKind.INVALID_OUTPUT

    asyncio.run(scenario())


def test_foreign_capture_exception_name_cannot_break_physical_accounting() -> None:
    foreign_error = type("捕获-" * 70, (Exception,), {})("private capture detail")

    class RaisingCaptureEnvironment(ScriptedEnvironment):
        async def capture(self, request):
            self.capture_calls += 1
            self.capture_requests.append(request)
            raise foreign_error

    async def scenario() -> None:
        environment = RaisingCaptureEnvironment(initial_observation=_world("old", False, "#old"))
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        with pytest.raises(type(foreign_error)):
            await session.resolve_confirmation(_decision(paused))
        root = session.state.recent_control_transitions[0]
        assert environment.capture_calls == 1
        assert session.observation_count == 2
        assert len(root.attempt_receipts) == 1
        assert root.attempt_receipts[0].exception_class.startswith("ExceptionClass_")

    asyncio.run(scenario())


def test_confirmation_action_space_exception_closes_same_root_after_capture() -> None:
    class RaisingSecondBuilder(ActionSpaceBuilder):
        calls = 0

        def build(self, task, observation):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("private action-space detail")
            return super().build(task, observation)

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("fresh", False, "#fresh"),),
        )
        loop = _loop()
        loop.action_space_builder = RaisingSecondBuilder()
        session = await (loop).start(environment, _task())
        paused = await session.run_until_pause()
        root_id = session.state.recent_control_transitions[0].transition_id

        with pytest.raises(RuntimeError, match="private action-space detail"):
            await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert root.transition_id == root_id
        assert root.after_observation_id == "fresh"
        assert root.task_evaluation is not None
        assert root.task_evaluation.observation_id == "fresh"
        assert root.reason_code == "runtime_exception"
        assert root.resulting_status is AgentLoopStatus.FAILED
        assert session.state.control_transition_total_count == 1
        assert session.approved_confirmation is None
        assert session.confirmation_continuation_scope is None

    asyncio.run(scenario())


def test_fresh_risk_block_overrides_prior_confirmation_for_same_subject() -> None:
    class BlockingFreshRisk:
        calls = 0

        def assess(self, task, selection):
            self.calls += 1
            assessment = RiskPolicy().assess(task, selection)
            if self.calls > 1:
                return replace(
                    assessment,
                    decision=RiskDecisionKind.BLOCK,
                    reason="fresh policy blocks execution",
                )
            return assessment

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("fresh", False, "#fresh"),),
        )
        loop = _loop()
        loop.risk_policy = BlockingFreshRisk()
        session = await (loop).start(environment, _task())
        paused = await session.run_until_pause()

        blocked = await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert blocked.status is AgentLoopStatus.BLOCKED
        assert blocked.reason_code == "risk_blocked_after_confirmation"
        assert root.reason_code == "risk_blocked_after_confirmation"
        assert root.task_evaluation is not None
        assert root.task_evaluation.observation_id == "fresh"
        assert root.execution_attempts == ()
        assert environment.execute_calls == 0
        assert blocked.observation_count == session.observation_count == 2
        assert sum(item.acquisition.attempts for item in (root,) if item.acquisition) == 1
        assert session.approved_confirmation is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "malformed", (object(), type("FakeRisk", (), {"decision": RiskDecisionKind.ALLOW, "reason": "allow"})())
)
def test_malformed_risk_policy_result_fails_closed_without_execution(malformed) -> None:
    class MalformedRiskPolicy:
        def assess(self, task, selection):
            return malformed

    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("initial", False, "#initial"))
        loop = _loop()
        loop.risk_policy = MalformedRiskPolicy()
        result = await (loop).run(environment, _task())
        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "risk_assessment_invalid"
        assert environment.execute_calls == 0

    asyncio.run(scenario())


def test_risk_assessment_for_another_selection_cannot_authorize_current_action() -> None:
    class WrongSubjectRiskPolicy:
        def assess(self, task, selection):
            assessment = RiskPolicy().assess(task, selection)
            wrong_subject = replace(assessment.subject, target_id="different-target")
            return replace(
                assessment,
                subject=wrong_subject,
                subject_id=wrong_subject.subject_id,
            )

    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("initial", False, "#initial"))
        loop = _loop()
        loop.risk_policy = WrongSubjectRiskPolicy()
        result = await (loop).run(environment, _task())
        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "risk_assessment_invalid"
        assert environment.execute_calls == 0

    asyncio.run(scenario())


def test_confirmation_has_no_dynamic_outcome_application_seam() -> None:
    assert not hasattr(_loop(), "_apply_outcome")


@pytest.mark.parametrize("exc", (RuntimeError("task failed"), asyncio.CancelledError()))
def test_confirmed_task_evaluator_exception_preserves_action_epoch_only(exc) -> None:
    class RaisingThirdTaskEvaluator(TaskEvaluator):
        def __init__(self):
            self.calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            if self.calls == 3:
                raise exc
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("confirmed", False, "#confirmed"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await (AgentLoop(FirstPolicy(), ActionEvaluator(), RaisingThirdTaskEvaluator())).start(
            environment, _task()
        )
        paused = await session.run_until_pause()

        with pytest.raises(type(exc)):
            await session.resolve_confirmation(_decision(paused))

        root = session.state.recent_control_transitions[0]
        assert root.after_observation_id == "after"
        assert root.action_evaluation is not None
        assert root.action_evaluation.after_observation_id == "after"
        assert root.task_evaluation is None
        assert root.reason_code == (
            "runtime_cancelled" if isinstance(exc, asyncio.CancelledError) else "runtime_exception"
        )

    asyncio.run(scenario())
