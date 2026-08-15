from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest

from affordance_runtime.agent import (
    Abort,
    AgentLoop,
    AgentLoopStatus,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.context.control_transition_projection import (
    project_control_transitions,
)
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.control_reducer import (
    AppendRoot,
    ControlRejected,
    ControlState,
    reduce_control,
)
from affordance_runtime.agent.control_transition import (
    ActionAdmissionOutcome,
    AdmissionStatus,
    ControlTransitionScope,
    PendingKind,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import EvaluationOutcome, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.world import (
    AcquisitionOrigin,
    ObservationRequestKind,
)
from tests.integration.agent.test_agent_loop import (
    ScriptedPolicy,
    SharedActionEvaluator,
    SharedTaskEvaluator,
    _loop,
    _sent,
    _task,
    _world,
)


def test_transition_is_frozen_and_scope_finalizes_once() -> None:
    state = AgentLoopState(_world("before", False))
    decision = Wait("context:one", "wait", 1)
    scope = ControlTransitionScope(state, decision)
    scope.set_reason("wait_continued")
    transition = scope.finalize(state, None)

    assert transition.sequence == 1
    assert transition.pending_kind is PendingKind.NONE
    assert transition.execution is None
    with pytest.raises(FrozenInstanceError):
        transition.reason_code = "changed"  # type: ignore[misc]
    with pytest.raises(RuntimeError, match="already finalized"):
        scope.finalize(state, None)


def test_admission_outcome_rejects_open_or_contradictory_shapes() -> None:
    with pytest.raises(ValueError, match="selection and allow assessment"):
        ActionAdmissionOutcome(AdmissionStatus.ADMITTED, "action_admitted")
    with pytest.raises(ValueError, match="issue or selected rejection"):
        ActionAdmissionOutcome(AdmissionStatus.REJECTED, "action_rejected")


def test_reducer_rejects_a_second_effectful_execution_attempt() -> None:
    async def scenario() -> None:
        result = await (_loop(ScriptedPolicy(["first"]))).run(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[_sent()],
            ),
            _task(),
        )
        root = result.control_transitions[0]
        execution = root.execution_attempts[0]
        receipt = root.attempt_receipts[-1]
        malformed = replace(
            root,
            execution_attempts=(execution, execution),
            attempt_receipts=(receipt, replace(receipt, attempt_id="attempt:999")),
        )

        rejected = reduce_control(ControlState(), AppendRoot(malformed, 12))

        assert isinstance(rejected, ControlRejected)
        assert rejected.code in {"duplicate_execution_request", "multiple_effectful_dispatches"}

    asyncio.run(scenario())


def test_transition_requires_identity_reachable_execution_and_unique_acquisition() -> None:
    async def scenario() -> None:
        result = await (_loop(ScriptedPolicy(["first"]))).run(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[_sent()],
            ),
            _task(),
        )
        root = result.control_transitions[0]
        assert isinstance(root.evaluation, EvaluationOutcome)
        execution = root.execution_attempts[0]
        primary = root.acquisition_attempts[0]

        cloned_execution = replace(execution)
        cloned_evaluation = replace(root.evaluation, execution=cloned_execution)
        with pytest.raises(ValueError, match="evaluation execution is not reachable"):
            replace(root, evaluation=cloned_evaluation)
        with pytest.raises(ValueError, match="acquisition attempts cannot repeat"):
            replace(root, acquisition_attempts=(primary, primary))
        with pytest.raises(ValueError, match="identity must derive"):
            replace(root.evaluation, evaluation_id="evaluation:foreign")
        with pytest.raises(ValueError, match="before authority mismatch"):
            replace(
                root,
                evaluation=replace(
                    root.evaluation,
                    before_observation=replace(root.before_observation),
                ),
            )
        assert root.admission is not None and root.admission.selection is not None
        with pytest.raises(ValueError, match="exact admitted selection"):
            replace(
                root,
                admission=replace(
                    root.admission,
                    selection=replace(root.admission.selection),
                ),
            )

    asyncio.run(scenario())


def test_admission_rejects_selection_risk_subject_divergence() -> None:
    async def scenario() -> None:
        result = await (_loop(ScriptedPolicy(["first"]))).run(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[_sent()],
            ),
            _task(),
        )
        admission = result.control_transitions[0].admission
        assert admission is not None and admission.selection is not None

        with pytest.raises(ValueError, match="risk subject"):
            replace(
                admission,
                selection=replace(admission.selection, target_id="foreign-target"),
            )

    asyncio.run(scenario())


