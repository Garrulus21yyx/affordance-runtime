from __future__ import annotations

import asyncio
from dataclasses import replace

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from affordance_runtime.agent.control_reducer import (
    AppendRoot,
    ControlAccepted,
    ControlRejected,
    ControlState,
    reduce_control,
)
from affordance_runtime.agent.control_transition import (
    ControlTransition,
    PendingKind,
    ProgressDelta,
)
from affordance_runtime.agent.decisions import Abort, RequestObservation, Wait
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import EvaluationOutcome
from affordance_runtime.world import AcquisitionOrigin, ObservationCapabilities
from tests.integration.agent.test_agent_loop import (
    ScriptedPolicy,
    _loop,
    _sent,
    _task,
    _world,
)
from tests.support.observation_acquisition import failed_acquisition


def _root(sequence: int) -> ControlTransition:
    world = _world(f"observation:{sequence}", False)
    return ControlTransition(
        f"transition:{sequence}",
        sequence,
        world,
        Wait(f"context:{sequence}", "bounded wait", 1),
        None,
        (),
        (),
        (),
        (),
        world,
        None,
        None,
        ProgressDelta(),
        PendingKind.NONE,
        None,
        "wait_continued",
    )


@given(st.integers(min_value=1, max_value=24))
@settings(max_examples=40)
def test_generated_exact_roots_have_monotonic_identity(sequence: int) -> None:
    root = _root(sequence)
    assert root.sequence == sequence
    assert root.transition_id.startswith(f"transition:{sequence}")
    assert root.before_observation is root.after_observation
    assert root.execution_attempts == ()
    assert root.acquisition_attempts == ()


@given(st.integers(min_value=1, max_value=12))
@settings(max_examples=30)
def test_generated_reducer_sequence_is_contiguous(length: int) -> None:
    world = _world("observation:shared", False)
    control = ControlState()
    for sequence in range(1, length + 1):
        transition = ControlTransition(
            f"transition:{sequence}",
            sequence,
            world,
            Wait(f"context:{sequence}", "bounded wait", 1),
            None,
            (),
            (),
            (),
            (),
            world,
            None,
            None,
            ProgressDelta(),
            PendingKind.NONE,
            None,
            "wait_continued",
        )
        reduced = reduce_control(control, AppendRoot(transition, length))
        assert isinstance(reduced, ControlAccepted)
        control = reduced.state
    assert control.total_count == length


def test_adjacent_roots_require_exact_world_object_continuity() -> None:
    first = _root(1)
    accepted = reduce_control(ControlState(), AppendRoot(first, 3))
    assert isinstance(accepted, ControlAccepted)
    cloned_world = replace(first.after_observation)
    second = replace(
        _root(2),
        before_observation=cloned_world,
        after_observation=cloned_world,
    )
    rejected = reduce_control(accepted.state, AppendRoot(second, 3))
    assert isinstance(rejected, ControlRejected)
    assert rejected.code == "observation_epoch_discontinuity"


def test_terminal_state_is_absorbing() -> None:
    world = _world("observation:terminal", False)
    terminal = replace(
        _root(1),
        before_observation=world,
        after_observation=world,
        decision=Abort("context:1", "stop", "policy"),
        resulting_status=AgentLoopStatus.FAILED,
        reason_code="abort_policy",
    )
    accepted = reduce_control(ControlState(), AppendRoot(terminal, 3))
    assert isinstance(accepted, ControlAccepted)
    assert isinstance(
        reduce_control(accepted.state, AppendRoot(_root(2), 3)),
        ControlRejected,
    )


def test_pending_status_cross_product_fails_closed() -> None:
    malformed = replace(
        _root(1),
        pending_kind=PendingKind.USER,
        resulting_status=AgentLoopStatus.FAILED,
    )
    rejected = reduce_control(ControlState(), AppendRoot(malformed, 3))
    assert isinstance(rejected, ControlRejected)
    assert rejected.code == "pending_status_mismatch"


