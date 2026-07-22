import pytest

from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_planning import (
    LLMTaskPlanner,
    PlanningRouter,
    PlanProgress,
    SubgoalSpec,
    TaskPlan,
    TaskPlanningBudgetSummary,
    TaskPlanningContext,
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


def _context(*, state_version: int = 4) -> TaskPlanningContext:
    return TaskPlanningContext(
        task_spec=_task(),
        state_version=state_version,
        remaining_budget=TaskPlanningBudgetSummary(
            steps_remaining=10,
            observations_remaining=10,
            replans_remaining=2,
            recoveries_remaining=2,
            effectful_actions_remaining=2,
        ),
    )


def test_simple_router_preserves_flat_path_as_one_verifier_backed_subgoal() -> None:
    plan = PlanningRouter().plan(_context())

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


def test_validator_rejects_non_monotonic_replacement_lineage() -> None:
    previous = synthetic_task_plan(_context())
    replacement = previous.model_copy(
        update={
            "plan_id": "replacement",
            "based_on_state_version": 5,
            "plan_version": previous.plan_version,
            "supersedes_plan_id": "wrong-plan",
        }
    )

    report = TaskPlanValidator().validate(
        replacement,
        _task(),
        state_version=5,
        previous_plan=previous,
    )

    assert report.status == TaskPlanValidationStatus.REJECT
    assert "invalid_replacement_plan_lineage" in {item.code for item in report.issues}


@pytest.mark.parametrize(
    "forbidden",
    (
        "use selector=#save",
        "mouse_click(120, 240)",
        "x=120 y=240",
        "backend=playwright",
        "approval_token=trusted",
        "grant capability settings.write",
    ),
)
def test_validator_rejects_executable_handles_and_authority_in_plan_text(forbidden: str) -> None:
    plan = synthetic_task_plan(_context())
    unsafe = plan.model_copy(update={"subgoals": (plan.subgoals[0].model_copy(update={"objective": forbidden}),)})

    report = TaskPlanValidator().validate(unsafe, _task(), state_version=4)

    assert report.status == TaskPlanValidationStatus.REJECT
    assert "executable_plan_content" in {item.code for item in report.issues}


def test_progress_selects_ready_subgoals_serially_and_preserves_evidence() -> None:
    task = _task()
    first = SubgoalSpec(
        subgoal_id="write",
        objective="Write",
        success_criteria=("written",),
        evidence_requirements=("receipt",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    second = SubgoalSpec(
        subgoal_id="verify",
        objective="Verify",
        depends_on=("write",),
        success_criteria=("verified",),
        evidence_requirements=("API",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    plan = TaskPlan(
        plan_id="plan-1",
        task_id=task.task_id,
        task_revision=task.revision,
        plan_version=1,
        based_on_state_version=0,
        generated_by=TaskPlanSource.RULE,
        subgoals=(first, second),
    )
    progress = PlanProgress()

    assert progress.activate_next(plan) == "write"
    progress.complete("write", ("receipt-1",))
    assert progress.activate_next(plan) == "verify"
    assert progress.evidence_by_subgoal == {"write": ["receipt-1"]}


def test_synthetic_plan_copies_task_constraints_into_verification_boundary() -> None:
    plan = synthetic_task_plan(_context(state_version=0))
    assert plan.subgoals[0].evidence_requirements == ("settings API confirms dark",)


def test_state_kernel_keeps_plan_immutable_and_tracks_progress_separately() -> None:
    task = _task()
    plan = synthetic_task_plan(_context(state_version=0).model_copy(update={"task_spec": task}))
    state = StateKernel(task.task_id, task.objective)

    state.install_task_plan(plan)
    assert state.task_plan == plan
    assert state.active_subgoal() == task.objective
    state.complete_subgoal("subgoal-1", ("settings-api-receipt",))

    assert state.task_plan == plan
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["subgoal-1"]
    assert state.evidence == ["settings-api-receipt"]


def test_replan_cannot_redefine_a_verified_subgoal() -> None:
    plan = synthetic_task_plan(_context(state_version=0))
    state = StateKernel(_task().task_id, _task().objective)
    state.install_task_plan(plan)
    state.complete_subgoal("subgoal-1", ("settings-state",))
    changed = plan.subgoals[0].model_copy(update={"success_criteria": ("different outcome",)})
    replacement = plan.model_copy(
        update={
            "plan_id": "plan-2",
            "plan_version": 2,
            "supersedes_plan_id": plan.plan_id,
            "based_on_state_version": state.version,
            "subgoals": (changed,),
        }
    )

    with pytest.raises(ValueError, match="cannot redefine"):
        state.replace_task_plan(replacement)


def test_subgoal_verifier_requires_independent_passed_evidence() -> None:
    from affordance_runtime.task_planning import VerifierBackedSubgoalVerifier

    subgoal = synthetic_task_plan(_context(state_version=0)).subgoals[0]
    verifier = VerifierBackedSubgoalVerifier()
    report = VerificationReport(
        VerificationStatus.PASSED,
        evidence=[
            VerificationEvidence(
                "observation_metadata",
                "saved",
                True,
                "post_action_observation",
                evidence_id="settings-state",
                criterion_ids=(criterion_id("subgoal", subgoal.subgoal_id, 0),),
                requirement_ids=(evidence_requirement_id("subgoal", subgoal.subgoal_id, 0),),
                environment_revision="revision-1",
                snapshot_id="snapshot-1",
                strength="strong",
            )
        ],
    )
    observation = Observation("revision-1", snapshot_id="snapshot-1")

    matched = verifier.verify(subgoal, report, observation)
    unmatched = verifier.verify(
        subgoal,
        VerificationReport(VerificationStatus.PASSED),
        observation,
    )

    assert matched.passed
    assert matched.match.evidence_ids == ("settings-state",)
    assert not unmatched.passed


class RepairingTaskPlanModel:
    provider = "fixed"
    model = "fixed-task-planner"
    endpoint_class = "test"
    last_call = None

    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, messages, output_schema, config):  # type: ignore[no-untyped-def]
        del config
        self.calls += 1
        if self.calls == 1:
            assert len(messages) == 2
            return output_schema.model_validate(
                {
                    "subgoals": [
                        {
                            "subgoal_id": "discover",
                            "objective": "Discover current setting",
                            "operation_class": "reversible_write",
                        }
                    ]
                }
            )
        assert "validation_errors" in messages[-1].content
        return output_schema.model_validate(
            {
                "subgoals": [
                    {
                        "subgoal_id": "discover",
                        "objective": "Discover current setting",
                        "success_criteria": ["setting is known"],
                        "evidence_requirements": ["settings API"],
                        "operation_class": "reversible_write",
                    },
                    {
                        "subgoal_id": "write",
                        "objective": "Write desired setting",
                        "depends_on": ["discover"],
                        "success_criteria": ["setting is dark"],
                        "evidence_requirements": ["settings API"],
                        "operation_class": "reversible_write",
                    },
                    {
                        "subgoal_id": "confirm",
                        "objective": "Confirm desired setting",
                        "depends_on": ["write"],
                        "success_criteria": ["setting remains dark"],
                        "evidence_requirements": ["settings API"],
                        "operation_class": "reversible_write",
                    },
                ]
            }
        )


def test_llm_task_planner_repairs_once_then_returns_runtime_bound_plan() -> None:
    import asyncio

    model = RepairingTaskPlanModel()
    plan = asyncio.run(LLMTaskPlanner(model).plan(_context()))

    assert model.calls == 2
    assert plan.generated_by == TaskPlanSource.LLM
    assert plan.task_id == _task().task_id
    assert len(plan.subgoals) == 3
    assert TaskPlanValidator().validate(plan, _task(), state_version=4).status == TaskPlanValidationStatus.ACCEPT
