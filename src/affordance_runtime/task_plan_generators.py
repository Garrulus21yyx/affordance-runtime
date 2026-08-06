"""Plan-candidate generator migration foundation.

SAR-3 keeps plan generation authority-free: generators return candidate steps
and do not create accepted plan identity, versions, supersession, or state
bindings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Protocol

from affordance_runtime.criteria import PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    StepSpec,
)
from affordance_runtime.task_intake import OperationClass, TaskSpec, TaskStructure
from affordance_runtime.task_plan_contracts import (
    PlanProposal,
    TaskPlanGeneratorSource,
)
from affordance_runtime.task_planner import TaskPlanningRequest
from affordance_runtime.task_source_references import task_source_refs
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    SatisfactionMode,
)


class PlanProposalGeneratorPort(Protocol):
    def generate(
        self,
        request: TaskPlanningRequest,
    ) -> PlanProposal | Awaitable[PlanProposal]: ...


@dataclass(frozen=True)
class RulePlanProposalGenerator:
    """Generate a direct StepSpec proposal from accepted task meaning."""

    default_evidence_source_kind: str = "dom_state"

    def generate(self, request: TaskPlanningRequest) -> PlanProposal:
        task_spec = request.task_spec
        source_refs = task_source_refs(task_spec)
        return PlanProposal(
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="rule-task-plan-generator",
            generator_version="sar-3-direct-candidate",
            based_on_observation_ref=request.environment.snapshot_id,
            based_on_state_version=request.state_version,
            steps=_steps_from_task_spec(
                task_spec,
                default_evidence_source_kind=self.default_evidence_source_kind,
            ),
            source_refs=source_refs,
        )


@dataclass(frozen=True)
class PricingPlanProposalGenerator:
    """Reference pricing plan draft generator, isolated from accepted-plan authority."""

    def generate(self, request: TaskPlanningRequest) -> PlanProposal:
        requirement_refs = tuple(item.requirement_id for item in request.task_spec.requirements)
        steps = (
            StepSpec(
                step_id="reveal-pro",
                objective="Reveal the Pro plan limits",
                interaction=ElementIntent("pricing.pro", task_source_refs(request.task_spec)),
                completion_criteria=(_target_revealed("criterion:reveal-pro", "pricing.pro"),),
                source_refs=task_source_refs(request.task_spec),
                requirement_refs=requirement_refs,
            ),
            StepSpec(
                step_id="reveal-enterprise",
                objective="Reveal the Enterprise plan limits",
                interaction=ElementIntent("pricing.enterprise", task_source_refs(request.task_spec)),
                completion_criteria=(_target_revealed("criterion:reveal-enterprise", "pricing.enterprise"),),
                source_refs=task_source_refs(request.task_spec),
                requirement_refs=requirement_refs,
                depends_on=("reveal-pro",),
            ),
        )
        return PlanProposal(
            task_spec_identity=request.task_spec.identity,
            task_revision=request.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="pricing-task-plan-generator",
            generator_version="tpa-5-draft",
            based_on_observation_ref=request.environment.snapshot_id,
            based_on_state_version=request.state_version,
            steps=steps,
            assumptions=("pricing cards can be revealed independently",),
            source_refs=task_source_refs(request.task_spec),
        )


@dataclass(frozen=True)
class PlanProposalGeneratorRouter:
    """Route planning requests to draft generators without accepting a plan."""

    rule_generator: PlanProposalGeneratorPort = field(default_factory=RulePlanProposalGenerator)
    complex_generator: PlanProposalGeneratorPort | None = None

    def generate(
        self,
        request: TaskPlanningRequest,
        *,
        complex_task: bool | None = None,
    ) -> PlanProposal | Awaitable[PlanProposal]:
        if complex_task is None:
            complex_task = request.task_spec.task_structure == TaskStructure.MULTI_STAGE
        if not complex_task:
            return self.rule_generator.generate(request)
        if self.complex_generator is None:
            raise ValueError("complex task requires a PlanProposalGeneratorPort")
        return self.complex_generator.generate(request)


def _steps_from_task_spec(
    task_spec: TaskSpec,
    *,
    default_evidence_source_kind: str,
) -> tuple[StepSpec, ...]:
    source_refs = task_source_refs(task_spec)
    requirement_refs = tuple(item.requirement_id for item in task_spec.requirements)
    state_holds = task_spec.operation_class in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
    return (
        StepSpec(
            step_id="step:implicit",
            objective=task_spec.objective,
            interaction=ElementIntent(
                task_spec.targets[0] if task_spec.targets else task_spec.task_id,
                source_refs,
            ),
            completion_criteria=(
                PredicateExpr(
                    "criterion:step:implicit",
                    SubjectExpr("target", task_spec.targets[0] if task_spec.targets else task_spec.task_id),
                    PredicateOperator.EXISTS if state_holds else PredicateOperator.CHANGED,
                    _policy(default_evidence_source_kind, action_caused=not state_holds),
                ),
            ),
            source_refs=source_refs,
            requirement_refs=requirement_refs,
            effect_authorization_refs=(() if state_holds else task_spec.allowed_effect_refs),
            effectful=not state_holds,
        ),
    )


def _target_revealed(criterion_id: str, target: str) -> PredicateExpr:
    return PredicateExpr(
        criterion_id,
        SubjectExpr("target", target),
        PredicateOperator.CHANGED,
        _policy("dom_state", action_caused=True),
    )


def _policy(source_kind: str, *, action_caused: bool = False) -> CriterionPolicy:
    source = EvidenceSourceKind(source_kind)
    return CriterionPolicy(
        satisfaction=(SatisfactionMode.ACTION_CAUSED if action_caused else SatisfactionMode.STATE_HOLDS),
        minimum_assurance=AssuranceLevel.STRUCTURAL,
        allowed_source_kinds=(source,),
        causal_lineage_required=action_caused,
    )