def test_reducer_rejects_decision_with_foreign_phase_facts() -> None:
    async def scenario() -> None:
        observe = RequestObservation(
            "context:test",
            "criterion_verification",
            "current_world",
            "",
            "refresh",
        )
        stop = Abort("context:test", "stop", "policy")
        result = await (_loop(ScriptedPolicy([observe, stop]))).run(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                independent_observations=(_world("fresh", False),),
            ),
            _task(),
        )
        observed = result.control_transitions[0]
        malformed = replace(
            observed,
            decision=stop,
            evaluation=None,
            control_feedback=None,
            resulting_status=AgentLoopStatus.FAILED,
            reason_code="abort_policy",
        )

        rejected = reduce_control(ControlState(), AppendRoot(malformed, 12))

        assert isinstance(rejected, ControlRejected)
        assert rejected.code == "decision_phase_shape_mismatch"

    asyncio.run(scenario())


def test_transition_rejects_unreached_world_before_model_projection() -> None:
    state = AgentLoopState(_world("before", False))
    scope = ControlTransitionScope(state, Wait("context:one", "wait", 1))
    scope.set_reason("runtime_exception")
    transition = scope.finalize(state, None)
    with pytest.raises(ValueError, match="not reachable"):
        replace(
            transition,
            after_observation=_world("after", False),
            direct_task_evaluation=TaskEvaluation(
                _task().task_id,
                "before",
                TaskEvaluationStatus.INCOMPLETE,
                "old epoch",
            ),
        )

    view = project_control_transitions((transition,))[0]

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
    assert len(state.recent_control_transitions) == 3


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
        session = await (AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())).start(
            ScriptedEnvironment(initial_observation=_world("before", False)), _task()
        )
        await session.run_until_pause()

        expected_roots = 2 if expected_reason == "action_outside_current_page" else 1
        assert session.state.control_transition_total_count == expected_roots
        transition = session.state.recent_control_transitions[0]
        assert transition.reason_code == expected_reason
        assert transition.before_observation_id == "before"
        if expected_roots == 2:
            assert session.state.recent_control_transitions[1].reason_code == ("no_progress_control_repetition")

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
            return RequestObservation(
                context.context_id,
                "criterion_verification",
                "shared-toggle",
                "",
                "refresh",
            )

    async def scenario() -> None:
        session = await (AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())).start(
            ScriptedEnvironment(
                initial_observation=_world("before", False), independent_observations=(_world("fresh", False),)
            ),
            _task(),
        )
        await session.run_until_pause()

        assert session.state.control_transition_total_count == 2
        refresh = session.state.recent_control_transitions[0]
        assert refresh.acquisition is not None
        assert str(refresh.acquisition.request.kind) == str(
            ObservationRequestKind.WAIT_REFRESH if kind == "wait" else ObservationRequestKind.POLICY_REQUEST
        )
        assert refresh.after_observation_id == "fresh"

    asyncio.run(scenario())


def test_action_transition_retains_typed_control_facts_once() -> None:
    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=[_sent()],
        )
        session = await (AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())).start(
            environment,
            _task(),
        )
        result = await session.run_until_pause()

        assert result.status is AgentLoopStatus.DONE
        assert result.control_transition_total_count == 1
        transition = result.control_transitions[0]
        assert transition.admission is not None
        assert transition.admission.status is AdmissionStatus.ADMITTED
        assert transition.execution is not None
        assert transition.execution.result.dispatch_status is DispatchStatus.SENT
        assert transition.execution.request is environment.executed_requests[0]
        assert transition.acquisition is not None
        assert transition.acquisition.origin is AcquisitionOrigin.POST_ACTION
        assert transition.execution.post_acquisition is transition.acquisition
        assert transition.evaluation is not None
        assert transition.evaluation.execution is transition.execution
        assert transition.evaluation.consumed_acquisition is transition.acquisition
        assert transition.evaluation.after_observation is result.final_observation
        assert transition.action_evaluation is not None
        assert transition.task_evaluation is not None

    asyncio.run(scenario())


def test_provider_failure_before_decision_creates_no_transition() -> None:
    class Policy:
        async def decide(self, context):
            del context
            return PolicyFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "provider unavailable")

    async def scenario() -> None:
        session = await (AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())).start(
            ScriptedEnvironment(initial_observation=_world("before", False)), _task()
        )
        await session.run_until_pause()
        assert session.state.control_transition_total_count == 0

    asyncio.run(scenario())
