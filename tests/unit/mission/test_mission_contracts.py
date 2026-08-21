from __future__ import annotations

import pytest
from pydantic import ValidationError

import affordance_runtime.mission as mission_api
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.mission import (
    AcceptedFact,
    EvidenceBoundary,
    EvidenceBoundaryRejectionClass,
    EvidenceBundle,
    EvidenceRequirement,
    ManagerAssessment,
    ManagerDecision,
    ManagerRecoveryView,
    ManagerRequestMode,
    ManagerRoleRequest,
    ManagerRoute,
    MissionState,
    SubtaskContract,
    SubtaskOutcomeKind,
    WorkingFactProposal,
    WorkingOutcomeProposal,
    WorkingStateProposal,
)
from affordance_runtime.model.mission_roles import (
    InitialManagerDecisionModel,
    ReviewManagerDecisionModel,
    SubtaskContractModel,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import SemanticTarget, StateFact
from tests.support.world import fused_world


def _task() -> TaskGoal:
    return TaskGoal("task:mission", "Find the answer and submit it.", requested_outputs=("answer",))


def _world(value: object = "42", observation_id: str = "obs"):
    target = SemanticTarget("target:answer", "text", "Answer", {"value": value})
    fact = StateFact(
        f"fact:{observation_id}:answer",
        target.target_id,
        "value",
        value,
        observation_id,
    )
    return fused_world(observation_id, (target,), (fact,), surface="browsergym")


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


def test_legacy_audit_boundary_export_is_removed() -> None:
    assert not hasattr(mission_api, "AuditBoundary")


def test_review_request_requires_one_complete_fresh_bundle() -> None:
    world = _world()
    subtask = SubtaskContract("Find answer", "Answer is visible", "Provides the requested answer")
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
    model = InitialManagerDecisionModel.model_validate(
        {
            "route": "execute_subtask",
            "subtask": {
                "objective": "Find the requested answer",
                "done_when": "The requested answer is visible",
                "task_link": "Provides the user's requested answer",
                "episode_turn_budget": 8,
            },
        }
    )

    assert isinstance(model.subtask, SubtaskContractModel)
    assert model.subtask.episode_turn_budget == 8


@pytest.mark.parametrize(
    ("model_type", "outcome_kind", "required_evidence"),
    (
        (InitialManagerDecisionModel, "state_change", ()),
        (
            InitialManagerDecisionModel,
            "evidence_packet",
            ({"key": "measured_value", "description": "exact measured value"},),
        ),
        (ReviewManagerDecisionModel, "state_change", ()),
        (
            ReviewManagerDecisionModel,
            "evidence_packet",
            ({"key": "measured_value", "description": "exact measured value"},),
        ),
    ),
)
def test_manager_initial_and_review_schemas_support_closed_subtask_outcomes(
    model_type, outcome_kind, required_evidence
) -> None:
    payload = {
        "route": "execute_subtask",
        "subtask": {
            "objective": "Produce one independently reviewable result",
            "done_when": "One bounded result is observable",
            "task_link": "Provides one unresolved requested result",
            "outcome_kind": outcome_kind,
            "required_evidence": required_evidence,
            "episode_turn_budget": 6,
        },
    }
    if model_type is ReviewManagerDecisionModel:
        payload["assessment"] = "unknown"
    model = model_type.model_validate(payload)
    assert model.subtask is not None
    assert model.subtask.outcome_kind == outcome_kind


def test_evidence_packet_requires_typed_bounded_evidence_requirement() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SubtaskContract(
            "Collect one result",
            "One evidence packet is ready",
            "Provides the requested result evidence",
            SubtaskOutcomeKind.EVIDENCE_PACKET,
        )
    contract = SubtaskContract(
        "Collect one result",
        "One evidence packet is ready",
        "Provides the requested result evidence",
        SubtaskOutcomeKind.EVIDENCE_PACKET,
        required_evidence=(EvidenceRequirement("measured_value", "exact measured value"),),
    )
    assert contract.required_evidence[0].key == "measured_value"


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
                "answer", "fact:obs:answer", "final response candidate"
            ),
        ),
        reason="Current evidence supports final formatting.",
        final_response={"answer": "42"},
        final_response_evidence_refs=("fact:obs:answer",),
    )

    proposal = decision.state_proposal(0)
    assert proposal is not None
    assert proposal.assessment is ManagerAssessment.SATISFIED
    assert decision.route is ManagerRoute.REQUEST_FINALIZATION


