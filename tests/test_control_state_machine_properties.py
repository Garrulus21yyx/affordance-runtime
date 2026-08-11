from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from test_confirmation_continuation import _task, _world

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.agent.accounting import RunAccounting
from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
)
from affordance_runtime.agent.control_reducer import (
    AppendRoot,
    ApplyContinuation,
    ControlAccepted,
    ControlRejected,
    ControlState,
    reduce_control,
    validate_control_state,
)
from affordance_runtime.agent.control_transition import (
    AcquisitionSummary,
    AdmissionStatus,
    AdmissionSummary,
    ControlContinuation,
    ControlTransition,
    ExecutionSummary,
    PendingKind,
    ProgressDelta,
)
from affordance_runtime.agent.decisions import SelectAction, Wait
from affordance_runtime.benchmarks.target_loop.failure_origin import (
    OBSERVATION_FAILURE_ORIGINS,
    observation_failure_origin,
)
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.execution import ActionError, DispatchStatus
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ObservationRequestKind,
)


class ControlReducerMachine(RuleBasedStateMachine):
    """Stepwise production/reference comparison for the bounded reducer."""

    def __init__(self) -> None:
        super().__init__()
        self.production = ControlState()
        self.model_roots: list[ControlTransition] = []
        self.model_total = 0
        self.model_sent_unknown = 0
        self.model_consumed: set[str] = set()
        self.model_terminal = ""
        self.model_waiting_user = False
        self.pending_root = ""
        self.last_consumed_root = ""
        self.accounting = RunAccounting()
        self.fake_execute_calls = 0
        self.fake_effectful_dispatches = 0

    @rule(
        limit=st.integers(min_value=1, max_value=4),
        dispatch=st.sampled_from((None, DispatchStatus.NOT_SENT, DispatchStatus.SENT,
                                  DispatchStatus.SENT_UNKNOWN)),
    )
    def append_legal_root(self, limit, dispatch) -> None:
        attempt_id = self.accounting.receipt_count + 1
        transition = _root(
            self.model_total + 1,
            dispatch=dispatch,
            attempt_id=attempt_id,
        )
        result = reduce_control(self.production, AppendRoot(transition, limit))
        if self.model_terminal or self.model_waiting_user or self.pending_root:
            assert isinstance(result, ControlRejected)
            return
        assert isinstance(result, ControlAccepted)
        self.production = result.state
        self.model_roots = (*self.model_roots, transition)[-limit:]
        self.model_roots = list(self.model_roots)
        self.model_total += 1
        self.model_sent_unknown += int(dispatch is DispatchStatus.SENT_UNKNOWN)
        for receipt in transition.attempt_receipts:
            self.accounting.record(receipt)
            self.fake_execute_calls += 1
            self.fake_effectful_dispatches += receipt.effectful_dispatches

    @precondition(
        lambda self: not self.model_terminal
        and not self.model_waiting_user
        and not self.pending_root
    )
    @rule(limit=st.integers(min_value=1, max_value=4))
    def request_confirmation(self, limit) -> None:
        transition = _root(
            self.model_total + 1,
            pending=PendingKind.CONFIRMATION,
            status=AgentLoopStatus.WAITING_CONFIRMATION,
        )
        result = reduce_control(self.production, AppendRoot(transition, limit))
        assert isinstance(result, ControlAccepted)
        self.production = result.state
        self.model_roots = list((*self.model_roots, transition)[-limit:])
        self.model_total += 1
        self.pending_root = transition.transition_id

    @precondition(lambda self: bool(self.pending_root))
    @rule(scenario=st.sampled_from((
        "no_dispatch", "retry", "exception", "cancel", "evaluated",
    )))
    def resolve_confirmation_once(self, scenario) -> None:
        continuation = _continuation_scenario(
            self.pending_root,
            scenario,
            self.accounting.receipt_count + 1,
        )
        status = continuation.resulting_status
        result = reduce_control(self.production, ApplyContinuation(continuation))
        assert isinstance(result, ControlAccepted)
        self.production = result.state
        index = next(
            i for i, item in enumerate(self.model_roots)
            if item.transition_id == self.pending_root
        )
        previous = self.model_roots[index]
        all_acquisitions = (
            *previous.acquisition_attempts,
            *continuation.acquisition_attempts,
        )
        self.model_roots[index] = replace(
            previous,
            execution=continuation.execution or previous.execution,
            execution_attempts=(
                *previous.execution_attempts,
                *continuation.execution_attempts,
            ),
            acquisition=(
                replace(
                    all_acquisitions[-1],
                    attempts=sum(item.attempts for item in all_acquisitions),
                )
                if all_acquisitions
                else None
            ),
            acquisition_attempts=all_acquisitions,
            attempt_receipts=(
                *previous.attempt_receipts,
                *continuation.attempt_receipts,
            ),
            after_observation_id=continuation.after_observation_id,
            task_evaluation=continuation.task_evaluation,
            pending_kind=continuation.pending_kind,
            resulting_status=status,
            reason_code=continuation.reason_code,
        )
        for receipt in continuation.attempt_receipts:
            self.accounting.record(receipt)
            self.fake_execute_calls += int(
                receipt.operation is AttemptOperation.EXECUTE
            )
            self.fake_effectful_dispatches += receipt.effectful_dispatches
        self.model_sent_unknown += sum(
            item.dispatch_status is DispatchStatus.SENT_UNKNOWN
            for item in continuation.attempt_receipts
        )
        self.model_consumed.add(self.pending_root)
        self.last_consumed_root = self.pending_root
        self.pending_root = ""
        self.model_terminal = (
            str(status)
            if status in {
                AgentLoopStatus.DONE,
                AgentLoopStatus.BLOCKED,
                AgentLoopStatus.CANCELLED,
                AgentLoopStatus.FAILED,
            }
            else ""
        )
        self.model_waiting_user = status is AgentLoopStatus.WAITING_USER

    @precondition(lambda self: bool(self.last_consumed_root))
    @rule()
    def replay_consumed_confirmation_is_rejected(self) -> None:
        result = reduce_control(
            self.production,
            ApplyContinuation(_continuation(
                self.last_consumed_root, AgentLoopStatus.DONE,
            )),
        )
        expected = (
            "terminal_state_is_absorbing"
            if self.model_terminal
            else "confirmation_root_already_consumed"
        )
        assert result == ControlRejected(expected)

    @precondition(lambda self: bool(self.model_terminal))
    @rule()
    def terminal_reentry_is_rejected(self) -> None:
        result = reduce_control(
            self.production,
            AppendRoot(_root(self.model_total + 1), 4),
        )
        assert result == ControlRejected("terminal_state_is_absorbing")

    @invariant()
    def production_matches_reference_after_every_step(self) -> None:
        assert self.production.total_count == self.model_total
        assert self.production.recent_transitions == tuple(self.model_roots)
        assert self.production.sent_unknown_total_count == self.model_sent_unknown
        assert set(self.production.continued_root_ids) == self.model_consumed
        assert self.production.terminal_status == self.model_terminal
        assert len({item.transition_id for item in self.model_roots}) == len(
            self.model_roots
        )
        assert sum(dict(self.production.kind_counts).values()) == self.model_total
        assert self.production.total_count >= len(self.production.recent_transitions)
        assert validate_control_state(self.production) is None
        assert self.accounting.execution_attempts == self.fake_execute_calls
        assert (
            self.accounting.effectful_dispatches
            == self.fake_effectful_dispatches
        )


