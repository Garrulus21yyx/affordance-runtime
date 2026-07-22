"""Bounded, verifier-oriented task planning above the action planner.

Task plans describe outcomes only.  They never contain executable GUI details,
capabilities, or approvals; those remain exclusively at the proposal and
contract boundaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Awaitable, Protocol
from uuid import uuid4

from pydantic import Field

from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import (
    CriteriaEvidenceMatcher,
    SubgoalVerificationReport,
    criteria_from_descriptions,
    evidence_requirements_from_descriptions,
)
from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.task_intake import OperationClass, StrictModel, TaskSpec
from affordance_runtime.verification import VerificationReport


class TaskPlanSource(StrEnum):
    RULE = "rule"
    LLM = "llm"
    PARENT = "parent"
    SKILL = "skill"


class TaskPlanValidationStatus(StrEnum):
    ACCEPT = "accept"
    REPAIRABLE = "repairable"
    REJECT = "reject"


class SubgoalSpec(StrictModel):
    subgoal_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    operation_class: OperationClass
    max_actions: int = Field(default=10, ge=1, le=50)
    max_recoveries: int = Field(default=2, ge=0, le=10)


class TaskPlan(StrictModel):
    schema_version: str = "1.0"
    plan_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_revision: int = Field(ge=1)
    plan_version: int = Field(ge=1)
    based_on_state_version: int = Field(ge=0)
    generated_by: TaskPlanSource
    subgoals: tuple[SubgoalSpec, ...] = Field(min_length=1, max_length=8)
    assumptions: tuple[str, ...] = ()


class TaskPlanCandidate(StrictModel):
    """The model-controlled portion of a task plan, without authority fields."""

    subgoals: tuple[SubgoalSpec, ...] = Field(min_length=1, max_length=8)
    assumptions: tuple[str, ...] = ()


@dataclass
class PlanProgress:
    """Mutable execution progress, deliberately kept out of TaskPlan."""

    active_subgoal_id: str = ""
    completed_subgoal_ids: list[str] = field(default_factory=list)
    failed_subgoal_ids: list[str] = field(default_factory=list)
    evidence_by_subgoal: dict[str, list[str]] = field(default_factory=dict)
    action_count_by_subgoal: dict[str, int] = field(default_factory=dict)
    task_replan_count: int = 0

    def ready_subgoal_ids(self, plan: TaskPlan) -> tuple[str, ...]:
        completed = set(self.completed_subgoal_ids)
        unavailable = completed | set(self.failed_subgoal_ids)
        return tuple(
            subgoal.subgoal_id
            for subgoal in plan.subgoals
            if subgoal.subgoal_id not in unavailable and all(item in completed for item in subgoal.depends_on)
        )

    def activate_next(self, plan: TaskPlan) -> str:
        if self.active_subgoal_id:
            return self.active_subgoal_id
        ready = self.ready_subgoal_ids(plan)
        self.active_subgoal_id = ready[0] if ready else ""
        return self.active_subgoal_id

    def complete(self, subgoal_id: str, evidence: tuple[str, ...]) -> None:
        if subgoal_id not in self.completed_subgoal_ids:
            self.completed_subgoal_ids.append(subgoal_id)
        self.evidence_by_subgoal[subgoal_id] = list(dict.fromkeys(evidence))
        if self.active_subgoal_id == subgoal_id:
            self.active_subgoal_id = ""

    def record_action(self, subgoal_id: str) -> None:
        self.action_count_by_subgoal[subgoal_id] = self.action_count_by_subgoal.get(subgoal_id, 0) + 1

    def action_budget_exhausted(self, plan: TaskPlan) -> bool:
        active_id = self.active_subgoal_id
        subgoal = next((item for item in plan.subgoals if item.subgoal_id == active_id), None)
        return subgoal is not None and self.action_count_by_subgoal.get(active_id, 0) >= subgoal.max_actions


class TaskPlanValidationIssue(StrictModel):
    code: str = Field(min_length=1)
    detail: str = ""


class TaskPlanValidationReport(StrictModel):
    status: TaskPlanValidationStatus
    issues: tuple[TaskPlanValidationIssue, ...] = ()


@dataclass(frozen=True)
class TaskPlanValidator:
    max_subgoals: int = 8
    max_actions_per_subgoal: int = 50
    max_recoveries_per_subgoal: int = 10

    def validate(self, plan: TaskPlan, task_spec: TaskSpec, *, state_version: int) -> TaskPlanValidationReport:
        fatal: list[TaskPlanValidationIssue] = []
        repairable: list[TaskPlanValidationIssue] = []
        if plan.task_id != task_spec.task_id:
            fatal.append(TaskPlanValidationIssue(code="task_id_mismatch"))
        if plan.task_revision != task_spec.revision:
            fatal.append(TaskPlanValidationIssue(code="task_revision_mismatch"))
        if plan.based_on_state_version != state_version:
            fatal.append(TaskPlanValidationIssue(code="state_version_mismatch"))
        if not 1 <= len(plan.subgoals) <= self.max_subgoals:
            fatal.append(TaskPlanValidationIssue(code="subgoal_count_out_of_bounds"))

        identifiers = [item.subgoal_id for item in plan.subgoals]
        if len(identifiers) != len(set(identifiers)):
            fatal.append(TaskPlanValidationIssue(code="duplicate_subgoal_id"))
        known = set(identifiers)
        for subgoal in plan.subgoals:
            if not subgoal.success_criteria:
                repairable.append(TaskPlanValidationIssue(code="missing_success_criteria", detail=subgoal.subgoal_id))
            if not subgoal.evidence_requirements:
                repairable.append(
                    TaskPlanValidationIssue(code="missing_evidence_requirements", detail=subgoal.subgoal_id)
                )
            if subgoal.max_actions > self.max_actions_per_subgoal:
                fatal.append(TaskPlanValidationIssue(code="action_budget_out_of_bounds", detail=subgoal.subgoal_id))
            if subgoal.max_recoveries > self.max_recoveries_per_subgoal:
                fatal.append(TaskPlanValidationIssue(code="recovery_budget_out_of_bounds", detail=subgoal.subgoal_id))
            if _operation_rank(subgoal.operation_class) > _operation_rank(task_spec.operation_class):
                fatal.append(TaskPlanValidationIssue(code="operation_class_escalation", detail=subgoal.subgoal_id))
            for dependency in subgoal.depends_on:
                if dependency == subgoal.subgoal_id:
                    fatal.append(TaskPlanValidationIssue(code="self_dependency", detail=subgoal.subgoal_id))
                elif dependency not in known:
                    fatal.append(TaskPlanValidationIssue(code="unknown_dependency", detail=dependency))
        if _has_cycle(plan.subgoals):
            fatal.append(TaskPlanValidationIssue(code="dependency_cycle"))
        dependency_targets = {dependency for item in plan.subgoals for dependency in item.depends_on}
        if not any(item.subgoal_id not in dependency_targets for item in plan.subgoals):
            fatal.append(TaskPlanValidationIssue(code="missing_terminal_subgoal"))

        if fatal:
            return TaskPlanValidationReport(status=TaskPlanValidationStatus.REJECT, issues=tuple(fatal + repairable))
        if repairable:
            return TaskPlanValidationReport(status=TaskPlanValidationStatus.REPAIRABLE, issues=tuple(repairable))
        return TaskPlanValidationReport(status=TaskPlanValidationStatus.ACCEPT)


class TaskPlannerPort(Protocol):
    def plan(self, task_spec: TaskSpec, *, state_version: int) -> TaskPlan | Awaitable[TaskPlan]: ...


class SubgoalVerifierPort(Protocol):
    def verify(
        self,
        subgoal: SubgoalSpec,
        report: VerificationReport,
        observation: Observation,
    ) -> SubgoalVerificationReport: ...


@dataclass(frozen=True)
class VerifierBackedSubgoalVerifier:
    """Bind fresh independent evidence to the active subgoal's obligations."""

    matcher: CriteriaEvidenceMatcher = CriteriaEvidenceMatcher()

    def verify(
        self,
        subgoal: SubgoalSpec,
        report: VerificationReport,
        observation: Observation,
    ) -> SubgoalVerificationReport:
        match = self.matcher.match(
            criteria=criteria_from_descriptions("subgoal", subgoal.subgoal_id, subgoal.success_criteria),
            requirements=evidence_requirements_from_descriptions(
                "subgoal", subgoal.subgoal_id, subgoal.evidence_requirements
            ),
            verification=report,
            observation=observation,
        )
        return SubgoalVerificationReport(subgoal.subgoal_id, match)


