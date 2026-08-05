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
    ElementIntent,
    EvidenceStrength,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.task_intake import OperationClass, TaskSpec, TaskStructure
from affordance_runtime.task_plan_contracts import (
    PlanCandidate,
    TaskPlanGeneratorSource,
)
from affordance_runtime.task_planner import TaskPlanningContext
from affordance_runtime.task_source_references import task_source_refs


class PlanCandidateGeneratorPort(Protocol):
    def generate(
        self,
        context: TaskPlanningContext,
    ) -> PlanCandidate | Awaitable[PlanCandidate]: ...


@dataclass(frozen=True)
class RulePlanCandidateGenerator:
    """Generate a direct StepSpec proposal from accepted task meaning."""

    default_evidence_source_kind: str = "dom_state"

    def generate(self, context: TaskPlanningContext) -> PlanCandidate:
        task_spec = context.task_spec
        source_refs = task_source_refs(task_spec)
        return PlanCandidate(
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="rule-task-plan-generator",
            generator_version="sar-3-direct-candidate",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
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
                interaction=ElementIntent("pricing.pro", task_source_refs(context.task_spec)),
                completion_criteria=(
                    StateCriterion(
                        criterion_id="criterion:reveal-pro",
                        source_refs=task_source_refs(context.task_spec),
                        subject="pricing.pro",
                        relation=StateCriterionRelation.IS_VISIBLE,
                        expected_value=True,
                        evidence_policy=CriterionEvidencePolicy(
                            minimum_strength=EvidenceStrength.INDEPENDENT,
                            allowed_source_kinds=("dom_state",),
                        ),
                    ),
                ),
                source_refs=task_source_refs(context.task_spec),
            ),
            StepSpec(
                step_id="reveal-enterprise",
                objective="Reveal the Enterprise plan limits",
                interaction=ElementIntent(
                    "pricing.enterprise", task_source_refs(context.task_spec)
                ),
                completion_criteria=(
                    StateCriterion(
                        criterion_id="criterion:reveal-enterprise",
                        source_refs=task_source_refs(context.task_spec),
                        subject="pricing.enterprise",
                        relation=StateCriterionRelation.IS_VISIBLE,
                        expected_value=True,
                        evidence_policy=CriterionEvidencePolicy(
                            minimum_strength=EvidenceStrength.INDEPENDENT,
                            allowed_source_kinds=("dom_state",),
                        ),
                    ),
                ),
                source_refs=task_source_refs(context.task_spec),
                depends_on=("reveal-pro",),
            ),
        )
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="pricing-task-plan-generator",
            generator_version="tpa-5-draft",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=steps,
            assumptions=("pricing cards can be revealed independently",),
            source_refs=task_source_refs(context.task_spec),
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
    source_refs = task_source_refs(task_spec)
    relation = (
        StateCriterionRelation.IS_VISIBLE
        if task_spec.operation_class in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
        else StateCriterionRelation.IS_COMPLETED
    )
    return (
        StepSpec(
            step_id="step:implicit",
            objective=task_spec.objective,
            interaction=ElementIntent(
                task_spec.targets[0] if task_spec.targets else task_spec.task_id,
                source_refs,
            ),
            completion_criteria=(
                StateCriterion(
                    criterion_id="criterion:step:implicit",
                    source_refs=source_refs,
                    subject=task_spec.targets[0] if task_spec.targets else task_spec.task_id,
                    relation=relation,
                    expected_value=(True if relation == StateCriterionRelation.IS_VISIBLE else None),
                    evidence_policy=CriterionEvidencePolicy(
                        minimum_strength=EvidenceStrength.INDEPENDENT,
                        allowed_source_kinds=(default_evidence_source_kind,),
                    ),
                ),
            ),
            source_refs=source_refs,
        ),
    )
