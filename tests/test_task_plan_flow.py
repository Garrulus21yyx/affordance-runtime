from dataclasses import dataclass

import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation, RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureClass
from affordance_runtime.simplified_runtime_contracts import ElementIntent, SourceReference
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_plan_flow import (
    TaskPlanCommitPreparation,
    TaskPlanCommitStateView,
    TaskPlanFlow,
    TaskPlanFlowKind,
    TaskPlanTraceProjection,
)
from affordance_runtime.task_plan_lifecycle import (
    TaskPlanLifecycle,
    TaskPlanReplacementReason,
)
from affordance_runtime.task_planning import (
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
from runtime_test_support import canonical_observation, make_interaction, remember_observation


@dataclass(frozen=True)
class Limits:
    max_steps: int = 20
    max_observations: int = 30
    max_replans: int = 10
    max_recoveries: int = 3
    max_effectful_actions: int = 5


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="flow-task",
        revision=1,
        objective="Save the selected setting",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("setting",),
        success_criteria=("setting is saved",),
        evidence_requirements=("saved state is independently observed",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-flow",
    )


class FlatFixturePlanner:
    def plan(self, context):  # type: ignore[no-untyped-def]
        task = context.task_spec
        outcome = SubgoalOutcome(
            subject="setting",
            relation=SubgoalOutcomeRelation.IS_COMPLETED,
        )
        return TaskPlan(
            plan_id=f"plan-{context.current_plan_version + 1}",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="setting-saved",
                    objective=task.objective,
                    interaction=ElementIntent(
                        "setting",
                        (SourceReference("request-flow", "unit:setting"),),
                    ),
                    success_criteria=task.success_criteria,
                    evidence_requirements=task.evidence_requirements,
                    operation_class=task.operation_class,
                    action_family=TaskPlanActionFamily.ACTIVATE,
                    outcome=outcome,
                ),
            ),
        )


def _snapshot() -> BrowserSnapshot:
    model = DomAdapter().transduce(
        "<main><button id='save'>Save setting</button></main>",
        environment_revision="environment-flow",
        snapshot_id="snapshot-flow",
        page_revision="page-flow",
    )
    observation = Observation(
        environment_revision="environment-flow",
        snapshot_id="snapshot-flow",
        page_revision="page-flow",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    return BrowserSnapshot(observation, model)


def _state() -> StateKernel:
    state = StateKernel(task_id=_task().task_id, goal=_task().objective)
    remember_observation(state, _snapshot().observation)
    return state


def test_task_plan_trace_projection_payload_is_deeply_immutable_from_source_payload() -> None:
    payload = {"plan": {"plan_id": "plan-1"}, "issues": ["missing-source"]}

    projection = TaskPlanTraceProjection("TaskPlanRejected", payload)
    payload["plan"]["plan_id"] = "mutated"  # type: ignore[index]
    payload["issues"].append("extra")  # type: ignore[union-attr]

    assert projection.payload["plan"] == {"plan_id": "plan-1"}
    assert projection.payload["issues"] == ("missing-source",)
    with pytest.raises(TypeError):
        projection.payload["plan"]["plan_id"] = "mutated"  # type: ignore[index]


def test_flow_prepares_accepted_initial_plan_without_mutating_state() -> None:
    state = _state()
    result = TaskPlanFlow(TaskPlanLifecycle(FlatFixturePlanner())).prepare(
        _task(),
        state,
        canonical_observation(_snapshot()),
        Limits(),
    )

    assert result.kind == TaskPlanFlowKind.INITIAL
    assert result.accepted
    assert result.transition is not None
    assert result.failure is None
    assert state.task_plan is None


def test_commit_preparation_projects_initial_trace_without_state_mutation() -> None:
    result = TaskPlanFlow(TaskPlanLifecycle(FlatFixturePlanner())).prepare(
        _task(),
        _state(),
        canonical_observation(_snapshot()),
        Limits(),
    )
    preparation = TaskPlanCommitPreparation(result)

    proposed = preparation.pre_commit_projection(state_phase="observing")
    accepted = preparation.acceptance_projection(
        state_phase="observing",
        committed=TaskPlanCommitStateView(active_subgoal="Save the selected setting"),
    )

    assert proposed is not None
    assert proposed.kind == "TaskPlanProposed"
    assert proposed.payload["validation"] == "accept"
    assert accepted.kind == "TaskPlanAccepted"
    assert accepted.payload["active_subgoal"] == "Save the selected setting"


class InvalidPlanner:
    def plan(self, context):  # type: ignore[no-untyped-def]
        plan = FlatFixturePlanner().plan(context)
        return plan.model_copy(update={"task_id": "wrong-task"})


class AlreadySatisfiedEntryPlanner:
    def plan(self, context):  # type: ignore[no-untyped-def]
        outcome = SubgoalOutcome(
            subject="Save setting",
            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
        )
        return TaskPlan(
            plan_id="plan-already-satisfied-entry",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=1,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="save-available",
                    objective=outcome.description(),
                    interaction=make_interaction('test target'),
                    success_criteria=(outcome.description(),),
                    evidence_requirements=("current button availability",),
                    operation_class=OperationClass.READ_ONLY,
                    action_family=TaskPlanActionFamily.WAIT,
                    outcome=outcome,
                ),
            ),
        )


