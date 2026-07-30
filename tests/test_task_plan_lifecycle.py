from dataclasses import dataclass, replace
from inspect import getsource

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.simplified_runtime_contracts import SourceReference, StateCriterion, StepSpec
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    OperationClass,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskSpec,
)
from affordance_runtime.task_plan_contracts import PlanCandidate, TaskPlanGeneratorSource
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


class CandidateInitialPlanner:
    def generate_candidate(self, context: TaskPlanningContext) -> PlanCandidate:
        task = context.task_spec
        return PlanCandidate(
            task_spec_identity=task.identity,
            task_revision=task.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="candidate-initial-test",
            steps=(
                StepSpec(
                    step_id="setting-saved",
                    objective="setting is saved",
                    completion_criteria=(
                        StateCriterion(
                            criterion_id="criterion:setting-saved",
                            source_refs=(
                                SourceReference(
                                    source_id="request-lifecycle",
                                    source_unit_id="saved state is independently observed",
                                    claim_id="claim-save-setting",
                                ),
                            ),
                            subject="setting",
                            relation=TaskObligationRelation.IS_COMPLETED,
                        ),
                    ),
                    source_refs=(
                        SourceReference(
                            source_id="request-lifecycle",
                            source_unit_id="saved state is independently observed",
                            claim_id="claim-save-setting",
                        ),
                    ),
                ),
            ),
            source_refs=(
                SourceReference(
                    source_id="request-lifecycle",
                    source_unit_id="request-lifecycle:claim-save-setting",
                    claim_id="claim-save-setting",
                ),
            ),
        )


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


def _obligation_task() -> TaskSpec:
    claim = SourcedTaskClaim(
        claim_id="claim-save-setting",
        kind=TaskClaimKind.EFFECT,
        statement="setting is saved",
        source_ref="request-lifecycle",
    )
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
        source_claims=(claim,),
        obligations=(
            TaskObligationSpec(
                obligation_id="setting-saved",
                kind=TaskObligationKind.EFFECT,
                subject="setting",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=(claim.claim_id,),
                evidence_requirements=("saved state is independently observed",),
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="setting",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        minimum_strength="independent",
                        source_constraints=("dom_state",),
                    ),
                ),
                blocking=True,
                terminal=True,
            ),
        ),
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
    assert state.active_subgoal() == ""
    assert state.activate_next_subgoal() == task.objective
    assert lifecycle.active_subgoal_spec(state) == transition.plan.subgoals[0]
    assert not lifecycle.completed(state)


def test_lifecycle_initial_plan_uses_deterministic_authority_admission() -> None:
    task = _obligation_task()
    snapshot = _snapshot()
    first_state = StateKernel(task_id=task.task_id, goal=task.objective)
    second_state = StateKernel(task_id=task.task_id, goal=task.objective)
    first_state.remember_observation(snapshot.observation)
    second_state.remember_observation(snapshot.observation)
    lifecycle = TaskPlanLifecycle(CandidateInitialPlanner())

    first = lifecycle.propose_initial(task, first_state, snapshot, Limits())
    second = lifecycle.propose_initial(task, second_state, snapshot, Limits())

    assert first.validation.status == TaskPlanValidationStatus.ACCEPT
    assert second.validation.status == TaskPlanValidationStatus.ACCEPT
    assert first.plan.plan_id == second.plan.plan_id
    assert first.plan.plan_version == 1
    assert first.plan.supersedes_plan_id == ""
    assert first.plan.based_on_state_version == first_state.version
    text = getsource(TaskPlanLifecycle.propose_initial)
    assert "admit_initial" in text
    assert "_resolve_task_plan(self.planner.plan(context))" not in text


def test_lifecycle_projects_bounded_current_state_without_password_value() -> None:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    model = DomAdapter().transduce(
        """
        <main>
          <input id='search-text' value='Keli'>
          <input id='password' type='password' value='secret'>
        </main>
        """,
        environment_revision="environment-state",
        snapshot_id="snapshot-state",
        page_revision="page-state",
    )
    enriched = []
    for item in model.affordances:
        extra = (
            {
                "selected_options": [f"option-{index}" for index in range(25)],
                "aria_selected": "true",
                "expanded": False,
            }
            if item.label == "search-text"
            else {"control_value": "must-not-leak"}
        )
        enriched.append(replace(item, state={**item.state, **extra}))
    model = replace(model, affordances=enriched)
    observation = Observation(
        "environment-state",
        snapshot_id="snapshot-state",
        page_revision="page-state",
        target_fingerprints={item.id: item.target_fingerprint for item in enriched},
    )
    snapshot = BrowserSnapshot(observation, model)
    state.remember_observation(observation)

    context = TaskPlanLifecycle.build_context(
        task,
        state,
        snapshot,
        Limits(),
        reason="initial",
    )

    by_label = {item.label: item.current_state for item in context.environment.affordances}
    assert by_label["search-text"].control_value == "Keli"
    assert by_label["search-text"].selected is True
    assert len(by_label["search-text"].selected_options) == 20
    assert by_label["search-text"].expanded is False
    assert by_label["password"].control_value is None


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
    assert state.activate_next_subgoal() == first.objective
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


