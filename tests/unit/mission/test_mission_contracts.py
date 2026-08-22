import json

import pytest

from affordance_runtime.agent import WorkingFact
from affordance_runtime.agent.budgets import EpisodeBudget
from affordance_runtime.agent.working_facts import validate_working_fact_collection
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.mission import (
    AcceptedWorkingOutcome,
    AuditorDecision,
    AuditorRoleRequest,
    EvidenceAssessment,
    EvidenceBoundary,
    EvidenceBundle,
    EvidenceRequirement,
    Milestone,
    MilestoneAdmissionRoute,
    MilestoneRoadmap,
    MissionState,
    PlannerDecision,
    PlannerRoute,
    PublicOutcomeSummary,
    WorkingOutcomeProposal,
)
from affordance_runtime.model.mission_roles import (
    MilestoneRoadmapModel,
    PlannerDecisionModel,
    _auditor_messages,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import SemanticTarget, StateFact
from tests.support.world import fused_world


def _milestone(identifier: str, *, depends_on=(), final=False):
    return Milestone(identifier, f"Outcome {identifier}", f"Observable {identifier}", (), depends_on, final)


def test_roadmap_is_bounded_closed_and_mechanically_selects_dependency_ready_milestone() -> None:
    roadmap = MilestoneRoadmap(1, (_milestone("first"), _milestone("second", depends_on=("first",), final=True)))
    assert roadmap.select_ready(MissionState.empty()).id == "first"
    mission = MissionState(
        1,
        (AcceptedWorkingOutcome("first", EvidenceAssessment.SATISFIED, ("fact:first",), "done"),),
    )
    assert roadmap.select_ready(mission).id == "second"


def test_unsatisfied_outcome_never_unlocks_a_dependency() -> None:
    roadmap = MilestoneRoadmap(1, (_milestone("first"), _milestone("second", depends_on=("first",))))
    mission = MissionState(
        1,
        (AcceptedWorkingOutcome("first", EvidenceAssessment.UNSATISFIED, (), "not done"),),
    )

    assert roadmap.select_ready(mission).id == "first"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AcceptedWorkingOutcome("result", EvidenceAssessment.SATISFIED, (), "done"),
        lambda: WorkingOutcomeProposal("result", EvidenceAssessment.SATISFIED, (), "done"),
        lambda: AuditorDecision(EvidenceAssessment.SATISFIED, (), "done"),
    ],
)
def test_satisfied_semantic_outcomes_cannot_enter_any_boundary_without_evidence(factory) -> None:
    with pytest.raises(ValueError, match="requires evidence refs"):
        factory()


@pytest.mark.parametrize(
    "milestones",
    [
        (),
        tuple(_milestone(f"m{index}") for index in range(6)),
        (_milestone("same"), _milestone("same")),
        (_milestone("one", depends_on=("missing",)),),
        (_milestone("one", depends_on=("two",)), _milestone("two", depends_on=("one",))),
        (_milestone("one", final=True), _milestone("two", final=True)),
    ],
)
def test_roadmap_rejects_open_or_ambiguous_graphs(milestones) -> None:
    with pytest.raises(ValueError):
        MilestoneRoadmap(1, milestones)


def test_planner_schema_contains_only_the_bounded_roadmap_algebra() -> None:
    fields = MilestoneRoadmapModel.model_json_schema()["$defs"]["MilestoneModel"]["properties"]
    assert set(fields) == {"id", "outcome", "done_when", "required_evidence", "depends_on", "final"}
    forbidden = {
        "entry_scope_key",
        "episode_turn_budget",
        "completed",
        "selector",
        "action",
        "tool",
    }
    assert forbidden.isdisjoint(fields)


