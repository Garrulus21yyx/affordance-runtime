"""Bounded, verifier-oriented task planning above the action planner."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Awaitable, Literal, Protocol, TypeAlias
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field, model_validator
from pydantic.json_schema import DEFAULT_REF_TEMPLATE, GenerateJsonSchema, JsonSchemaMode

from affordance_runtime import task_action_family_resolution as action_family_resolution
from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import (
    CriteriaEvidenceMatcher,
    SubgoalVerificationReport,
    criteria_from_descriptions,
    evidence_requirements_from_descriptions,
)
from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.simplified_runtime_contracts import (
    InteractionIntent,
    StateCriterionRelation,
    interaction_for_state,
)
from affordance_runtime.task_intake import (
    OperationClass,
    StrictModel,
    TaskObligationKind,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
    TaskStructure,
)
from affordance_runtime.task_source_references import obligation_source_refs, obligation_value_source, task_source_refs
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

TASK_PLAN_SCHEMA_VERSION = "1.2"
TASK_PLAN_ENTRY_SCHEMA_POLICY_VERSION = "explicit-entry-envelope-v1"
TASK_PLAN_CARDINALITY_POLICY_VERSION = "flat-1-multistage-initial-2-replacement-1-to-8-v2"
TASK_PLAN_CONTEXT_POLICY_VERSION = "bounded-current-state-v1"
TASK_PLAN_OUTCOME_STATE_SUPPORT_POLICY_VERSION = "typed-subject-state-support-v1"
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
    interaction: InteractionIntent
    depends_on: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    operation_class: OperationClass
    action_family: TaskPlanActionFamily | None = None
    outcome: SubgoalOutcome | None = None
    max_actions: int = Field(default=10, ge=1, le=50)
    max_recoveries: int = Field(default=2, ge=0, le=10)


SubgoalOutcomeRelation = CriterionRelation


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
    value_obligation_id: str = ""

    @model_validator(mode="after")
    def validate_value_reference(self) -> "SubgoalOutcome":
        value_relations = {
            SubgoalOutcomeRelation.EQUALS,
            SubgoalOutcomeRelation.CONTAINS,
            SubgoalOutcomeRelation.MATCHES,
            SubgoalOutcomeRelation.IS_ORDERED_AS,
        }
        if self.value and self.value_obligation_id:
            raise ValueError("subgoal outcome cannot carry literal and obligation values")
        if self.value_obligation_id and self.relation not in value_relations:
            raise ValueError("subgoal outcome reference requires a value relation")
        return self

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
        reference = (
            f"output of {self.value_obligation_id}"
            if self.value_obligation_id
            else ""
        )
        return " ".join(part for part in (self.subject.strip(), phrase, value, reference) if part)


SubgoalSpec.model_rebuild()


class _RequiredValueCandidateOutcome(SubgoalOutcome):
    value: str = Field(min_length=1)


class _UnaryCandidateOutcome(SubgoalOutcome):
    value: Literal[""] = ""


class EqualsCandidateOutcome(_RequiredValueCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.EQUALS]


class ContainsCandidateOutcome(_RequiredValueCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.CONTAINS]


class MatchesCandidateOutcome(_RequiredValueCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.MATCHES]


class OrderedCandidateOutcome(_RequiredValueCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_ORDERED_AS]


class VisibleCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_VISIBLE]


class AbsentCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_ABSENT]


class AvailableCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_AVAILABLE]


class SelectedCandidateOutcome(SubgoalOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_SELECTED]


class CheckedCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_CHECKED]


class ExpandedCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_EXPANDED]


class CompletedCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.IS_COMPLETED]


class ChangedCandidateOutcome(_UnaryCandidateOutcome):
    relation: Literal[SubgoalOutcomeRelation.HAS_CHANGED]


ActivationSubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome
    | ContainsCandidateOutcome
    | MatchesCandidateOutcome
    | VisibleCandidateOutcome
    | AbsentCandidateOutcome
    | CheckedCandidateOutcome
    | ExpandedCandidateOutcome
    | CompletedCandidateOutcome
    | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
TextEntrySubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome
    | ContainsCandidateOutcome
    | MatchesCandidateOutcome
    | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
SelectionSubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome
    | ContainsCandidateOutcome
    | SelectedCandidateOutcome
    | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
PressKeySubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome
    | ContainsCandidateOutcome
    | MatchesCandidateOutcome
    | VisibleCandidateOutcome
    | AbsentCandidateOutcome
    | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
DragSubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome | OrderedCandidateOutcome | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
NavigationSubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome
    | ContainsCandidateOutcome
    | MatchesCandidateOutcome
    | VisibleCandidateOutcome
    | AvailableCandidateOutcome
    | CompletedCandidateOutcome
    | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
ScrollSubgoalOutcome: TypeAlias = Annotated[
    ContainsCandidateOutcome | VisibleCandidateOutcome | ChangedCandidateOutcome,
    Field(discriminator="relation"),
]
WaitSubgoalOutcome: TypeAlias = Annotated[
    EqualsCandidateOutcome
    | ContainsCandidateOutcome
    | MatchesCandidateOutcome
    | OrderedCandidateOutcome
    | VisibleCandidateOutcome
    | AbsentCandidateOutcome
    | AvailableCandidateOutcome
    | SelectedCandidateOutcome
    | CheckedCandidateOutcome
    | ExpandedCandidateOutcome
    | CompletedCandidateOutcome
    | ChangedCandidateOutcome,
    Field(discriminator="relation"),
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
    outcome: WaitSubgoalOutcome
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

    allowed_families = (
        _context_action_families(context)
        if context.environment.affordances
        else frozenset()
    )
    constrain_entry = bool(
        allowed_families and allowed_families != frozenset(TaskPlanActionFamily)
    )
    relax_replacement_cardinality = bool(context.completed_subgoal_ids)
    if not constrain_entry and not relax_replacement_cardinality:
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
            if constrain_entry:
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
            if relax_replacement_cardinality:
                schema["properties"]["remaining_subgoals"]["minItems"] = 0
            schema["title"] = TaskPlanProviderEnvelope.__name__
            return schema

    ContextualTaskPlanProviderEnvelope.__name__ = TaskPlanProviderEnvelope.__name__
    ContextualTaskPlanProviderEnvelope.__qualname__ = TaskPlanProviderEnvelope.__qualname__
    return ContextualTaskPlanProviderEnvelope


class PlanningAffordanceState(StrictModel):
    """Small, handle-free current-state projection for outcome planning."""

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
    current_state: PlanningAffordanceState = Field(
        default_factory=PlanningAffordanceState
    )


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

    schema_version: str = "1.1"
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
class TaskProgress:
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


PlanProgress = TaskProgress

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
        completed_ids = (
            set(planning_context.completed_subgoal_ids)
            if planning_context is not None
            else set()
        )
        effective_subgoal_count = len(
            {item.subgoal_id for item in plan.subgoals} | completed_ids
        )
        if (
            task_spec.task_structure == TaskStructure.MULTI_STAGE
            and plan.generated_by in {TaskPlanSource.LLM, TaskPlanSource.PARENT}
            and effective_subgoal_count < 2
        ):
            repairable.append(
                TaskPlanValidationIssue(
                    code="multi_stage_plan_not_decomposed",
                    detail=str(effective_subgoal_count),
                    field="subgoals",
                    disallowed_values=(str(effective_subgoal_count),),
                    required_semantics="at_least_two_outcome_subgoals",
                )
            )
        if previous_plan is not None and completed_ids:
            previous_by_id = {item.subgoal_id: item for item in previous_plan.subgoals}
            replacement_by_id = {item.subgoal_id: item for item in plan.subgoals}
            missing = completed_ids - replacement_by_id.keys()
            redefined = {
                subgoal_id
                for subgoal_id in completed_ids & replacement_by_id.keys()
                if previous_by_id.get(subgoal_id) != replacement_by_id[subgoal_id]
            }
            if missing:
                fatal.append(
                    TaskPlanValidationIssue(
                        code="verified_subgoal_missing",
                        detail=",".join(sorted(missing)),
                    )
                )
            if redefined:
                fatal.append(
                    TaskPlanValidationIssue(
                        code="verified_subgoal_redefined",
                        detail=",".join(sorted(redefined)),
                    )
                )
            previous_unfinished = {
                item.subgoal_id for item in previous_plan.subgoals
            } - completed_ids
            replacement_unfinished = replacement_by_id.keys() - completed_ids
            issue = task_plan_entry_state_issue(previous_plan, planning_context)
            if not replacement_unfinished and previous_unfinished - ({issue.detail} if issue is not None else set()):
                repairable.append(
                    TaskPlanValidationIssue(
                        code="replacement_missing_unfinished_subgoal",
                        field="subgoals",
                        required_semantics="at_least_one_unfinished_outcome_subgoal",
                    )
                )

        identifiers = [item.subgoal_id for item in plan.subgoals]
        if len(identifiers) != len(set(identifiers)):
            fatal.append(TaskPlanValidationIssue(code="duplicate_subgoal_id"))
        known = set(identifiers)
        if task_spec.obligations:
            expected_subgoals = {
                item.obligation_id: TaskObligationOutcomeCompiler._compile_obligation(
                    item,
                    task_spec.operation_class,
                )
                for item in task_spec.obligations
            }
            actual_subgoals = {item.subgoal_id: item for item in plan.subgoals}
            missing_obligations = expected_subgoals.keys() - actual_subgoals.keys()
            unexpected_subgoals = actual_subgoals.keys() - expected_subgoals.keys()
            if missing_obligations:
                fatal.append(
                    TaskPlanValidationIssue(
                        code="obligation_subgoal_missing",
                        detail=",".join(sorted(missing_obligations)),
                    )
                )
            if unexpected_subgoals:
                fatal.append(
                    TaskPlanValidationIssue(
                        code="unbound_obligation_subgoal",
                        detail=",".join(sorted(unexpected_subgoals)),
                    )
                )
            for obligation_id in expected_subgoals.keys() & actual_subgoals.keys():
                expected = expected_subgoals[obligation_id]
                actual = actual_subgoals[obligation_id]
                if (
                    actual.depends_on != expected.depends_on
                    or actual.outcome != expected.outcome
                    or actual.evidence_requirements != expected.evidence_requirements
                    or actual.operation_class != expected.operation_class
                ):
                    fatal.append(
                        TaskPlanValidationIssue(
                            code="obligation_subgoal_mismatch",
                            detail=obligation_id,
                        )
                    )
        for subgoal in plan.subgoals:
            if (
                task_spec.task_structure == TaskStructure.MULTI_STAGE
                and (
                    plan.generated_by != TaskPlanSource.RULE
                    or
                    subgoal.outcome is None
                    or subgoal.objective != subgoal.outcome.description()
                )
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
                repairable.append(TaskPlanValidationIssue(code="missing_evidence_requirements", detail=subgoal.subgoal_id))
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
            if subgoal.outcome is not None and (
                value_issue := _task_plan_outcome_value_issue(subgoal)
            ) is not None:
                repairable.append(value_issue)
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
        entry_state_issue = task_plan_entry_state_issue(plan, planning_context)
        if entry_state_issue is not None:
            repairable = [
                issue
                for issue in repairable
                if (issue.detail, issue.code)
                != (entry_state_issue.detail, "outcome_value_forbidden")
            ]
            repairable.append(entry_state_issue)
        else:
            entry_issue = task_plan_entry_state_support_issue(plan, planning_context)
            entry_issue = entry_issue or task_plan_entry_feasibility_issue(plan, planning_context)
            if entry_issue is not None:
                repairable.append(entry_issue)
        dependency_targets = {dependency for item in plan.subgoals for dependency in item.depends_on}
        if not any(item.subgoal_id not in dependency_targets for item in plan.subgoals):
            fatal.append(TaskPlanValidationIssue(code="missing_terminal_subgoal"))

        status = TaskPlanValidationStatus.REJECT if fatal else (
            TaskPlanValidationStatus.REPAIRABLE if repairable else TaskPlanValidationStatus.ACCEPT
        )
        return TaskPlanValidationReport(status=status, issues=tuple(fatal + repairable))


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


def task_plan_entry_state_issue(
    plan: TaskPlan,
    context: TaskPlanningContext | None,
) -> TaskPlanValidationIssue | None:
    """Reject only a uniquely grounded entry predicate already proven current."""
    entry = _contextual_entry_subgoal(plan, context)
    if entry is None or entry.outcome is None or context is None:
        return None
    subject_tokens = planning_semantic_tokens(entry.outcome.subject)
    if not subject_tokens:
        return None
    matches = tuple(item for item in context.environment.affordances if _planning_affordance_matches_subject(subject_tokens, item))
    if len(matches) != 1 or not _planning_outcome_is_current(
        entry.outcome,
        matches[0],
    ):
        return None
    return TaskPlanValidationIssue(
        code="entry_outcome_already_satisfied",
        detail=entry.subgoal_id,
        field="outcome",
        disallowed_values=(entry.outcome.description(),),
        required_semantics=(
            "different_currently_unsatisfied_outcome_without_boolean_negation"
        ),
    )


def task_plan_entry_state_support_issue(
    plan: TaskPlan,
    context: TaskPlanningContext | None,
) -> TaskPlanValidationIssue | None:
    """Reject a uniquely grounded state predicate only when incompatibility is explicit."""
    entry = _contextual_entry_subgoal(plan, context)
    if entry is None or entry.outcome is None or context is None:
        return None
    subject_tokens = planning_semantic_tokens(entry.outcome.subject)
    matches = tuple(
        item for item in context.environment.affordances if subject_tokens and _planning_affordance_matches_subject(subject_tokens, item)
    )
    if len(matches) != 1:
        return None
    affordance = matches[0]
    relation = entry.outcome.relation
    role = affordance.role.casefold().strip().replace("-", "_")
    known_non_checkable = {
        "button",
        "link",
        "option",
        "select",
        "textbox",
        "treeitem",
    }
    known_non_selectable = {
        "button",
        "checkbox",
        "link",
        "radio",
        "switch",
        "textbox",
    }
    known_non_expandable = {
        "checkbox",
        "link",
        "option",
        "radio",
        "switch",
        "textbox",
    }
    unsupported = (
        relation == SubgoalOutcomeRelation.IS_CHECKED
        and affordance.current_state.checked is None
        and role in known_non_checkable
    ) or (
        relation == SubgoalOutcomeRelation.IS_SELECTED
        and affordance.current_state.selected is None
        and not affordance.current_state.selected_options
        and role in known_non_selectable
    ) or (
        relation == SubgoalOutcomeRelation.IS_EXPANDED
        and affordance.current_state.expanded is None
        and role in known_non_expandable
    )
    if not unsupported:
        return None
    return TaskPlanValidationIssue(
        code="entry_outcome_state_unsupported",
        detail=entry.subgoal_id,
        field="outcome.relation",
        disallowed_values=(relation.value,),
        required_semantics="state_relation_supported_by_unique_current_subject",
    )


def _task_plan_outcome_value_issue(
    subgoal: SubgoalSpec,
) -> TaskPlanValidationIssue | None:
    outcome = subgoal.outcome
    if outcome is None:
        return None
    value = outcome.value.strip()
    value_required = {
        SubgoalOutcomeRelation.EQUALS,
        SubgoalOutcomeRelation.CONTAINS,
        SubgoalOutcomeRelation.MATCHES,
        SubgoalOutcomeRelation.IS_ORDERED_AS,
    }
    value_forbidden = {
        SubgoalOutcomeRelation.IS_VISIBLE,
        SubgoalOutcomeRelation.IS_ABSENT,
        SubgoalOutcomeRelation.IS_AVAILABLE,
        SubgoalOutcomeRelation.IS_CHECKED,
        SubgoalOutcomeRelation.IS_EXPANDED,
        SubgoalOutcomeRelation.IS_COMPLETED,
        SubgoalOutcomeRelation.HAS_CHANGED,
    }
    if outcome.relation in value_required and not (value or outcome.value_obligation_id):
        return TaskPlanValidationIssue(
            code="outcome_value_required",
            detail=subgoal.subgoal_id,
            field="outcome.value",
            required_semantics="non_empty_value_for_relation",
        )
    if outcome.relation in value_forbidden and (value or outcome.value_obligation_id):
        return TaskPlanValidationIssue(
            code="outcome_value_forbidden",
            detail=subgoal.subgoal_id,
            field="outcome.value",
            disallowed_values=tuple(
                item for item in (value, outcome.value_obligation_id) if item
            ),
            required_semantics="empty_value_for_unary_relation",
        )
    return None


def _planning_outcome_is_current(
    outcome: SubgoalOutcome,
    affordance: PlanningAffordanceSummary,
) -> bool:
    state = affordance.current_state
    value = _planning_normalized_value(outcome.value)
    observed_values = tuple(
        _planning_normalized_value(item)
        for item in (state.control_value, *state.selected_options)
        if isinstance(item, str)
    )
    if outcome.relation == SubgoalOutcomeRelation.EQUALS:
        return bool(value) and value in observed_values
    if outcome.relation == SubgoalOutcomeRelation.CONTAINS:
        return bool(value) and any(value in item for item in observed_values)
    if outcome.relation == SubgoalOutcomeRelation.IS_VISIBLE:
        if state.visible is not True:
            return False
        if not value or _planning_boolean_predicate_value(
            value,
            SubgoalOutcomeRelation.IS_VISIBLE,
        ):
            return True
        label = _planning_normalized_value(affordance.label)
        return value in observed_values or value in label
    if outcome.relation == SubgoalOutcomeRelation.IS_AVAILABLE:
        return state.visible is True and state.enabled is not False
    if outcome.relation == SubgoalOutcomeRelation.IS_CHECKED:
        return state.checked is True
    if outcome.relation == SubgoalOutcomeRelation.IS_SELECTED:
        if value and not _planning_boolean_predicate_value(
            value,
            SubgoalOutcomeRelation.IS_SELECTED,
        ):
            return value in tuple(
                _planning_normalized_value(item) for item in state.selected_options
            )
        return state.selected is True or bool(state.selected_options)
    if outcome.relation == SubgoalOutcomeRelation.IS_EXPANDED:
        return state.expanded is True
    return False


def planning_semantic_tokens(value: str) -> tuple[str, ...]:
    aliases = {"box": "input", "field": "input", "text": "input", "textbox": "input"}
    return tuple(
        aliases.get(token, token)
        for token in re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)
        if token
    )


def _planning_affordance_matches_subject(
    subject_tokens: tuple[str, ...],
    affordance: PlanningAffordanceSummary,
) -> bool:
    label_tokens = planning_semantic_tokens(affordance.label)
    current_tokens = {*label_tokens, *planning_semantic_tokens(affordance.role)}
    return label_tokens == subject_tokens or bool(subject_tokens) and set(subject_tokens).issubset(current_tokens)


def _planning_normalized_value(value: str) -> str:
    return " ".join(value.casefold().split())


def _planning_boolean_predicate_value(
    value: str,
    relation: SubgoalOutcomeRelation,
) -> bool:
    relation_markers = {
        SubgoalOutcomeRelation.IS_VISIBLE: {"visible"},
        SubgoalOutcomeRelation.IS_SELECTED: {"selected"},
    }
    return value in {"1", "true", "yes", *relation_markers.get(relation, set())}


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
    families: set[TaskPlanActionFamily] = set()
    for affordance in context.environment.affordances:
        for action in affordance.supported_actions:
            try:
                families.add(TaskPlanActionFamily(action_family_resolution.action_family_value(action)))
            except ValueError:
                pass
    return frozenset(families)


def _action_outcome_relation_compatible(
    action_family: TaskPlanActionFamily,
    relation: SubgoalOutcomeRelation,
) -> bool:
    return relation in task_plan_allowed_outcome_relations(action_family)


def _infer_obligation_action_family(
    obligation: TaskObligationSpec,
    task_operation: OperationClass,
    relation: SubgoalOutcomeRelation,
    context: TaskPlanningContext | None,
) -> TaskPlanActionFamily | None:
    if obligation.interaction_relation is not None:
        return TaskPlanActionFamily.DRAG
    value = action_family_resolution.infer_obligation_action_family_value(
        obligation_kind=obligation.kind.value,
        task_operation=task_operation.value,
        subject=obligation.subject,
        relation=relation.value,
        affordances=context.environment.affordances if context is not None else (),
        allowed_relations_by_family={family.value: frozenset(item.value for item in relations) for family, relations in _ACTION_OUTCOME_RELATIONS.items()},
    )
    return TaskPlanActionFamily(value) if value is not None else None


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
class TaskObligationOutcomeCompiler:
    """Compile immutable TaskSpec obligations into one typed outcome graph."""

    max_subgoals: int = 8

    def compile(self, context: TaskPlanningContext) -> TaskPlan:
        task_spec = context.task_spec
        obligations = task_spec.obligations
        if not obligations:
            raise ValueError("task obligation outcome compilation requires obligations")
        if len(obligations) > self.max_subgoals:
            raise ValueError("task obligation graph exceeds task plan limit")
        return TaskPlan(
            plan_id=f"plan-{uuid4().hex}",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=tuple(
                self._compile_obligation(
                    item,
                    task_spec.operation_class,
                    context,
                )
                for item in obligations
            ),
            assumptions=(),
        )

    @staticmethod
    def _compile_obligation(
        obligation: TaskObligationSpec,
        task_operation: OperationClass,
        context: TaskPlanningContext | None = None,
    ) -> SubgoalSpec:
        relation = SubgoalOutcomeRelation(obligation.relation.value)
        outcome = SubgoalOutcome(
            subject=obligation.subject,
            relation=relation,
            value=(
                obligation.expected_value
                if obligation.value_source == TaskObligationValueSource.LITERAL
                else ""
            ),
            value_obligation_id=(
                obligation.value_obligation_id
                if obligation.value_source == TaskObligationValueSource.OBLIGATION_OUTPUT
                else ""
            ),
        )
        source_refs = obligation_source_refs(obligation, context.task_spec if context is not None else None)
        interaction = interaction_for_state(
            outcome.subject,
            StateCriterionRelation(outcome.relation),
            outcome.value,
            source_refs,
            obligation.interaction_values,
            obligation_value_source(obligation, context.task_spec if context is not None else None),
            obligation.interaction_relation.runtime_tuple
            if obligation.interaction_relation is not None
            else None,
        )
        return SubgoalSpec(
            subgoal_id=obligation.obligation_id,
            objective=outcome.description(),
            depends_on=obligation.depends_on,
            success_criteria=(outcome.description(),),
            evidence_requirements=obligation.evidence_requirements,
            operation_class=(
                task_operation
                if obligation.kind == TaskObligationKind.EFFECT
                else OperationClass.READ_ONLY
            ),
            action_family=_infer_obligation_action_family(obligation, task_operation, relation, context),
            outcome=outcome,
            interaction=interaction,
        )


@dataclass(frozen=True)
class RuleTaskPlanner:
    """Compile canonical immutable obligations."""

    obligation_compiler: TaskObligationOutcomeCompiler = TaskObligationOutcomeCompiler()

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        if not context.task_spec.obligations:
            raise ValueError("rule task planning requires canonical obligations")
        return self.obligation_compiler.compile(context)


TASK_PLANNER_PROMPT_VERSION = "task-planner-v12"
_TASK_PLANNER_SYSTEM_PROMPT = """You are a bounded task planner. Return only a TaskPlanProviderEnvelope. Put the first currently executable and currently unsatisfied outcome in entry_subgoal and later effect-dependent outcomes in remaining_subgoals. Treat current_state as observation evidence only: do not return an entry outcome already proven by its uniquely matching current affordance. Repair an already-satisfied entry by choosing a different pending outcome, never by negating the predicate. Use is_checked only for a checkable state, is_selected only for a selectable state, and is_expanded only for an expandable state; ordinary buttons, links, and textboxes do not gain those states merely because they can be activated. equals, contains, matches, and is_ordered_as require a non-empty value. is_visible, is_absent, is_available, is_checked, is_expanded, is_completed, and has_changed require an empty value; never encode true or false in value. is_selected may name an optional selected value. When completed_subgoal_ids are supplied, return only new or unfinished subgoals; Runtime carries the exact immutable completed units forward.
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
        candidate = await self._provider_candidate(context)
        return _legacy_plan_from_provider_candidate(candidate, context)

    async def generate_candidate(self, context: TaskPlanningContext):  # noqa: ANN201
        from affordance_runtime.task_plan_generators import plan_candidate_from_provider_candidate

        candidate = await self._provider_candidate(context)
        return plan_candidate_from_provider_candidate(candidate, context)

    async def _provider_candidate(self, context: TaskPlanningContext) -> TaskPlanCandidate:
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
        plan = _legacy_plan_from_provider_candidate(candidate, context)
        report = self.validator.validate(
            plan,
            task_spec,
            state_version=context.state_version,
            previous_plan_id=context.current_plan_id,
            previous_plan_version=context.current_plan_version,
            planning_context=context,
        )
        if report.status != TaskPlanValidationStatus.REPAIRABLE:
            return candidate
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
        return repaired_envelope.to_candidate()


