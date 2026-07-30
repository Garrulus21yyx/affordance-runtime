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


def test_planner_port_public_contract_returns_closed_response_union() -> None:
    import inspect

    from affordance_runtime.planning_contracts import PlannerPort

    annotation = inspect.signature(PlannerPort.propose).return_annotation

    assert "PlannerResponse" in annotation
    assert "PlannerDecision" not in annotation


def test_generalist_planner_standard_contract_is_request_only() -> None:
    import inspect

    from affordance_runtime.generalist_planner import GeneralistLMPlanner

    signature = inspect.signature(GeneralistLMPlanner.propose)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        and parameter.name != "self"
    ]

    assert [parameter.name for parameter in positional] == ["request"]
    assert "PlannerResponse" in str(signature.return_annotation)
    assert "PlannerDecision" not in str(signature.return_annotation)


def test_parent_agent_adapter_standard_contract_is_request_only() -> None:
    import inspect

    from affordance_runtime.planner_adapters import ParentAgentPlannerAdapter

    signature = inspect.signature(ParentAgentPlannerAdapter.propose)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        and parameter.name != "self"
    ]

    assert [parameter.name for parameter in positional] == ["request"]
    assert "PlannerResponse" in str(signature.return_annotation)
    assert "PlannerDecision" not in str(signature.return_annotation)


def test_planner_response_compatibility_converts_to_legacy_decision() -> None:
    from affordance_runtime.planner_compatibility import planner_response_to_decision
    from affordance_runtime.planning import PlannerActionKind, PlannerProposal
    from affordance_runtime.planning_contracts import PlannerDoneResponse, PlannerProposalResponse

    proposal = PlannerProposal(
        proposal_id="proposal:activate",
        based_on_task_revision=1,
        based_on_state_version=2,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="semantic:save",
        parameters={},
        expected_effects=("saved",),
    )

    proposal_decision = planner_response_to_decision(
        PlannerProposalResponse(proposal=proposal, reason="ready")
    )
    done_decision = planner_response_to_decision(
        PlannerDoneResponse(result={"status": "done"}, reason="verified")
    )

    assert proposal_decision.proposal is proposal
    assert proposal_decision.done is False
    assert proposal_decision.contract is None
    assert done_decision.done is True
    assert done_decision.result["status"] == "done"


def test_planner_unsupported_response_preserves_typed_reason_in_compatibility_decision() -> None:
    from affordance_runtime.planner_compatibility import planner_response_to_decision
    from affordance_runtime.planning_contracts import PlannerUnsupportedResponse

    decision = planner_response_to_decision(
        PlannerUnsupportedResponse(
            reason_code="no_feasible_action_choice",
            message="Runtime could not construct an active-step action choice.",
        )
    )

    assert decision.proposal is None
    assert decision.done is False
    assert decision.reason == "Runtime could not construct an active-step action choice."
    assert decision.planner_context["unsupported_reason_code"] == (
        "no_feasible_action_choice"
    )
