from __future__ import annotations

from pathlib import Path

import pytest

from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepActivityStatus,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_contracts import (
    InitialTaskPlanRequest,
    PlanCandidate,
    PlanIssueKind,
    PlanIssueReport,
    TaskPlanAuthorityBinder,
    TaskPlanDecision,
    TaskPlanDecisionStatus,
    TaskPlanGeneratorSource,
    TaskPlanIssue,
    TaskPlanRepairDirective,
    TaskPlanRevisionRequest,
    TaskPlanRevisionTrigger,
)
from affordance_runtime.task_planning import TaskPlanActionFamily

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "affordance_runtime"


def _source() -> SourceReference:
    return SourceReference(
        source_id="source:req",
        source_unit_id="source:req:unit:1",
        claim_id="claim:1",
    )


def _criterion(criterion_id: str = "criterion:step:1") -> StateCriterion:
    return StateCriterion(
        criterion_id=criterion_id,
        source_refs=(_source(),),
        subject="semantic:target",
        relation=StateCriterionRelation.IS_VISIBLE,
        expected_value=True,
        evidence_policy=CriterionEvidencePolicy(
            EvidenceStrength.INDEPENDENT,
            ("dom_state",),
        ),
    )


def _state_criterion(
    *,
    criterion_id: str,
    subject: str,
    relation: StateCriterionRelation,
    expected_value: object = None,
) -> StateCriterion:
    return StateCriterion(
        criterion_id=criterion_id,
        source_refs=(_source(),),
        subject=subject,
        relation=relation,
        expected_value=expected_value,
        evidence_policy=CriterionEvidencePolicy(
            EvidenceStrength.INDEPENDENT,
            ("dom_state",),
        ),
    )


def _step(step_id: str = "step:1", *, depends_on: tuple[str, ...] = ()) -> StepSpec:
    return StepSpec(
        step_id=step_id,
        objective=f"complete {step_id}",
        interaction=ElementIntent("semantic:setting", (_source(),)),
        completion_criteria=(_criterion(f"criterion:{step_id}"),),
        source_refs=(_source(),),
        depends_on=depends_on,
    )


def _criterion_step(
    step_id: str,
    *,
    subject: str,
    relation: StateCriterionRelation,
    expected_value: object = None,
) -> StepSpec:
    return StepSpec(
        step_id=step_id,
        objective=f"{subject} {relation.value}",
        interaction=ElementIntent(subject, (_source(),)),
        completion_criteria=(
            _state_criterion(
                criterion_id=f"criterion:{step_id}",
                subject=subject,
                relation=relation,
                expected_value=expected_value,
            ),
        ),
        source_refs=(_source(),),
    )


def _candidate(*steps: StepSpec) -> PlanCandidate:
    return PlanCandidate(
        task_spec_identity="sha256:task",
        task_revision=1,
        generated_by=TaskPlanGeneratorSource.RULE,
        generator_id="rule-task-planner",
        steps=steps or (_step(),),
        source_refs=(_source(),),
    )


def test_task_plan_authority_binder_preserves_bindable_action_family() -> None:
    request = InitialTaskPlanRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=3,
        objective="Complete controls",
        observation_refs=("snapshot:1",),
        remaining_budget_steps=5,
        operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    candidate = _candidate(
        _criterion_step(
            "text",
            subject="text_field:Myron",
            relation=StateCriterionRelation.HAS_CHANGED,
        ),
        _criterion_step(
            "slider",
            subject="slider_value_7",
            relation=StateCriterionRelation.HAS_CHANGED,
        ),
        _criterion_step(
            "checkbox",
            subject="checkbox_3_state",
            relation=StateCriterionRelation.HAS_CHANGED,
        ),
        _criterion_step(
            "submit",
            subject="submit_button_state",
            relation=StateCriterionRelation.HAS_CHANGED,
        ),
    )

    plan = TaskPlanAuthorityBinder().bind_initial(request, candidate)

    assert tuple(item.action_family for item in plan.subgoals) == (
        TaskPlanActionFamily.TYPE_TEXT,
        TaskPlanActionFamily.PRESS_KEY,
        TaskPlanActionFamily.ACTIVATE,
        TaskPlanActionFamily.ACTIVATE,
    )