ControlReducerMachine.TestCase.settings = settings(
    max_examples=100,
    stateful_step_count=30,
    deadline=None,
)


@given(
    junk=st.one_of(
        st.none(),
        st.integers(),
        st.text(max_size=12),
        st.lists(st.integers(), max_size=3),
        st.dictionaries(st.text(max_size=3), st.integers(), max_size=2),
    )
)
def test_arbitrary_control_state_shapes_never_escape_typed_reduction(junk) -> None:
    states = (
        replace(ControlState(), terminal_status=junk),
        replace(ControlState(), continued_root_ids=(junk,)),
        replace(ControlState(), kind_counts=((junk, 1),)),
    )
    for state in states:
        result = reduce_control(state, AppendRoot(_root(1), 1))
        assert isinstance(result, ControlAccepted | ControlRejected)


def _root(
    sequence: int,
    *,
    dispatch: DispatchStatus | None = None,
    pending: PendingKind = PendingKind.NONE,
    status: AgentLoopStatus | None = None,
    attempt_id: int | None = None,
) -> ControlTransition:
    execution = None
    executions = ()
    receipts = ()
    acquisition = None
    acquisitions = ()
    if dispatch is not None:
        request_id = f"request:{sequence}"
        transport_success = dispatch is DispatchStatus.SENT
        error = None if transport_success else ActionError.EXECUTION_FAILED
        execution = ExecutionSummary(
            request_id,
            request_id,
            "backend",
            dispatch,
            transport_success,
            error,
            0,
        )
        executions = (execution,)
        receipt = AttemptReceipt(
            f"attempt:{attempt_id or sequence}", AttemptOperation.EXECUTE, "post_action",
            AcquisitionOrigin.POST_ACTION, AcquisitionOrigin.POST_ACTION,
            AttemptDisposition.RETURNED, "post_action_acquired", 1, 1,
            int(dispatch is not DispatchStatus.NOT_SENT), 0, dispatch,
            request_id, request_id, True,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        )
        receipts = (receipt,)
        acquisition = AcquisitionSummary(
            AcquisitionStatus.ACQUIRED, AcquisitionOrigin.POST_ACTION,
            "post_action_acquired", 1, "post_action", AcquisitionOrigin.POST_ACTION,
        )
        acquisitions = (acquisition,)
        decision = SelectAction(f"context:{sequence}", "action")
        admission = AdmissionSummary(AdmissionStatus.ADMITTED, "admitted")
    elif pending is PendingKind.CONFIRMATION:
        decision = SelectAction(f"context:{sequence}", "action")
        request_id = ""
        admission = AdmissionSummary(
            AdmissionStatus.CONFIRMATION_REQUIRED, "admitted"
        )
    else:
        decision = Wait(f"context:{sequence}", "wait", 1)
        request_id = ""
        admission = None
    return ControlTransition(
        f"transition:{sequence}", sequence, f"observation:{sequence}", decision,
        admission, execution,
        executions, acquisition, acquisitions, receipts,
        f"observation:{sequence + 1}", None, None, ProgressDelta(), pending,
        status, "root_recorded", request_id=request_id,
    )