@dataclass(frozen=True)
class RuleTaskPlanner:
    """Creates a deterministic flat plan for a directly verifiable task."""

    def plan(self, task_spec: TaskSpec, *, state_version: int) -> TaskPlan:
        return synthetic_task_plan(task_spec, state_version=state_version, generated_by=TaskPlanSource.RULE)


TASK_PLANNER_PROMPT_VERSION = "task-planner-v1"
_TASK_PLANNER_SYSTEM_PROMPT = """You are a bounded task planner. Return only a TaskPlanCandidate.
Decompose only open-world, multi-stage, cross-application, or data-dependent work into 3-8 outcome-oriented subgoals. Each subgoal needs verifiable success criteria and independent evidence requirements. Preserve the supplied TaskSpec constraints and operation class; do not invent destructive scope, recipients, credentials, payment, approval, or authority.
Subgoals are desired environment states, never UI scripts. Do not output selectors, coordinates, backend handles, executable code, capabilities, approval tokens, or action instructions. Dependencies express a small serial-ready partial order. The runtime executes one ready subgoal at a time and independently verifies progress."""


@dataclass
class LLMTaskPlanner:
    """Model-backed task decomposition with exactly one repairable retry."""

    model: ModelPort
    validator: TaskPlanValidator = field(default_factory=TaskPlanValidator)
    config: ModelConfig = field(
        default_factory=lambda: ModelConfig(
            temperature=0.0,
            max_tokens=1_024,
            prompt_version=TASK_PLANNER_PROMPT_VERSION,
        )
    )

    async def plan(self, task_spec: TaskSpec, *, state_version: int) -> TaskPlan:
        context = {
            "task_spec": task_spec.model_dump(mode="json"),
            "state_version": state_version,
            "constraints": list(task_spec.constraints),
            "forbidden_effects": list(task_spec.forbidden_effects),
        }
        messages = [
            ModelMessage(role="system", content=_TASK_PLANNER_SYSTEM_PROMPT),
            ModelMessage(role="user", content=json.dumps(context, sort_keys=True)),
        ]
        candidate = await self.model.generate_structured(messages, TaskPlanCandidate, self.config)
        plan = self._bind_candidate(candidate, task_spec, state_version=state_version)
        report = self.validator.validate(plan, task_spec, state_version=state_version)
        if report.status != TaskPlanValidationStatus.REPAIRABLE:
            return plan
        repair_context = {
            "validation_errors": [item.model_dump(mode="json") for item in report.issues],
            "instruction": "Repair only the reported plan fields; retain outcome-only semantics and constraints.",
        }
        repaired = await self.model.generate_structured(
            [
                *messages,
                ModelMessage(role="assistant", content=candidate.model_dump_json()),
                ModelMessage(role="user", content=json.dumps(repair_context, sort_keys=True)),
            ],
            TaskPlanCandidate,
            self.config,
        )
        return self._bind_candidate(repaired, task_spec, state_version=state_version)

    @staticmethod
    def _bind_candidate(candidate: TaskPlanCandidate, task_spec: TaskSpec, *, state_version: int) -> TaskPlan:
        return TaskPlan(
            plan_id=f"plan-{uuid4().hex}",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=1,
            based_on_state_version=state_version,
            generated_by=TaskPlanSource.LLM,
            subgoals=candidate.subgoals,
            assumptions=candidate.assumptions,
        )