@given(
    st.sampled_from(
        (
            "evaluation_identity",
            "evaluation_before_identity",
            "admission_selection_identity",
            "success_without_evaluation",
        )
    )
)
@settings(max_examples=16, deadline=None)
def test_generated_single_phase_authority_mutations_fail_closed(mutation: str) -> None:
    async def action_root():
        result = await (_loop(ScriptedPolicy(["first"]))).run(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                post_observations=(_world("after", True),),
                results=[_sent()],
            ),
            _task(),
        )
        return result.control_transitions[0]

    root = asyncio.run(action_root())
    assert isinstance(root.evaluation, EvaluationOutcome)
    assert root.admission is not None and root.admission.selection is not None
    try:
        if mutation == "evaluation_identity":
            malformed = replace(
                root,
                evaluation=replace(root.evaluation, evaluation_id="evaluation:foreign"),
            )
        elif mutation == "evaluation_before_identity":
            malformed = replace(
                root,
                evaluation=replace(
                    root.evaluation,
                    before_observation=replace(root.before_observation),
                ),
            )
        elif mutation == "admission_selection_identity":
            malformed = replace(
                root,
                admission=replace(
                    root.admission,
                    selection=replace(root.admission.selection),
                ),
            )
        else:
            malformed = replace(root, evaluation=None)
    except ValueError:
        return

    reduced = reduce_control(ControlState(), AppendRoot(malformed, 3))
    assert isinstance(reduced, ControlRejected)


@given(st.sampled_from((AgentLoopStatus.DONE, AgentLoopStatus.WAITING_USER, AgentLoopStatus.WAITING_CONFIRMATION)))
@settings(max_examples=12)
def test_generated_wait_disposition_mutations_fail_closed(status: AgentLoopStatus) -> None:
    malformed = replace(
        _root(1),
        resulting_status=status,
        pending_kind=(
            PendingKind.USER
            if status is AgentLoopStatus.WAITING_USER
            else PendingKind.CONFIRMATION
            if status is AgentLoopStatus.WAITING_CONFIRMATION
            else PendingKind.NONE
        ),
    )
    reduced = reduce_control(ControlState(), AppendRoot(malformed, 3))
    assert isinstance(reduced, ControlRejected)


@given(
    st.sampled_from(("wait", "observation")),
    st.booleans(),
    st.sampled_from(
        (
            None,
            AgentLoopStatus.FAILED,
            AgentLoopStatus.BLOCKED,
            AgentLoopStatus.WAITING_USER,
            AgentLoopStatus.DONE,
        )
    ),
)
@settings(max_examples=30, deadline=None)
def test_generated_capture_failure_disposition_product_fails_closed(
    decision_kind: str,
    unavailable: bool,
    mutation: AgentLoopStatus | None,
) -> None:
    decision = (
        Wait("context:test", "settle", 1)
        if decision_kind == "wait"
        else RequestObservation(
            "context:test",
            "criterion_verification",
            "current_world",
            "",
            "refresh",
        )
    )
    expected = AgentLoopStatus.BLOCKED if unavailable else AgentLoopStatus.FAILED
    assume(mutation is not expected)

    async def failed_root():
        class Policy:
            async def decide(self, context):
                return replace(decision, context_id=context.context_id)

        class FailedEnvironment(ScriptedEnvironment):
            async def capture(self, request):
                return failed_acquisition(
                    AcquisitionOrigin.INDEPENDENT_CAPTURE,
                    "required_source_exhausted",
                    kind=request.kind,
                    acquisition_id="acquisition:2",
                    request=request,
                )

        environment_type = ScriptedEnvironment if unavailable else FailedEnvironment
        result = await (_loop(Policy())).run(
            environment_type(
                initial_observation=_world("before", False),
                observation_capabilities=(
                    ObservationCapabilities(False, True) if unavailable else ObservationCapabilities(True, True)
                ),
            ),
            _task(),
        )
        return result.control_transitions[0]

    root = asyncio.run(failed_root())
    assert root.resulting_status is expected
    malformed = replace(root, resulting_status=mutation)
    reduced = reduce_control(ControlState(), AppendRoot(malformed, 3))
    assert isinstance(reduced, ControlRejected)


@given(st.sampled_from((AgentLoopStatus.FAILED, AgentLoopStatus.BLOCKED, AgentLoopStatus.CANCELLED)))
@settings(max_examples=12, deadline=None)
def test_generated_successful_wait_cannot_be_relabelled_terminal(
    mutation: AgentLoopStatus,
) -> None:
    async def successful_wait_root():
        class Policy:
            calls = 0

            async def decide(self, context):
                self.calls += 1
                if self.calls == 1:
                    return Wait(context.context_id, "settle", 1)
                return Abort(context.context_id, "stop", "policy")

        result = await (_loop(Policy())).run(
            ScriptedEnvironment(
                initial_observation=_world("before", False),
                independent_observations=(_world("fresh", False),),
            ),
            _task(),
        )
        return result.control_transitions[0]

    root = asyncio.run(successful_wait_root())
    assert root.resulting_status is None
    malformed = replace(root, resulting_status=mutation)
    reduced = reduce_control(ControlState(), AppendRoot(malformed, 3))
    assert isinstance(reduced, ControlRejected)
