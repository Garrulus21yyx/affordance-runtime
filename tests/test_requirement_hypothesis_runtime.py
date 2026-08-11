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
        SemanticTarget(f"entity:{index}", "textbox", f"Field {index}", {"value": ""})
        for index in range(target_count)
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


def test_admission_is_atomic_and_runtime_assigns_ids() -> None:
    world = _world()
    rejected = admit_requirement_hypotheses(
        RequirementHypothesisState(),
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (_proposal("entity:0"), _proposal("entity:missing")),
        ),
        world,
    )

    assert rejected.state == RequirementHypothesisState()
    assert rejected.accepted_count == 0
    assert rejected.rejected_codes == (HypothesisAdmissionCode.UNKNOWN_ENTITY,)

    accepted = admit_requirement_hypotheses(
        rejected.state,
        RequirementHypothesisProposalBatch(
            HypothesisProposalMode.INITIAL,
            (_proposal("entity:0"),),
        ),
        world,
    )
    assert accepted.accepted_count == 1
    assert accepted.state.active[0].hypothesis_id == "hypothesis:1"


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
