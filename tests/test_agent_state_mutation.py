from test_agent_loop import _world

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
)
from affordance_runtime.task import LocalObjective
from affordance_runtime.task_plan_contracts import TaskPlan, TaskPlanGeneratorSource
from runtime_test_support import legacy_step_spec


def _plan() -> TaskPlan:
    refs = (SourceReference("request", "request:plan:1"),)
    step = legacy_step_spec(
        step_id="step:1",
        objective="enable shared state",
        interaction=ElementIntent("shared state", refs),
        completion_criteria=(
            StateCriterion(
                "criterion:step:1",
                refs,
                subject="shared state",
                relation=StateCriterionRelation.IS_COMPLETED,
                evidence_policy=CriterionEvidencePolicy(
                    EvidenceStrength.INDEPENDENT,
                    ("dom_state",),
                ),
            ),
        ),
        source_refs=refs,
    )
    return TaskPlan(
        plan_id="plan:1",
        task_id="task:1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=0,
        based_on_observation_ref="observation:1",
        generated_by=TaskPlanGeneratorSource.RULE,
        steps=(step,),
    )


def test_objective_and_plan_mutators_increment_progress_revision() -> None:
    state = AgentLoopState(_world("before", False))
    objective = LocalObjective({"enabled": True})
    plan = _plan()

    state.set_active_objective(objective)
    state.clear_active_objective()
    state.replace_plan(plan)

    assert state.active_objective is None
    assert state.plan == plan
    assert state.progress_revision == 3


def test_pending_mutators_increment_pending_revision() -> None:
    state = AgentLoopState(_world("before", False))

    state.set_pending_question("question")
    state.clear_pending_question()

    assert state.pending_user_question == ""
    assert state.pending_revision == 2
