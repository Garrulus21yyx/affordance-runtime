from affordance_runtime.planning import ProposalRejectionCode
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy
from affordance_runtime.recovery_commands import RecoveryCommandKind


def test_target_scope_rejection_allows_only_bounded_step_replan() -> None:
    decision = ProposalRejectionRecoveryPolicy().decide(
        ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
        "semantic:wrong-target",
        "relational_evidence_not_proven",
        "semantic:wrong-target",
    )

    assert decision.recoverable
    assert decision.available_commands == frozenset(
        {RecoveryCommandKind.REPLAN_STEP, RecoveryCommandKind.ABORT}
    )
    assert decision.planner_feedback == (
        "target_out_of_scope:relational_evidence_not_proven:semantic:wrong-target"
    )
    assert decision.rejection_context.semantic_target_id == "semantic:wrong-target"
    assert decision.rejection_context.reason_code == "relational_evidence_not_proven"


def test_authority_and_structural_rejections_remain_terminal() -> None:
    policy = ProposalRejectionRecoveryPolicy()

    for code in ProposalRejectionCode:
        if code == ProposalRejectionCode.TARGET_OUT_OF_SCOPE:
            continue
        decision = policy.decide(code)
        assert not decision.recoverable, code
        assert decision.available_commands == frozenset({RecoveryCommandKind.ABORT}), code