def test_task_plan_authority_binder_does_not_infer_action_family_for_read_only_step() -> None:
    request = InitialTaskPlanRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=3,
        objective="Observe controls",
        observation_refs=("snapshot:1",),
        remaining_budget_steps=5,
    )

    plan = TaskPlanAuthorityBinder().bind_initial(
        request,
        _candidate(
            _criterion_step(
                "visible",
                subject="submit_button_state",
                relation=StateCriterionRelation.IS_AVAILABLE,
            ),
        ),
    )

    assert plan.subgoals[0].operation_class == OperationClass.READ_ONLY
    assert plan.subgoals[0].action_family is None


def _plan_view() -> TaskPlanView:
    return TaskPlanView(
        plan_id="plan:1",
        plan_version=1,
        task_spec_identity="sha256:task",
        task_revision=1,
        steps=(_step(),),
        active_step_id="step:1",
    )


def _progress_view() -> StepProgressView:
    return StepProgressView(
        plan_id="plan:1",
        plan_version=1,
        active_step_id="step:1",
        activity_status=StepActivityStatus.ACTIVE,
        ready_step_ids=("step:1",),
    )


def test_task_plan_draft_rejects_authority_fields_and_bad_graph() -> None:
    draft = _candidate(_step("step:a"), _step("step:b", depends_on=("step:a",)))

    assert isinstance(draft, PlanCandidate)
    assert not hasattr(draft, "plan_id")
    assert not hasattr(draft, "plan_version")
    assert not hasattr(draft, "supersedes_plan_id")
    assert not hasattr(draft, "based_on_state_version")
    assert draft.steps[1].depends_on == ("step:a",)

    with pytest.raises(ValueError, match="step ids must be unique"):
        _candidate(_step("step:a"), _step("step:a"))
    with pytest.raises(ValueError, match="unknown draft step dependency"):
        _candidate(_step("step:a", depends_on=("missing",)))
    with pytest.raises(ValueError, match="cycle"):
        _candidate(_step("step:a", depends_on=("step:b",)), _step("step:b", depends_on=("step:a",)))
    with pytest.raises(ValueError, match="forbidden implementation detail"):
        PlanCandidate(
            task_spec_identity="sha256:task",
            task_revision=1,
            generated_by=TaskPlanGeneratorSource.LLM,
            generator_id="model",
            steps=(_step(),),
            assumptions=("use selector #submit",),
            source_refs=(_source(),),
        )


def test_plan_candidate_is_the_canonical_unaccepted_plan_model() -> None:
    source = (SOURCE_ROOT / "task_plan_contracts.py").read_text(encoding="utf-8")

    candidate = PlanCandidate(
        task_spec_identity="sha256:task",
        task_revision=1,
        generated_by=TaskPlanGeneratorSource.RULE,
        generator_id="rule-task-planner",
        steps=(_step(),),
        source_refs=(_source(),),
    )

    assert isinstance(candidate, PlanCandidate)
    assert "class PlanCandidate" in source
    assert "TaskPlanDraft" not in source


def test_initial_and_revision_requests_are_distinct_and_identity_bound() -> None:
    initial = InitialTaskPlanRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=3,
        objective="Do the task",
        observation_refs=("snapshot:1",),
        remaining_budget_steps=5,
    )
    assert initial.observation_refs == ("snapshot:1",)

    trigger = TaskPlanRevisionTrigger(
        kind="step_unexecutable",
        reason_code="action_family_unavailable",
        evidence_refs=("evidence:1",),
        affected_step_id="step:1",
    )
    revision = TaskPlanRevisionRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=4,
        previous_plan=_plan_view(),
        previous_progress=_progress_view(),
        trigger=trigger,
        observation_refs=("snapshot:2",),
        remaining_budget_steps=4,
    )
    assert revision.previous_plan.plan_id == "plan:1"

    with pytest.raises(ValueError, match="previous progress plan identity mismatch"):
        TaskPlanRevisionRequest(
            task_spec_identity="sha256:task",
            task_revision=1,
            evaluated_at_state_version=4,
            previous_plan=_plan_view(),
            previous_progress=StepProgressView(plan_id="other", plan_version=1, active_step_id=None),
            trigger=trigger,
            observation_refs=("snapshot:2",),
            remaining_budget_steps=4,
        )


