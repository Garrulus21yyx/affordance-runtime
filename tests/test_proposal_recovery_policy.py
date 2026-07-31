from affordance_runtime.planning import ProposalRejectionCode
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy


def test_target_scope_rejection_defers_to_step_planner_owner() -> None:
    decision = ProposalRejectionRecoveryPolicy().decide(
        ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
        "semantic:wrong-target",
        "relational_evidence_not_proven",
        "semantic:wrong-target",
    )

    assert decision.recoverable
    assert not hasattr(decision, "available_commands")
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
        assert not hasattr(decision, "available_commands"), code