@dataclass(frozen=True)
class PlanningRouter:
    """Routes simple work to the flat path and delegates complex work explicitly."""

    rule_planner: TaskPlannerPort = field(default_factory=RuleTaskPlanner)
    complex_planner: TaskPlannerPort | None = None

    def plan(
        self, task_spec: TaskSpec, *, state_version: int, complex_task: bool = False
    ) -> TaskPlan | Awaitable[TaskPlan]:
        if not complex_task:
            return self.rule_planner.plan(task_spec, state_version=state_version)
        if self.complex_planner is None:
            raise ValueError("complex task requires an LLMTaskPlanner or accepted task planner")
        return self.complex_planner.plan(task_spec, state_version=state_version)


def synthetic_task_plan(
    task_spec: TaskSpec,
    *,
    state_version: int,
    generated_by: TaskPlanSource = TaskPlanSource.RULE,
) -> TaskPlan:
    """Preserve the existing flat action loop as one verifier-backed subgoal."""

    return TaskPlan(
        plan_id=f"plan-{uuid4().hex}",
        task_id=task_spec.task_id,
        task_revision=task_spec.revision,
        plan_version=1,
        based_on_state_version=state_version,
        generated_by=generated_by,
        subgoals=(
            SubgoalSpec(
                subgoal_id="subgoal-1",
                objective=task_spec.objective,
                success_criteria=task_spec.success_criteria,
                evidence_requirements=task_spec.evidence_requirements or task_spec.success_criteria,
                operation_class=task_spec.operation_class,
            ),
        ),
        assumptions=(),
    )


def _has_cycle(subgoals: tuple[SubgoalSpec, ...]) -> bool:
    dependencies = {item.subgoal_id: set(item.depends_on) for item in subgoals}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        cyclic = any(visit(dependency) for dependency in dependencies[node] if dependency in dependencies)
        visiting.remove(node)
        visited.add(node)
        return cyclic

    return any(visit(identifier) for identifier in dependencies)


def _operation_rank(operation: OperationClass) -> int:
    return {
        OperationClass.READ_ONLY: 0,
        OperationClass.NAVIGATION: 1,
        OperationClass.REVERSIBLE_WRITE: 2,
        OperationClass.EXTERNAL_SIDE_EFFECT: 3,
        OperationClass.IRREVERSIBLE: 4,
    }[operation]
