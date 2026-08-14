from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
)
from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    ControlTransitionScope,
    PendingKind,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.model_boundary.control_transition_projection import (
    project_control_transitions,
)
from affordance_runtime.model_boundary.failures import ModelFailureKind
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ObservationRequestKind,
)


def test_transition_is_frozen_bounded_and_strips_adapter_payload() -> None:
    state = AgentLoopState(_world("before", False))
    decision = SelectAction("context:one", "action:one")
    scope = ControlTransitionScope(state, decision)
    scope.record_admission(AdmissionStatus.ADMITTED, "action_admitted")
    result = ActionResult(
        "request:one",
        DispatchStatus.SENT,
        "dom",
        True,
        adapter_evidence={"selector": "#private", "raw_payload": "secret"},
    )
    scope.record_execution_receipt(
        AttemptReceipt(
            "attempt:1",
            AttemptOperation.EXECUTE,
            "post_action",
            AcquisitionOrigin.POST_ACTION,
            AcquisitionOrigin.POST_ACTION,
            AttemptDisposition.RETURNED,
            "post_action_acquired",
            1,
            1,
            1,
            0,
            DispatchStatus.SENT,
            "request:one",
            "request:one",
            True,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        ),
        "request:one",
        None,
        result,
    )
    transition = scope.finalize(state, None)

    assert transition.sequence == 1
    assert transition.pending_kind is PendingKind.NONE
    assert "selector" not in repr(transition)
    assert "raw_payload" not in repr(transition)
    assert transition.as_turn().result is not None
    assert transition.as_turn().result.adapter_evidence == {}
    with pytest.raises(FrozenInstanceError):
        transition.reason_code = "changed"  # type: ignore[misc]
    with pytest.raises(RuntimeError, match="already finalized"):
        scope.finalize(state, None)


def test_transition_rejects_old_task_evaluation_epoch_before_model_projection() -> None:
    state = AgentLoopState(_world("before", False))
    scope = ControlTransitionScope(state, Wait("context:one", "wait", 1))
    scope.set_reason("runtime_exception")
    transition = scope.finalize(state, None)
    with pytest.raises(ValueError, match="task evaluation"):
        replace(
            transition,
            after_observation_id="after",
            task_evaluation=TaskEvaluation(
                _task().task_id,
                "before",
                TaskEvaluationStatus.INCOMPLETE,
                "old epoch",
            ),
        )

    current = replace(transition, after_observation_id="after")
    view = project_control_transitions((current,))[0]

    assert view.task_evaluation_status == ""
    assert view.reason == "runtime_exception"
    assert view.semantic_summary["resulting_status"] == ""
    assert view.semantic_summary["execution_attempt_count"] == 0


def test_transition_rejects_before_evaluation_from_another_observation() -> None:
    state = AgentLoopState(_world("before", False))
    scope = ControlTransitionScope(state, Wait("context:one", "wait", 1))
    scope.set_reason("runtime_exception")
    transition = scope.finalize(state, None)

    with pytest.raises(ValueError, match="before task evaluation"):
        replace(
            transition,
            before_task_evaluation=TaskEvaluation(
                _task().task_id,
                "another-observation",
                TaskEvaluationStatus.INCOMPLETE,
                "wrong epoch",
            ),
        )


@pytest.mark.parametrize("reason_code", ("", "Raw message", "selector:#x", "x" * 97))
def test_transition_rejects_unbounded_or_unstable_reason_codes(reason_code: str) -> None:
    state = AgentLoopState(_world("before", False))
    scope = ControlTransitionScope(state, Abort("context:one", "stop", "policy"))
    with pytest.raises(ValueError, match="reason_code"):
        scope.set_reason(reason_code)


def test_exact_root_total_survives_bounded_suffix() -> None:
    state = AgentLoopState(_world("before", False), recent_turn_limit=3)
    for index in range(7):
        decision = Wait(f"context:{index}", f"wait {index}", 1)
        scope = ControlTransitionScope(state, decision)
        scope.set_reason("wait_continued")
        scope.finalize(state, None)

    assert state.control_transition_total_count == 7
    assert [item.sequence for item in state.recent_control_transitions] == [5, 6, 7]
    assert len(state.recent_turns) == 3


@pytest.mark.parametrize(
    ("decision_factory", "expected_reason"),
    (
        (lambda context: AskUser(context, "Which account?"), "user_input_requested"),
        (lambda context: Abort(context, "stop", "policy"), "abort_policy"),
        (
            lambda context: ProposeDone(context, ("unknown",), (), "done", ()),
            "invalid_completion_claim",
        ),
        (
            lambda context: RequestActionPage(context, cursor="invalid"),
            "invalid_action_page_request",
        ),
        (
            lambda context: SelectAction(context, "action:outside"),
            "action_outside_current_page",
        ),
    ),
)
def test_each_terminal_accepted_decision_creates_one_root(
    decision_factory,
    expected_reason: str,
) -> None:
    class Policy:
        async def decide(self, context):
            return decision_factory(context.context_id)

    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).start(StaticEnvironment([_world("before", False)]), _task())
        await session.run_until_pause()

        expected_roots = 2 if expected_reason == "action_outside_current_page" else 1
        assert session.state.control_transition_total_count == expected_roots
        transition = session.state.recent_control_transitions[0]
        assert transition.reason_code == expected_reason
        assert transition.before_observation_id == "before"
        if expected_roots == 2:
            assert session.state.recent_control_transitions[1].reason_code == (
                "no_progress_control_repetition"
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ("observe", "wait"))
def test_refresh_decision_and_following_abort_each_create_one_root(kind: str) -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 2:
                return Abort(context.context_id, "stop", "policy")
            if kind == "wait":
                return Wait(context.context_id, "settle", 1)
            offer = context.world.observation_capabilities[0]
            return RequestObservation(
                context.context_id,
                "shared-toggle",
                offer.modality,
                offer.assurance,
                "refresh",
            )

    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).start(StaticEnvironment([_world("before", False), _world("fresh", False)]), _task())
        await session.run_until_pause()

        assert session.state.control_transition_total_count == 2
        refresh = session.state.recent_control_transitions[0]
        assert refresh.acquisition is not None
        assert refresh.acquisition.request_kind == str(
            ObservationRequestKind.WAIT_REFRESH
            if kind == "wait"
            else ObservationRequestKind.POLICY_REQUEST
        )
        assert refresh.after_observation_id == "fresh"

    asyncio.run(scenario())


def test_action_transition_retains_typed_control_facts_once() -> None:
    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [_sent()]),
            _task(),
        )
        result = await session.run_until_pause()

        assert result.status is AgentLoopStatus.DONE
        assert result.control_transition_total_count == 1
        transition = result.control_transitions[0]
        assert transition.admission is not None
        assert transition.admission.status is AdmissionStatus.ADMITTED
        assert transition.execution is not None
        assert transition.execution.dispatch_status is DispatchStatus.SENT
        assert transition.acquisition is not None
        assert transition.acquisition.attempts == 1
        assert transition.action_evaluation is not None
        assert transition.task_evaluation is not None

    asyncio.run(scenario())


def test_provider_failure_before_decision_creates_no_transition() -> None:
    class Policy:
        async def decide(self, context):
            del context
            return PolicyFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "provider unavailable")

    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).start(StaticEnvironment([_world("before", False)]), _task())
        await session.run_until_pause()
        assert session.state.control_transition_total_count == 0

    asyncio.run(scenario())
