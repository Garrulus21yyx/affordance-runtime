"""Observation-grounded, authority-free TaskPlan proposal policy."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Awaitable, Protocol
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from affordance_runtime.criteria import LiteralValue, PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.simplified_runtime_contracts import (
    SourceReference,
    StateCriterionRelation,
    StepSpec,
    interaction_for_state,
)
from affordance_runtime.task_intake import StrictModel, TaskSpec, TaskStructure
from affordance_runtime.task_plan_contracts import PlanCandidate, TaskPlanGeneratorSource
from affordance_runtime.task_source_references import task_source_refs
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    SatisfactionMode,
)

TASK_PLAN_SCHEMA_VERSION = "2.0"
TASK_PLAN_ENTRY_SCHEMA_POLICY_VERSION = "canonical-steps-v2"
TASK_PLAN_CARDINALITY_POLICY_VERSION = "bounded-plan-proposal-v2"
TASK_PLAN_CONTEXT_POLICY_VERSION = "canonical-task-planning-request-v2"
TASK_PLAN_OUTCOME_STATE_SUPPORT_POLICY_VERSION = "typed-criterion-expression-v2"
TASK_PLANNER_PROMPT_VERSION = "task-planner-v14"

_VALUE_RELATIONS = frozenset(
    {
        CriterionRelation.EQUALS,
        CriterionRelation.CONTAINS,
        CriterionRelation.MATCHES,
        CriterionRelation.IS_ORDERED_AS,
    }
)


class PlanningAffordanceState(StrictModel):
    visible: bool | None = None
    enabled: bool | None = None
    control_value: str | None = Field(default=None, max_length=240)
    checked: bool | None = None
    selected: bool | None = None
    selected_options: tuple[str, ...] = Field(default=(), max_length=20)
    expanded: bool | None = None
    element_tag: str = Field(default="", max_length=40)


class PlanningAffordanceSummary(StrictModel):
    semantic_target_id: str = Field(min_length=1)
    role: str = ""
    label: str = ""
    supported_actions: tuple[str, ...] = ()
    current_state: PlanningAffordanceState = Field(default_factory=PlanningAffordanceState)


class PlanningEnvironmentSummary(StrictModel):
    environment_revision: str = ""
    snapshot_id: str = ""
    page_revision: str = ""
    url: str = ""
    affordances: tuple[PlanningAffordanceSummary, ...] = Field(default=(), max_length=64)


class CriteriaEvidenceLedgerEntry(StrictModel):
    step_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class TaskPlanningFailureSummary(StrictModel):
    phase: str = ""
    error_code: str = ""
    reason: str = ""
    step_id: str = ""
    environment_revision: str = ""


class TaskPlanningRecoverySummary(StrictModel):
    incident_id: str = ""
    root_error_code: str = ""
    terminal_outcome: str = ""
    findings: tuple[str, ...] = Field(default=(), max_length=16)
    attempted_actions: tuple[str, ...] = Field(default=(), max_length=16)


class TaskPlanningBudgetSummary(StrictModel):
    steps_remaining: int = Field(ge=0)
    observations_remaining: int = Field(ge=0)
    replans_remaining: int = Field(ge=0)
    recoveries_remaining: int = Field(ge=0)
    effectful_actions_remaining: int = Field(ge=0)


class TaskPlanningContext(StrictModel):
    """Bounded current canonical state supplied to a proposal generator."""

    schema_version: str = "2.0"
    task_spec: TaskSpec
    state_version: int = Field(ge=0)
    reason: str = "initial"
    current_plan_id: str = ""
    current_plan_version: int = Field(default=0, ge=0)
    environment: PlanningEnvironmentSummary = Field(default_factory=PlanningEnvironmentSummary)
    active_step_id: str = ""
    completed_step_ids: tuple[str, ...] = ()
    failed_step_ids: tuple[str, ...] = ()
    criteria_evidence_ledger: tuple[CriteriaEvidenceLedgerEntry, ...] = ()
    failures: tuple[TaskPlanningFailureSummary, ...] = Field(default=(), max_length=16)
    recovery_summary: TaskPlanningRecoverySummary | None = None
    disproved_assumptions: tuple[str, ...] = Field(default=(), max_length=16)
    remaining_budget: TaskPlanningBudgetSummary


class TaskPlannerPort(Protocol):
    def generate_candidate(
        self, context: TaskPlanningContext
    ) -> PlanCandidate | Awaitable[PlanCandidate]: ...


@dataclass(frozen=True)
class PlanningRouter:
    """Select a proposal generator without accepting or versioning its output."""

    complex_planner: TaskPlannerPort | None = None

    def generate_candidate(
        self, context: TaskPlanningContext
    ) -> PlanCandidate | Awaitable[PlanCandidate]:
        from affordance_runtime.task_plan_generators import RulePlanCandidateGenerator

        if context.task_spec.task_structure != TaskStructure.MULTI_STAGE:
            return RulePlanCandidateGenerator().generate(context)
        if self.complex_planner is None:
            return RulePlanCandidateGenerator().generate(context)
        return self.complex_planner.generate_candidate(context)


class TaskPlanStepProposal(StrictModel):
    """Provider proposal for one semantic step, never a concrete action."""

    step_id: str = Field(min_length=1)
    objective: str = Field(min_length=1, max_length=480)
    subject: str = Field(min_length=1, max_length=480)
    relation: CriterionRelation
    value: str = Field(default="", max_length=480)
    requirement_refs: tuple[str, ...] = Field(min_length=1)
    effect_authorization_refs: tuple[str, ...] = ()
    effectful: bool = False
    enabling_need: str = Field(default="", max_length=480)
    depends_on: tuple[str, ...] = ()
    max_actions: int = Field(default=10, ge=1, le=50)
    max_recoveries: int = Field(default=2, ge=0, le=10)

    @model_validator(mode="after")
    def validate_shape(self) -> "TaskPlanStepProposal":
        if self.relation in _VALUE_RELATIONS and not self.value.strip():
            raise ValueError(f"{self.relation.value} requires a value")
        if self.relation not in _VALUE_RELATIONS and self.value:
            raise ValueError(f"{self.relation.value} does not accept a value")
        if self.effectful and not self.effect_authorization_refs:
            raise ValueError("effectful provider step requires admitted effect refs")
        return self


class TaskPlanProviderResponse(StrictModel):
    steps: tuple[TaskPlanStepProposal, ...] = Field(min_length=1, max_length=8)
    assumptions: tuple[str, ...] = ()


def task_planner_model_config() -> ModelConfig:
    return ModelConfig(
        temperature=0.0,
        max_tokens=1_024,
        prompt_version=TASK_PLANNER_PROMPT_VERSION,
    )


_TASK_PLANNER_SYSTEM_PROMPT = """You are a bounded task planner. Return only a TaskPlanProviderResponse containing semantic StepSpec proposals. Every step must cite admitted requirement IDs and every effectful step must cite admitted effect authorization IDs. Return typed desired state, dependencies, and budgets only. Never return selectors, coordinates, backend handles, locators, approval tokens, concrete actions, capability grants, or raw source text. Observation is enabling evidence, never user authorization. Runtime independently admits and versions the plan."""


@dataclass
class StrictTaskPlanner:
    """Provider-facing planner over the canonical bounded TaskPlanningContext."""

    model: ModelPort
    config: ModelConfig = field(default_factory=task_planner_model_config)

    async def generate_candidate(self, context: TaskPlanningContext) -> PlanCandidate:
        summary = task_spec_planning_summary(context.task_spec)
        planning_context = context.model_dump(mode="json", exclude={"task_spec"})
        messages = (
            ModelMessage(role="system", content=_TASK_PLANNER_SYSTEM_PROMPT),
            ModelMessage(
                role="user",
                content=json.dumps(
                    {"task_spec": summary, "planning_context": planning_context},
                    sort_keys=True,
                ),
            ),
        )
        response = await self.model.generate_structured(
            messages,
            TaskPlanProviderResponse,
            self.config,
        )
        source_refs = task_source_refs(context.task_spec)
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.LLM,
            generator_id="strict-task-planner",
            generator_version=TASK_PLANNER_PROMPT_VERSION,
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=tuple(_canonical_provider_step(item, source_refs) for item in response.steps),
            assumptions=response.assumptions,
            source_refs=source_refs,
        )


def _canonical_provider_step(
    proposal: TaskPlanStepProposal,
    source_refs: tuple[SourceReference, ...],
) -> StepSpec:
    relation = StateCriterionRelation(proposal.relation)
    expected_value = proposal.value or None
    return StepSpec(
        step_id=proposal.step_id,
        objective=proposal.objective,
        interaction=interaction_for_state(
            proposal.subject,
            relation,
            expected_value,
            source_refs,
        ),
        completion_criteria=(
            PredicateExpr(
                criterion_id=f"criterion:{proposal.step_id}",
                subject=SubjectExpr("target", proposal.subject, relation.value),
                operator=_predicate_operator(relation),
                policy=CriterionPolicy(
                    satisfaction=(
                        SatisfactionMode.ACTION_CAUSED
                        if proposal.effectful
                        else SatisfactionMode.STATE_HOLDS
                    ),
                    minimum_assurance=AssuranceLevel.STRUCTURAL,
                    allowed_source_kinds=(EvidenceSourceKind.DOM_STATE,),
                    causal_lineage_required=proposal.effectful,
                ),
                value=None if expected_value is None else LiteralValue(expected_value),
                source_refs=tuple(ref.source_unit_id for ref in source_refs),
            ),
        ),
        source_refs=source_refs,
        requirement_refs=proposal.requirement_refs,
        effect_authorization_refs=proposal.effect_authorization_refs,
        effectful=proposal.effectful,
        enabling_need=proposal.enabling_need,
        depends_on=proposal.depends_on,
        max_actions=proposal.max_actions,
        max_recoveries=proposal.max_recoveries,
    )


def _predicate_operator(relation: StateCriterionRelation) -> PredicateOperator:
    return {
        StateCriterionRelation.EQUALS: PredicateOperator.EQUALS,
        StateCriterionRelation.CONTAINS: PredicateOperator.CONTAINS,
        StateCriterionRelation.MATCHES: PredicateOperator.MATCHES_REGEX,
        StateCriterionRelation.IS_VISIBLE: PredicateOperator.EXISTS,
        StateCriterionRelation.IS_ABSENT: PredicateOperator.ABSENT,
        StateCriterionRelation.IS_AVAILABLE: PredicateOperator.EXISTS,
        StateCriterionRelation.IS_SELECTED: PredicateOperator.SELECTED,
        StateCriterionRelation.IS_CHECKED: PredicateOperator.CHECKED,
        StateCriterionRelation.IS_EXPANDED: PredicateOperator.EQUALS,
        StateCriterionRelation.IS_COMPLETED: PredicateOperator.CHANGED,
        StateCriterionRelation.IS_ORDERED_AS: PredicateOperator.ORDERED_AS,
        StateCriterionRelation.HAS_CHANGED: PredicateOperator.CHANGED,
    }[relation]


def task_spec_planning_summary(task_spec: TaskSpec) -> dict[str, object]:
    return {
        "schema_version": task_spec.schema_version,
        "revision": task_spec.revision,
        "objective": task_spec.objective,
        "operation_class": task_spec.operation_class.value,
        "requirements": [item.model_dump(mode="json") for item in task_spec.requirements],
        "inputs": [item.model_dump(mode="json") for item in task_spec.inputs],
        "allowed_effect_refs": list(task_spec.allowed_effect_refs),
        "hard_constraint_refs": list(task_spec.hard_constraint_refs),
        "preference_refs": list(task_spec.preference_refs),
        "forbidden_effect_refs": list(task_spec.forbidden_effect_refs),
        "capability_ceiling": list(task_spec.capability_ceiling),
        "success": task_spec.success.model_dump(mode="json") if task_spec.success else None,
        "required_outputs": [item.model_dump(mode="json") for item in task_spec.required_outputs],
        "risk_policy": task_spec.risk_policy.model_dump(mode="json") if task_spec.risk_policy else None,
        "source_envelope_ref": task_spec.source_envelope_ref,
        "source_binding_digest": task_spec.source_binding_digest,
    }


def task_planning_context_summary(context: TaskPlanningContext) -> dict[str, object]:
    summary = context.model_dump(mode="json", exclude={"task_spec"})
    summary["task_spec"] = task_spec_planning_summary(context.task_spec)
    environment = summary.get("environment")
    if isinstance(environment, dict):
        parsed = urlsplit(str(environment.get("url") or ""))
        environment["url"] = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else parsed.scheme or ""
        )
    return summary