def _continuation(root_id: str, status: AgentLoopStatus) -> ControlContinuation:
    pending = (
        PendingKind.USER
        if status is AgentLoopStatus.WAITING_USER
        else PendingKind.NONE
    )
    return ControlContinuation(
        root_id, "observation:confirmed", None, (), (), None, (), None, "",
        None, None, ProgressDelta(), pending, status,
        "confirmation_resolved",
    )


def _continuation_scenario(
    root_id: str,
    scenario: str,
    first_attempt_id: int,
) -> ControlContinuation:
    if scenario == "no_dispatch":
        return _continuation(root_id, AgentLoopStatus.WAITING_USER)
    if scenario in {"exception", "cancel"}:
        disposition = (
            AttemptDisposition.CANCELLED
            if scenario == "cancel"
            else AttemptDisposition.THREW
        )
        status = (
            AgentLoopStatus.CANCELLED
            if scenario == "cancel"
            else AgentLoopStatus.FAILED
        )
        receipt = AttemptReceipt(
            f"attempt:{first_attempt_id}",
            AttemptOperation.EXECUTE,
            "execute",
            AcquisitionOrigin.POST_ACTION,
            None,
            disposition,
            "execute_cancelled" if scenario == "cancel" else "execute_exception",
            0,
            1,
            0,
            0,
            expected_request_id=f"request:{first_attempt_id}",
            exception_class="CancelledError" if scenario == "cancel" else "RuntimeError",
        )
        return replace(
            _continuation(root_id, status),
            attempt_receipts=(receipt,),
        )

    dispatches = (
        (DispatchStatus.NOT_SENT, DispatchStatus.SENT)
        if scenario == "retry"
        else (DispatchStatus.SENT,)
    )
    executions = []
    acquisitions = []
    receipts = []
    for offset, dispatch in enumerate(dispatches):
        attempt_id = first_attempt_id + offset
        request_id = f"request:{attempt_id}"
        summary = ExecutionSummary(
            request_id,
            request_id,
            "backend",
            dispatch,
            dispatch is DispatchStatus.SENT,
            None if dispatch is DispatchStatus.SENT else ActionError.EXECUTION_FAILED,
        )
        acquisition = AcquisitionSummary(
            AcquisitionStatus.ACQUIRED,
            AcquisitionOrigin.POST_ACTION,
            "post_action_acquired",
            1,
            "post_action",
            AcquisitionOrigin.POST_ACTION,
        )
        executions.append(summary)
        acquisitions.append(acquisition)
        receipts.append(AttemptReceipt(
            f"attempt:{attempt_id}",
            AttemptOperation.EXECUTE,
            "post_action",
            AcquisitionOrigin.POST_ACTION,
            AcquisitionOrigin.POST_ACTION,
            AttemptDisposition.RETURNED,
            "post_action_acquired",
            1,
            1,
            int(dispatch is not DispatchStatus.NOT_SENT),
            0,
            dispatch,
            request_id,
            request_id,
            True,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        ))
    after_id = "observation:confirmed"
    task_evaluation = (
        TaskEvaluation(
            "task:state-machine",
            after_id,
            TaskEvaluationStatus.COMPLETE,
            "completed",
        )
        if scenario == "evaluated"
        else None
    )
    return replace(
        _continuation(
            root_id,
            AgentLoopStatus.DONE if scenario == "evaluated" else None,
        ),
        acquisition=replace(acquisitions[-1], attempts=len(acquisitions)),
        acquisition_attempts=tuple(acquisitions),
        attempt_receipts=tuple(receipts),
        execution=executions[-1],
        execution_attempts=tuple(executions),
        task_evaluation=task_evaluation,
    )


