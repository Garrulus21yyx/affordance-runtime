import pytest

from affordance_runtime.agent import WorkingFact
from affordance_runtime.agent.budgets import EpisodeBudget
from affordance_runtime.mission import (
    AcceptedWorkingOutcome,
    AuditorDecision,
    EvidenceAssessment,
    EvidenceBoundary,
    EvidenceBundle,
    EvidenceRequirement,
    Milestone,
    MilestoneRoadmap,
    MissionState,
    PlannerDecision,
    PlannerRoute,
    WorkingOutcomeProposal,
)
from affordance_runtime.model.mission_roles import MilestoneRoadmapModel, PlannerDecisionModel
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


def test_planner_envelope_ignores_bounded_description_extras_but_rejects_missing_contract_fields() -> None:
    model = PlannerDecisionModel.model_validate(
        {
            "route": "roadmap",
            "roadmap": {
                "version": 1,
                "description": "ignored envelope description",
                "milestones": [
                    {
                        "id": "result",
                        "outcome": "Requested result is available",
                        "done_when": "A fresh result is observable",
                        "required_evidence": [],
                        "depends_on": [],
                        "final": True,
                        "description": "ignored milestone description",
                    }
                ],
            },
        }
    )
    assert model.roadmap is not None
    with pytest.raises(ValueError):
        PlannerDecisionModel.model_validate(
            {"route": "roadmap", "roadmap": {"version": 1, "milestones": [{"id": "missing"}]}}
        )


def test_planner_decision_has_no_state_write_or_finalization_fields() -> None:
    decision = PlannerDecision(PlannerRoute.ROADMAP, MilestoneRoadmap(1, (_milestone("result"),)))
    assert set(vars(decision)) == {"route", "roadmap", "question", "reason"}


def test_unrelated_world_change_cannot_mechanically_complete_a_no_evidence_milestone() -> None:
    admission = EvidenceBoundary().evaluate_milestone(
        MissionState.empty(),
        _milestone("business_outcome"),
        fused_world("before"),
        fused_world("after"),
        (),
        "planner claimed completion",
    )
    assert admission.assessment is EvidenceAssessment.UNKNOWN
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
    assert admission.reason_code == "semantic_evidence_assessment_required"
    assert admission.proposal is None


def test_hard_cap_16_is_rejected_and_ordinary_budget_is_exactly_15() -> None:
    assert EpisodeBudget.ordinary().turns == 15
    with pytest.raises(ValueError):
        EpisodeBudget.explicit(16)
