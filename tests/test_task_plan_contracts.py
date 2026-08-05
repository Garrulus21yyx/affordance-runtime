from __future__ import annotations

import pytest

from affordance_runtime.simplified_runtime_contracts import (
    CompositeCriterion,
    CompositeCriterionOperator,
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
from affordance_runtime.task_plan_contracts import (
    InitialTaskPlanRequest,
    PlanCandidate,
    PlanIssueKind,
    PlanIssueReport,
    TaskPlanAuthority,
    TaskPlanDecision,
    TaskPlanDecisionStatus,
    TaskPlanGeneratorSource,
    TaskPlanIssue,
    TaskPlanRepairDirective,
    TaskPlanRevisionRequest,
    TaskPlanRevisionTrigger,
)


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


def _candidate(
    *steps: StepSpec,
    observation_ref: str = "snapshot:1",
    state_version: int = 3,
) -> PlanCandidate:
    return PlanCandidate(
        task_spec_identity="sha256:task",
        task_revision=1,
        generated_by=TaskPlanGeneratorSource.RULE,
        generator_id="rule-task-planner",
        steps=steps or (_step(),),
        based_on_observation_ref=observation_ref,
        based_on_state_version=state_version,
        source_refs=(_source(),),
    )


def test_task_plan_authority_preserves_composite_criteria_and_typed_values() -> None:
    request = InitialTaskPlanRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=3,
        objective="Preserve canonical step semantics",
        observation_refs=("snapshot:1",),
        remaining_budget_steps=5,
    )
    first = _state_criterion(
        criterion_id="criterion:first",
        subject="amount",
        relation=StateCriterionRelation.EQUALS,
        expected_value=500,
    )
    second = _state_criterion(
        criterion_id="criterion:second",
        subject="approved",
        relation=StateCriterionRelation.EQUALS,
        expected_value=True,
    )
    composite = CompositeCriterion(
        criterion_id="criterion:all",
        source_refs=(_source(),),
        operator=CompositeCriterionOperator.ALL_OF,
        child_criterion_ids=(first.criterion_id, second.criterion_id),
    )
    step = StepSpec(
        step_id="step:typed",
        objective="preserve typed completion",
        interaction=ElementIntent("semantic:setting", (_source(),)),
        completion_criteria=(first, second, composite),
        source_refs=(_source(),),
    )

    decision = TaskPlanAuthority().admit_initial(request, _candidate(step))
    assert decision.plan is not None
    plan = decision.plan

    assert plan.steps == (step,)
    assert plan.steps[0].completion_criteria[0].expected_value == 500
    assert plan.steps[0].completion_criteria[1].expected_value is True
    assert plan.based_on_observation_ref == "snapshot:1"


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
    assert draft.based_on_state_version == 3
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
    candidate = PlanCandidate(
        task_spec_identity="sha256:task",
        task_revision=1,
        generated_by=TaskPlanGeneratorSource.RULE,
        generator_id="rule-task-planner",
        steps=(_step(),),
        source_refs=(_source(),),
    )

    assert isinstance(candidate, PlanCandidate)
    assert not hasattr(candidate, "plan_id")
    assert not hasattr(candidate, "plan_version")


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
    decision = TaskPlanAuthority().admit_initial(
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
    assert decision.plan is not None
    accepted = TaskPlanDecision.accepted(decision.plan)
    assert accepted.status == TaskPlanDecisionStatus.ACCEPTED
    assert accepted.plan_digest

    with pytest.raises(ValueError, match="accepted decision requires plan"):
        TaskPlanDecision(TaskPlanDecisionStatus.ACCEPTED)
    with pytest.raises(ValueError, match="rejected decision cannot carry plan"):
        TaskPlanDecision(
            TaskPlanDecisionStatus.REJECTED,
            plan=decision.plan,
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


def test_task_plan_authority_owns_plan_identity_versions_and_freshness() -> None:
    request = InitialTaskPlanRequest(
        task_spec_identity="sha256:task",
        task_revision=1,
        evaluated_at_state_version=3,
        objective="Do the task",
        observation_refs=("snapshot:1",),
        remaining_budget_steps=5,
    )
    authority = TaskPlanAuthority()
    first_decision = authority.admit_initial(request, _candidate())
    retry_decision = authority.admit_initial(request, _candidate())
    assert first_decision.plan is not None
    assert retry_decision.plan is not None
    first = first_decision.plan
    retry = retry_decision.plan

    assert first.plan_id == retry.plan_id
    assert first.plan_version == 1
    assert first.supersedes_plan_id == ""
    assert first.based_on_state_version == 3

    revision_decision = authority.admit_revision(
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
        _candidate(
            _step("step:1"),
            _step("step:2", depends_on=("step:1",)),
            observation_ref="snapshot:2",
            state_version=8,
        ),
    )
    assert revision_decision.plan is not None
    revision = revision_decision.plan
    assert revision.plan_version == 2
    assert revision.supersedes_plan_id == first.plan_id
    assert revision.plan_id != first.plan_id

    stale = authority.admit_initial(
        request,
        _candidate(observation_ref="snapshot:stale", state_version=2),
    )
    assert stale.status == TaskPlanDecisionStatus.REJECTED
    assert {issue.code for issue in stale.issues} == {
        "observation_basis_stale",
        "state_basis_stale",
    }