def test_root_identity_and_observation_epoch_are_global_sequence_invariants() -> None:
    first = reduce_control(ControlState(), AppendRoot(_root(1), 1))
    assert isinstance(first, ControlAccepted)
    discontinuous = replace(_root(2), before_observation_id="observation:foreign")
    assert reduce_control(first.state, AppendRoot(discontinuous, 1)) == ControlRejected(
        "observation_epoch_discontinuity"
    )
    second = reduce_control(first.state, AppendRoot(_root(2), 1))
    assert isinstance(second, ControlAccepted)
    reused = replace(_root(3), transition_id="transition:1")
    assert reduce_control(second.state, AppendRoot(reused, 1)) == ControlRejected(
        "root_identity_sequence_mismatch"
    )


def test_execution_summaries_cannot_create_physical_attempt_truth() -> None:
    fabricated = replace(_root(1, dispatch=DispatchStatus.SENT_UNKNOWN), attempt_receipts=())
    assert reduce_control(ControlState(), AppendRoot(fabricated, 1)) == ControlRejected(
        "execution_receipt_count_mismatch"
    )


def test_every_command_validates_the_merged_candidate_state() -> None:
    first = reduce_control(
        ControlState(),
        AppendRoot(_root(1, dispatch=DispatchStatus.SENT, attempt_id=1), 4),
    )
    assert isinstance(first, ControlAccepted)
    second = _root(2, dispatch=DispatchStatus.SENT, attempt_id=1)
    assert validate_control_state(
        ControlState((second,), 2, (("SelectAction", 2),))
    ) is None
    assert reduce_control(first.state, AppendRoot(second, 4)) == ControlRejected(
        "duplicate_attempt_receipt"
    )