def _legacy_plan_from_provider_candidate(
    candidate: TaskPlanCandidate,
    context: TaskPlanningContext,
) -> TaskPlan:
    task_spec = context.task_spec
    return TaskPlan(
        plan_id=f"plan-{uuid4().hex}",
        task_id=task_spec.task_id,
        task_revision=task_spec.revision,
        plan_version=context.current_plan_version + 1,
        supersedes_plan_id=context.current_plan_id,
        based_on_state_version=context.state_version,
        generated_by=TaskPlanSource.LLM,
        subgoals=tuple(
            _legacy_subgoal_from_provider_candidate(item, context)
            for item in candidate.subgoals
        ),
        assumptions=candidate.assumptions,
    )


def _legacy_subgoal_from_provider_candidate(
    item: TaskPlanSubgoalCandidate,
    context: TaskPlanningContext,
) -> SubgoalSpec:
    outcome = SubgoalOutcome.model_validate(item.outcome.model_dump(mode="json"))
    source_refs = task_source_refs(context.task_spec)
    return SubgoalSpec(
        subgoal_id=item.subgoal_id,
        objective=outcome.description(),
        depends_on=item.depends_on,
        success_criteria=(outcome.description(),),
        evidence_requirements=item.evidence_requirements,
        operation_class=item.operation_class,
        action_family=TaskPlanActionFamily(item.action_family),
        outcome=outcome,
        interaction=interaction_for_state(
            outcome.subject,
            StateCriterionRelation(outcome.relation),
            outcome.value,
            source_refs,
        ),
        max_actions=item.max_actions,
        max_recoveries=item.max_recoveries,
    )


