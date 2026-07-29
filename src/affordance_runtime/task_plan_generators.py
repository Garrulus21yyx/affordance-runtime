"""TaskPlanDraft generator migration foundation.

TPA-5 keeps the existing TaskPlannerPort production path intact while exposing
draft-producing generator interfaces for rule, router, and reference planning
surfaces. The generated drafts do not contain Runtime-owned plan identity,
version, supersession, or state binding fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Protocol

from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.task_intake import SourcedTaskClaim, TaskSpec, TaskStructure
from affordance_runtime.task_plan_contracts import (
    TaskPlanDraft,
    TaskPlanGeneratorSource,
)
from affordance_runtime.task_planning import (
    RuleTaskPlanner,
    TaskPlan,
    TaskPlannerPort,
    TaskPlanningContext,
)


class TaskPlanDraftGeneratorPort(Protocol):
    def generate(
        self,
        context: TaskPlanningContext,
    ) -> TaskPlanDraft | Awaitable[TaskPlanDraft]: ...


@dataclass(frozen=True)
class TaskPlanDraftProjector:
    """Project a legacy TaskPlan candidate into authority-free draft form."""

    default_evidence_source_kind: str = "dom_state"

    def project(self, plan: TaskPlan, *, task_spec: TaskSpec) -> TaskPlanDraft:
        return TaskPlanDraft(
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            generated_by=TaskPlanGeneratorSource(plan.generated_by.value),
            generator_id=plan.generated_by.value,
            generator_version="legacy-taskplanner-draft-projection",
            steps=tuple(self._step_from_subgoal(subgoal, task_spec) for subgoal in plan.subgoals),
            assumptions=plan.assumptions,
            source_refs=_task_source_refs(task_spec),
        )

    def _step_from_subgoal(self, subgoal, task_spec: TaskSpec) -> StepSpec:  # noqa: ANN001
        _reject_forbidden_step_content(subgoal.objective)
        criterion = self._criterion_from_subgoal(subgoal, task_spec)
        return StepSpec(
            step_id=subgoal.subgoal_id,
            objective=subgoal.objective,
            depends_on=subgoal.depends_on,
            completion_criteria=(criterion,),
            source_refs=_subgoal_source_refs(subgoal.subgoal_id, task_spec),
        )

    def _criterion_from_subgoal(self, subgoal, task_spec: TaskSpec) -> StateCriterion:  # noqa: ANN001
        source_refs = _subgoal_source_refs(subgoal.subgoal_id, task_spec)
        if subgoal.outcome is not None:
            return StateCriterion(
                criterion_id=f"criterion:{subgoal.subgoal_id}",
                source_refs=source_refs,
                subject=subgoal.outcome.subject,
                relation=StateCriterionRelation(subgoal.outcome.relation.value),
                expected_value=subgoal.outcome.value or None,
                evidence_policy=CriterionEvidencePolicy(
                    minimum_strength=EvidenceStrength.INDEPENDENT,
                    allowed_source_kinds=(self.default_evidence_source_kind,),
                ),
            )
        return StateCriterion(
            criterion_id=f"criterion:{subgoal.subgoal_id}",
            source_refs=source_refs,
            subject=subgoal.subgoal_id,
            relation=StateCriterionRelation.IS_VISIBLE,
            expected_value=True,
            evidence_policy=CriterionEvidencePolicy(
                minimum_strength=EvidenceStrength.INDEPENDENT,
                allowed_source_kinds=(self.default_evidence_source_kind,),
            ),
        )


@dataclass(frozen=True)
class RuleTaskPlanDraftGenerator:
    """Draft-producing wrapper for the existing rule task planner."""

    legacy_planner: TaskPlannerPort = field(default_factory=RuleTaskPlanner)
    projector: TaskPlanDraftProjector = TaskPlanDraftProjector()

    def generate(self, context: TaskPlanningContext) -> TaskPlanDraft:
        plan = self.legacy_planner.plan(context)
        if not isinstance(plan, TaskPlan):
            raise TypeError("rule task plan generator requires synchronous legacy planner output")
        return self.projector.project(plan, task_spec=context.task_spec)


@dataclass(frozen=True)
class PricingTaskPlanDraftGenerator:
    """Reference pricing plan draft generator, isolated from accepted-plan authority."""

    def generate(self, context: TaskPlanningContext) -> TaskPlanDraft:
        steps = (
            StepSpec(
                step_id="reveal-pro",
                objective="Reveal the Pro plan limits",
                completion_criteria=(
                    StateCriterion(
                        criterion_id="criterion:reveal-pro",
                        source_refs=_task_source_refs(context.task_spec),
                        subject="pricing.pro",
                        relation=StateCriterionRelation.IS_VISIBLE,
                        expected_value=True,
                        evidence_policy=CriterionEvidencePolicy(
                            minimum_strength=EvidenceStrength.INDEPENDENT,
                            allowed_source_kinds=("dom_state",),
                        ),
                    ),
                ),
                source_refs=_task_source_refs(context.task_spec),
            ),
            StepSpec(
                step_id="reveal-enterprise",
                objective="Reveal the Enterprise plan limits",
                completion_criteria=(
                    StateCriterion(
                        criterion_id="criterion:reveal-enterprise",
                        source_refs=_task_source_refs(context.task_spec),
                        subject="pricing.enterprise",
                        relation=StateCriterionRelation.IS_VISIBLE,
                        expected_value=True,
                        evidence_policy=CriterionEvidencePolicy(
                            minimum_strength=EvidenceStrength.INDEPENDENT,
                            allowed_source_kinds=("dom_state",),
                        ),
                    ),
                ),
                source_refs=_task_source_refs(context.task_spec),
                depends_on=("reveal-pro",),
            ),
        )
        return TaskPlanDraft(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="pricing-task-plan-generator",
            generator_version="tpa-5-draft",
            steps=steps,
            assumptions=("pricing cards can be revealed independently",),
            source_refs=_task_source_refs(context.task_spec),
        )


@dataclass(frozen=True)
class TaskPlanDraftGeneratorRouter:
    """Route planning requests to draft generators without accepting a plan."""

    rule_generator: TaskPlanDraftGeneratorPort = field(default_factory=RuleTaskPlanDraftGenerator)
    complex_generator: TaskPlanDraftGeneratorPort | None = None

    def generate(
        self,
        context: TaskPlanningContext,
        *,
        complex_task: bool | None = None,
    ) -> TaskPlanDraft | Awaitable[TaskPlanDraft]:
        if context.task_spec.obligations:
            return self.rule_generator.generate(context)
        if complex_task is None:
            complex_task = context.task_spec.task_structure == TaskStructure.MULTI_STAGE
        if not complex_task:
            return self.rule_generator.generate(context)
        if self.complex_generator is None:
            raise ValueError("complex task requires a TaskPlanDraftGeneratorPort")
        return self.complex_generator.generate(context)


def _task_source_refs(task_spec: TaskSpec) -> tuple[SourceReference, ...]:
    refs: list[SourceReference] = []
    for claim in task_spec.source_claims:
        refs.extend(_claim_source_refs(claim))
    if refs:
        return tuple(refs)
    return (
        SourceReference(
            source_id=task_spec.source_request_ref,
            source_unit_id=f"{task_spec.source_request_ref}:whole_request",
        ),
    )


def _subgoal_source_refs(subgoal_id: str, task_spec: TaskSpec) -> tuple[SourceReference, ...]:
    obligation = next((item for item in task_spec.obligations if item.obligation_id == subgoal_id), None)
    if obligation is None:
        return _task_source_refs(task_spec)
    claims = {item.claim_id: item for item in task_spec.source_claims}
    refs: list[SourceReference] = []
    for claim_id in obligation.claim_ids:
        claim = claims.get(claim_id)
        if claim is not None:
            refs.extend(_claim_source_refs(claim))
    if refs:
        return tuple(refs)
    return _task_source_refs(task_spec)


def _claim_source_refs(claim: SourcedTaskClaim) -> tuple[SourceReference, ...]:
    source_unit_ids = claim.source_unit_ids or (f"{claim.source_ref}:{claim.claim_id}",)
    return tuple(
        SourceReference(
            source_id=claim.source_ref,
            source_unit_id=source_unit_id,
            claim_id=claim.claim_id,
        )
        for source_unit_id in source_unit_ids
    )


def _reject_forbidden_step_content(value: str) -> None:
    lowered = value.casefold()
    forbidden = ("selector", "xpath", "backend", "coordinate", "locator", "approval_token", "#")
    if any(item in lowered for item in forbidden):
        raise ValueError("forbidden implementation detail in task plan draft")