def test_flow_preserves_initial_validation_issues_without_mutating_state() -> None:
    state = _state()
    result = TaskPlanFlow(TaskPlanLifecycle(InvalidPlanner())).prepare(
        _task(),
        state,
        canonical_observation(_snapshot()),
        Limits(),
    )

    assert result.kind == TaskPlanFlowKind.INITIAL
    assert not result.accepted
    assert result.transition is not None
    assert result.failure is not None
    assert result.failure.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
    assert result.failure.failure_class == FailureClass.VALIDATION
    assert {item.code for item in result.failure.issues} == {"task_id_mismatch"}
    assert state.task_plan is None


def test_flow_treats_already_satisfied_entry_as_progress_precheck_not_plan_failure() -> None:
    state = _state()
    result = TaskPlanFlow(TaskPlanLifecycle(AlreadySatisfiedEntryPlanner())).prepare(
        _task(),
        state,
        canonical_observation(_snapshot()),
        Limits(),
    )

    assert result.kind == TaskPlanFlowKind.INITIAL
    assert result.accepted
    assert result.transition is not None
    assert result.failure is None
    assert {item.code for item in result.transition.validation.issues} == {
        "entry_outcome_already_satisfied"
    }
    assert state.task_plan is None


def test_commit_preparation_projects_failure_and_normalizes_commit_exception() -> None:
    invalid = TaskPlanFlow(TaskPlanLifecycle(InvalidPlanner())).prepare(
        _task(),
        _state(),
        canonical_observation(_snapshot()),
        Limits(),
    )
    rejection = TaskPlanCommitPreparation(invalid).failure_projection(state_phase="observing")
    assert rejection.kind == "TaskPlanRejected"
    assert rejection.payload["validation"] == "reject"

    accepted = TaskPlanFlow(TaskPlanLifecycle(FlatFixturePlanner())).prepare(
        _task(),
        _state(),
        canonical_observation(_snapshot()),
        Limits(),
    )
    normalized = TaskPlanCommitPreparation(accepted).with_commit_failure(RuntimeError("state changed"))
    assert normalized.failure is not None
    assert normalized.failure.message == "RuntimeError: state changed"


class ExplodingPlanner:
    def plan(self, context):  # type: ignore[no-untyped-def]
        del context
        raise RuntimeError("provider unavailable")


def test_flow_types_initial_invocation_failure() -> None:
    result = TaskPlanFlow(TaskPlanLifecycle(ExplodingPlanner())).prepare(
        _task(),
        _state(),
        canonical_observation(_snapshot()),
        Limits(),
    )

    assert result.kind == TaskPlanFlowKind.INITIAL
    assert result.transition is None
    assert result.failure is not None
    assert result.failure.error_code == RuntimeErrorCode.PLANNER_FAILED
    assert result.failure.failure_class == FailureClass.PLANNING
    assert result.failure.message == "RuntimeError: provider unavailable"


