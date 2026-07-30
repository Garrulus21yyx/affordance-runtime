"""Neutral TaskPlan authority contracts.

TPA-4/SAR-3 foundation. This module defines candidate, request, decision, issue,
and generator contracts for a future TaskPlanAuthority owner. It does not connect
those contracts to runtime plan admission or Coordinator commit paths.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, is_dataclass
from enum import StrEnum
from typing import Awaitable, Protocol

from affordance_runtime.simplified_runtime_contracts import (
    SourceReference,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import SubgoalSpec, TaskPlan, TaskPlanSource

_FORBIDDEN_IMPLEMENTATION_DETAIL = re.compile(
    r"(?:\bselector\b|\bxpath\b|\bbackend\b|\bcoordinate\b|\blocator\b|#[-_\w]+|approval_token)",
    re.IGNORECASE,
)


class TaskPlanGeneratorSource(StrEnum):
    RULE = "rule"
    LLM = "llm"
    PARENT = "parent"
    SKILL = "skill"


class PlanIssueKind(StrEnum):
    STEP_UNEXECUTABLE = "step_unexecutable"
    ACTION_BUDGET_EXHAUSTED = "action_budget_exhausted"
    CRITERION_UNVERIFIABLE = "criterion_unverifiable"
    PLAN_ASSUMPTION_INVALID = "plan_assumption_invalid"
    TASK_REQUIREMENTS_CHANGED = "task_requirements_changed"


class TaskPlanDecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REPAIR_REQUIRED = "repair_required"
    CLARIFICATION_REQUIRED = "clarification_required"
    NO_PLAN_REQUIRED = "no_plan_required"


@dataclass(frozen=True)
class PlanCandidate:
    task_spec_identity: str
    task_revision: int
    generated_by: TaskPlanGeneratorSource
    generator_id: str
    steps: tuple[StepSpec, ...]
    generator_version: str = ""
    assumptions: tuple[str, ...] = ()
    source_refs: tuple[SourceReference, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("task_spec_identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if not isinstance(self.generated_by, TaskPlanGeneratorSource):
            raise ValueError("unsupported generator source")
        _require_nonblank("generator_id", self.generator_id)
        if self.generator_version:
            _require_nonblank("generator_version", self.generator_version)
        _require_tuple("steps", self.steps)
        if not self.steps:
            raise ValueError("draft steps cannot be empty")
        _require_tuple("assumptions", self.assumptions)
        _require_tuple("source_refs", self.source_refs)
        if not self.source_refs:
            raise ValueError("draft source refs cannot be empty")
        _reject_forbidden_text((*self.assumptions,))
        _validate_draft_step_graph(self.steps)


@dataclass(frozen=True)
class InitialTaskPlanRequest:
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    objective: str
    observation_refs: tuple[str, ...]
    remaining_budget_steps: int

    def __post_init__(self) -> None:
        _validate_request_identity(
            self.task_spec_identity,
            self.task_revision,
            self.evaluated_at_state_version,
        )
        _require_nonblank("objective", self.objective)
        _require_unique_nonblank("observation refs", self.observation_refs)
        if self.remaining_budget_steps < 0:
            raise ValueError("remaining budget cannot be negative")


@dataclass(frozen=True)
class TaskPlanRevisionTrigger:
    kind: str
    reason_code: str
    evidence_refs: tuple[str, ...] = ()
    affected_step_id: str = ""

    def __post_init__(self) -> None:
        allowed = {item.value for item in PlanIssueKind}
        if self.kind not in allowed:
            raise ValueError("unsupported revision trigger")
        _require_nonblank("reason_code", self.reason_code)
        _require_tuple("evidence_refs", self.evidence_refs)
        _require_unique_nonblank("evidence refs", self.evidence_refs)
        if self.affected_step_id:
            _require_nonblank("affected_step_id", self.affected_step_id)


@dataclass(frozen=True)
class TaskPlanRevisionRequest:
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    previous_plan: TaskPlanView
    previous_progress: StepProgressView
    trigger: TaskPlanRevisionTrigger
    observation_refs: tuple[str, ...]
    remaining_budget_steps: int

    def __post_init__(self) -> None:
        _validate_request_identity(
            self.task_spec_identity,
            self.task_revision,
            self.evaluated_at_state_version,
        )
        if self.previous_plan.task_spec_identity != self.task_spec_identity:
            raise ValueError("previous plan task identity mismatch")
        if self.previous_plan.task_revision != self.task_revision:
            raise ValueError("previous plan task revision mismatch")
        if self.previous_progress.plan_id != self.previous_plan.plan_id:
            raise ValueError("previous progress plan identity mismatch")
        if self.previous_progress.plan_version != self.previous_plan.plan_version:
            raise ValueError("previous progress plan version mismatch")
        if self.trigger.affected_step_id and self.trigger.affected_step_id not in self.previous_plan.step_ids:
            raise ValueError("affected step must exist in previous plan")
        _require_unique_nonblank("observation refs", self.observation_refs)
        if self.remaining_budget_steps < 0:
            raise ValueError("remaining budget cannot be negative")


@dataclass(frozen=True)
class PlanIssueReport:
    plan_id: str
    plan_version: int
    step_id: str
    kind: PlanIssueKind
    reason_code: str
    evidence_refs: tuple[str, ...]
    observed_at_state_version: int

    def __post_init__(self) -> None:
        _require_nonblank("plan_id", self.plan_id)
        if self.plan_version < 1:
            raise ValueError("plan version must be positive")
        _require_nonblank("step_id", self.step_id)
        if not isinstance(self.kind, PlanIssueKind):
            raise ValueError("unsupported plan issue kind")
        _require_nonblank("reason_code", self.reason_code)
        _require_unique_nonblank("evidence refs", self.evidence_refs)
        if self.observed_at_state_version < 0:
            raise ValueError("observed state version cannot be negative")


@dataclass(frozen=True)
class TaskPlanIssue:
    code: str
    message: str
    fatal: bool = True

    def __post_init__(self) -> None:
        _require_nonblank("code", self.code)
        _require_nonblank("message", self.message)


@dataclass(frozen=True)
class TaskPlanRepairDirective:
    reason_code: str
    instruction: str

    def __post_init__(self) -> None:
        _require_nonblank("reason_code", self.reason_code)
        _require_nonblank("instruction", self.instruction)


@dataclass(frozen=True)
class TaskPlanDecision:
    status: TaskPlanDecisionStatus
    plan: TaskPlan | None = None
    plan_digest: str = ""
    issues: tuple[TaskPlanIssue, ...] = ()
    repair_directives: tuple[TaskPlanRepairDirective, ...] = ()
    clarification_question: str = ""

    @classmethod
    def accepted(cls, plan: TaskPlan) -> TaskPlanDecision:
        return cls(
            status=TaskPlanDecisionStatus.ACCEPTED,
            plan=plan,
            plan_digest=_digest(plan),
        )

    @classmethod
    def repair_required(cls, *directives: TaskPlanRepairDirective) -> TaskPlanDecision:
        return cls(
            status=TaskPlanDecisionStatus.REPAIR_REQUIRED,
            repair_directives=directives,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskPlanDecisionStatus):
            raise ValueError("unsupported task plan decision status")
        _require_tuple("issues", self.issues)
        _require_tuple("repair_directives", self.repair_directives)
        if self.status == TaskPlanDecisionStatus.ACCEPTED:
            if self.plan is None:
                raise ValueError("accepted decision requires plan")
            _require_nonblank("plan_digest", self.plan_digest)
            if self.issues or self.repair_directives or self.clarification_question:
                raise ValueError("accepted decision cannot carry issues or repair directives")
            return
        if self.plan is not None:
            raise ValueError(f"{self.status.value} decision cannot carry plan")
        if self.plan_digest:
            raise ValueError(f"{self.status.value} decision cannot carry plan digest")
        if self.status == TaskPlanDecisionStatus.REJECTED and not self.issues:
            raise ValueError("rejected decision requires issue")
        if self.status == TaskPlanDecisionStatus.REPAIR_REQUIRED and not self.repair_directives:
            raise ValueError("repair decision requires directives")
        if self.status == TaskPlanDecisionStatus.CLARIFICATION_REQUIRED:
            if not self.clarification_question.strip():
                raise ValueError("clarification decision requires question")


@dataclass(frozen=True)
class TaskPlanAuthorityBinder:
    def bind_initial(self, request: InitialTaskPlanRequest, draft: PlanCandidate) -> TaskPlan:
        _validate_draft_matches_request(request, draft)
        digest = _digest(draft)
        return _bind_task_plan(
            request=request,
            draft=draft,
            plan_id=_plan_id(
                request.task_spec_identity,
                request.task_revision,
                request.evaluated_at_state_version,
                "",
                0,
                digest,
            ),
            plan_version=1,
            supersedes_plan_id="",
        )

    def bind_revision(self, request: TaskPlanRevisionRequest, draft: PlanCandidate) -> TaskPlan:
        _validate_draft_matches_request(request, draft)
        digest = _digest(draft)
        return _bind_task_plan(
            request=request,
            draft=draft,
            plan_id=_plan_id(
                request.task_spec_identity,
                request.task_revision,
                request.evaluated_at_state_version,
                request.previous_plan.plan_id,
                request.previous_plan.plan_version,
                digest,
            ),
            plan_version=request.previous_plan.plan_version + 1,
            supersedes_plan_id=request.previous_plan.plan_id,
        )


class TaskPlanGeneratorPort(Protocol):
    def generate(
        self,
        request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
    ) -> PlanCandidate | Awaitable[PlanCandidate]: ...


TaskPlanDraft = PlanCandidate


def _bind_task_plan(
    *,
    request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
    draft: PlanCandidate,
    plan_id: str,
    plan_version: int,
    supersedes_plan_id: str,
) -> TaskPlan:
    return TaskPlan(
        plan_id=plan_id,
        task_id=draft.task_spec_identity,
        task_revision=draft.task_revision,
        plan_version=plan_version,
        supersedes_plan_id=supersedes_plan_id,
        based_on_state_version=request.evaluated_at_state_version,
        generated_by=TaskPlanSource(draft.generated_by.value),
        subgoals=tuple(_subgoal_from_step(step) for step in draft.steps),
        assumptions=draft.assumptions,
    )


def _subgoal_from_step(step: StepSpec) -> SubgoalSpec:
    return SubgoalSpec(
        subgoal_id=step.step_id,
        objective=step.objective,
        depends_on=step.depends_on,
        success_criteria=tuple(criterion.criterion_id for criterion in step.completion_criteria),
        evidence_requirements=tuple(ref.source_unit_id for ref in step.source_refs),
        operation_class=OperationClass.READ_ONLY,
    )


def _validate_draft_matches_request(
    request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
    draft: PlanCandidate,
) -> None:
    if draft.task_spec_identity != request.task_spec_identity:
        raise ValueError("draft task identity mismatch")
    if draft.task_revision != request.task_revision:
        raise ValueError("draft task revision mismatch")


def _plan_id(
    task_spec_identity: str,
    task_revision: int,
    state_version: int,
    previous_plan_id: str,
    previous_plan_version: int,
    draft_digest: str,
) -> str:
    return f"plan:{_digest((task_spec_identity, task_revision, state_version, previous_plan_id, previous_plan_version, draft_digest))[:24]}"


def _digest(value: object) -> str:
    encoded = json.dumps(_stable_value(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _stable_value(item) for key, item in vars(value).items()}
    if hasattr(value, "model_dump"):
        return _stable_value(value.model_dump(mode="json"))  # type: ignore[attr-defined]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _stable_value(item) for key, item in value.items()}
    return value


def _validate_request_identity(task_spec_identity: str, task_revision: int, state_version: int) -> None:
    _require_nonblank("task_spec_identity", task_spec_identity)
    if task_revision < 1:
        raise ValueError("task revision must be positive")
    if state_version < 0:
        raise ValueError("state version cannot be negative")


def _validate_draft_step_graph(steps: tuple[StepSpec, ...]) -> None:
    step_ids = tuple(step.step_id for step in steps)
    _require_unique_nonblank("step ids", step_ids)
    known = set(step_ids)
    for step in steps:
        unknown = set(step.depends_on) - known
        if unknown:
            raise ValueError("unknown draft step dependency")
    _reject_cycles(steps)


def _reject_cycles(steps: tuple[StepSpec, ...]) -> None:
    dependencies = {step.step_id: set(step.depends_on) for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("draft step dependency cycle")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in dependencies[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in dependencies:
        visit(step_id)


def _reject_forbidden_text(values: tuple[str, ...]) -> None:
    for value in values:
        _require_nonblank("assumption", value)
        if _FORBIDDEN_IMPLEMENTATION_DETAIL.search(value):
            raise ValueError("forbidden implementation detail in task plan draft")


def _require_nonblank(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be blank")


def _require_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def _require_no_blank_values(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot contain blank values")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    _require_tuple(label, values)
    _require_no_blank_values(label, values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