def test_planner_schema_rejects_all_extra_authority_fields_and_missing_contract_fields() -> None:
    base = {
        "id": "result",
        "outcome": "Requested result is available",
        "done_when": "A fresh result is observable",
        "required_evidence": [],
        "depends_on": [],
        "final": True,
    }
    for extra in ("tool", "action", "selector", "target_ref", "coordinates", "field_commands", "episode_budget"):
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            PlannerDecisionModel.model_validate(
                {
                    "route": "roadmap",
                    "roadmap": {"version": 1, "milestones": [{**base, extra: "forbidden"}]},
                }
            )
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        PlannerDecisionModel.model_validate(
            {"route": "roadmap", "roadmap": {"version": 1, "description": "extra", "milestones": [base]}}
        )
    with pytest.raises(ValueError):
        PlannerDecisionModel.model_validate(
            {"route": "roadmap", "roadmap": {"version": 1, "milestones": [{"id": "missing"}]}}
        )


def test_planner_decision_has_no_state_write_or_finalization_fields() -> None:
    decision = PlannerDecision(PlannerRoute.ROADMAP, MilestoneRoadmap(1, (_milestone("result"),)))
    assert set(vars(decision)) == {"route", "roadmap", "question", "reason"}


def test_unrelated_world_change_routes_to_semantic_audit_but_cannot_mechanically_complete() -> None:
    admission = EvidenceBoundary().evaluate_milestone(
        MissionState.empty(),
        _milestone("business_outcome"),
        fused_world("before"),
        fused_world("after", targets=(SemanticTarget("unrelated", "status", "Unrelated change"),)),
        (),
        "planner claimed completion",
    )
    assert admission.assessment is EvidenceAssessment.UNKNOWN
    assert admission.route is MilestoneAdmissionRoute.SEMANTIC_AUDIT
    assert admission.proposal is None


def test_matching_required_key_cannot_turn_an_unrelated_scalar_into_semantic_proof() -> None:
    world = fused_world(
        "semantic-proof",
        targets=(SemanticTarget("unrelated", "status", "Unrelated scalar"),),
        facts=(StateFact("result", "unrelated", "value", 7, "semantic-proof"),),
    )
    record = EvidenceBundle.from_world(world).evidence_records[0]
    admission = EvidenceBoundary().evaluate_milestone(
        MissionState.empty(),
        Milestone(
            "purchase",
            "Purchase completed",
            "The requested order is confirmed",
            (EvidenceRequirement("confirmation", "Exact order confirmation"),),
        ),
        world,
        world,
        (WorkingFact("confirmation", record, 1, "model-selected but semantically unrelated scalar"),),
        "planner claimed completion",
    )
    assert admission.assessment is EvidenceAssessment.UNKNOWN
    assert admission.route is MilestoneAdmissionRoute.SEMANTIC_AUDIT
    assert admission.reason_code == "semantic_evidence_assessment_required"
    assert admission.proposal is None


@pytest.mark.parametrize("value", (float("nan"), float("inf"), "x" * 2_001))
def test_non_public_scalar_is_rejected_before_it_can_reach_semantic_auditor(value) -> None:
    with pytest.raises(ValueError, match="bounded public scalar"):
        WorkingFact(
            "result",
            EvidenceRecord("fact:private", "world", "fact", "fixture", value=value),
            1,
            "retain result",
        )


def test_formal_complete_evaluation_admits_without_auditor_and_promotes_required_working_fact() -> None:
    world = fused_world(
        "formal-complete",
        targets=(SemanticTarget("result", "status", "Result"),),
        facts=(StateFact("result", "result", "value", "ready", "formal-complete"),),
    )
    record = EvidenceBundle.from_world(world).evidence_records[0]
    fact = WorkingFact("result", record, 1, "retain exact result")
    admission = EvidenceBoundary().evaluate_milestone(
        MissionState.empty(),
        Milestone(
            "result",
            "Requested result is ready",
            "Native criterion is complete",
            (EvidenceRequirement("result", "Exact result"),),
            final=True,
        ),
        world,
        world,
        (fact,),
        "native completion",
        TaskEvaluation(
            "task:formal",
            world.observation_id,
            TaskEvaluationStatus.COMPLETE,
            "complete",
            completion_evidence_refs=(record.evidence_ref,),
        ),
    )

    assert admission.route is MilestoneAdmissionRoute.SATISFIED
    assert admission.proposal is not None
    assert admission.proposal.promote_facts[0].key == "result"


