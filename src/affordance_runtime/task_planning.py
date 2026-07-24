"""Bounded, verifier-oriented task planning above the action planner.

Task plans describe outcomes only.  They never contain executable GUI details,
capabilities, or approvals; those remain exclusively at the proposal and
contract boundaries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Awaitable, Literal, Protocol, TypeAlias
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field
from pydantic.json_schema import DEFAULT_REF_TEMPLATE, GenerateJsonSchema, JsonSchemaMode

from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import (
    CriteriaEvidenceMatcher,
    SubgoalVerificationReport,
    criteria_from_descriptions,
    evidence_requirements_from_descriptions,
)
from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.task_intake import OperationClass, StrictModel, TaskSpec, TaskStructure
from affordance_runtime.verification import VerificationReport

_FORBIDDEN_PLAN_CONTENT = re.compile(
    r"(?:"
    r"\bxpath\b|\bcss\s*=|\bselector\s*[:=]|\bbackend_handle\s*[:=]|"
    r"\b(?:mark_id|browser_handle|approval_token)\b|"
    r"\b(?:x|y)\s*[:=]\s*-?\d|"
    r"\b(?:pointer|mouse)_(?:click|move|down|up|drag)\s*\(|"
    r"\blocator\.|\bbackend\s*[:=]|\bgrant\s+capabilit(?:y|ies)\b"
    r")",
    re.IGNORECASE,
)
_ACTION_INSTRUCTION_SUBGOAL = re.compile(
    r"(?:^\s*(?:activate|choose|click|drag|drop|fill|press|scroll|select|type)\b|"
    r"^\s*enter\b.+\b(?:in|into)\b)",
    re.IGNORECASE,
)

TASK_PLAN_SCHEMA_VERSION = "1.1"
TASK_PLAN_ENTRY_SCHEMA_POLICY_VERSION = "explicit-entry-envelope-v1"
TASK_PLAN_CARDINALITY_POLICY_VERSION = "flat-1-multistage-2-to-8-v1"


class TaskPlanSource(StrEnum):
    RULE = "rule"
    LLM = "llm"
    PARENT = "parent"
    SKILL = "skill"


class TaskPlanActionFamily(StrEnum):
    ACTIVATE = "activate"
    POINT_ACTIVATE = "point_activate"
    TYPE_TEXT = "type_text"
    SELECT_OPTION = "select_option"
    PRESS_KEY = "press_key"
    DRAG = "drag"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    WAIT = "wait"


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
    action_family: TaskPlanActionFamily | None = None
    outcome: SubgoalOutcome | None = None
    max_actions: int = Field(default=10, ge=1, le=50)
    max_recoveries: int = Field(default=2, ge=0, le=10)


class SubgoalOutcomeRelation(StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"
    MATCHES = "matches"
    IS_VISIBLE = "is_visible"
    IS_ABSENT = "is_absent"
    IS_AVAILABLE = "is_available"
    IS_SELECTED = "is_selected"
    IS_CHECKED = "is_checked"
    IS_EXPANDED = "is_expanded"
    IS_COMPLETED = "is_completed"
    IS_ORDERED_AS = "is_ordered_as"
    HAS_CHANGED = "has_changed"


_ACTION_OUTCOME_RELATIONS: dict[TaskPlanActionFamily, frozenset[SubgoalOutcomeRelation]] = {
    TaskPlanActionFamily.ACTIVATE: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.MATCHES,
            SubgoalOutcomeRelation.IS_VISIBLE,
            SubgoalOutcomeRelation.IS_ABSENT,
            SubgoalOutcomeRelation.IS_CHECKED,
            SubgoalOutcomeRelation.IS_EXPANDED,
            SubgoalOutcomeRelation.IS_COMPLETED,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.POINT_ACTIVATE: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.MATCHES,
            SubgoalOutcomeRelation.IS_VISIBLE,
            SubgoalOutcomeRelation.IS_ABSENT,
            SubgoalOutcomeRelation.IS_CHECKED,
            SubgoalOutcomeRelation.IS_EXPANDED,
            SubgoalOutcomeRelation.IS_COMPLETED,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.TYPE_TEXT: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.MATCHES,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.SELECT_OPTION: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.IS_SELECTED,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.PRESS_KEY: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.MATCHES,
            SubgoalOutcomeRelation.IS_VISIBLE,
            SubgoalOutcomeRelation.IS_ABSENT,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.DRAG: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.IS_ORDERED_AS,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.NAVIGATE: frozenset(
        {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.MATCHES,
            SubgoalOutcomeRelation.IS_VISIBLE,
            SubgoalOutcomeRelation.IS_AVAILABLE,
            SubgoalOutcomeRelation.IS_COMPLETED,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.SCROLL: frozenset(
        {
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.IS_VISIBLE,
            SubgoalOutcomeRelation.HAS_CHANGED,
        }
    ),
    TaskPlanActionFamily.WAIT: frozenset(SubgoalOutcomeRelation),
}


def task_plan_allowed_outcome_relations(
    action_family: TaskPlanActionFamily,
) -> frozenset[SubgoalOutcomeRelation]:
    """Return the authoritative semantic relation set for one action family."""

    return _ACTION_OUTCOME_RELATIONS[action_family]


class SubgoalOutcome(StrictModel):
    """Provider-authored state predicate, never an executable instruction."""

    subject: str = Field(min_length=1)
    relation: SubgoalOutcomeRelation
    value: str = ""

    def description(self) -> str:
        phrase = {
            SubgoalOutcomeRelation.EQUALS: "equals",
            SubgoalOutcomeRelation.CONTAINS: "contains",
            SubgoalOutcomeRelation.MATCHES: "matches",
            SubgoalOutcomeRelation.IS_VISIBLE: "is visible",
            SubgoalOutcomeRelation.IS_ABSENT: "is absent",
            SubgoalOutcomeRelation.IS_AVAILABLE: "is available",
            SubgoalOutcomeRelation.IS_SELECTED: "is selected",
            SubgoalOutcomeRelation.IS_CHECKED: "is checked",
            SubgoalOutcomeRelation.IS_EXPANDED: "is expanded",
            SubgoalOutcomeRelation.IS_COMPLETED: "is completed",
            SubgoalOutcomeRelation.IS_ORDERED_AS: "is ordered as",
            SubgoalOutcomeRelation.HAS_CHANGED: "has changed",
        }[self.relation]
        value = self.value.strip()
        return " ".join(part for part in (self.subject.strip(), phrase, value) if part)


SubgoalSpec.model_rebuild()


class ActivationSubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.MATCHES,
        SubgoalOutcomeRelation.IS_VISIBLE,
        SubgoalOutcomeRelation.IS_ABSENT,
        SubgoalOutcomeRelation.IS_CHECKED,
        SubgoalOutcomeRelation.IS_EXPANDED,
        SubgoalOutcomeRelation.IS_COMPLETED,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class TextEntrySubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.MATCHES,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class SelectionSubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.IS_SELECTED,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class PressKeySubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.MATCHES,
        SubgoalOutcomeRelation.IS_VISIBLE,
        SubgoalOutcomeRelation.IS_ABSENT,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class DragSubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.IS_ORDERED_AS,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class NavigationSubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.MATCHES,
        SubgoalOutcomeRelation.IS_VISIBLE,
        SubgoalOutcomeRelation.IS_AVAILABLE,
        SubgoalOutcomeRelation.IS_COMPLETED,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class ScrollSubgoalOutcome(SubgoalOutcome):
    relation: Literal[
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.IS_VISIBLE,
        SubgoalOutcomeRelation.HAS_CHANGED,
    ]


class _TaskPlanSubgoalCandidateBase(StrictModel):
    """Shared model-controlled fields without runtime binding authority."""

    subgoal_id: str = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = Field(min_length=1)
    operation_class: OperationClass
    max_actions: int = Field(default=10, ge=1, le=50)
    max_recoveries: int = Field(default=2, ge=0, le=10)


class ActivationTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: ActivationSubgoalOutcome
    action_family: Literal[
        TaskPlanActionFamily.ACTIVATE,
        TaskPlanActionFamily.POINT_ACTIVATE,
    ]


class TextEntryTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: TextEntrySubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.TYPE_TEXT]


class SelectionTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: SelectionSubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.SELECT_OPTION]


class PressKeyTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: PressKeySubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.PRESS_KEY]


class DragTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: DragSubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.DRAG]


class NavigationTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: NavigationSubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.NAVIGATE]


class ScrollTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: ScrollSubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.SCROLL]


class WaitTaskPlanSubgoalCandidate(_TaskPlanSubgoalCandidateBase):
    outcome: SubgoalOutcome
    action_family: Literal[TaskPlanActionFamily.WAIT]


TaskPlanSubgoalCandidate: TypeAlias = Annotated[
    ActivationTaskPlanSubgoalCandidate
    | TextEntryTaskPlanSubgoalCandidate
    | SelectionTaskPlanSubgoalCandidate
    | PressKeyTaskPlanSubgoalCandidate
    | DragTaskPlanSubgoalCandidate
    | NavigationTaskPlanSubgoalCandidate
    | ScrollTaskPlanSubgoalCandidate
    | WaitTaskPlanSubgoalCandidate,
    Field(discriminator="action_family"),
]


class TaskPlan(StrictModel):
    schema_version: str = TASK_PLAN_SCHEMA_VERSION
    plan_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_revision: int = Field(ge=1)
    plan_version: int = Field(ge=1)
    supersedes_plan_id: str = ""
    based_on_state_version: int = Field(ge=0)
    generated_by: TaskPlanSource
    subgoals: tuple[SubgoalSpec, ...] = Field(min_length=1, max_length=8)
    assumptions: tuple[str, ...] = ()


class TaskPlanCandidate(StrictModel):
    """The model-controlled portion of a task plan, without authority fields."""

    subgoals: tuple[TaskPlanSubgoalCandidate, ...] = Field(min_length=1, max_length=8)
    assumptions: tuple[str, ...] = ()


class TaskPlanProviderEnvelope(StrictModel):
    """Provider-only shape with an explicitly constrained entry field."""

    entry_subgoal: TaskPlanSubgoalCandidate
    remaining_subgoals: tuple[TaskPlanSubgoalCandidate, ...] = Field(
        default=(),
        max_length=7,
        json_schema_extra={"minItems": 1},
    )
    assumptions: tuple[str, ...] = ()

    def to_candidate(self) -> TaskPlanCandidate:
        return TaskPlanCandidate(
            subgoals=(self.entry_subgoal, *self.remaining_subgoals),
            assumptions=self.assumptions,
        )


def task_plan_provider_model_for_context(
    context: TaskPlanningContext,
) -> type[TaskPlanProviderEnvelope]:
    """Constrain the explicit provider entry while leaving future items generic."""

    if not context.environment.affordances:
        return TaskPlanProviderEnvelope
    allowed_families = _context_action_families(context)
    if not allowed_families or allowed_families == frozenset(TaskPlanActionFamily):
        return TaskPlanProviderEnvelope
    allowed_values = tuple(sorted(item.value for item in allowed_families))

    class ContextualTaskPlanProviderEnvelope(TaskPlanProviderEnvelope):
        @classmethod
        def model_json_schema(
            cls,
            by_alias: bool = True,
            ref_template: str = DEFAULT_REF_TEMPLATE,
            schema_generator: type[GenerateJsonSchema] = GenerateJsonSchema,
            mode: JsonSchemaMode = "validation",
            *,
            union_format: Literal["any_of", "primitive_type_array"] = "any_of",
        ) -> dict[str, Any]:
            schema = super().model_json_schema(
                by_alias=by_alias,
                ref_template=ref_template,
                schema_generator=schema_generator,
                mode=mode,
                union_format=union_format,
            )
            entry_schema = schema["properties"]["entry_subgoal"]
            mapping = entry_schema["discriminator"]["mapping"]
            entry_mapping = {value: mapping[value] for value in allowed_values}
            entry_refs = tuple(dict.fromkeys(entry_mapping.values()))
            schema["properties"]["entry_subgoal"] = {
                "discriminator": {
                    "propertyName": "action_family",
                    "mapping": entry_mapping,
                },
                "oneOf": [{"$ref": value} for value in entry_refs],
                "title": "Entry Subgoal",
            }
            schema["title"] = TaskPlanProviderEnvelope.__name__
            return schema

    ContextualTaskPlanProviderEnvelope.__name__ = TaskPlanProviderEnvelope.__name__
    ContextualTaskPlanProviderEnvelope.__qualname__ = TaskPlanProviderEnvelope.__qualname__
    return ContextualTaskPlanProviderEnvelope


class PlanningAffordanceSummary(StrictModel):
    semantic_target_id: str = Field(min_length=1)
    role: str = ""
    label: str = ""
    supported_actions: tuple[str, ...] = ()


class PlanningEnvironmentSummary(StrictModel):
    environment_revision: str = ""
    snapshot_id: str = ""
    page_revision: str = ""
    url: str = ""
    affordances: tuple[PlanningAffordanceSummary, ...] = Field(default=(), max_length=64)


class CriteriaEvidenceLedgerEntry(StrictModel):
    subgoal_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class TaskPlanningFailureSummary(StrictModel):
    phase: str = ""
    error_code: str = ""
    reason: str = ""
    subgoal_id: str = ""
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
    """Bounded, handle-free input for initial planning and replanning."""

    schema_version: str = "1.0"
    task_spec: TaskSpec
    state_version: int = Field(ge=0)
    reason: str = "initial"
    current_plan_id: str = ""
    current_plan_version: int = Field(default=0, ge=0)
    environment: PlanningEnvironmentSummary = Field(default_factory=PlanningEnvironmentSummary)
    active_subgoal_id: str = ""
    completed_subgoal_ids: tuple[str, ...] = ()
    failed_subgoal_ids: tuple[str, ...] = ()
    criteria_evidence_ledger: tuple[CriteriaEvidenceLedgerEntry, ...] = ()
    failures: tuple[TaskPlanningFailureSummary, ...] = Field(default=(), max_length=16)
    recovery_summary: TaskPlanningRecoverySummary | None = None
    disproved_assumptions: tuple[str, ...] = Field(default=(), max_length=16)
    remaining_budget: TaskPlanningBudgetSummary


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
    field: str = ""
    disallowed_values: tuple[str, ...] = ()
    required_semantics: str = ""


class TaskPlanRepairDirective(StrictModel):
    """Typed, authority-free correction derived from a validation issue."""

    subgoal_id: str = ""
    field: str = Field(min_length=1)
    disallowed_values: tuple[str, ...] = ()
    required_semantics: str = Field(min_length=1)


class TaskPlanValidationReport(StrictModel):
    status: TaskPlanValidationStatus
    issues: tuple[TaskPlanValidationIssue, ...] = ()


@dataclass(frozen=True)
class TaskPlanValidator:
    max_subgoals: int = 8
    max_actions_per_subgoal: int = 50
    max_recoveries_per_subgoal: int = 10

    def validate(
        self,
        plan: TaskPlan,
        task_spec: TaskSpec,
        *,
        state_version: int,
        previous_plan: TaskPlan | None = None,
        previous_plan_id: str = "",
        previous_plan_version: int = 0,
        planning_context: TaskPlanningContext | None = None,
    ) -> TaskPlanValidationReport:
        fatal: list[TaskPlanValidationIssue] = []
        repairable: list[TaskPlanValidationIssue] = []
        if plan.task_id != task_spec.task_id:
            fatal.append(TaskPlanValidationIssue(code="task_id_mismatch"))
        if plan.task_revision != task_spec.revision:
            fatal.append(TaskPlanValidationIssue(code="task_revision_mismatch"))
        if plan.based_on_state_version != state_version:
            fatal.append(TaskPlanValidationIssue(code="state_version_mismatch"))
        expected_plan_id = previous_plan.plan_id if previous_plan is not None else previous_plan_id
        expected_plan_version = previous_plan.plan_version if previous_plan is not None else previous_plan_version
        if not expected_plan_id:
            if plan.plan_version != 1 or plan.supersedes_plan_id:
                fatal.append(TaskPlanValidationIssue(code="invalid_initial_plan_lineage"))
        elif (
            plan.plan_version != expected_plan_version + 1
            or plan.supersedes_plan_id != expected_plan_id
            or plan.plan_id == expected_plan_id
        ):
            fatal.append(TaskPlanValidationIssue(code="invalid_replacement_plan_lineage"))
        if not 1 <= len(plan.subgoals) <= self.max_subgoals:
            fatal.append(TaskPlanValidationIssue(code="subgoal_count_out_of_bounds"))
        if (
            task_spec.task_structure == TaskStructure.MULTI_STAGE
            and plan.generated_by in {TaskPlanSource.LLM, TaskPlanSource.PARENT}
            and len(plan.subgoals) < 2
        ):
            repairable.append(
                TaskPlanValidationIssue(
                    code="multi_stage_plan_not_decomposed",
                    detail=str(len(plan.subgoals)),
                    field="subgoals",
                    disallowed_values=(str(len(plan.subgoals)),),
                    required_semantics="at_least_two_outcome_subgoals",
                )
            )

        identifiers = [item.subgoal_id for item in plan.subgoals]
        if len(identifiers) != len(set(identifiers)):
            fatal.append(TaskPlanValidationIssue(code="duplicate_subgoal_id"))
        known = set(identifiers)
        for subgoal in plan.subgoals:
            if (
                task_spec.task_structure == TaskStructure.MULTI_STAGE
                and _is_action_instruction_subgoal(subgoal.objective)
            ):
                repairable.append(
                    TaskPlanValidationIssue(
                        code="action_instruction_subgoal",
                        detail=subgoal.subgoal_id,
                    )
                )
            if not subgoal.success_criteria:
                repairable.append(TaskPlanValidationIssue(code="missing_success_criteria", detail=subgoal.subgoal_id))
            if not subgoal.evidence_requirements:
                repairable.append(
                    TaskPlanValidationIssue(code="missing_evidence_requirements", detail=subgoal.subgoal_id)
                )
            if (
                subgoal.outcome is not None
                and subgoal.action_family is not None
                and not _action_outcome_relation_compatible(
                    subgoal.action_family,
                    subgoal.outcome.relation,
                )
            ):
                precondition_only = (
                    subgoal.outcome.relation == SubgoalOutcomeRelation.IS_AVAILABLE
                )
                repairable.append(
                    TaskPlanValidationIssue(
                        code=(
                            "precondition_only_outcome"
                            if precondition_only
                            else "incompatible_action_outcome"
                        ),
                        detail=subgoal.subgoal_id,
                        field="outcome.relation",
                        disallowed_values=(subgoal.outcome.relation.value,),
                        required_semantics="post_action_state",
                    )
                )
            if subgoal.max_actions > self.max_actions_per_subgoal:
                fatal.append(TaskPlanValidationIssue(code="action_budget_out_of_bounds", detail=subgoal.subgoal_id))
            if subgoal.max_recoveries > self.max_recoveries_per_subgoal:
                fatal.append(TaskPlanValidationIssue(code="recovery_budget_out_of_bounds", detail=subgoal.subgoal_id))
            if _operation_rank(subgoal.operation_class) > _operation_rank(task_spec.operation_class):
                fatal.append(TaskPlanValidationIssue(code="operation_class_escalation", detail=subgoal.subgoal_id))
            if _contains_executable_plan_content(
                (
                    subgoal.objective,
                    *subgoal.success_criteria,
                    *subgoal.evidence_requirements,
                )
            ):
                fatal.append(
                    TaskPlanValidationIssue(
                        code="executable_plan_content",
                        detail=subgoal.subgoal_id,
                    )
                )
            for dependency in subgoal.depends_on:
                if dependency == subgoal.subgoal_id:
                    fatal.append(TaskPlanValidationIssue(code="self_dependency", detail=subgoal.subgoal_id))
                elif dependency not in known:
                    fatal.append(TaskPlanValidationIssue(code="unknown_dependency", detail=dependency))
        if _has_cycle(plan.subgoals):
            fatal.append(TaskPlanValidationIssue(code="dependency_cycle"))
        if _contains_executable_plan_content(plan.assumptions):
            fatal.append(
                TaskPlanValidationIssue(
                    code="executable_plan_content",
                    detail="assumptions",
                )
            )
        entry_issue = task_plan_entry_feasibility_issue(plan, planning_context)
        if entry_issue is not None:
            repairable.append(entry_issue)
        dependency_targets = {dependency for item in plan.subgoals for dependency in item.depends_on}
        if not any(item.subgoal_id not in dependency_targets for item in plan.subgoals):
            fatal.append(TaskPlanValidationIssue(code="missing_terminal_subgoal"))

        if fatal:
            return TaskPlanValidationReport(status=TaskPlanValidationStatus.REJECT, issues=tuple(fatal + repairable))
        if repairable:
            return TaskPlanValidationReport(status=TaskPlanValidationStatus.REPAIRABLE, issues=tuple(repairable))
        return TaskPlanValidationReport(status=TaskPlanValidationStatus.ACCEPT)


def task_plan_entry_feasibility_issue(
    plan: TaskPlan,
    context: TaskPlanningContext | None,
) -> TaskPlanValidationIssue | None:
    """Return the current-entry issue without revalidating immutable lineage."""

    entry = _contextual_entry_subgoal(plan, context)
    if (
        entry is None
        or entry.action_family is None
        or context is None
        or not context.environment.affordances
        or entry.action_family in _context_action_families(context)
    ):
        return None
    return TaskPlanValidationIssue(
        code="entry_action_family_unavailable",
        detail=entry.subgoal_id,
        field="action_family",
        disallowed_values=(entry.action_family.value,),
        required_semantics="currently_bindable_action_family",
    )


def _contextual_entry_subgoal(
    plan: TaskPlan,
    context: TaskPlanningContext | None,
) -> SubgoalSpec | None:
    if context is None:
        return None
    completed = set(context.completed_subgoal_ids)
    failed = set(context.failed_subgoal_ids)
    if context.active_subgoal_id:
        active = next(
            (
                item
                for item in plan.subgoals
                if item.subgoal_id == context.active_subgoal_id
                and item.subgoal_id not in completed | failed
            ),
            None,
        )
        if active is not None:
            return active
    return next(
        (
            item
            for item in plan.subgoals
            if item.subgoal_id not in completed | failed
            and all(dependency in completed for dependency in item.depends_on)
        ),
        None,
    )


def _context_action_families(
    context: TaskPlanningContext,
) -> frozenset[TaskPlanActionFamily]:
    aliases = {
        "click": TaskPlanActionFamily.ACTIVATE,
        "fill": TaskPlanActionFamily.TYPE_TEXT,
        "type": TaskPlanActionFamily.TYPE_TEXT,
        "select": TaskPlanActionFamily.SELECT_OPTION,
        "press": TaskPlanActionFamily.PRESS_KEY,
        "drop": TaskPlanActionFamily.DRAG,
    }
    families: set[TaskPlanActionFamily] = set()
    for affordance in context.environment.affordances:
        for action in affordance.supported_actions:
            normalized = action.strip().lower()
            try:
                families.add(TaskPlanActionFamily(normalized))
            except ValueError:
                alias = aliases.get(normalized)
                if alias is not None:
                    families.add(alias)
    return frozenset(families)


def _action_outcome_relation_compatible(
    action_family: TaskPlanActionFamily,
    relation: SubgoalOutcomeRelation,
) -> bool:
    """Enforce the provider-neutral semantic action/outcome relation matrix."""

    return relation in task_plan_allowed_outcome_relations(action_family)


def task_plan_repair_directives(
    issues: tuple[TaskPlanValidationIssue, ...],
) -> tuple[TaskPlanRepairDirective, ...]:
    """Project validator issues into bounded model-facing field constraints."""

    return tuple(
        TaskPlanRepairDirective(
            subgoal_id=issue.detail,
            field=issue.field,
            disallowed_values=issue.disallowed_values,
            required_semantics=issue.required_semantics,
        )
        for issue in issues
        if issue.field and issue.required_semantics
    )


class TaskPlannerPort(Protocol):
    def plan(self, context: TaskPlanningContext) -> TaskPlan | Awaitable[TaskPlan]: ...


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

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        return synthetic_task_plan(context, generated_by=TaskPlanSource.RULE)


TASK_PLANNER_PROMPT_VERSION = "task-planner-v8"
_TASK_PLANNER_SYSTEM_PROMPT = """You are a bounded task planner. Return only a TaskPlanProviderEnvelope. Put the first currently executable outcome in entry_subgoal and later effect-dependent outcomes in remaining_subgoals.
Decompose only open-world, multi-stage, cross-application, or data-dependent work into 2-8 outcome-oriented subgoals. Represent each outcome only as a subject, one supplied state relation, and an optional semantic value. Declare exactly one supplied semantic action_family that can satisfy that state. Every subgoal needs non-empty independent evidence requirements. Preserve the supplied TaskSpec constraints and operation class; do not invent destructive scope, recipients, credentials, payment, approval, or authority.
Subgoals are desired environment states, never UI scripts. action_family is only a semantic family constraint, not an action instruction. Use an outcome relation compatible with that family: type_text changes/matches a value; select_option selects or changes a value; drag changes order/state; navigate exposes a destination; scroll exposes content; activate/point_activate produces an exact, checked, expanded, completed, visible, absent, or changed state. is_available is only a precondition for an action requiring a current target, and is_selected belongs to select_option rather than generic activation. Do not output selectors, coordinates, target ids, backend handles, executable code, capabilities, approval tokens, action sequences, or success criteria prose; Runtime derives the criterion from the typed outcome. Dependencies express a small serial-ready partial order. The runtime executes one ready subgoal at a time and independently verifies progress."""


def task_planner_model_config() -> ModelConfig:
    """Return the versioned decoding contract used by TaskPlan generation."""

    return ModelConfig(
        temperature=0.0,
        max_tokens=1_024,
        prompt_version=TASK_PLANNER_PROMPT_VERSION,
    )


@dataclass
class LLMTaskPlanner:
    """Model-backed task decomposition with exactly one repairable retry."""

    model: ModelPort
    validator: TaskPlanValidator = field(default_factory=TaskPlanValidator)
    config: ModelConfig = field(default_factory=task_planner_model_config)

    async def plan(self, context: TaskPlanningContext) -> TaskPlan:
        task_spec = context.task_spec
        planner_context = context.model_dump(mode="json", exclude={"task_spec"})
        planner_context["task_spec"] = task_spec_planning_summary(task_spec)
        prompt_context = {
            "task_spec": task_spec_planning_summary(task_spec),
            "planning_context": planner_context,
            "constraints": list(task_spec.constraints),
            "forbidden_effects": list(task_spec.forbidden_effects),
        }
        messages = [
            ModelMessage(role="system", content=_TASK_PLANNER_SYSTEM_PROMPT),
            ModelMessage(role="user", content=json.dumps(prompt_context, sort_keys=True)),
        ]
        provider_model = task_plan_provider_model_for_context(context)
        envelope = await self.model.generate_structured(messages, provider_model, self.config)
        candidate = envelope.to_candidate()
        plan = self._bind_candidate(candidate, context)
        report = self.validator.validate(
            plan,
            task_spec,
            state_version=context.state_version,
            previous_plan_id=context.current_plan_id,
            previous_plan_version=context.current_plan_version,
            planning_context=context,
        )
        if report.status != TaskPlanValidationStatus.REPAIRABLE:
            return plan
        repair_context = {
            "validation_errors": [item.model_dump(mode="json") for item in report.issues],
            "repair_directives": [
                item.model_dump(mode="json")
                for item in task_plan_repair_directives(report.issues)
            ],
            "instruction": "Repair only the reported plan fields; retain outcome-only semantics and constraints.",
        }
        repaired_envelope = await self.model.generate_structured(
            [
                *messages,
                ModelMessage(role="assistant", content=envelope.model_dump_json()),
                ModelMessage(role="user", content=json.dumps(repair_context, sort_keys=True)),
            ],
            provider_model,
            self.config,
        )
        return self._bind_candidate(repaired_envelope.to_candidate(), context)

    @staticmethod
    def _bind_candidate(candidate: TaskPlanCandidate, context: TaskPlanningContext) -> TaskPlan:
        task_spec = context.task_spec
        return TaskPlan(
            plan_id=f"plan-{uuid4().hex}",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.LLM,
            subgoals=tuple(LLMTaskPlanner._bind_subgoal_candidate(item) for item in candidate.subgoals),
            assumptions=candidate.assumptions,
        )

    @staticmethod
    def _bind_subgoal_candidate(item: TaskPlanSubgoalCandidate) -> SubgoalSpec:
        outcome = SubgoalOutcome.model_validate(item.outcome.model_dump(mode="json"))
        return SubgoalSpec(
            subgoal_id=item.subgoal_id,
            objective=outcome.description(),
            depends_on=item.depends_on,
            success_criteria=(outcome.description(),),
            evidence_requirements=item.evidence_requirements,
            operation_class=item.operation_class,
            action_family=TaskPlanActionFamily(item.action_family),
            outcome=outcome,
            max_actions=item.max_actions,
            max_recoveries=item.max_recoveries,
        )


@dataclass(frozen=True)
class PlanningRouter:
    """Routes simple work to the flat path and delegates complex work explicitly."""

    rule_planner: TaskPlannerPort = field(default_factory=RuleTaskPlanner)
    complex_planner: TaskPlannerPort | None = None

    def plan(
        self,
        context: TaskPlanningContext,
        *,
        complex_task: bool | None = None,
    ) -> TaskPlan | Awaitable[TaskPlan]:
        if complex_task is None:
            complex_task = context.task_spec.task_structure == TaskStructure.MULTI_STAGE
        if not complex_task:
            return self.rule_planner.plan(context)
        if self.complex_planner is None:
            raise ValueError("complex task requires an LLMTaskPlanner or accepted task planner")
        return self.complex_planner.plan(context)


def task_spec_planning_summary(task_spec: TaskSpec) -> dict[str, object]:
    """Return task authority without runtime or source identity fields."""

    return {
        "schema_version": task_spec.schema_version,
        "revision": task_spec.revision,
        "objective": task_spec.objective,
        "operation_class": task_spec.operation_class.value,
        "task_structure": task_spec.task_structure.value,
        "targets": list(task_spec.targets),
        "entities": [{"name": item.name, "value": item.value} for item in task_spec.entities],
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
    """Serialize a planning context without suite/run identity leakage."""

    summary = context.model_dump(mode="json", exclude={"task_spec"})
    summary["task_spec"] = task_spec_planning_summary(context.task_spec)
    environment = summary.get("environment")
    if isinstance(environment, dict):
        environment["url"] = _planning_url_origin(str(environment.get("url") or ""))
    return summary


def _planning_url_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return parsed.scheme or ""


def synthetic_task_plan(
    context: TaskPlanningContext,
    *,
    generated_by: TaskPlanSource = TaskPlanSource.RULE,
) -> TaskPlan:
    """Preserve the existing flat action loop as one verifier-backed subgoal."""

    task_spec = context.task_spec
    return TaskPlan(
        plan_id=f"plan-{uuid4().hex}",
        task_id=task_spec.task_id,
        task_revision=task_spec.revision,
        plan_version=context.current_plan_version + 1,
        supersedes_plan_id=context.current_plan_id,
        based_on_state_version=context.state_version,
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


def _contains_executable_plan_content(values: tuple[str, ...]) -> bool:
    return any(_FORBIDDEN_PLAN_CONTENT.search(value) is not None for value in values)


def _is_action_instruction_subgoal(objective: str) -> bool:
    """Reject UI procedures where a multi-stage plan requires an outcome."""

    return _ACTION_INSTRUCTION_SUBGOAL.search(objective) is not None


def _operation_rank(operation: OperationClass) -> int:
    return {
        OperationClass.READ_ONLY: 0,
        OperationClass.NAVIGATION: 1,
        OperationClass.REVERSIBLE_WRITE: 2,
        OperationClass.EXTERNAL_SIDE_EFFECT: 3,
        OperationClass.IRREVERSIBLE: 4,
    }[operation]