def test_pending_confirmation_cannot_already_have_crossed_execute_port() -> None:
    pending = _root(
        1,
        pending=PendingKind.CONFIRMATION,
        status=AgentLoopStatus.WAITING_CONFIRMATION,
    )
    dispatched = _root(1, dispatch=DispatchStatus.SENT)
    contradictory = replace(
        pending,
        execution=dispatched.execution,
        execution_attempts=dispatched.execution_attempts,
        acquisition=dispatched.acquisition,
        acquisition_attempts=dispatched.acquisition_attempts,
        attempt_receipts=dispatched.attempt_receipts,
        request_id=dispatched.request_id,
    )
    assert reduce_control(
        ControlState(), AppendRoot(contradictory, 1)
    ) == ControlRejected("confirmation_lifecycle_mismatch")


def test_task_evaluation_epoch_is_closed_at_continuation_boundary() -> None:
    root = _root(
        1,
        pending=PendingKind.CONFIRMATION,
        status=AgentLoopStatus.WAITING_CONFIRMATION,
    )
    accepted = reduce_control(ControlState(), AppendRoot(root, 1))
    assert isinstance(accepted, ControlAccepted)
    stale = TaskEvaluation(
        "task:state-machine",
        "observation:stale",
        TaskEvaluationStatus.INCOMPLETE,
        "stale",
    )
    with pytest.raises(ValueError, match="after observation"):
        replace(
            _continuation(root.transition_id, AgentLoopStatus.DONE),
            task_evaluation=stale,
        )


@pytest.mark.parametrize(
    ("backend", "transport_success", "error"),
    (("backend", False, None), ("", True, None)),
)
def test_execution_summary_is_a_total_action_result_projection(
    backend, transport_success, error,
) -> None:
    from affordance_runtime.agent.control_transition import ExecutionSummary

    with pytest.raises(ValueError, match="ActionResult"):
        ExecutionSummary(
            "request:one",
            "request:one",
            backend,
            DispatchStatus.SENT,
            transport_success,
            error,
        )


def test_confirmation_continuation_must_leave_pending_state() -> None:
    root = _root(
        1,
        pending=PendingKind.CONFIRMATION,
        status=AgentLoopStatus.WAITING_CONFIRMATION,
    )
    accepted = reduce_control(ControlState(), AppendRoot(root, 1))
    assert isinstance(accepted, ControlAccepted)
    continuation = replace(
        _continuation(root.transition_id, AgentLoopStatus.WAITING_CONFIRMATION),
        pending_kind=PendingKind.CONFIRMATION,
    )
    assert reduce_control(
        accepted.state, ApplyContinuation(continuation)
    ) == ControlRejected("confirmation_continuation_must_resolve")


def test_control_state_validation_is_total_over_malformed_state_shapes() -> None:
    command = AppendRoot(_root(1), 1)
    malformed_counts = ControlState(kind_counts=(("Wait",),))
    assert reduce_control(malformed_counts, command) == ControlRejected(
        "invalid_control_kind_totals"
    )

    first = _root(1)
    third = _root(3)
    gapped = ControlState((first, third), 3, (("Wait", 3),))
    assert reduce_control(gapped, AppendRoot(_root(4), 1)) == ControlRejected(
        "invalid_control_suffix"
    )

    terminal = _root(1, status=AgentLoopStatus.DONE)
    hidden_terminal = ControlState((terminal,), 1, (("Wait", 1),))
    assert reduce_control(hidden_terminal, AppendRoot(_root(2), 1)) == ControlRejected(
        "terminal_status_projection_mismatch"
    )

    contradictory_kinds = ControlState((first,), 1, (("SelectAction", 1),))
    assert reduce_control(
        contradictory_kinds, AppendRoot(_root(2), 1)
    ) == ControlRejected("invalid_control_kind_totals")

    impossible_history = ControlState(continued_root_ids=("transition:999",))
    assert reduce_control(impossible_history, command) == ControlRejected(
        "invalid_continuation_history"
    )
    impossible_unknown_total = ControlState(sent_unknown_total_count=1)
    assert reduce_control(impossible_unknown_total, command) == ControlRejected(
        "invalid_sent_unknown_total"
    )
    missing_epoch_anchor = ControlState(total_count=1, kind_counts=(("Wait", 1),))
    assert reduce_control(missing_epoch_anchor, AppendRoot(_root(2), 1)) == ControlRejected(
        "invalid_control_suffix"
    )

    pending = _root(
        1,
        pending=PendingKind.CONFIRMATION,
        status=AgentLoopStatus.WAITING_CONFIRMATION,
    )
    later = _root(2)
    hidden_pending = ControlState(
        (pending, later),
        2,
        (("Wait", 2),),
    )
    assert reduce_control(
        hidden_pending,
        ApplyContinuation(_continuation(pending.transition_id, AgentLoopStatus.DONE)),
    ) == ControlRejected("invalid_nonlatest_stopping_transition")

    stopped_then_running = ControlState(
        (_root(1, status=AgentLoopStatus.DONE), _root(2)),
        2,
        (("Wait", 2),),
    )
    assert reduce_control(
        stopped_then_running, AppendRoot(_root(3), 1)
    ) == ControlRejected("invalid_nonlatest_stopping_transition")