def test_lifecycle_requests_replacement_for_newly_ready_satisfied_outcome() -> None:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    context = TaskPlanLifecycle.build_context(
        task,
        state,
        _snapshot(),
        Limits(),
        reason="initial",
    )
    base = PlanningRouter().plan(context)
    first = base.subgoals[0].model_copy(
        update={
            "subgoal_id": "first",
            "action_family": TaskPlanActionFamily.ACTIVATE,
        }
    )
    already_visible = SubgoalSpec(
        subgoal_id="already-visible",
        objective="Save setting is visible",
        outcome=SubgoalOutcome(
            subject="Save setting",
            relation=SubgoalOutcomeRelation.IS_VISIBLE,
        ),
        depends_on=("first",),
        success_criteria=("Save setting is visible",),
        evidence_requirements=("current button visibility",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
    )
    state.install_task_plan(
        base.model_copy(update={"subgoals": (first, already_visible)})
    )
    state.complete_subgoal("first", ("evidence:first",))

    decision = TaskPlanLifecycle(PlanningRouter()).evaluate_replacement(
        task,
        state,
        _snapshot(),
        Limits(),
    )

    assert decision.required
    assert (
        decision.reason
        == TaskPlanReplacementReason.ACTIVE_SUBGOAL_OUTCOME_ALREADY_SATISFIED
    )
    assert decision.subgoal_id == "already-visible"
    assert state.task_plan is not None
    assert state.task_plan.plan_id == base.plan_id
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["first"]


def test_lifecycle_requests_replacement_for_newly_ready_unsupported_state() -> None:
    task = _task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    context = TaskPlanLifecycle.build_context(
        task,
        state,
        _snapshot(),
        Limits(),
        reason="initial",
    )
    base = PlanningRouter().plan(context)
    first = base.subgoals[0].model_copy(
        update={"subgoal_id": "first", "action_family": TaskPlanActionFamily.ACTIVATE}
    )
    unsupported = SubgoalSpec(
        subgoal_id="unsupported",
        objective="Save setting is checked",
        outcome=SubgoalOutcome(
            subject="Save setting",
            relation=SubgoalOutcomeRelation.IS_CHECKED,
        ),
        depends_on=("first",),
        success_criteria=("Save setting is checked",),
        evidence_requirements=("current checked state",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
    )
    state.install_task_plan(base.model_copy(update={"subgoals": (first, unsupported)}))
    state.complete_subgoal("first", ("evidence:first",))

    decision = TaskPlanLifecycle(PlanningRouter()).evaluate_replacement(
        task,
        state,
        _snapshot(),
        Limits(),
    )

    assert decision.required
    assert (
        decision.reason
        == TaskPlanReplacementReason.ACTIVE_SUBGOAL_OUTCOME_STATE_UNSUPPORTED
    )
    assert decision.subgoal_id == "unsupported"
    assert state.task_plan is not None
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["first"]


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
    assert state.activate_next_subgoal() == "setting control is selected"
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
    assert state.activate_next_subgoal() == "setting control is saved"


def test_lifecycle_replacement_uses_taskplan_authority_revision_admission() -> None:
    task = _obligation_task()
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    snapshot = _snapshot()
    state.remember_observation(snapshot.observation)
    context = TaskPlanLifecycle.build_context(task, state, snapshot, Limits(), reason="initial")
    previous = PlanningRouter().plan(context)
    state.install_task_plan(previous)
    state.activate_next_subgoal()
    previous_version = state.version

    transition = TaskPlanLifecycle(CandidateInitialPlanner()).propose_replacement(
        task,
        state,
        snapshot,
        Limits(),
        reason="subgoal_action_budget_exhausted",
    )

    assert transition.validation.status == TaskPlanValidationStatus.ACCEPT
    assert transition.previous_plan == previous
    assert transition.plan.plan_version == previous.plan_version + 1
    assert transition.plan.supersedes_plan_id == previous.plan_id
    assert transition.plan.plan_id != previous.plan_id
    assert transition.plan.based_on_state_version == previous_version
    assert state.task_plan == previous
    text = getsource(TaskPlanLifecycle.propose_replacement)
    assert "admit_revision" in text


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
