from __future__ import annotations

import pytest

from affordance_runtime.mission import (
    AuditBoundary,
    EvidenceBundle,
    ManagerAssessment,
    ManagerDecision,
    ManagerRecoveryView,
    ManagerRequestMode,
    ManagerRoleRequest,
    ManagerRoute,
    MissionState,
    SubtaskContract,
    WorkingFactProposal,
    WorkingOutcomeProposal,
)
from affordance_runtime.model.mission_roles import ManagerDecisionModel, SubtaskContractModel
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import SemanticTarget, StateFact
from tests.support.world import fused_world


def _task() -> TaskGoal:
    return TaskGoal("task:mission", "Find the answer and submit it.", requested_outputs=("answer",))


def _world(value: object = "42"):
    target = SemanticTarget("target:answer", "text", "Answer", {"value": value})
    fact = StateFact("fact:obs:answer", target.target_id, "value", value, "obs")
    return fused_world("obs", (target,), (fact,), surface="browsergym")


def test_initial_manager_request_is_explicit_and_ref_free() -> None:
    request = ManagerRoleRequest(
        mode=ManagerRequestMode.INITIAL_PLAN,
        original_task=_task(),
        mission_state=MissionState.empty(),
        remaining_rounds=4,
    )

    assert request.mode is ManagerRequestMode.INITIAL_PLAN
    assert request.active_subtask is None
    assert request.review_world is None


def test_review_request_requires_one_complete_fresh_bundle() -> None:
    world = _world()
    subtask = SubtaskContract("Find answer", "Answer is visible")
    recovery = ManagerRecoveryView("outcome_proposed", True, subtask)
    with pytest.raises(ValueError, match="complete fresh review"):
        ManagerRoleRequest(
            mode=ManagerRequestMode.REVIEW_AND_ROUTE,
            original_task=_task(),
            mission_state=MissionState.empty(),
            recovery=recovery,
            active_subtask=subtask,
            review_world=world,
        )


def test_initial_manager_produces_exactly_one_bounded_subtask() -> None:
    model = ManagerDecisionModel.model_validate(
        {
            "assessment": "not_applicable",
            "route": "execute_subtask",
            "subtask": {
                "objective": "Find the requested answer",
                "done_when": "The requested answer is visible",
                "episode_turn_budget": 8,
            },
        }
    )

    assert isinstance(model.subtask, SubtaskContractModel)
    assert model.subtask.episode_turn_budget == 8


def test_manager_review_carries_assessment_route_and_working_proposals_together() -> None:
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.REQUEST_FINALIZATION,
        ("fact:obs:answer",),
        (
            WorkingOutcomeProposal(
                "outcome:answer",
                ManagerAssessment.SATISFIED,
                ("fact:obs:answer",),
                "answer visible",
            ),
        ),
        (
            WorkingFactProposal(
                "answer", "fact:obs:answer", "42", "final response candidate"
            ),
        ),
        reason="Current evidence supports final formatting.",
    )

    proposal = decision.state_proposal(0)
    assert proposal is not None
    assert proposal.assessment is ManagerAssessment.SATISFIED
    assert decision.route is ManagerRoute.REQUEST_FINALIZATION


def test_evidence_boundary_accepts_exact_identity_and_is_the_only_state_writer() -> None:
    world = _world()
    bundle = EvidenceBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.kind == "fact")
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.REQUEST_FINALIZATION,
        (record.evidence_ref,),
        (
            WorkingOutcomeProposal(
                "outcome:answer",
                ManagerAssessment.SATISFIED,
                (record.evidence_ref,),
                "answer visible",
            ),
        ),
        (
            WorkingFactProposal(
                "answer", record.evidence_ref, record.value, "final response candidate"
            ),
        ),
    )
    mission = MissionState.empty()

    accepted = AuditBoundary().accept(mission, decision.state_proposal(0), bundle)

    assert accepted.accepted
    assert accepted.mission_state.version == 1
    assert accepted.mission_state.working_outcomes[0].outcome_id == "outcome:answer"
    assert mission == MissionState.empty()


def test_evidence_boundary_rejection_does_not_change_mission_state() -> None:
    world = _world()
    bundle = EvidenceBundle.from_world(world)
    mission = MissionState.empty()
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.REQUEST_FINALIZATION,
        ("fact:missing",),
        (
            WorkingOutcomeProposal(
                "outcome:answer",
                ManagerAssessment.SATISFIED,
                ("fact:missing",),
                "unsupported",
            ),
        ),
    )

    rejected = AuditBoundary().accept(mission, decision.state_proposal(0), bundle)

    assert not rejected.accepted
    assert rejected.mission_state is mission
