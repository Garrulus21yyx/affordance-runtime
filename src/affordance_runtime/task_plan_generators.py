"""Plan-candidate generator migration foundation.

SAR-3 keeps plan generation authority-free: generators return candidate steps
and do not create accepted plan identity, versions, supersession, or state
bindings.
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
from affordance_runtime.task_intake import (
    SourcedTaskClaim,
    TaskObligationSpec,
    TaskSpec,
    TaskStructure,
)
from affordance_runtime.task_plan_contracts import (
    PlanCandidate,
    TaskPlanGeneratorSource,
)
from affordance_runtime.task_planning import (
    SubgoalOutcome,
    TaskPlanCandidate,
    TaskPlanningContext,
)


class PlanCandidateGeneratorPort(Protocol):
    def generate(
        self,
        context: TaskPlanningContext,
    ) -> PlanCandidate | Awaitable[PlanCandidate]: ...


@dataclass(frozen=True)
class RulePlanCandidateGenerator:
    """Generate authority-free plan candidates from canonical task obligations."""

    default_evidence_source_kind: str = "dom_state"

    def generate(self, context: TaskPlanningContext) -> PlanCandidate:
        task_spec = context.task_spec
        source_refs = _task_source_refs(task_spec)
        return PlanCandidate(
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="rule-task-plan-generator",
            generator_version="sar-3-direct-candidate",
            steps=_steps_from_task_spec(
                task_spec,
                default_evidence_source_kind=self.default_evidence_source_kind,
            ),
            source_refs=source_refs,
        )


@dataclass(frozen=True)
class PricingPlanCandidateGenerator:
    """Reference pricing plan draft generator, isolated from accepted-plan authority."""

    def generate(self, context: TaskPlanningContext) -> PlanCandidate:
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
        return PlanCandidate(
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
class PlanCandidateGeneratorRouter:
    """Route planning requests to draft generators without accepting a plan."""

    rule_generator: PlanCandidateGeneratorPort = field(default_factory=RulePlanCandidateGenerator)
    complex_generator: PlanCandidateGeneratorPort | None = None

    def generate(
        self,
        context: TaskPlanningContext,
        *,
        complex_task: bool | None = None,
    ) -> PlanCandidate | Awaitable[PlanCandidate]:
        if context.task_spec.obligations:
            return self.rule_generator.generate(context)
        if complex_task is None:
            complex_task = context.task_spec.task_structure == TaskStructure.MULTI_STAGE
        if not complex_task:
            return self.rule_generator.generate(context)
        if self.complex_generator is None:
            raise ValueError("complex task requires a PlanCandidateGeneratorPort")
        return self.complex_generator.generate(context)


def _steps_from_task_spec(
    task_spec: TaskSpec,
    *,
    default_evidence_source_kind: str,
) -> tuple[StepSpec, ...]:
    if task_spec.obligations:
        return tuple(
            _step_from_obligation(
                obligation,
                task_spec,
                default_evidence_source_kind=default_evidence_source_kind,
            )
            for obligation in task_spec.obligations
        )
    source_refs = _task_source_refs(task_spec)
    return (
        StepSpec(
            step_id="step:implicit",
            objective=task_spec.objective,
            completion_criteria=(
                StateCriterion(
                    criterion_id="criterion:step:implicit",
                    source_refs=source_refs,
                    subject=task_spec.targets[0] if task_spec.targets else task_spec.task_id,
                    relation=StateCriterionRelation.IS_VISIBLE,
                    expected_value=True,
                    evidence_policy=CriterionEvidencePolicy(
                        minimum_strength=EvidenceStrength.INDEPENDENT,
                        allowed_source_kinds=(default_evidence_source_kind,),
                    ),
                ),
            ),
            source_refs=source_refs,
        ),
    )


def plan_candidate_from_provider_candidate(
    candidate: TaskPlanCandidate,
    context: TaskPlanningContext,
) -> PlanCandidate:
    task_spec = context.task_spec
    source_refs = _task_source_refs(task_spec)
    steps = []
    for item in candidate.subgoals:
        outcome = SubgoalOutcome.model_validate(item.outcome.model_dump(mode="json"))
        steps.append(
            StepSpec(
                step_id=item.subgoal_id,
                objective=outcome.description(),
                depends_on=item.depends_on,
                completion_criteria=(
                    StateCriterion(
                        criterion_id=f"criterion:{item.subgoal_id}",
                        source_refs=source_refs,
                        subject=outcome.subject,
                        relation=StateCriterionRelation(outcome.relation),
                        expected_value=outcome.value or None,
                        evidence_policy=CriterionEvidencePolicy(
                            minimum_strength=EvidenceStrength.INDEPENDENT,
                            allowed_source_kinds=("dom_state",),
                        ),
                    ),
                ),
                source_refs=source_refs,
            )
        )
    return PlanCandidate(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        generated_by=TaskPlanGeneratorSource.LLM,
        generator_id="llm-task-planner",
        generator_version="sar-3-provider-candidate",
        steps=tuple(steps),
        assumptions=candidate.assumptions,
        source_refs=source_refs,
    )


def _step_from_obligation(
    obligation: TaskObligationSpec,
    task_spec: TaskSpec,
    *,
    default_evidence_source_kind: str,
) -> StepSpec:
    source_refs = _subgoal_source_refs(obligation.obligation_id, task_spec)
    objective = _objective_for_obligation(obligation, task_spec)
    _reject_forbidden_step_content(objective)
    return StepSpec(
        step_id=obligation.obligation_id,
        objective=objective,
        depends_on=obligation.depends_on,
        completion_criteria=(
            StateCriterion(
                criterion_id=f"criterion:{obligation.obligation_id}",
                source_refs=source_refs,
                subject=obligation.subject,
                relation=StateCriterionRelation(obligation.relation),
                expected_value=obligation.expected_value,
                evidence_policy=CriterionEvidencePolicy(
                    minimum_strength=EvidenceStrength.INDEPENDENT,
                    allowed_source_kinds=(default_evidence_source_kind,),
                ),
            ),
        ),
        source_refs=source_refs,
    )


def _objective_for_obligation(
    obligation: TaskObligationSpec,
    task_spec: TaskSpec,
) -> str:
    claims = {item.claim_id: item for item in task_spec.source_claims}
    for claim_id in obligation.claim_ids:
        claim = claims.get(claim_id)
        if claim is not None and claim.statement.strip():
            return claim.statement
    if obligation.expected_value is not None:
        return f"{obligation.subject} {obligation.relation.value} {obligation.expected_value}"
    return f"{obligation.subject} {obligation.relation.value}"


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
