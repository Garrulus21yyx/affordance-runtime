from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_progress import (
    CurrentStateSubgoalCompletionEvaluator,
    TaskPlanProgressStateView,
)
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


def _plan(
    *,
    relation: SubgoalOutcomeRelation = SubgoalOutcomeRelation.IS_AVAILABLE,
) -> TaskPlan:
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
    read_only_subgoal = SubgoalSpec(
        subgoal_id="submit-button-available",
        objective=f"submit button {relation.value}",
        depends_on=("text-field-changed",),
        success_criteria=(f"submit button {relation.value}",),
        evidence_requirements=("current submit button observation",),
        operation_class=OperationClass.READ_ONLY,
        action_family=TaskPlanActionFamily.WAIT,
        outcome=SubgoalOutcome(
            subject="Submit",
            relation=relation,
        ),
    )
    return TaskPlan(
        plan_id="plan-submit",
        task_id="task-submit",
        task_revision=1,
        plan_version=1,
        based_on_state_version=7,
        generated_by=TaskPlanSource.RULE,
        subgoals=(text_subgoal, read_only_subgoal),
    )


def _progress(
    plan: TaskPlan,
    *,
    completed: tuple[str, ...] = ("text-field-changed",),
    plan_id: str | None = None,
    plan_version: int | None = None,
    state_version: int | None = None,
) -> TaskPlanProgressStateView:
    progress = TaskPlanProgressStateView(
        plan_id=plan.plan_id if plan_id is None else plan_id,
        plan_version=plan.plan_version if plan_version is None else plan_version,
        based_on_state_version=(
            plan.based_on_state_version if state_version is None else state_version
        ),
        active_subgoal_id="submit-button-available",
        completed_subgoal_ids=completed,
        failed_subgoal_ids=(),
    )
    return progress


def _environment(
    *,
    visible: bool | None = True,
    enabled: bool | None = True,
    duplicate: bool = False,
    snapshot_id: str = "snapshot-1",
) -> PlanningEnvironmentSummary:
    affordance = PlanningAffordanceSummary(
        semantic_target_id="submit-button",
        role="button",
        label="Submit",
        supported_actions=("activate",),
        current_state=PlanningAffordanceState(visible=visible, enabled=enabled),
    )
    affordances = (affordance,)
    if duplicate:
        affordances = (
            affordance,
            affordance.model_copy(update={"semantic_target_id": "submit-button-2"}),
        )
    return PlanningEnvironmentSummary(
        environment_revision="env-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
        affordances=affordances,
    )


def test_required_available_subgoal_is_completed_without_deleting_obligation() -> None:
    plan = _plan()
    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(),
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


def test_visible_subgoal_can_be_completed_from_current_observation() -> None:
    plan = _plan(relation=SubgoalOutcomeRelation.IS_VISIBLE)

    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(visible=True, enabled=None),
    )

    assert preparation is not None
    assert preparation.subgoal_id == "submit-button-available"


def test_dependency_must_be_completed_before_current_state_progress() -> None:
    plan = _plan()

    assert (
        CurrentStateSubgoalCompletionEvaluator().evaluate(
            plan=plan,
            progress=_progress(plan, completed=()),
            environment=_environment(),
        )
        is None
    )


def test_multiple_matching_affordances_fail_closed() -> None:
    plan = _plan()

    assert (
        CurrentStateSubgoalCompletionEvaluator().evaluate(
            plan=plan,
            progress=_progress(plan),
            environment=_environment(duplicate=True),
        )
        is None
    )


def test_hidden_or_disabled_affordance_does_not_satisfy_availability() -> None:
    plan = _plan()
    evaluator = CurrentStateSubgoalCompletionEvaluator()

    assert evaluator.evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(visible=False),
    ) is None
    assert evaluator.evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(enabled=False),
    ) is None


def test_stale_progress_identity_is_rejected() -> None:
    plan = _plan()
    evaluator = CurrentStateSubgoalCompletionEvaluator()

    assert evaluator.evaluate(
        plan=plan,
        progress=_progress(plan, plan_id="older-plan"),
        environment=_environment(),
    ) is None
    assert evaluator.evaluate(
        plan=plan,
        progress=_progress(plan, plan_version=0),
        environment=_environment(),
    ) is None
    assert evaluator.evaluate(
        plan=plan,
        progress=_progress(plan, state_version=6),
        environment=_environment(),
    ) is None