def test_plan_issue_report_cannot_carry_plan_patch_fields() -> None:
    issue = PlanIssueReport(
        plan_id="plan:1",
        plan_version=1,
        step_id="step:1",
        kind=PlanIssueKind.STEP_UNEXECUTABLE,
        reason_code="action_family_unavailable",
        evidence_refs=("evidence:1",),
        observed_at_state_version=5,
    )
    assert not hasattr(issue, "replacement_steps")
    assert not hasattr(issue, "patch")
    assert not hasattr(issue, "complete_step")


def test_task_plan_decision_status_invariants() -> None:
    plan = TaskPlanAuthorityBinder().bind_initial(
        InitialTaskPlanRequest(
            task_spec_identity="sha256:task",
            task_revision=1,
            evaluated_at_state_version=3,
            objective="Do the task",
            observation_refs=("snapshot:1",),
            remaining_budget_steps=5,
        ),
        _candidate(),
    )
    accepted = TaskPlanDecision.accepted(plan)
    assert accepted.status == TaskPlanDecisionStatus.ACCEPTED
    assert accepted.plan_digest

    with pytest.raises(ValueError, match="accepted decision requires plan"):
        TaskPlanDecision(TaskPlanDecisionStatus.ACCEPTED)
    with pytest.raises(ValueError, match="rejected decision cannot carry plan"):
        TaskPlanDecision(
            TaskPlanDecisionStatus.REJECTED,
            plan=plan,
            issues=(TaskPlanIssue("fatal", "bad"),),
        )
    with pytest.raises(ValueError, match="repair decision requires directives"):
        TaskPlanDecision(TaskPlanDecisionStatus.REPAIR_REQUIRED)
    with pytest.raises(ValueError, match="clarification decision requires question"):
        TaskPlanDecision(TaskPlanDecisionStatus.CLARIFICATION_REQUIRED)

    repair = TaskPlanDecision.repair_required(
        TaskPlanRepairDirective(reason_code="missing_step", instruction="add a sourced step")
    )
    assert repair.status == TaskPlanDecisionStatus.REPAIR_REQUIRED


def test_task_plan_authority_binder_owns_plan_identity_and_versions() -> None:
    request = InitialTaskPlanRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=3,
        objective="Do the task",
        observation_refs=("snapshot:1",),
        remaining_budget_steps=5,
    )
    binder = TaskPlanAuthorityBinder()
    first = binder.bind_initial(request, _candidate())
    retry = binder.bind_initial(request, _candidate())

    assert first.plan_id == retry.plan_id
    assert first.plan_version == 1
    assert first.supersedes_plan_id == ""
    assert first.based_on_state_version == 3

    revision = binder.bind_revision(
        TaskPlanRevisionRequest(
            task_spec_identity="sha256:task",
            task_revision=1,
            evaluated_at_state_version=8,
            previous_plan=TaskPlanView(
                plan_id=first.plan_id,
                plan_version=first.plan_version,
                task_spec_identity="sha256:task",
                task_revision=1,
                steps=(_step(),),
                active_step_id="step:1",
            ),
            previous_progress=StepProgressView(
                plan_id=first.plan_id,
                plan_version=first.plan_version,
                active_step_id="step:1",
                activity_status=StepActivityStatus.ACTIVE,
                ready_step_ids=("step:1",),
            ),
            trigger=TaskPlanRevisionTrigger(
                kind="step_unexecutable",
                reason_code="action_family_unavailable",
                evidence_refs=("evidence:1",),
                affected_step_id="step:1",
            ),
            observation_refs=("snapshot:2",),
            remaining_budget_steps=4,
        ),
        _candidate(_step("step:1"), _step("step:2", depends_on=("step:1",))),
    )

    assert revision.plan_version == 2
    assert revision.supersedes_plan_id == first.plan_id
    assert revision.plan_id != first.plan_id
