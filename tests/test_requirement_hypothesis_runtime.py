from itertools import permutations

import pytest

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.task import (
    HypothesisAdmissionCode,
    HypothesisPredicateAssessment,
    HypothesisProposalMode,
    RequirementHypothesisProposal,
    RequirementHypothesisProposalBatch,
    RequirementHypothesisState,
    TaskGoal,
    admit_requirement_hypotheses,
    assess_requirement_hypotheses,
)
from affordance_runtime.task.frontier import synchronize_verified_task_state
from affordance_runtime.task.frontier_contracts import (
    FactAvailable,
    LiteralExpected,
    TargetAbsent,
    TargetFieldEquals,
)
from affordance_runtime.world import (
    ActionSpace,
    CoverageState,
    EntityInventoryStatus,
    EntityInventorySummary,
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldObservation,
)


def _world(*, complete: bool = True, target_count: int = 1) -> WorldObservation:
    targets = tuple(
        SemanticTarget(f"entity:{index}", "textbox", f"Field {index}", {"value": ""}) for index in range(target_count)
    )
    inventory = (
        EntityInventorySummary(
            status=EntityInventoryStatus.COMPLETE,
            entity_count=len(targets),
            entity_total_count=len(targets),
        )
        if complete
        else EntityInventorySummary()
    )
    source = SurfaceObservation(
        "observation:1",
        "dom",
        "revision:1",
        ObservationSourceProfile.dom(),
        targets=targets,
        entity_inventory=inventory,
    )
    return WorldObservation(
        "observation:1",
        targets,
        (),
        (),
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )


def _evaluation(status: TaskEvaluationStatus = TaskEvaluationStatus.INCOMPLETE):
    return TaskEvaluation("task:1", "observation:1", status, "fixture evaluation")


def _proposal(target_id: str, value: str = "Ada") -> RequirementHypothesisProposal:
    return RequirementHypothesisProposal(
        f"Set {target_id}",
        TargetFieldEquals(target_id, "value", LiteralExpected(value)),
        (target_id,),
    )


def test_admission_installs_valid_items_and_rejects_bad_references_independently() -> None:
    world = _world()
    admitted = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (_proposal("entity:0"), _proposal("entity:missing")),
        ),
        world,
    )

    assert admitted.accepted_count == 1
    assert admitted.rejected_count == 1
    assert admitted.rejected_codes == (HypothesisAdmissionCode.UNKNOWN_ENTITY,)
    assert admitted.state.active[0].hypothesis_id == "hypothesis:1"
    assert admitted.state.active[0].predicate.target_id == "entity:0"


def test_admission_installs_known_target_while_rejecting_unknown_fact() -> None:
    admitted = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (
                _proposal("entity:0"),
                RequirementHypothesisProposal(
                    "Check a hallucinated fact",
                    FactAvailable("fact:missing"),
                    ("entity:0",),
                ),
            ),
        ),
        _world(),
    )

    assert admitted.accepted_count == 1
    assert admitted.rejected_codes == (HypothesisAdmissionCode.UNKNOWN_FACT,)
    assert len(admitted.state.active) == 1


def test_admission_deduplicates_repeated_items_within_one_batch() -> None:
    proposal = _proposal("entity:0")
    admitted = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (proposal, proposal),
        ),
        _world(),
    )

    assert admitted.accepted_count == 1
    assert admitted.rejected_count == 1
    assert admitted.rejected_codes == (HypothesisAdmissionCode.DUPLICATE,)
    assert len(admitted.state.active) == 1


@pytest.mark.parametrize(
    "items",
    tuple(permutations(("valid", "unknown", "duplicate"))),
)
def test_mixed_admission_has_one_item_addressed_outcome_per_input_regardless_of_order(
    items: tuple[str, ...],
) -> None:
    proposals = tuple(_proposal("entity:missing") if item == "unknown" else _proposal("entity:0") for item in items)

    admitted = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(HypothesisProposalMode.INITIAL, proposals),
        _world(),
    )

    assert admitted.accepted_count == 1
    assert admitted.rejected_count == 2
    assert set(admitted.accepted_item_indices).isdisjoint(item.item_index for item in admitted.rejections)
    assert sorted((*admitted.accepted_item_indices, *(item.item_index for item in admitted.rejections))) == [0, 1, 2]
    assert {item.code for item in admitted.rejections} == {
        HypothesisAdmissionCode.UNKNOWN_ENTITY,
        HypothesisAdmissionCode.DUPLICATE,
    }


def test_repeated_replace_remains_live_after_retired_history_reaches_capacity() -> None:
    state = RequirementHypothesisState()
    for index in range(24):
        state = admit_requirement_hypotheses(
            state,
            RequirementHypothesisProposalBatch(
                HypothesisProposalMode.REPLACE if index else HypothesisProposalMode.INITIAL,
                (_proposal("entity:0", f"value-{index}"),),
            ),
            _world(),
        ).state

    assert len(state.hypotheses) <= 16
    assert len(state.active) == 1
    assert state.active[0].predicate.expected.value == "value-23"
    assert state.active[0].hypothesis_id == "hypothesis:24"


def test_invalid_replace_batch_does_not_retire_existing_hypotheses() -> None:
    initial = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (_proposal("entity:0"),),
        ),
        _world(),
    ).state

    rejected = admit_requirement_hypotheses(
        initial,
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.REPLACE,
            (_proposal("entity:missing"),),
        ),
        _world(),
    )

    assert rejected.accepted_count == 0
    assert rejected.rejected_codes == (HypothesisAdmissionCode.UNKNOWN_ENTITY,)
    assert rejected.state == initial


def test_verifier_does_not_infer_absence_from_incomplete_inventory() -> None:
    initial = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (
                RequirementHypothesisProposal(
                    "Remove the target",
                    TargetAbsent("entity:0"),
                    ("entity:0",),
                ),
            ),
        ),
        _world(complete=False),
    ).state
    incomplete_without_target = _world(complete=False, target_count=0)

    assessed = assess_requirement_hypotheses(
        initial,
        incomplete_without_target,
        _evaluation(),
    )

    assert assessed.active[0].assessment is HypothesisPredicateAssessment.UNKNOWN


def test_hypotheses_are_projected_but_do_not_change_action_authority() -> None:
    world = _world()
    admitted = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (_proposal("entity:0"),),
        ),
        world,
    )
    state = AgentLoopState(world)
    state.install_requirement_hypotheses(admitted.state)
    task = TaskGoal("task:1", "Set the field")
    actions = ActionSpace(world.observation_id, ())
    state.install_verified_task_state(
        synchronize_verified_task_state(task, _evaluation(), world, None),
    )

    context = ContextBuilder().build(task, state, actions, _evaluation())

    assert context.actions.options == ()
    assert context.progress.task_frontier is not None
    hypotheses = context.progress.task_frontier.requirement_hypotheses
    assert hypotheses[0].hypothesis_id == "hypothesis:1"
    assert hypotheses[0].assessment == "unknown"


def test_incremental_proposal_budget_is_finite() -> None:
    state = AgentLoopState(_world())
    for index in range(4):
        state.record_requirement_hypothesis_proposal(f"basis:{index}")

    with pytest.raises(ValueError, match="budget"):
        state.record_requirement_hypothesis_proposal("basis:overflow")
