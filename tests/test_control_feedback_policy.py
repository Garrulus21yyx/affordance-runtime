from __future__ import annotations

from affordance_runtime.agent.control_feedback import (
    ContractViolationSnapshot,
    ControlFeedback,
    ControlFeedbackKind,
    ControlFeedbackSource,
    FeedbackBudgetDisposition,
    NextDecisionDisposition,
    RecoveryConstraints,
    RelatedDecisionSnapshot,
    apply_feedback_budget,
)


def _feedback(issue: str, *, scope: str = "a" * 64) -> ControlFeedback:
    return ControlFeedback(
        ControlFeedbackKind.REPAIRABLE_REJECTION,
        "invalid_action_parameters",
        ControlFeedbackSource.ACTION_ADMISSION,
        NextDecisionDisposition.CORRECT_OR_REPLAN,
        False,
        None,
        ("parameters",),
        scope,
        issue * 64,
        related_decision=RelatedDecisionSnapshot("select_action", "action:1"),
        violation=ContractViolationSnapshot(
            "current_action_space", "invalid_action_parameters", ("parameters",), {}, {},
        ),
        recovery=RecoveryConstraints(must_change_fields=("parameters",), retry_allowed=True),
    )


def test_two_distinct_issues_share_one_scope_budget() -> None:
    first = apply_feedback_budget("", (), _feedback("b"))
    second = apply_feedback_budget("a" * 64, first.issue_digests, _feedback("c"))
    repeated = apply_feedback_budget("a" * 64, second.issue_digests, _feedback("b"))
    third = apply_feedback_budget("a" * 64, second.issue_digests, _feedback("d"))

    assert first.disposition is FeedbackBudgetDisposition.DELIVER
    assert second.disposition is FeedbackBudgetDisposition.DELIVER
    assert repeated.disposition is FeedbackBudgetDisposition.TERMINATE
    assert third.disposition is FeedbackBudgetDisposition.TERMINATE


def test_semantic_scope_change_replaces_prior_issue_budget() -> None:
    decision = apply_feedback_budget(
        "a" * 64,
        ("b" * 64, "c" * 64),
        _feedback("d", scope="e" * 64),
    )

    assert decision.disposition is FeedbackBudgetDisposition.DELIVER
    assert decision.issue_digests == ("d" * 64,)
