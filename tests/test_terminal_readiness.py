import pytest

from affordance_runtime.terminal_readiness import (
    ObligationState,
    TaskObligationEvidence,
    TerminalCandidate,
    TerminalReadinessEvaluator,
    TerminalReadinessStatus,
)


def _evidence(
    obligation_id: str,
    state: ObligationState,
    *,
    revision: int = 2,
    epoch: str = "snapshot-2",
    current: bool = False,
) -> TaskObligationEvidence:
    return TaskObligationEvidence(
        obligation_id,
        state,
        revision,
        verification_refs=(f"artifact:{obligation_id}",)
        if state == ObligationState.SATISFIED
        else (),
        observation_epoch_id=epoch if current else "",
        require_current_epoch=current,
    )


def test_direct_terminal_with_complete_empty_dependencies_is_ready() -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(TerminalCandidate("semantic:submit", dependencies_complete=True),),
        obligations=(),
    )

    assert decision.ready_target_ids == ("semantic:submit",)
    assert decision.blocked_target_ids == ()


def test_open_prerequisite_blocks_terminal() -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:submit",
                prerequisite_obligation_ids=("field:value",),
                dependencies_complete=True,
            ),
        ),
        obligations=(_evidence("field:value", ObligationState.OPEN),),
    )

    candidate = decision.candidates[0]
    assert candidate.status == TerminalReadinessStatus.BLOCKED
    assert candidate.blocking_obligation_ids == ("field:value",)


@pytest.mark.parametrize("dependencies_complete", [False, True])
def test_incomplete_or_missing_dependency_evidence_is_unknown(
    dependencies_complete: bool,
) -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:send",
                prerequisite_obligation_ids=("draft:body",),
                dependencies_complete=dependencies_complete,
            ),
        ),
        obligations=(),
    )

    assert decision.candidates[0].status == TerminalReadinessStatus.UNKNOWN
    assert decision.ready_target_ids == ()


@pytest.mark.parametrize(
    ("revision", "epoch", "current"),
    [(1, "snapshot-2", False), (2, "snapshot-1", True)],
)
def test_stale_revision_or_required_epoch_cannot_satisfy_terminal(
    revision: int,
    epoch: str,
    current: bool,
) -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:submit",
                prerequisite_obligation_ids=("selection:chosen",),
                dependencies_complete=True,
            ),
        ),
        obligations=(
            _evidence(
                "selection:chosen",
                ObligationState.SATISFIED,
                revision=revision,
                epoch=epoch,
                current=current,
            ),
        ),
    )

    assert decision.candidates[0].status == TerminalReadinessStatus.UNKNOWN


def test_current_verified_prerequisites_admit_only_their_terminal() -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:submit",
                prerequisite_obligation_ids=("selection:chosen",),
                dependencies_complete=True,
            ),
            TerminalCandidate(
                "semantic:publish",
                prerequisite_obligation_ids=("approval:granted",),
                dependencies_complete=True,
            ),
        ),
        obligations=(
            _evidence(
                "selection:chosen",
                ObligationState.SATISFIED,
                current=True,
            ),
            _evidence("approval:granted", ObligationState.OPEN),
        ),
    )

    assert decision.ready_target_ids == ("semantic:submit",)
    assert decision.blocked_target_ids == ("semantic:publish",)


def test_satisfied_obligation_requires_verification_reference() -> None:
    with pytest.raises(ValueError, match="verification evidence"):
        TaskObligationEvidence("field:value", ObligationState.SATISFIED, 2)
