from __future__ import annotations

from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StepActivityStatus,
)
from affordance_runtime.simplified_step_projection import (
    LegacyStepProjectionStatus,
    TaskCompletionProjectionStatus,
    project_legacy_task_plan_to_step_view,
    project_state_legacy_task_plan_to_step_view,
    project_task_completion_criterion,
)
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
    TaskObligationValueSource,
    TaskSpec,
)
from affordance_runtime.task_planning import (
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)


def _task_spec() -> TaskSpec:
    claim_a = SourcedTaskClaim(
        claim_id="claim:type-name",
        kind=TaskClaimKind.EFFECT,
        statement="name equals Alice",
        source_ref="source:user:1",
        source_unit_ids=("unit:type-name",),
    )
    claim_b = SourcedTaskClaim(
        claim_id="claim:submit",
        kind=TaskClaimKind.TERMINAL,
        statement="form submitted",
        source_ref="source:user:1",
        source_unit_ids=("unit:submit",),
    )
    return TaskSpec(
        task_id="task:1",
        revision=1,
        objective="Type Alice and submit",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("semantic:name", "semantic:submit"),
        success_criteria=("form submitted",),
        source_request_ref="source:user:1",
        source_claims=(claim_a, claim_b),
        obligations=(
            TaskObligationSpec(
                obligation_id="step:type-name",
                kind=TaskObligationKind.EFFECT,
                subject="semantic:name",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.LITERAL,
                expected_value="Alice",
                claim_ids=("claim:type-name",),
                evidence_requirements=("evidence:name",),
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="semantic:name",
                        relation=TaskObligationRelation.EQUALS,
                        value_ref="Alice",
                        minimum_strength="independent",
                        source_constraints=("post_action_observation",),
                    ),
                ),
            ),
            TaskObligationSpec(
                obligation_id="step:submit",
                kind=TaskObligationKind.EFFECT,
                subject="semantic:submit",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=("claim:submit",),
                depends_on=("step:type-name",),
                evidence_requirements=("evidence:submit",),
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.ACCESSIBILITY_STATE,
                        subject="semantic:submit",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        minimum_strength="authoritative",
                        source_constraints=("post_action_observation",),
                    ),
                ),
                terminal=True,
            ),
        ),
    )


def _plan(task: TaskSpec) -> TaskPlan:
    name_source = SourceReference(
        source_id="source:user:1",
        source_unit_id="unit:type-name",
        claim_id="claim:type-name",
    )
    submit_source = SourceReference(
        source_id="source:user:1",
        source_unit_id="unit:submit",
        claim_id="claim:submit",
    )
    return TaskPlan(
        plan_id="plan:1",
        task_id=task.task_id,
        task_revision=task.revision,
        plan_version=1,
        based_on_state_version=3,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="step:type-name",
                objective="Type Alice",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="semantic:name",
                    relation=SubgoalOutcomeRelation.EQUALS,
                    value="Alice",
                ),
                interaction=ElementIntent("semantic:name", (name_source,)),
                success_criteria=("name equals Alice",),
                evidence_requirements=("evidence:name",),
            ),
            SubgoalSpec(
                subgoal_id="step:submit",
                objective="Submit form",
                depends_on=("step:type-name",),
                operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=SubgoalOutcome(
                    subject="semantic:submit",
                    relation=SubgoalOutcomeRelation.IS_COMPLETED,
                ),
                interaction=ElementIntent(
                    "semantic:submit",
                    (submit_source,),
                    role="button",
                ),
                success_criteria=("form submitted",),
                evidence_requirements=("evidence:submit",),
            ),
        ),
    )


def test_projects_legacy_task_plan_with_exact_ids_and_evidence() -> None:
    task = _task_spec()
    plan = _plan(task)
    progress = PlanProgress(
        active_subgoal_id="step:submit",
        completed_subgoal_ids=["step:type-name"],
        evidence_by_subgoal={"step:type-name": ["evidence:name:1"]},
    )

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=progress,
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTED
    assert result.task_plan_view is not None
    assert result.step_progress_view is not None
    assert result.task_plan_view.step_ids == ("step:type-name", "step:submit")
    assert result.task_plan_view.steps[1].depends_on == ("step:type-name",)
    assert result.task_plan_view.steps[0].source_refs[0].source_unit_id == "unit:type-name"
    assert result.task_plan_view.steps[0].source_refs[0].claim_id == "claim:type-name"
    assert (
        result.task_plan_view.steps[0]
        .completion_criteria[0]
        .evidence_policy
        .allowed_source_kinds
        == ("dom_state",)
    )
    assert (
        result.task_plan_view.steps[1]
        .completion_criteria[0]
        .evidence_policy
        .minimum_strength
        == EvidenceStrength.AUTHORITATIVE
    )
    assert result.step_progress_view.active_step_id == "step:submit"
    assert result.step_progress_view.activity_status == StepActivityStatus.ACTIVE
    assert result.step_progress_view.completed_step_ids == ("step:type-name",)
    assert result.step_progress_view.evidence_by_step_id == (
        ("step:type-name", ("evidence:name:1",)),
    )


def test_projection_rejects_lexical_mapping_when_subgoal_id_differs() -> None:
    task = _task_spec()
    plan = _plan(task).model_copy(
        update={
            "subgoals": (
                _plan(task).subgoals[0].model_copy(
                    update={"subgoal_id": "typed name field"}
                ),
                _plan(task).subgoals[1],
            ),
        }
    )

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=PlanProgress(),
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTION_INVALID
    assert "exact obligation id" in result.reason