@dataclass(frozen=True)
class PlanningRouter:
    """Compile canonical obligations or delegate explicit open-world decomposition."""

    obligation_compiler: TaskObligationOutcomeCompiler = TaskObligationOutcomeCompiler()
    complex_planner: TaskPlannerPort | None = None

    def plan(self, context: TaskPlanningContext) -> TaskPlan | Awaitable[TaskPlan]:
        if context.task_spec.obligations:
            return self.obligation_compiler.compile(context)
        if context.task_spec.task_structure != TaskStructure.MULTI_STAGE:
            raise ValueError("flat task planning requires canonical obligations")
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
        "requested_effects": [
            {
                "operation_class": item.operation_class.value,
                "target": item.target,
                "capability": item.capability,
                "description": item.description,
            }
            for item in task_spec.requested_effects
        ],
        "entities": [{"name": item.name, "value": item.value} for item in task_spec.entities],
        "preferences": list(task_spec.preferences),
        "desired_outputs": list(task_spec.desired_outputs),
        "success_criteria": list(task_spec.success_criteria),
        "constraints": list(task_spec.constraints),
        "semantic_value_constraints": [
            {
                "relation": item.relation.value,
                "value": item.value,
                "target": item.target,
            }
            for item in task_spec.semantic_value_constraints
        ],
        "source_claims": [
            {
                "claim_id": item.claim_id,
                "kind": item.kind.value,
                "statement": item.statement,
                "required": item.required,
            }
            for item in task_spec.source_claims
        ],
        "obligations": [
            {
                "obligation_id": item.obligation_id,
                "kind": item.kind.value,
                "subject": item.subject,
                "relation": item.relation.value,
                "value_source": item.value_source.value,
                "expected_value": item.expected_value,
                "value_obligation_id": item.value_obligation_id,
                "claim_ids": list(item.claim_ids),
                "depends_on": list(item.depends_on),
                "evidence_requirements": list(item.evidence_requirements),
                "blocking": item.blocking,
                "terminal": item.terminal,
            }
            for item in task_spec.obligations
        ],
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
