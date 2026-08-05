"""Observation-grounded, authority-free TaskPlan proposal policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Protocol
from urllib.parse import urlsplit

from pydantic import Field

from affordance_runtime.task_intake import StrictModel, TaskSpec, TaskStructure
from affordance_runtime.task_plan_contracts import PlanCandidate


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


def task_spec_planning_summary(task_spec: TaskSpec) -> dict[str, object]:
    requested_effects = [item.model_dump(mode="json") for item in task_spec.requested_effects]
    for item in requested_effects:
        item.pop("source_ref", None)
    entities = [item.model_dump(mode="json") for item in task_spec.entities]
    for item in entities:
        item.pop("source_ref", None)
    return {
        "schema_version": task_spec.schema_version,
        "revision": task_spec.revision,
        "objective": task_spec.objective,
        "operation_class": task_spec.operation_class.value,
        "task_structure": task_spec.task_structure.value,
        "targets": list(task_spec.targets),
        "requested_effects": requested_effects,
        "entities": entities,
        "preferences": list(task_spec.preferences),
        "desired_outputs": list(task_spec.desired_outputs),
        "success_criteria": list(task_spec.success_criteria),
        "constraints": list(task_spec.constraints),
        "forbidden_effects": list(task_spec.forbidden_effects),
        "evidence_requirements": list(task_spec.evidence_requirements),
        "requested_capabilities": list(task_spec.requested_capabilities),
        "ambiguity_status": task_spec.ambiguity_status,
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