def _state_requiring_replacement() -> StateKernel:
    state = _state()
    first = SubgoalSpec(
        subgoal_id="first",
        objective="setting preparation changed",
        interaction=make_interaction('setting preparation'),
        success_criteria=("setting preparation changed",),
        evidence_requirements=("preparation evidence",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
        outcome=SubgoalOutcome(
            subject="setting preparation",
            relation=SubgoalOutcomeRelation.HAS_CHANGED,
        ),
    )
    unsupported = SubgoalSpec(
        subgoal_id="unsupported",
        objective="Save setting is checked",
        interaction=make_interaction('Save setting'),
        depends_on=("first",),
        success_criteria=("Save setting is checked",),
        evidence_requirements=("current checked state",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
        outcome=SubgoalOutcome(
            subject="Save setting",
            relation=SubgoalOutcomeRelation.IS_CHECKED,
        ),
    )
    state.install_task_plan(
        TaskPlan(
            plan_id="original-plan",
            task_id=_task().task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.LLM,
            subgoals=(first, unsupported),
        )
    )
    state.complete_step("first", ("evidence:first",))
    return state


class ReplacementPlanner:
    def __init__(self, relation: SubgoalOutcomeRelation) -> None:
        self.relation = relation

    def plan(self, context):  # type: ignore[no-untyped-def]
        replacement = SubgoalSpec(
            subgoal_id="replacement",
            objective=SubgoalOutcome(
                subject="Save setting",
                relation=self.relation,
            ).description(),
            interaction=make_interaction('Save setting'),
            depends_on=("first",),
            success_criteria=("replacement outcome",),
            evidence_requirements=("fresh current state",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            action_family=TaskPlanActionFamily.ACTIVATE,
            outcome=SubgoalOutcome(
                subject="Save setting",
                relation=self.relation,
            ),
        )
        return TaskPlan(
            plan_id="replacement-plan",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.LLM,
            subgoals=(replacement,),
        )


def test_flow_preserves_replacement_reason_and_validation_issue() -> None:
    state = _state_requiring_replacement()
    result = TaskPlanFlow(
        TaskPlanLifecycle(ReplacementPlanner(SubgoalOutcomeRelation.IS_CHECKED))
    ).prepare(_task(), state, canonical_observation(_snapshot()), Limits())

    assert result.kind == TaskPlanFlowKind.REPLACEMENT
    assert result.replacement is not None
    assert (
        result.replacement.reason
        == TaskPlanReplacementReason.ACTIVE_SUBGOAL_OUTCOME_STATE_UNSUPPORTED
    )
    assert result.transition is not None
    assert result.failure is not None
    assert {item.code for item in result.failure.issues} == {
        "entry_outcome_state_unsupported"
    }
    assert "entry_outcome_state_unsupported" in result.failure.message
    assert state.task_plan is not None
    assert state.task_plan.plan_id == "original-plan"


def test_flow_discards_current_state_satisfied_read_only_subgoal_without_replanning() -> None:
    state = _state()
    first = SubgoalSpec(
        subgoal_id="first",
        objective="setting preparation changed",
        interaction=make_interaction('setting preparation'),
        success_criteria=("setting preparation changed",),
        evidence_requirements=("preparation evidence",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
        outcome=SubgoalOutcome(
            subject="setting preparation",
            relation=SubgoalOutcomeRelation.HAS_CHANGED,
        ),
    )
    visible = SubgoalSpec(
        subgoal_id="visible",
        objective="Save setting is visible",
        interaction=make_interaction('Save setting'),
        depends_on=("first",),
        success_criteria=("Save setting is visible",),
        evidence_requirements=("current button visibility",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
        outcome=SubgoalOutcome(
            subject="Save setting",
            relation=SubgoalOutcomeRelation.IS_VISIBLE,
        ),
    )
    state.install_task_plan(
        TaskPlan(
            plan_id="original-plan",
            task_id=_task().task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.LLM,
            subgoals=(first, visible),
        )
    )
    state.complete_step("first", ("evidence:first",))
    state.activate_next_step()

    result = TaskPlanFlow(
        TaskPlanLifecycle(ReplacementPlanner(SubgoalOutcomeRelation.HAS_CHANGED))
    ).prepare(_task(), state, canonical_observation(_snapshot()), Limits())

    assert result.kind == TaskPlanFlowKind.REPLACEMENT
    assert result.accepted
    assert result.transition is not None
    assert result.transition.previous_plan is state.task_plan
    assert [item.subgoal_id for item in result.transition.plan.subgoals] == ["first"]
    assert result.failure is None
    assert state.task_progress is not None
    assert state.task_progress.completed_subgoal_ids == ["first"]


def test_flow_discards_ready_current_state_satisfied_read_only_subgoal_when_active_projection_empty() -> None:
    state = _state()
    first = SubgoalSpec(
        subgoal_id="first",
        objective="text field value changed",
        interaction=make_interaction('text field'),
        success_criteria=("text field value changed",),
        evidence_requirements=("text evidence",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.TYPE_TEXT,
        outcome=SubgoalOutcome(
            subject="text field",
            relation=SubgoalOutcomeRelation.HAS_CHANGED,
        ),
    )
    submit_available = SubgoalSpec(
        subgoal_id="submit-available",
        objective="Save setting is available",
        interaction=make_interaction('Save setting'),
        depends_on=("first",),
        success_criteria=("Save setting is available",),
        evidence_requirements=("current button availability",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.ACTIVATE,
        outcome=SubgoalOutcome(
            subject="Save setting",
            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
        ),
    )
    state.install_task_plan(
        TaskPlan(
            plan_id="original-plan",
            task_id=_task().task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.LLM,
            subgoals=(first, submit_available),
        )
    )
    state.complete_step("first", ("evidence:first",))
    assert state.task_progress is not None
    assert state.task_progress.active_subgoal_id == ""

    result = TaskPlanFlow(
        TaskPlanLifecycle(ReplacementPlanner(SubgoalOutcomeRelation.IS_AVAILABLE))
    ).prepare(_task(), state, canonical_observation(_snapshot()), Limits())

    assert result.kind == TaskPlanFlowKind.REPLACEMENT
    assert result.accepted
    assert result.transition is not None
    assert result.transition.previous_plan is state.task_plan
    assert [item.subgoal_id for item in result.transition.plan.subgoals] == ["first"]
    assert result.failure is None
    assert state.task_progress.completed_subgoal_ids == ["first"]


def test_flow_prepares_valid_replacement_without_committing_it() -> None:
    state = _state_requiring_replacement()
    result = TaskPlanFlow(
        TaskPlanLifecycle(ReplacementPlanner(SubgoalOutcomeRelation.HAS_CHANGED))
    ).prepare(_task(), state, canonical_observation(_snapshot()), Limits())

    assert result.kind == TaskPlanFlowKind.REPLACEMENT
    assert result.accepted
    assert result.transition is not None
    assert result.transition.previous_plan is state.task_plan
    assert result.transition.plan.plan_id == "replacement-plan"
    assert state.task_plan is not None
    assert state.task_plan.plan_id == "original-plan"