def test_projects_flat_single_step_task_plan() -> None:
    task = _task_spec().model_copy(
        update={
            "obligations": (_task_spec().obligations[0].model_copy(update={"terminal": True}),)
        }
    )
    plan = TaskPlan(
        plan_id="plan:flat",
        task_id=task.task_id,
        task_revision=task.revision,
        plan_version=1,
        based_on_state_version=3,
        generated_by=TaskPlanSource.RULE,
        subgoals=(_plan(_task_spec()).subgoals[0],),
    )

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=PlanProgress(active_subgoal_id="step:type-name"),
        evaluated_at_state_version=4,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTED
    assert result.task_plan_view is not None
    assert result.task_plan_view.step_ids == ("step:type-name",)


def test_projection_reports_stale_plan_revision() -> None:
    task = _task_spec()
    plan = _plan(task).model_copy(update={"task_revision": 2})

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=PlanProgress(),
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.STALE_PLAN


def test_state_projection_is_read_only() -> None:
    task = _task_spec()
    plan = _plan(task)
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    state.install_task_plan(plan)
    state.activate_next_step()
    state.complete_step("step:type-name", ("evidence:name:1",))
    version = state.version

    result = project_state_legacy_task_plan_to_step_view(
        task_spec=task,
        state=state,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTED
    assert state.version == version


def test_completed_plan_does_not_project_last_step_as_active() -> None:
    task = _task_spec()
    plan = _plan(task)
    progress = PlanProgress(
        completed_subgoal_ids=["step:type-name", "step:submit"],
        evidence_by_subgoal={
            "step:type-name": ["evidence:name:1"],
            "step:submit": ["evidence:submit:1"],
        },
    )

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=progress,
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTED
    assert result.step_progress_view is not None
    assert result.step_progress_view.activity_status == StepActivityStatus.COMPLETED
    assert result.step_progress_view.active_step_id is None
    assert result.step_progress_view.ready_step_ids == ()


def test_ready_but_not_activated_step_is_not_projected_as_active() -> None:
    task = _task_spec()
    plan = _plan(task)
    progress = PlanProgress(
        completed_subgoal_ids=["step:type-name"],
        evidence_by_subgoal={"step:type-name": ["evidence:name:1"]},
    )

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=progress,
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTED
    assert result.step_progress_view is not None
    assert result.step_progress_view.activity_status == StepActivityStatus.READY_NOT_ACTIVATED
    assert result.step_progress_view.active_step_id is None
    assert result.step_progress_view.ready_step_ids == ("step:submit",)


def test_projection_rejects_unknown_completed_failed_or_evidence_ids() -> None:
    task = _task_spec()
    plan = _plan(task)

    for progress, reason in (
        (PlanProgress(completed_subgoal_ids=["unknown"]), "unknown completed"),
        (PlanProgress(failed_subgoal_ids=["unknown"]), "unknown failed"),
        (
            PlanProgress(evidence_by_subgoal={"step:type-name": ["evidence:name:1"]}),
            "evidence key",
        ),
    ):
        result = project_legacy_task_plan_to_step_view(
            task_spec=task,
            plan=plan,
            progress=progress,
            evaluated_at_state_version=8,
        )

        assert result.status == LegacyStepProjectionStatus.PROJECTION_INVALID
        assert reason in result.reason


def test_projection_rejects_completed_step_without_evidence() -> None:
    task = _task_spec()
    plan = _plan(task)

    result = project_legacy_task_plan_to_step_view(
        task_spec=task,
        plan=plan,
        progress=PlanProgress(completed_subgoal_ids=["step:type-name"]),
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.PROJECTION_INVALID
    assert "without verifier evidence" in result.reason


def test_projection_rejects_unspecified_typed_evidence_policy() -> None:
    task = _task_spec()
    unsupported = task.model_copy(
        update={
            "obligations": (
                task.obligations[0].model_copy(
                    update={"typed_evidence_requirements": ()}
                ),
                task.obligations[1],
            )
        }
    )

    result = project_legacy_task_plan_to_step_view(
        task_spec=unsupported,
        plan=_plan(task),
        progress=PlanProgress(active_subgoal_id="step:type-name"),
        evaluated_at_state_version=8,
    )

    assert result.status == LegacyStepProjectionStatus.UNSUPPORTED_EVIDENCE_POLICY


def test_projects_single_terminal_obligation_as_task_completion_criterion() -> None:
    task = _task_spec()

    result = project_task_completion_criterion(task)

    assert result.status == TaskCompletionProjectionStatus.PROJECTED
    assert result.criterion is not None
    assert result.criterion.criterion_id == "step:submit"


def test_task_completion_projection_pending_without_terminal_obligation() -> None:
    task = _task_spec().model_copy(
        update={
            "obligations": (
                _task_spec().obligations[0],
                _task_spec().obligations[1].model_copy(update={"terminal": False}),
            )
        }
    )

    result = project_task_completion_criterion(task)

    assert result.status == TaskCompletionProjectionStatus.PENDING
    assert result.criterion is None


def test_task_completion_projection_rejects_ambiguous_terminal_obligations() -> None:
    task = _task_spec()
    ambiguous = task.model_copy(
        update={
            "obligations": (
                task.obligations[0].model_copy(update={"terminal": True}),
                task.obligations[1],
            )
        }
    )

    result = project_task_completion_criterion(ambiguous)

    assert result.status == TaskCompletionProjectionStatus.UNSUPPORTED
    assert "multiple terminal" in result.reason
