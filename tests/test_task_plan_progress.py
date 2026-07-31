from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_progress import (
    CurrentStateEvidence,
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
from runtime_test_support import make_interaction


def _plan(
    *,
    relation: SubgoalOutcomeRelation = SubgoalOutcomeRelation.IS_AVAILABLE,
    subject: str = "Submit",
) -> TaskPlan:
    text_subgoal = SubgoalSpec(
        subgoal_id="text-field-changed",
        objective="text field has changed",
        interaction=make_interaction('text field'),
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
        interaction=make_interaction('test target'),
        depends_on=("text-field-changed",),
        success_criteria=(f"submit button {relation.value}",),
        evidence_requirements=("current submit button observation",),
        operation_class=OperationClass.READ_ONLY,
        action_family=TaskPlanActionFamily.WAIT,
        outcome=SubgoalOutcome(
            subject=subject,
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
        plan_based_on_state_version=(
            plan.based_on_state_version if state_version is None else state_version
        ),
        evaluated_at_state_version=9,
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
    page_revision: str = "page-1",
    environment_revision: str = "env-1",
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
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=page_revision,
        affordances=affordances,
    )


def test_required_available_subgoal_is_completed_without_deleting_obligation() -> None:
    plan = _plan()
    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(),
        evaluated_at_state_version=9,
    )

    assert preparation is not None
    assert preparation.plan_id == plan.plan_id
    assert preparation.plan_version == plan.plan_version
    assert preparation.evaluated_at_state_version == 9
    assert preparation.subgoal_id == "submit-button-available"
    assert preparation.source == "current_observation"
    assert preparation.criterion_ids == (
        "subgoal:submit-button-available:criterion:0",
    )
    assert preparation.requirement_ids == (
        "subgoal:submit-button-available:evidence-requirement:0",
    )
    assert preparation.evidence == (
        CurrentStateEvidence(
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
            semantic_target_id="submit-button",
            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
            observed_value=True,
            artifact_refs=(),
        ),
    )
    assert tuple(item.subgoal_id for item in plan.subgoals) == (
        "text-field-changed",
        "submit-button-available",
    )


def test_symbolic_submit_button_subject_matches_unique_submit_button() -> None:
    plan = _plan(subject="submit_button")

    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(),
    )

    assert preparation is not None
    assert preparation.evidence[0].semantic_target_id == "submit-button"


def test_textarea_subject_uses_element_kind_instead_of_shared_textbox_role() -> None:
    plan = _plan(subject="textarea")
    environment = PlanningEnvironmentSummary(
        environment_revision="env-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        affordances=(
            PlanningAffordanceSummary(
                semantic_target_id="semantic:source",
                role="textbox",
                label="Alpha",
                supported_actions=("type_text",),
                current_state=PlanningAffordanceState(
                    visible=True,
                    enabled=True,
                    element_tag="textarea",
                ),
            ),
            PlanningAffordanceSummary(
                semantic_target_id="semantic:destination",
                role="textbox",
                label="Beta",
                supported_actions=("type_text",),
                current_state=PlanningAffordanceState(
                    visible=True,
                    enabled=True,
                    element_tag="input",
                ),
            ),
            PlanningAffordanceSummary(
                semantic_target_id="semantic:source-scroll-region",
                role="scroll_region",
                label="Alpha scroll region",
                supported_actions=("press_key",),
                current_state=PlanningAffordanceState(
                    visible=True,
                    enabled=True,
                    element_tag="textarea",
                ),
            ),
        ),
    )

    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=environment,
    )

    assert preparation is not None
    assert preparation.evidence[0].semantic_target_id == "semantic:source"


def test_visible_subgoal_can_be_completed_from_current_observation() -> None:
    plan = _plan(relation=SubgoalOutcomeRelation.IS_VISIBLE)

    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(visible=True, enabled=None),
    )

    assert preparation is not None
    assert preparation.subgoal_id == "submit-button-available"


def test_selected_list_value_can_be_completed_from_current_observation() -> None:
    plan = TaskPlan(
        plan_id="plan-selection",
        task_id="task-selection",
        task_revision=1,
        plan_version=1,
        based_on_state_version=7,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="list-selected",
                objective="list has selected value",
                interaction=make_interaction('list'),
                success_criteria=("list has selected value",),
                evidence_requirements=("current list observation",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.SELECT_OPTION,
                outcome=SubgoalOutcome(
                    subject="list",
                    relation=SubgoalOutcomeRelation.IS_SELECTED,
                    value="Ertha",
                ),
            ),
        ),
    )
    progress = TaskPlanProgressStateView(
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        plan_based_on_state_version=plan.based_on_state_version,
        evaluated_at_state_version=9,
        active_subgoal_id="list-selected",
        completed_subgoal_ids=(),
        failed_subgoal_ids=(),
    )
    environment = PlanningEnvironmentSummary(
        environment_revision="env-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        affordances=(
            PlanningAffordanceSummary(
                semantic_target_id="semantic:options:1",
                role="combobox",
                label="options",
                supported_actions=("select_option",),
                current_state=PlanningAffordanceState(
                    visible=True,
                    enabled=True,
                    selected_options=("Ertha",),
                ),
            ),
        ),
    )

    preparation = CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=progress,
        environment=environment,
        evaluated_at_state_version=9,
    )

    assert preparation is not None
    assert preparation.evidence[0].observed_value == "Ertha"


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
    assert evaluator.evaluate(
        plan=plan,
        progress=_progress(plan),
        environment=_environment(),
        evaluated_at_state_version=10,
    ) is None


def test_stale_observation_identity_is_rejected() -> None:
    plan = _plan()
    progress = _progress(plan)
    evaluator = CurrentStateSubgoalCompletionEvaluator()

    assert evaluator.evaluate(
        plan=plan,
        progress=progress,
        environment=_environment(snapshot_id="older-snapshot"),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None
    assert evaluator.evaluate(
        plan=plan,
        progress=progress,
        environment=_environment(page_revision="older-page"),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None
    assert evaluator.evaluate(
        plan=plan,
        progress=progress,
        environment=_environment(environment_revision="older-env"),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None
