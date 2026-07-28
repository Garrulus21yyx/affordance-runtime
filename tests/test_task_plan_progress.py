import pytest

from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import (
    PlanningAffordanceState,
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "V-PRB-6B RED: Core does not yet expose verifier-backed current-state "
        "progress accounting for required read-only subgoals"
    ),
)
def test_required_available_subgoal_is_completed_without_deleting_obligation() -> None:
    from affordance_runtime.task_plan_progress import (
        CurrentStateSubgoalCompletionEvaluator,
        TaskPlanProgressStateView,
    )

    text_subgoal = SubgoalSpec(
        subgoal_id="text-field-changed",
        objective="text field has changed",
        success_criteria=("text field has changed",),
        evidence_requirements=("post-text evidence",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.TYPE_TEXT,
        outcome=SubgoalOutcome(
            subject="text field",
            relation=SubgoalOutcomeRelation.HAS_CHANGED,
        ),
    )
    submit_subgoal = SubgoalSpec(
        subgoal_id="submit-button-available",
        objective="submit button is available",
        depends_on=("text-field-changed",),
        success_criteria=("submit button is available",),
        evidence_requirements=("current submit button observation",),
        operation_class=OperationClass.READ_ONLY,
        action_family=TaskPlanActionFamily.WAIT,
        outcome=SubgoalOutcome(
            subject="Submit",
            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
        ),
    )
    plan = TaskPlan(
        plan_id="plan-submit",
        task_id="task-submit",
        task_revision=1,
        plan_version=1,
        based_on_state_version=7,
        generated_by=TaskPlanSource.RULE,
        subgoals=(text_subgoal, submit_subgoal),
    )
    progress = TaskPlanProgressStateView(
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        based_on_state_version=7,
        active_subgoal_id="submit-button-available",
        completed_subgoal_ids=("text-field-changed",),
        failed_subgoal_ids=(),
    )
    environment = PlanningEnvironmentSummary(
        environment_revision="env-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        affordances=(
            PlanningAffordanceSummary(
                semantic_target_id="submit-button",
                role="button",
                label="Submit",
                supported_actions=("activate",),
                current_state=PlanningAffordanceState(visible=True, enabled=True),
            ),
        ),
    )

    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=progress,
        environment=environment,
    )

    assert preparation is not None
    assert preparation.plan_id == plan.plan_id
    assert preparation.plan_version == plan.plan_version
    assert preparation.based_on_state_version == 7
    assert preparation.snapshot_id == "snapshot-1"
    assert preparation.subgoal_id == "submit-button-available"
    assert preparation.source == "current_observation"
    assert preparation.evidence_refs
    assert tuple(item.subgoal_id for item in plan.subgoals) == (
        "text-field-changed",
        "submit-button-available",
    )