def test_pending_status_and_attempt_identity_algebras_are_closed() -> None:
    contradictory = _root(
        1,
        pending=PendingKind.USER,
        status=AgentLoopStatus.DONE,
    )
    assert reduce_control(
        ControlState(), AppendRoot(contradictory, 1)
    ) == ControlRejected("pending_status_mismatch")

    terminal_evaluation = TaskEvaluation(
        "task:1",
        "observation:2",
        TaskEvaluationStatus.BLOCKED,
        "official terminal failure",
        outcome=TaskOutcomeFact(
            TaskOutcomeKind.TERMINAL_FAILURE,
            "verified_terminal_task_failure",
            ("fact:observation:2:status",),
        ),
    )
    mismatched_terminal = replace(
        _root(1, status=AgentLoopStatus.DONE),
        task_evaluation=terminal_evaluation,
    )
    assert reduce_control(
        ControlState(), AppendRoot(mismatched_terminal, 1)
    ) == ControlRejected("task_outcome_disposition_mismatch")
    matched_terminal = replace(
        _root(1, status=AgentLoopStatus.BLOCKED),
        task_evaluation=terminal_evaluation,
    )
    assert isinstance(
        reduce_control(ControlState(), AppendRoot(matched_terminal, 1)),
        ControlAccepted,
    )

    root = _root(1, dispatch=DispatchStatus.SENT_UNKNOWN)
    duplicate = replace(
        root,
        execution_attempts=(*root.execution_attempts, *root.execution_attempts),
        acquisition=replace(root.acquisition, attempts=2),
        acquisition_attempts=(*root.acquisition_attempts, *root.acquisition_attempts),
        attempt_receipts=(*root.attempt_receipts, *root.attempt_receipts),
    )
    assert reduce_control(
        ControlState(), AppendRoot(duplicate, 1)
    ) == ControlRejected("duplicate_attempt_receipt")

    reset_receipt = AttemptReceipt(
        "attempt:1",
        AttemptOperation.RESET,
        "reset",
        AcquisitionOrigin.RESET,
        AcquisitionOrigin.RESET,
        AttemptDisposition.RETURNED,
        "reset_acquired",
        1,
        0,
        0,
        0,
        acquisition_status=AcquisitionStatus.ACQUIRED,
    )
    reset_summary = AcquisitionSummary(
        AcquisitionStatus.ACQUIRED,
        AcquisitionOrigin.RESET,
        "reset_acquired",
        1,
        "reset",
        AcquisitionOrigin.RESET,
    )
    reset_in_root = replace(
        _root(1),
        acquisition=reset_summary,
        acquisition_attempts=(reset_summary,),
        attempt_receipts=(reset_receipt,),
    )
    assert reduce_control(
        ControlState(), AppendRoot(reset_in_root, 1)
    ) == ControlRejected("reset_receipt_outside_control_root")

    impossible_acquisition = AcquisitionSummary(
        AcquisitionStatus.ACQUIRED,
        None,
        "capture_acquired",
        0,
        "wait_refresh",
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
    )
    invalid_acquisition_root = replace(
        _root(1),
        acquisition=impossible_acquisition,
        acquisition_attempts=(impossible_acquisition,),
    )
    assert reduce_control(
        ControlState(), AppendRoot(invalid_acquisition_root, 1)
    ) == ControlRejected("acquisition_attempt_status_mismatch")


