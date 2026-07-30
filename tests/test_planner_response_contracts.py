from __future__ import annotations

import pytest


def test_planner_response_union_rejects_action_contract_authority() -> None:
    from affordance_runtime.planning import PlannerActionKind, PlannerProposal
    from affordance_runtime.planning_contracts import (
        PlannerProposalResponse,
        PlannerResponseStatus,
    )

    proposal = PlannerProposal(
        proposal_id="proposal:finish",
        based_on_task_revision=1,
        based_on_state_version=0,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.FINISH,
        parameters={},
        expected_effects=("task done",),
    )
    response = PlannerProposalResponse(proposal=proposal, reason="ready")

    assert response.status == PlannerResponseStatus.PROPOSAL
    assert response.proposal is proposal
    assert not hasattr(response, "contract")


def test_planner_response_variants_have_state_invariants() -> None:
    from affordance_runtime.planning_contracts import (
        PlannerClarificationResponse,
        PlannerDoneResponse,
        PlannerUnsupportedResponse,
    )

    assert PlannerDoneResponse(result={"answer": ["ok"]}).result["answer"] == ("ok",)

    with pytest.raises(ValueError, match="question"):
        PlannerClarificationResponse(question="")

    with pytest.raises(ValueError, match="reason"):
        PlannerUnsupportedResponse(reason_code="")