def test_working_fact_proposal_cannot_accept_a_model_supplied_value() -> None:
    with pytest.raises(TypeError):
        WorkingFactProposal(
            "answer",
            "fact:obs:answer",
            "model supplied value",
            "final response candidate",
        )

    with pytest.raises(ValidationError):
        ReviewManagerDecisionModel.model_validate(
            {
                "assessment": "satisfied",
                "route": "request_finalization",
                "working_facts": [
                    {
                        "key": "answer",
                        "evidence_ref": "F1",
                        "value": "model supplied value",
                        "purpose": "final response candidate",
                    }
                ],
                "final_response": {"answer": "42"},
                "final_response_evidence_refs": ["F1"],
            }
        )


def test_evidence_boundary_accepts_exact_identity_and_is_the_only_state_writer() -> None:
    world = _world()
    bundle = EvidenceBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.kind == "fact")
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.REQUEST_FINALIZATION,
        evidence_refs=(record.evidence_ref,),
        working_outcomes=(
            WorkingOutcomeProposal(
                "outcome:answer",
                ManagerAssessment.SATISFIED,
                (record.evidence_ref,),
                "answer visible",
            ),
        ),
        working_facts=(
            WorkingFactProposal(
                "answer", record.evidence_ref, "final response candidate"
            ),
        ),
        final_response={"answer": "42"},
        final_response_evidence_refs=(record.evidence_ref,),
    )
    mission = MissionState.empty()

    accepted = EvidenceBoundary().accept(mission, decision.state_proposal(0), bundle)

    assert accepted.accepted
    assert accepted.mission_state.version == 1
    assert accepted.mission_state.working_outcomes[0].outcome_id == "outcome:answer"
    assert mission == MissionState.empty()


def test_pinned_episode_fact_is_mechanically_promoted_with_original_lineage() -> None:
    acquired_world = _world("33 units", "obs:acquired")
    acquired_bundle = EvidenceBundle.from_world(acquired_world)
    record = next(item for item in acquired_bundle.evidence_records if item.kind == "fact")
    pinned = WorkingFact("measured_distance", record, 4, "compare after navigation")
    review_world = _world("fresh review", "obs:review")
    review_bundle = EvidenceBundle.from_world(review_world, (pinned,))
    proposal = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.EXECUTE_SUBTASK,
        working_facts=(
            WorkingFactProposal(
                "measured_distance",
                record.evidence_ref,
                "carry the measured value",
            ),
        ),
        subtask=SubtaskContract(
            "Continue comparison",
            "One comparison result is visible",
            "Advances the requested comparison",
        ),
    ).state_proposal(0)
    assert proposal is not None

    admitted = EvidenceBoundary().accept(MissionState.empty(), proposal, review_bundle)

    assert admitted.accepted
    accepted = admitted.mission_state.accepted_facts[0]
    assert accepted.record is record
    assert accepted.record.value == "33 units"
    assert accepted.record.observation_id == acquired_world.observation_id
    assert admitted.mission_state.carry_working_facts(("measured_distance",))[0].record is record
    with_unrelated = MissionState(
        admitted.mission_state.version,
        admitted.mission_state.working_outcomes,
        (
            accepted,
            AcceptedFact("unrelated_value", record, "not selected by this subtask", 1),
        ),
        admitted.mission_state.evidence_lineage,
    )
    carried = with_unrelated.carry_working_facts(("measured_distance",))
    assert tuple(item.key for item in carried) == ("measured_distance",)


def test_manager_can_promote_one_composite_working_outcome_from_multiple_scalar_refs() -> None:
    world = fused_world(
        "obs:composite",
        (
            SemanticTarget("target:identity", "text", "Facility", {"value": "North Hub"}),
            SemanticTarget("target:distance", "status", "Distance", {"value": "17 km"}),
        ),
        (
            StateFact("fact:identity", "target:identity", "value", "North Hub", "obs:composite"),
            StateFact("fact:distance", "target:distance", "value", "17 km", "obs:composite"),
        ),
        surface="browsergym",
    )
    bundle = EvidenceBundle.from_world(world)
    refs = tuple(
        item.evidence_ref
        for item in bundle.evidence_records
        if item.kind == "fact" and item.value in {"North Hub", "17 km"}
    )
    assert len(refs) == 2
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.BLOCKED,
        evidence_refs=refs,
        working_outcomes=(
            WorkingOutcomeProposal(
                "outcome:facility_verified",
                ManagerAssessment.SATISFIED,
                refs,
                "North Hub, 17 km",
            ),
        ),
    )
    proposal = decision.state_proposal(0)
    assert proposal is not None

    admitted = EvidenceBoundary().accept(MissionState.empty(), proposal, bundle)

    assert admitted.accepted
    outcome = admitted.mission_state.working_outcomes[0]
    assert outcome.outcome_id == "outcome:facility_verified"
    assert {item.value for item in outcome.evidence_records} == {"North Hub", "17 km"}


