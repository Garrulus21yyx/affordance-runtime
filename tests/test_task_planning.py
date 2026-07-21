from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_planning import (
    PlanningRouter,
    PlanProgress,
    SubgoalSpec,
    TaskPlan,
    TaskPlanSource,
    TaskPlanValidationStatus,
    TaskPlanValidator,
    synthetic_task_plan,
)
from affordance_runtime.verification import VerificationEvidence, VerificationReport, VerificationStatus


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Update the theme and confirm it",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme is dark",),
        evidence_requirements=("settings API confirms dark",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-1",
    )


def test_simple_router_preserves_flat_path_as_one_verifier_backed_subgoal() -> None:
    plan = PlanningRouter().plan(_task(), state_version=4)

    assert plan.generated_by == TaskPlanSource.RULE
    assert len(plan.subgoals) == 1
    assert plan.subgoals[0].objective == _task().objective
    assert TaskPlanValidator().validate(plan, _task(), state_version=4).status == TaskPlanValidationStatus.ACCEPT


def test_validator_rejects_stale_escalating_and_cyclic_plans() -> None:
    plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=3,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="a",
                objective="Write theme",
                depends_on=("b",),
                success_criteria=("theme is dark",),
                evidence_requirements=("API confirms",),
                operation_class=OperationClass.IRREVERSIBLE,
            ),
            SubgoalSpec(
                subgoal_id="b",
                objective="Confirm theme",
                depends_on=("a",),
                success_criteria=("theme is dark",),
                evidence_requirements=("API confirms",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
            ),
        ),
    )

    report = TaskPlanValidator().validate(plan, _task(), state_version=4)

    assert report.status == TaskPlanValidationStatus.REJECT
    assert {item.code for item in report.issues} >= {
        "task_revision_mismatch",
        "state_version_mismatch",
        "operation_class_escalation",
        "dependency_cycle",
    }


def test_validator_marks_missing_verification_requirements_repairable() -> None:
    plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=2,
        plan_version=1,
        based_on_state_version=4,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="a",
                objective="Update theme",
                operation_class=OperationClass.REVERSIBLE_WRITE,
            ),
        ),
    )

    report = TaskPlanValidator().validate(plan, _task(), state_version=4)

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in report.issues} == {"missing_success_criteria", "missing_evidence_requirements"}


def test_progress_selects_ready_subgoals_serially_and_preserves_evidence() -> None:
    task = _task()
    first = SubgoalSpec(
        subgoal_id="write", objective="Write", success_criteria=("written",), evidence_requirements=("receipt",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    second = SubgoalSpec(
        subgoal_id="verify", objective="Verify", depends_on=("write",), success_criteria=("verified",),
        evidence_requirements=("API",), operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    plan = TaskPlan(
        plan_id="plan-1", task_id=task.task_id, task_revision=task.revision, plan_version=1,
        based_on_state_version=0, generated_by=TaskPlanSource.RULE, subgoals=(first, second),
    )
    progress = PlanProgress()

    assert progress.activate_next(plan) == "write"
    progress.complete("write", ("receipt-1",))
    assert progress.activate_next(plan) == "verify"
    assert progress.evidence_by_subgoal == {"write": ["receipt-1"]}


def test_synthetic_plan_copies_task_constraints_into_verification_boundary() -> None:
    plan = synthetic_task_plan(_task(), state_version=0)
    assert plan.subgoals[0].evidence_requirements == ("settings API confirms dark",)


def test_state_kernel_keeps_plan_immutable_and_tracks_progress_separately() -> None:
    task = _task()
    plan = synthetic_task_plan(task, state_version=0)
    state = StateKernel(task.task_id, task.objective)

    state.install_task_plan(plan)
    assert state.task_plan == plan
    assert state.active_subgoal() == task.objective
    state.complete_subgoal("subgoal-1", ("settings-api-receipt",))

    assert state.task_plan == plan
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["subgoal-1"]
    assert state.evidence == ["settings-api-receipt"]


def test_subgoal_verifier_requires_independent_passed_evidence() -> None:
    from affordance_runtime.task_planning import VerifierBackedSubgoalVerifier

    subgoal = synthetic_task_plan(_task(), state_version=0).subgoals[0]
    verifier = VerifierBackedSubgoalVerifier()
    report = VerificationReport(
        VerificationStatus.PASSED,
        evidence=[VerificationEvidence("observation_metadata", "saved", True, "post_action_observation")],
    )

    assert verifier.verify(subgoal, report) == ("observation_metadata:saved",)
    assert verifier.verify(subgoal, VerificationReport(VerificationStatus.PASSED)) is None
