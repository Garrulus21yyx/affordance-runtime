from affordance_runtime.agent.run_control import (
    CooperativeRunControl,
    RunControlAdmissionKind,
    RunControlBoundary,
    RunControlKind,
    RunControlOutcomeKind,
)
from affordance_runtime.execution.contracts import DispatchStatus


def test_cancel_supersedes_pending_pause_with_one_typed_outcome_each() -> None:
    control = CooperativeRunControl()

    pause = control.request("pause:1", RunControlKind.PAUSE)
    cancel = control.request("cancel:1", RunControlKind.CANCEL)
    outcome = control.acknowledge(
        RunControlBoundary.AFTER_DISPATCH,
        dispatch_status=DispatchStatus.SENT_UNKNOWN,
    )

    assert pause.outcome is RunControlAdmissionKind.ACCEPTED
    assert cancel.outcome is RunControlAdmissionKind.ACCEPTED
    assert control.outcome("pause:1").outcome is RunControlOutcomeKind.SUPERSEDED
    assert outcome is not None
    assert outcome.outcome is RunControlOutcomeKind.CANCELLED
    assert outcome.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert control.pending is None


def test_pause_boundary_requires_explicit_resume_and_is_idempotent_by_command() -> None:
    control = CooperativeRunControl()

    first = control.request("pause:1", RunControlKind.PAUSE)
    duplicate = control.request("pause:1", RunControlKind.PAUSE)
    paused = control.acknowledge(RunControlBoundary.BEFORE_POLICY)

    assert first.outcome is RunControlAdmissionKind.ACCEPTED
    assert duplicate.outcome is RunControlAdmissionKind.DUPLICATE
    assert paused is control.paused
    assert control.request("pause:2", RunControlKind.PAUSE).outcome is RunControlAdmissionKind.CONFLICT

    resumed = control.resume("resume:1")

    assert resumed.outcome is RunControlOutcomeKind.RESUMED
    assert control.paused is None