@pytest.mark.parametrize(
    ("overall_assessment", "working_assessment"),
    (
        (ManagerAssessment.UNSATISFIED, ManagerAssessment.SATISFIED),
        (ManagerAssessment.SATISFIED, ManagerAssessment.UNSATISFIED),
    ),
)
def test_evidence_boundary_keeps_overall_and_working_assessments_independent(
    overall_assessment: ManagerAssessment,
    working_assessment: ManagerAssessment,
) -> None:
    world = _world()
    bundle = EvidenceBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.kind == "fact")
    decision = ManagerDecision(
        overall_assessment,
        ManagerRoute.BLOCKED,
        evidence_refs=(record.evidence_ref,),
        working_outcomes=(
            WorkingOutcomeProposal(
                "outcome:partial_result",
                working_assessment,
                (record.evidence_ref,),
                "One independently evidenced partial result.",
            ),
        ),
    )
    proposal = decision.state_proposal(0)
    assert proposal is not None

    admitted = EvidenceBoundary().accept(MissionState.empty(), proposal, bundle)

    assert admitted.accepted
    assert admitted.mission_state.version == 1
    assert admitted.mission_state.working_outcomes[0].assessment is working_assessment
    assert proposal.assessment is overall_assessment


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
        final_response={"answer": "unsupported"},
        final_response_evidence_refs=("fact:missing",),
    )

    rejected = EvidenceBoundary().accept(mission, decision.state_proposal(0), bundle)

    assert not rejected.accepted
    assert rejected.mission_state is mission
    assert rejected.rejection_class is EvidenceBoundaryRejectionClass.FATAL


def test_evidence_boundary_classifies_idempotent_fact_write_as_recoverable_noop() -> None:
    world = _world()
    bundle = EvidenceBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.kind == "fact")
    first = WorkingStateProposal(
        ManagerAssessment.SATISFIED,
        0,
        promote_facts=(
            WorkingFactProposal("answer", record.evidence_ref, "retain the answer"),
        ),
    )
    admitted = EvidenceBoundary().accept(MissionState.empty(), first, bundle)
    assert admitted.accepted
    repeated = WorkingStateProposal(
        ManagerAssessment.UNSATISFIED,
        admitted.mission_state.version,
        promote_facts=(
            WorkingFactProposal("answer", record.evidence_ref, "retain the answer"),
        ),
    )

    rejected = EvidenceBoundary().accept(admitted.mission_state, repeated, bundle)

    assert not rejected.accepted
    assert rejected.reason_code == "working_state_noop"
    assert rejected.rejection_class is EvidenceBoundaryRejectionClass.RECOVERABLE_SHAPE
    assert rejected.mission_state is admitted.mission_state


@pytest.mark.parametrize(
    "route,kwargs",
    [
        (
            ManagerRoute.EXECUTE_SUBTASK,
            {
                "subtask": SubtaskContract(
                    "Do work", "Work is done", "Advances the requested work"
                ),
                "final_response": {},
            },
        ),
        (ManagerRoute.ASK_USER, {"question": "Which value?", "final_response": {}}),
        (ManagerRoute.BLOCKED, {"final_response": {}}),
    ],
)
def test_non_final_routes_reject_terminal_response_fields(route, kwargs) -> None:
    with pytest.raises(ValueError, match="only request_finalization"):
        ManagerDecision(ManagerAssessment.UNKNOWN, route, **kwargs)


def test_request_finalization_rejects_missing_direct_response() -> None:
    with pytest.raises(ValueError, match="complete final_response"):
        ManagerDecision(
            ManagerAssessment.SATISFIED,
            ManagerRoute.REQUEST_FINALIZATION,
            final_response_evidence_refs=("fact:answer",),
        )


def test_manager_decision_model_accepts_direct_business_value_without_tool_envelope() -> None:
    model = ReviewManagerDecisionModel.model_validate(
        {
            "assessment": "satisfied",
            "route": "request_finalization",
            "final_response": {"answer": "42"},
            "final_response_evidence_refs": ("F1",),
        }
    )

    assert model.final_response == {"answer": "42"}
