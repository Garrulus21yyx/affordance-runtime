from __future__ import annotations

import importlib
import inspect

import pytest

from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
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


def _progress_api():
    try:
        return importlib.import_module("affordance_runtime.task_plan_progress")
    except ModuleNotFoundError as exc:  # pragma: no cover - RED before module exists
        pytest.fail(f"missing task_plan_progress module: {exc}")


def _text_subgoal() -> SubgoalSpec:
    return SubgoalSpec(
        subgoal_id="text-changed",
        objective="Text field changed to Kanesha",
        success_criteria=("text criterion",),
        evidence_requirements=("text evidence",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.TYPE_TEXT,
        outcome=SubgoalOutcome(
            subject="text_field",
            relation=SubgoalOutcomeRelation.HAS_CHANGED,
        ),
    )


def _submit_available_subgoal(*, depends_on: tuple[str, ...] = ("text-changed",)) -> SubgoalSpec:
    return SubgoalSpec(
        subgoal_id="submit-available",
        objective="Submit button is available",
        depends_on=depends_on,
        success_criteria=("submit available criterion",),
        evidence_requirements=("submit availability evidence",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
        outcome=SubgoalOutcome(
            subject="submit_button",
            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
        ),
    )


def _plan() -> TaskPlan:
    return TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=3,
        based_on_state_version=7,
        generated_by=TaskPlanSource.LLM,
        subgoals=(_text_subgoal(), _submit_available_subgoal()),
    )


def _progress_view(*, completed: tuple[str, ...] = ("text-changed",)):
    api = _progress_api()
    return api.TaskPlanProgressStateView(
        plan_id="plan-1",
        plan_version=3,
        based_on_state_version=7,
        snapshot_id="snapshot-1",
        environment_revision="env-1",
        page_revision="page-1",
        active_subgoal_id="submit-available",
        completed_subgoal_ids=completed,
        failed_subgoal_ids=(),
    )


def _environment(
    *affordances: PlanningAffordanceSummary,
    snapshot_id: str = "snapshot-1",
    environment_revision: str = "env-1",
    page_revision: str = "page-1",
) -> PlanningEnvironmentSummary:
    return PlanningEnvironmentSummary(
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=page_revision,
        affordances=affordances
        or (
            PlanningAffordanceSummary(
                semantic_target_id="semantic-submit",
                role="button",
                label="Submit",
                supported_actions=("click",),
                current_state=PlanningAffordanceState(visible=True, enabled=True),
            ),
        ),
    )


def _evaluate(
    *affordances: PlanningAffordanceSummary,
    plan: TaskPlan | None = None,
    completed: tuple[str, ...] = ("text-changed",),
    **env_kwargs,
):
    api = _progress_api()
    return api.CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan or _plan(),
        progress=_progress_view(completed=completed),
        environment=_environment(*affordances, **env_kwargs),
    )


def test_required_read_only_subgoal_is_completed_from_current_observation_not_deleted() -> None:
    plan = _plan()

    preparation = _evaluate(plan=plan)

    assert preparation is not None
    assert preparation.subgoal_id == "submit-available"
    assert preparation.plan_id == "plan-1"
    assert preparation.plan_version == 3
    assert preparation.based_on_state_version == 7
    assert preparation.snapshot_id == "snapshot-1"
    assert preparation.criterion_ids == ("submit available criterion",)
    assert preparation.requirement_ids == ("submit availability evidence",)
    assert preparation.evidence_refs
    assert [item.subgoal_id for item in plan.subgoals] == ["text-changed", "submit-available"]


def test_obligation_coverage_is_preserved_when_current_state_completes_subgoal() -> None:
    plan = _plan()

    assert _evaluate(plan=plan) is not None
    assert {item.subgoal_id for item in plan.subgoals} == {
        "text-changed",
        "submit-available",
    }


def test_dependency_must_be_completed_before_current_state_completion() -> None:
    assert _evaluate(completed=()) is None


def test_multiple_matching_controls_fail_closed() -> None:
    first = PlanningAffordanceSummary(
        semantic_target_id="semantic-submit-1",
        role="button",
        label="Submit",
        supported_actions=("click",),
        current_state=PlanningAffordanceState(visible=True, enabled=True),
    )
    second = PlanningAffordanceSummary(
        semantic_target_id="semantic-submit-2",
        role="button",
        label="Submit form",
        supported_actions=("click",),
        current_state=PlanningAffordanceState(visible=True, enabled=True),
    )

    assert _evaluate(first, second) is None


@pytest.mark.parametrize(
    "state",
    [
        PlanningAffordanceState(visible=False, enabled=True),
        PlanningAffordanceState(visible=True, enabled=False),
    ],
)
def test_hidden_or_disabled_control_does_not_satisfy_availability(
    state: PlanningAffordanceState,
) -> None:
    affordance = PlanningAffordanceSummary(
        semantic_target_id="semantic-submit",
        role="button",
        label="Submit",
        supported_actions=("click",),
        current_state=state,
    )

    assert _evaluate(affordance) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plan_id", "other-plan"),
        ("plan_version", 4),
        ("based_on_state_version", 8),
        ("snapshot_id", "other-snapshot"),
        ("environment_revision", "other-env"),
        ("page_revision", "other-page"),
    ],
)
def test_stale_identity_is_rejected(field: str, value: object) -> None:
    api = _progress_api()
    progress = _progress_view()
    progress = api.TaskPlanProgressStateView(
        **{**progress.__dict__, field: value},
    )

    result = api.CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=_plan(),
        progress=progress,
        environment=_environment(),
    )

    assert result is None


def test_progress_contract_exposes_no_external_authority_inputs() -> None:
    api = _progress_api()
    signature = inspect.signature(api.CurrentStateSubgoalCompletionEvaluator.evaluate)
    parameter_names = set(signature.parameters)

    assert "receipt" not in parameter_names
    assert "official_reward" not in parameter_names
    assert "task_name" not in parameter_names
    assert "url" not in parameter_names
    assert "selector" not in parameter_names


def test_completion_preparation_allows_existing_finish_guard_to_pass_after_commit() -> None:
    api = _progress_api()
    plan = _plan()
    state = StateKernel(task_id="task-1", goal="Enter text and submit")
    state.install_task_plan(plan)
    state.complete_subgoal("text-changed", ("evidence:text",))
    preparation = api.CurrentStateSubgoalCompletionEvaluator().evaluate(
        plan=plan,
        progress=api.TaskPlanProgressStateView.from_state(
            state,
            snapshot_id="snapshot-1",
            environment_revision="env-1",
            page_revision="page-1",
        ),
        environment=_environment(),
    )

    assert preparation is not None
    state.complete_subgoal(preparation.subgoal_id, preparation.evidence_refs)

    assert TaskPlanLifecycle.completed(state)