def test_auditor_request_rejects_any_packet_larger_than_the_exact_128_records_offered() -> None:
    records = tuple(
        EvidenceRecord(
            f"fact:{index}",
            "audit-world",
            "fact",
            "provider-free",
            source_observation_id="source:audit",
            source_modality="structural",
            source_assurance="structural",
            value=index,
        )
        for index in range(129)
    )
    bundle = EvidenceBundle("audit-world", ("source:audit",), records, total_evidence_count=129)
    summary = PublicOutcomeSummary("before", "audit-world", True)

    with pytest.raises(ValueError, match="exceeds 128"):
        AuditorRoleRequest.from_authorities(
            TaskGoal("task:audit-packet", "Inspect result"),
            _milestone("result"),
            MissionState.empty(),
            (),
            summary,
            "outcome_proposed",
            bundle,
        )

    packet = bundle.bounded_packet()
    request = AuditorRoleRequest.from_authorities(
        TaskGoal("task:audit-packet", "Inspect result"),
        _milestone("result"),
        MissionState.empty(),
        (),
        summary,
        "outcome_proposed",
        packet,
    )
    assert len(request.audit_bundle.evidence_records) == 128
    assert request.audit_bundle.resolve("fact:128") is None


def test_evidence_bundle_deduplicates_aliased_pins_and_rejects_ref_collisions() -> None:
    world = fused_world("pin-alias-world")
    record = EvidenceRecord(
        "fact:shared",
        world.observation_id,
        "fact",
        "fixture",
        source_observation_id=world.sources[0].observation_id,
        source_modality="structural",
        source_assurance="structural",
        value="same",
    )
    first = WorkingFact("first", record, 1, "retain first")
    second = WorkingFact("second", record, 2, "retain second")
    bundle = EvidenceBundle.from_world(world, (first, second))
    assert bundle.pinned_evidence_refs == (record.evidence_ref,)
    assert tuple(item for item in bundle.evidence_records if item.evidence_ref == record.evidence_ref) == (record,)

    conflicting = WorkingFact(
        "conflicting",
        EvidenceRecord(
            record.evidence_ref,
            world.observation_id,
            "fact",
            "fixture",
            source_observation_id=world.sources[0].observation_id,
            source_modality="structural",
            source_assurance="structural",
            value="different",
        ),
        3,
        "retain conflict",
    )
    with pytest.raises(ValueError, match="conflicting observation versions"):
        validate_working_fact_collection((first, conflicting))
    with pytest.raises(ValueError, match="conflicting records"):
        EvidenceBundle.from_world(world, (first, conflicting))


def test_auditor_serialized_task_projection_excludes_nested_benchmark_oracles() -> None:
    world = fused_world(
        "audit-oracle-world",
        targets=(SemanticTarget("result", "status", "Requested result"),),
    )
    request = AuditorRoleRequest.from_authorities(
        TaskGoal(
            "task:audit-oracle",
            "Verify whether the requested business result is present",
            success_criteria=(
                {
                    "id": "native-result",
                    "predicate": "result",
                    "value": True,
                    "expected_answer": "PRIVATE-ORACLE-7",
                    "reward": 1.0,
                    "trajectory": ["click secret"],
                },
            ),
        ),
        _milestone("result"),
        MissionState.empty(),
        (),
        PublicOutcomeSummary("before", world.observation_id, True),
        "outcome_proposed",
        EvidenceBundle.from_world(world).bounded_packet(),
    )

    serialized = json.dumps([item.content for item in _auditor_messages(request)])
    assert "PRIVATE-ORACLE-7" not in serialized
    assert "click secret" not in serialized
    assert '"reward"' not in serialized
    assert "success_criteria" not in serialized


def test_hard_cap_16_is_rejected_and_ordinary_budget_is_exactly_15() -> None:
    assert EpisodeBudget.ordinary().turns == 15
    with pytest.raises(ValueError):
        EpisodeBudget.explicit(16)
