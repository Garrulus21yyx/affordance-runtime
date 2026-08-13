"""Canonical TaskPlan contracts and admission authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass
from enum import StrEnum
from typing import Any, Awaitable, Protocol

from affordance_runtime.simplified_runtime_contracts import (
    RelationIntent,
    SourceReference,
    StateCriterionRelation,
    StepActivityStatus,
    StepProgressView,
    StepSpec,
    TaskPlanView,
    interaction_for_state,
)
from affordance_runtime.task_intake import OperationClass, StrictModel, TaskSpec

_FORBIDDEN_IMPLEMENTATION_DETAIL = re.compile(
    r"(?:\bselector\b|\bxpath\b|\bbackend\b|\bcoordinate\b|\blocator\b|#[-_\w]+|approval_token)",
    re.IGNORECASE,
)


class TaskPlanGeneratorSource(StrEnum):
    RULE = "rule"
    LLM = "llm"
    PARENT = "parent"
    SKILL = "skill"


@dataclass(frozen=True)
class TaskRequirementProjection:
    requirement_id: str
    kind: str
    subject: str
    target_identity: str = ""
    destination_identity: str = ""
    relation: str = ""
    value: str = ""
    operation_class: str = ""
    material_effect_kind: str = "none"
    capability: str = ""
    input_bindings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("requirement_id", self.requirement_id)
        _require_nonblank("kind", self.kind)
        _require_nonblank("subject", self.subject)


def project_task_requirements(task_spec: TaskSpec) -> tuple[TaskRequirementProjection, ...]:
    return tuple(
        TaskRequirementProjection(
            requirement_id=requirement.requirement_id,
            kind=requirement.payload.kind,
            subject=requirement.payload.subject,
            target_identity=requirement.payload.target_identity,
            destination_identity=requirement.payload.destination_identity,
            relation=requirement.payload.relation,
            value=requirement.payload.value,
            operation_class=(
                requirement.payload.operation_class.value
                if requirement.payload.operation_class is not None
                else ""
            ),
            material_effect_kind=requirement.payload.material_effect_kind.value,
            capability=requirement.payload.capability,
            input_bindings=tuple(
                (binding.field, binding.value)
                for binding in task_spec.inputs
                if binding.requirement_ref == requirement.requirement_id
            ),
        )
        for requirement in task_spec.requirements
    )


class TaskPlan(StrictModel):
    """One admitted, observation-bound execution hypothesis."""

    schema_version: str = "2.0"
    plan_id: str
    task_id: str
    task_revision: int
    plan_version: int
    supersedes_plan_id: str = ""
    based_on_state_version: int
    based_on_observation_ref: str
    generated_by: TaskPlanGeneratorSource
    steps: tuple[StepSpec, ...]
    assumptions: tuple[str, ...] = ()

    def model_post_init(self, __context: object) -> None:
        del __context
        _validate_step_execution_algebra(self.steps)

    def step(self, step_id: str) -> StepSpec | None:
        return next((item for item in self.steps if item.step_id == step_id), None)

def project_task_plan_views(
    plan: TaskPlan,
    *,
    task_spec_identity: str,
    task_revision: int,
    progress: Any,
) -> tuple[TaskPlanView, StepProgressView]:
    completed = tuple(progress.completed_step_ids)
    failed = tuple(progress.failed_step_ids)
    active = progress.active_step_id or None
    ready = tuple(progress.ready_step_ids(plan)) if active is None else ()
    status = (
        StepActivityStatus.ACTIVE
        if active is not None
        else StepActivityStatus.READY_NOT_ACTIVATED
        if ready
        else StepActivityStatus.COMPLETED
        if set(completed) == {step.step_id for step in plan.steps}
        else StepActivityStatus.NO_PLAN
    )
    return (
        TaskPlanView(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            task_spec_identity=task_spec_identity,
            task_revision=task_revision,
            steps=plan.steps,
            active_step_id=active,
        ),
        StepProgressView(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            active_step_id=active,
            activity_status=status,
            completed_step_ids=completed,
            failed_step_ids=failed,
            ready_step_ids=ready,
            evidence_by_step_id=tuple((step_id, tuple(progress.evidence_for_step(step_id))) for step_id in completed),
        ),
    )


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
class PlanProposal:
    task_spec_identity: str
    task_revision: int
    generated_by: TaskPlanGeneratorSource
    generator_id: str
    steps: tuple[StepSpec, ...]
    based_on_observation_ref: str = ""
    based_on_state_version: int = -1
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
        _validate_step_execution_algebra(self.steps)
        if self.based_on_observation_ref:
            _require_nonblank("based_on_observation_ref", self.based_on_observation_ref)
        if self.based_on_state_version < -1:
            raise ValueError("candidate state version cannot be less than -1")


@dataclass(frozen=True)
class InitialTaskPlanRequest:
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    objective: str
    observation_refs: tuple[str, ...]
    remaining_budget_steps: int
    allowed_requirement_ids: tuple[str, ...]
    allowed_effect_ids: tuple[str, ...] = ()
    operation_class: OperationClass = OperationClass.READ_ONLY
    task_id: str = ""
    requirement_projections: tuple[TaskRequirementProjection, ...] = ()

    def __post_init__(self) -> None:
        _validate_request_identity(
            self.task_spec_identity,
            self.task_revision,
            self.evaluated_at_state_version,
        )
        if self.task_id:
            _require_nonblank("task_id", self.task_id)
        _require_nonblank("objective", self.objective)
        if not isinstance(self.operation_class, OperationClass):
            raise ValueError("unsupported operation class")
        _require_unique_nonblank("observation refs", self.observation_refs)
        _require_unique_nonblank("allowed requirement ids", self.allowed_requirement_ids)
        if not self.allowed_requirement_ids:
            raise ValueError("task planning request requires admitted requirements")
        if not self.requirement_projections:
            raise ValueError("task planning request requires typed requirement projections")
        _validate_requirement_projections(self.allowed_requirement_ids, self.requirement_projections)
        _require_unique_nonblank("allowed effect ids", self.allowed_effect_ids)
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
    allowed_requirement_ids: tuple[str, ...]
    allowed_effect_ids: tuple[str, ...] = ()
    operation_class: OperationClass = OperationClass.READ_ONLY
    task_id: str = ""
    requirement_projections: tuple[TaskRequirementProjection, ...] = ()

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
        if not self.requirement_projections:
            raise ValueError("task plan revision requires typed requirement projections")
        _validate_requirement_projections(self.allowed_requirement_ids, self.requirement_projections)
        if self.trigger.affected_step_id and self.trigger.affected_step_id not in self.previous_plan.step_ids:
            raise ValueError("affected step must exist in previous plan")
        if not isinstance(self.operation_class, OperationClass):
            raise ValueError("unsupported operation class")
        if self.task_id:
            _require_nonblank("task_id", self.task_id)
        _require_unique_nonblank("observation refs", self.observation_refs)
        _require_unique_nonblank("allowed requirement ids", self.allowed_requirement_ids)
        if not self.allowed_requirement_ids:
            raise ValueError("task planning request requires admitted requirements")
        _require_unique_nonblank("allowed effect ids", self.allowed_effect_ids)
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

    @classmethod
    def rejected(cls, *issues: TaskPlanIssue) -> TaskPlanDecision:
        return cls(status=TaskPlanDecisionStatus.REJECTED, issues=issues)

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
class TaskPlanAuthority:
    def admit_initial(
        self,
        request: InitialTaskPlanRequest,
        candidate: PlanProposal,
    ) -> TaskPlanDecision:
        issues = self._validate(request, candidate)
        if issues:
            return TaskPlanDecision.rejected(*issues)
        return TaskPlanDecision.accepted(
            _bind_task_plan(
                request=request,
                draft=candidate,
                plan_id=_plan_id(
                    request.task_spec_identity,
                    request.task_revision,
                    request.evaluated_at_state_version,
                    "",
                    0,
                    _digest(candidate),
                ),
                plan_version=1,
                supersedes_plan_id="",
            )
        )

    def admit_revision(
        self,
        request: TaskPlanRevisionRequest,
        candidate: PlanProposal,
    ) -> TaskPlanDecision:
        issues = self._validate(request, candidate)
        if issues:
            return TaskPlanDecision.rejected(*issues)
        return TaskPlanDecision.accepted(
            _bind_task_plan(
                request=request,
                draft=candidate,
                plan_id=_plan_id(
                    request.task_spec_identity,
                    request.task_revision,
                    request.evaluated_at_state_version,
                    request.previous_plan.plan_id,
                    request.previous_plan.plan_version,
                    _digest(candidate),
                ),
                plan_version=request.previous_plan.plan_version + 1,
                supersedes_plan_id=request.previous_plan.plan_id,
            )
        )

    @staticmethod
    def _validate(
        request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
        candidate: PlanProposal,
    ) -> tuple[TaskPlanIssue, ...]:
        issues: list[TaskPlanIssue] = []
        if candidate.task_spec_identity != request.task_spec_identity:
            issues.append(TaskPlanIssue("task_identity_mismatch", "candidate task identity is stale"))
        if candidate.task_revision != request.task_revision:
            issues.append(TaskPlanIssue("task_revision_mismatch", "candidate task revision is stale"))
        current_observation_ref = request.observation_refs[0]
        if candidate.based_on_observation_ref != current_observation_ref:
            issues.append(TaskPlanIssue("observation_basis_stale", "candidate observation basis is not current"))
        if candidate.based_on_state_version != request.evaluated_at_state_version:
            issues.append(TaskPlanIssue("state_basis_stale", "candidate state basis is not current"))
        if len(candidate.steps) > request.remaining_budget_steps:
            issues.append(TaskPlanIssue("step_budget_exceeded", "candidate exceeds remaining step budget"))
        allowed_requirements = set(request.allowed_requirement_ids)
        allowed_effects = set(request.allowed_effect_ids)
        completed_step_ids = (
            set(request.previous_progress.completed_step_ids) if isinstance(request, TaskPlanRevisionRequest) else set()
        )
        for step in candidate.steps:
            if step.step_id in completed_step_ids:
                issues.append(
                    TaskPlanIssue(
                        "completed_step_reinserted",
                        f"replacement reinserted completed step {step.step_id}",
                    )
                )
            if set(step.requirement_refs) - allowed_requirements:
                issues.append(
                    TaskPlanIssue(
                        "requirement_trace_invalid",
                        f"step {step.step_id} is not traceable to admitted requirements",
                    )
                )
            invalid_effect_authorization = step.effectful and (
                not step.effect_authorization_refs or bool(set(step.effect_authorization_refs) - allowed_effects)
            )
            if invalid_effect_authorization:
                issues.append(
                    TaskPlanIssue(
                        "effect_authorization_invalid",
                        f"step {step.step_id} lacks admitted effect authorization",
                    )
                )
            if not invalid_effect_authorization and set(step.effect_authorization_refs) - set(step.requirement_refs):
                issues.append(
                    TaskPlanIssue(
                        "effect_authorization_trace_invalid",
                        f"step {step.step_id} effect authorization is not part of its requirement trace",
                    )
                )
            semantic_issue = _semantic_step_issue(step, request)
            if semantic_issue is not None:
                issues.append(semantic_issue)
        return tuple(issues)


def _semantic_step_issue(
    step: StepSpec,
    request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
) -> TaskPlanIssue | None:
    if not request.requirement_projections:
        return (
            TaskPlanIssue(
                "requirement_projection_missing",
                f"effectful step {step.step_id} lacks typed requirement semantics",
            )
            if step.effectful
            else None
        )
    projections = {
        item.requirement_id: item
        for item in request.requirement_projections
        if item.requirement_id in step.requirement_refs
    }
    if set(step.requirement_refs) - set(projections):
        return TaskPlanIssue("requirement_projection_missing", f"step {step.step_id} lacks typed requirement semantics")
    if not projections:
        return (
            TaskPlanIssue("requirement_projection_missing", f"step {step.step_id} lacks typed requirement semantics")
            if step.effectful
            else None
        )
    effect_requirements = tuple(item for item in projections.values() if item.kind == "effect")
    if step.effectful and not effect_requirements:
        return TaskPlanIssue("semantic_effect_laundering", f"step {step.step_id} wraps non-effect authority")
    if step.effectful and all(
        item.operation_class in {"", OperationClass.READ_ONLY.value, OperationClass.NAVIGATION.value}
        for item in effect_requirements
    ):
        return TaskPlanIssue("semantic_operation_exceeds_requirement", f"step {step.step_id} exceeds read authority")
    if step.operation_class:
        allowed_operations = {item.operation_class for item in effect_requirements if item.operation_class}
        if allowed_operations and step.operation_class not in allowed_operations:
            return TaskPlanIssue("semantic_operation_mismatch", f"step {step.step_id} operation is not subsumed")
    targets, destinations, roles = _interaction_semantics(step)
    allowed_targets = {
        value.casefold()
        for item in projections.values()
        for value in _authorized_target_names(item)
        if value.strip()
    }
    if targets and allowed_targets and not all(value.casefold() in allowed_targets for value in targets):
        return TaskPlanIssue(
            "semantic_resource_mismatch",
            f"step {step.step_id} targets {targets!r}, outside authorized {tuple(sorted(allowed_targets))!r}",
        )
    allowed_destinations = {
        item.destination_identity.casefold()
        for item in projections.values()
        if item.destination_identity.strip()
    }
    if step.effectful and step.task_usage == "execute" and allowed_destinations and not destinations:
        return TaskPlanIssue(
            "semantic_destination_missing",
            f"step {step.step_id} omits the destination required by its relational effect",
        )
    if destinations and allowed_destinations and not all(
        value.casefold() in allowed_destinations for value in destinations
    ):
        return TaskPlanIssue("semantic_destination_mismatch", f"step {step.step_id} changes destination")
    allowed_bindings = {
        (field.casefold(), value.casefold())
        for item in projections.values()
        for field, value in item.input_bindings
    }
    proposed_bindings = {(field.casefold(), value.casefold()) for field, value in step.material_bindings}
    if allowed_bindings and proposed_bindings != allowed_bindings:
        return TaskPlanIssue("semantic_material_binding_incomplete", f"step {step.step_id} omits named material values")
    if proposed_bindings - allowed_bindings:
        return TaskPlanIssue("semantic_material_value_mismatch", f"step {step.step_id} changes named material values")
    allowed_capabilities = {item.capability for item in projections.values() if item.capability}
    if roles and allowed_capabilities and any(role not in allowed_capabilities for role in roles):
        return TaskPlanIssue("semantic_element_function_mismatch", f"step {step.step_id} changes element function")
    if step.task_usage not in {"execute", "observe", "verify"}:
        return TaskPlanIssue("semantic_task_usage_invalid", f"step {step.step_id} has unauthorized task usage")
    return None


def _authorized_target_names(projection: TaskRequirementProjection) -> tuple[str, ...]:
    """Return exact and canonically projected names for one admitted target.

    Task requirements may carry an opaque source identity such as
    ``dom_button_1``.  The typed interaction projection deliberately separates
    the embedded role and exposes that same identity as ``dom 1`` plus role
    ``button``.  Admission must compare like with like, while retaining the
    original identity as an independently authorized spelling.
    """

    names = tuple(value for value in (projection.target_identity, projection.subject) if value.strip())
    relation = (
        StateCriterionRelation(projection.relation)
        if projection.relation in {item.value for item in StateCriterionRelation}
        else StateCriterionRelation.IS_AVAILABLE
    )
    source_refs = (SourceReference("task-requirement", projection.requirement_id),)
    projected: list[str] = []
    for name in names:
        interaction = interaction_for_state(name, relation, projection.value or None, source_refs)
        if hasattr(interaction, "target"):
            projected.append(str(interaction.target))
        elif hasattr(interaction, "collection"):
            projected.append(str(interaction.collection.target))
        elif hasattr(interaction, "source"):
            projected.append(str(interaction.source.target))
        else:
            projected.append(str(interaction.region))
    return tuple(dict.fromkeys((*names, *projected)))


def _interaction_semantics(step: StepSpec) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    interaction = step.interaction
    if hasattr(interaction, "target"):
        return (str(interaction.target),), (), ()
    if hasattr(interaction, "collection"):
        return (str(interaction.collection.target),), (), ()
    if isinstance(interaction, RelationIntent):
        destination = interaction.destination
        return (
            (str(interaction.source.target),),
            ((str(destination.target),) if destination is not None else ()),
            (),
        )
    return (str(interaction.region),), (), (str(interaction.capability),)


class TaskPlanGeneratorPort(Protocol):
    def generate(
        self,
        request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
    ) -> PlanProposal | Awaitable[PlanProposal]: ...


def _bind_task_plan(
    *,
    request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
    draft: PlanProposal,
    plan_id: str,
    plan_version: int,
    supersedes_plan_id: str,
) -> TaskPlan:
    return TaskPlan(
        plan_id=plan_id,
        task_id=getattr(request, "task_id", "") or draft.task_spec_identity,
        task_revision=draft.task_revision,
        plan_version=plan_version,
        supersedes_plan_id=supersedes_plan_id,
        based_on_state_version=request.evaluated_at_state_version,
        based_on_observation_ref=request.observation_refs[0],
        generated_by=draft.generated_by,
        steps=draft.steps,
        assumptions=draft.assumptions,
    )


def _validate_draft_matches_request(
    request: InitialTaskPlanRequest | TaskPlanRevisionRequest,
    draft: PlanProposal,
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


def _validate_step_execution_algebra(steps: tuple[StepSpec, ...]) -> None:
    """Validate the closed execution union without coupling foundation imports."""

    executions = tuple(step.execution for step in steps if step.execution is not None)
    if not executions:
        return
    from affordance_runtime.task.step_execution import (
        AggregateStepExecution,
        EntityStepExecution,
        SetStepExecution,
    )

    supported = EntityStepExecution | SetStepExecution | AggregateStepExecution
    if any(not isinstance(item, supported) for item in executions):
        raise TypeError("TaskPlan contains an unsupported step execution contract")


def _stable_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _stable_value(item) for key, item in vars(value).items()}
    if hasattr(value, "model_dump"):
        return _stable_value(value.model_dump(mode="python"))  # type: ignore[attr-defined]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in value.items()}
    return value


def _validate_request_identity(task_spec_identity: str, task_revision: int, state_version: int) -> None:
    _require_nonblank("task_spec_identity", task_spec_identity)
    if task_revision < 1:
        raise ValueError("task revision must be positive")
    if state_version < 0:
        raise ValueError("state version cannot be negative")


def _validate_requirement_projections(
    allowed_requirement_ids: tuple[str, ...],
    projections: tuple[TaskRequirementProjection, ...],
) -> None:
    projection_ids = tuple(item.requirement_id for item in projections)
    _require_unique_nonblank("requirement projection ids", projection_ids)
    if set(projection_ids) != set(allowed_requirement_ids):
        raise ValueError("typed requirement projections must exactly cover admitted requirements")


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