@given(
    kind=st.sampled_from(tuple(TaskOutcomeKind)),
    dispatch=st.sampled_from((DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN)),
    action_status=st.sampled_from(tuple(ActionEvaluationStatus)),
    runtime_failure=st.booleans(),
)
def test_task_outcome_cross_domain_precedence_is_closed(
    kind: TaskOutcomeKind,
    dispatch: DispatchStatus,
    action_status: ActionEvaluationStatus,
    runtime_failure: bool,
) -> None:
    task_status = {
        TaskOutcomeKind.RUNNING_INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
        TaskOutcomeKind.TERMINAL_SUCCESS: TaskEvaluationStatus.COMPLETE,
        TaskOutcomeKind.TERMINAL_FAILURE: TaskEvaluationStatus.BLOCKED,
        TaskOutcomeKind.VERIFIER_UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
    }[kind]
    terminal_ref = "fact:observation:2:task-status"
    evidence_refs = (terminal_ref,) if kind in {
        TaskOutcomeKind.TERMINAL_SUCCESS,
        TaskOutcomeKind.TERMINAL_FAILURE,
    } else ()
    task_evaluation = TaskEvaluation(
        "task:state-machine",
        "observation:2",
        task_status,
        "generated task fact",
        completion_evidence_refs=(
            evidence_refs if kind is TaskOutcomeKind.TERMINAL_SUCCESS else ()
        ),
        outcome=TaskOutcomeFact(kind, f"generated_{kind.value}", evidence_refs),
    )
    action_evaluation = ActionEvaluation(
        "request:1",
        "observation:1",
        "observation:2",
        action_status,
        "generated action fact",
        ("fact:observation:2:action",)
        if action_status in {
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        }
        else (),
    )

    if kind is TaskOutcomeKind.TERMINAL_SUCCESS:
        pending, resulting = PendingKind.NONE, AgentLoopStatus.DONE
    elif kind is TaskOutcomeKind.TERMINAL_FAILURE:
        pending, resulting = PendingKind.NONE, AgentLoopStatus.BLOCKED
    elif runtime_failure:
        pending, resulting = PendingKind.NONE, AgentLoopStatus.FAILED
    elif dispatch is DispatchStatus.SENT_UNKNOWN:
        pending, resulting = PendingKind.UNKNOWN_EFFECT, AgentLoopStatus.WAITING_USER
    elif action_status is ActionEvaluationStatus.REJECTED:
        pending, resulting = PendingKind.NONE, AgentLoopStatus.FAILED
    elif kind is TaskOutcomeKind.VERIFIER_UNAVAILABLE:
        pending, resulting = PendingKind.NONE, AgentLoopStatus.WAITING_USER
    else:
        pending, resulting = PendingKind.NONE, None

    generated = replace(
        _root(1, dispatch=dispatch),
        action_evaluation=action_evaluation,
        task_evaluation=task_evaluation,
        pending_kind=pending,
        resulting_status=resulting,
        reason_code="generated_precedence",
    )
    reduced = reduce_control(ControlState(), AppendRoot(generated, 1))
    assert isinstance(reduced, ControlAccepted), reduced


def test_observation_failure_origin_mapping_is_total_and_path_independent() -> None:
    assert set(OBSERVATION_FAILURE_ORIGINS) == set(ObservationRequestKind)
    for kind in ObservationRequestKind:
        assert observation_failure_origin(kind) is observation_failure_origin(kind.value)


def test_changed_fresh_risk_material_cannot_reuse_old_subject() -> None:
    selection = _selection_for_risk()
    assessment = RiskPolicy().assess(_task(), selection)
    with pytest.raises(ValueError, match="canonical semantics"):
        replace(
            assessment,
            decision=RiskDecisionKind.BLOCK,
            risk=type(assessment.risk).HIGH,
        )


def _selection_for_risk():
    from affordance_runtime.world.action_space import ActionSpaceBuilder

    world = _world("risk", False, "#private")
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    return ActionSpaceBuilder().admit(option, {})
