from dataclasses import dataclass

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_plan_lifecycle import (
    TaskPlanLifecycle,
    TaskPlanReplacementReason,
)
from affordance_runtime.task_planning import (
    PlanningRouter,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanningContext,
    TaskPlanSource,
    TaskPlanValidationStatus,
)


@dataclass(frozen=True)
class Limits:
    max_steps: int = 20
    max_observations: int = 30
    max_replans: int = 10
    max_recoveries: int = 3
    max_effectful_actions: int = 5


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="lifecycle-task",
        revision=1,
        objective="Save the selected setting",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("setting",),
        success_criteria=("setting is saved",),
        evidence_requirements=("saved state is independently observed",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-lifecycle",
    )


def _snapshot() -> BrowserSnapshot:
    model = DomAdapter().transduce(
        "<main><button id='save'>Save setting</button></main>",
        environment_revision="environment-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
    )
    observation = Observation(
        environment_revision="environment-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    return BrowserSnapshot(observation, model)


def test_lifecycle_prepares_initial_transition_without_mutating_run_state() -> None:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    state.remember_observation(_snapshot().observation)
    lifecycle = TaskPlanLifecycle(PlanningRouter())

    transition = lifecycle.propose_initial(task, state, _snapshot(), Limits())

    assert transition.validation.status == TaskPlanValidationStatus.ACCEPT
    assert transition.context.environment.affordances[0].label == "Save setting"
    assert transition.context.remaining_budget.steps_remaining == 20
    assert state.task_plan is None
    assert state.plan_progress is None

    state.install_task_plan(transition.plan)
    assert state.active_subgoal() == task.objective
    assert lifecycle.active_subgoal_spec(state) == transition.plan.subgoals[0]
    assert not lifecycle.completed(state)


class InvalidAsyncPlanner:
    async def plan(self, context: TaskPlanningContext) -> TaskPlan:
        valid = PlanningRouter().plan(context)
        return valid.model_copy(update={"task_id": "different-task"})


class UnavailableEntryPlanner:
    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        valid = PlanningRouter().plan(context)
        return valid.model_copy(
            update={
                "subgoals": (
                    valid.subgoals[0].model_copy(
                        update={
                            "objective": "settings page is available",
                            "success_criteria": ("settings page is available",),
                            "action_family": TaskPlanActionFamily.NAVIGATE,
                            "outcome": SubgoalOutcome(
                                subject="settings page",
                                relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                            ),
                        }
                    ),
                )
            }
        )


def test_lifecycle_resolves_async_planner_and_rejects_invalid_plan_without_installing_it() -> None:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    state.remember_observation(_snapshot().observation)

    transition = TaskPlanLifecycle(InvalidAsyncPlanner()).propose_initial(
        task,
        state,
        _snapshot(),
        Limits(),
    )

    assert transition.validation.status == TaskPlanValidationStatus.REJECT
    assert {item.code for item in transition.validation.issues} == {"task_id_mismatch"}
    assert state.task_plan is None
    assert state.plan_progress is None


def test_lifecycle_applies_contextual_entry_validation_to_non_llm_planner() -> None:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    state.remember_observation(_snapshot().observation)

    transition = TaskPlanLifecycle(UnavailableEntryPlanner()).propose_initial(
        task,
        state,
        _snapshot(),
        Limits(),
    )

    assert transition.validation.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in transition.validation.issues} == {
        "entry_action_family_unavailable"
    }
    assert state.task_plan is None


