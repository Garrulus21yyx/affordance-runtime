from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_plan_contracts import TaskPlan, TaskPlanGeneratorSource
from affordance_runtime.task_plan_progress import TaskProgress
from runtime_test_support import legacy_step_spec


def _step(step_id: str) -> StepSpec:
    refs = (SourceReference("request", f"request:{step_id}"),)
    return legacy_step_spec(
        step_id=step_id,
        objective=step_id,
        interaction=ElementIntent(step_id, refs),
        completion_criteria=(
            StateCriterion(
                criterion_id=f"criterion:{step_id}",
                source_refs=refs,
                subject=step_id,
                relation=StateCriterionRelation.IS_COMPLETED,
                evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
            ),
        ),
        source_refs=refs,
    )


def _plan(plan_id: str, version: int, *steps: StepSpec) -> TaskPlan:
    return TaskPlan(
        plan_id=plan_id,
        task_id="task:1",
        task_revision=1,
        plan_version=version,
        supersedes_plan_id="" if version == 1 else "plan:1",
        based_on_state_version=version,
        based_on_observation_ref=f"observation:{version}",
        generated_by=TaskPlanGeneratorSource.RULE,
        steps=steps,
    )


def test_replan_preserves_facts_bindings_and_verified_records_without_step_carry_forward() -> None:
    first = _plan("plan:1", 1, _step("discover"), _step("apply"))
    replacement = _plan("plan:2", 2, _step("apply:new"))
    state = StateKernel("task:1", "Do the task")
    state.install_task_plan(first)
    assert isinstance(state.task_progress, TaskProgress)
    state.task_progress.facts["fact:account"] = "verified"
    state.task_progress.bindings["binding:recipient"] = "recipient:42"
    state.complete_step("discover", ("evidence:1",), ("criterion:discover",))

    state.replace_task_plan(replacement)

    assert state.task_progress.facts == {"fact:account": "verified"}
    assert state.task_progress.bindings == {"binding:recipient": "recipient:42"}
    assert state.task_progress.verified_steps[0].step_id == "discover"
    assert replacement.steps == (_step("apply:new"),)
    assert "discover" not in {step.step_id for step in replacement.steps}
