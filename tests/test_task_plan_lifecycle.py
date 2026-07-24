from dataclasses import dataclass

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_planning import (
    PlanningRouter,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanningContext,
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