def _installed_two_step_state(second_family: TaskPlanActionFamily) -> tuple[TaskSpec, StateKernel]:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    context = TaskPlanLifecycle.build_context(task, state, _snapshot(), Limits(), reason="initial")
    base = PlanningRouter().plan(context)
    first = base.subgoals[0].model_copy(
        update={
            "subgoal_id": "first",
            "action_family": TaskPlanActionFamily.ACTIVATE,
        }
    )
    second = SubgoalSpec(
        subgoal_id="second",
        objective="setting control is selected",
        outcome=SubgoalOutcome(
            subject="setting control",
            relation=SubgoalOutcomeRelation.IS_SELECTED,
        ),
        depends_on=("first",),
        success_criteria=("setting control is selected",),
        evidence_requirements=("current control state",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=second_family,
    )
    state.install_task_plan(base.model_copy(update={"subgoals": (first, second)}))
    assert state.active_subgoal() == first.objective
    state.complete_subgoal("first", ("evidence:first",))
    return task, state


def test_lifecycle_requests_replacement_for_newly_ready_unavailable_family() -> None:
    task, state = _installed_two_step_state(TaskPlanActionFamily.SELECT_OPTION)

    decision = TaskPlanLifecycle(PlanningRouter()).evaluate_replacement(
        task,
        state,
        _snapshot(),
        Limits(),
    )

    assert decision.required
    assert decision.reason == TaskPlanReplacementReason.ACTIVE_SUBGOAL_ACTION_FAMILY_UNAVAILABLE
    assert decision.subgoal_id == "second"
    assert decision.unavailable_action_family == "select_option"
    assert state.plan_progress is not None
    assert state.plan_progress.active_subgoal_id == ""


def test_lifecycle_keeps_compatible_or_unobservable_transition_without_replanning() -> None:
    task, state = _installed_two_step_state(TaskPlanActionFamily.ACTIVATE)
    lifecycle = TaskPlanLifecycle(PlanningRouter())

    compatible = lifecycle.evaluate_replacement(task, state, _snapshot(), Limits())
    empty_snapshot = BrowserSnapshot(
        Observation("environment-empty", snapshot_id="snapshot-empty"),
        DomAdapter().transduce(
            "<main></main>",
            environment_revision="environment-empty",
            snapshot_id="snapshot-empty",
        ),
    )
    unknown = lifecycle.evaluate_replacement(task, state, empty_snapshot, Limits())
    assert state.active_subgoal() == "setting control is selected"
    state.complete_subgoal("second", ("evidence:second",))
    completed = lifecycle.evaluate_replacement(task, state, _snapshot(), Limits())

    assert not compatible.required
    assert not unknown.required
    assert not completed.required


class ReplacementPlanner:
    def __init__(self, *, redefine_completed: bool = False, omit_unfinished: bool = False) -> None:
        self.redefine_completed = redefine_completed
        self.omit_unfinished = omit_unfinished

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        completed = SubgoalSpec(
            subgoal_id="first",
            objective="model-authored replacement of verified state",
            outcome=SubgoalOutcome(
                subject="different setting",
                relation=SubgoalOutcomeRelation.HAS_CHANGED,
            ),
            success_criteria=("different setting changed",),
            evidence_requirements=("different evidence",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            action_family=TaskPlanActionFamily.ACTIVATE,
        )
        unfinished = SubgoalSpec(
            subgoal_id="replacement",
            objective="setting control is saved",
            outcome=SubgoalOutcome(
                subject="setting control",
                relation=SubgoalOutcomeRelation.IS_COMPLETED,
            ),
            depends_on=("first",),
            success_criteria=("setting control is saved",),
            evidence_requirements=("current saved state",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            action_family=TaskPlanActionFamily.ACTIVATE,
        )
        subgoals = (() if self.omit_unfinished else (unfinished,))
        if self.redefine_completed:
            subgoals = (completed, *subgoals)
        return TaskPlan(
            plan_id="replacement-plan",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.LLM,
            subgoals=subgoals or (completed,),
        )


def test_replacement_carries_forward_exact_completed_spec_without_mutating_state() -> None:
    task, state = _installed_two_step_state(TaskPlanActionFamily.ACTIVATE)
    previous = state.task_plan
    assert previous is not None
    previous_version = state.version

    transition = TaskPlanLifecycle(ReplacementPlanner()).propose_replacement(
        task,
        state,
        _snapshot(),
        Limits(),
        reason="subgoal_action_budget_exhausted",
    )

    assert transition.validation.status == TaskPlanValidationStatus.ACCEPT
    assert transition.plan.subgoals[0] == previous.subgoals[0]
    assert tuple(item.subgoal_id for item in transition.plan.subgoals) == (
        "first",
        "replacement",
    )
    assert state.task_plan == previous
    assert state.version == previous_version

    state.replace_task_plan(transition.plan)
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["first"]
    assert state.plan_progress.evidence_by_subgoal == {"first": ["evidence:first"]}
    assert state.active_subgoal() == "setting control is saved"


def test_replacement_discards_model_redefinition_of_completed_spec() -> None:
    task, state = _installed_two_step_state(TaskPlanActionFamily.ACTIVATE)
    previous = state.task_plan
    assert previous is not None

    transition = TaskPlanLifecycle(
        ReplacementPlanner(redefine_completed=True)
    ).propose_replacement(
        task,
        state,
        _snapshot(),
        Limits(),
        reason="subgoal_action_budget_exhausted",
    )

    assert transition.validation.status == TaskPlanValidationStatus.ACCEPT
    assert transition.plan.subgoals[0] == previous.subgoals[0]
    assert all(
        item.objective != "model-authored replacement of verified state"
        for item in transition.plan.subgoals
    )


def test_replacement_without_unfinished_work_is_repairable() -> None:
    task, state = _installed_two_step_state(TaskPlanActionFamily.ACTIVATE)

    transition = TaskPlanLifecycle(
        ReplacementPlanner(redefine_completed=True, omit_unfinished=True)
    ).propose_replacement(
        task,
        state,
        _snapshot(),
        Limits(),
        reason="subgoal_action_budget_exhausted",
    )

    assert transition.validation.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in transition.validation.issues} == {
        "replacement_missing_unfinished_subgoal"
    }
