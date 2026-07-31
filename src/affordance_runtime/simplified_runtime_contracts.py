"""Neutral contracts for the simplified active-step runtime architecture.

These types are foundation-only. They intentionally do not import StateKernel,
Coordinator, TaskPlan implementations, executors, verifiers, trace, adapters, or
benchmarks. Runtime hookup and authority cutover are separate slices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, TypeAlias

from affordance_runtime.semantics import (
    CriterionRelation,
    EvidencePolicy,
    EvidenceStrength,
)

StateCriterionRelation = CriterionRelation
CriterionEvidencePolicy = EvidencePolicy


class CompositeCriterionOperator(StrEnum):
    ALL_OF = "all_of"
    ANY_OF = "any_of"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    STALE = "stale"


class ActionOutcomeStatus(StrEnum):
    VERIFIED_EFFECT = "verified_effect"
    NO_EFFECT = "no_effect"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"
    STALE = "stale"


class StepActivityStatus(StrEnum):
    ACTIVE = "active"
    READY_NOT_ACTIVATED = "ready_not_activated"
    COMPLETED = "completed"
    NO_PLAN = "no_plan"


CriterionRole: TypeAlias = Literal["completion", "precondition"]
FrozenScalar: TypeAlias = str | bool | int | float | None


class ValueExprKind(StrEnum):
    LITERAL = "literal"
    SOURCE_VALUE = "source_value"


class ElementOperationKind(StrEnum):
    AUTO = "auto"
    FOCUS = "focus"
    SCROLL_FORWARD = "scroll_forward"
    SCROLL_BACKWARD = "scroll_backward"


@dataclass(frozen=True)
class ValueExpr:
    kind: ValueExprKind
    values: tuple[FrozenScalar, ...]
    source_refs: tuple[SourceReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ValueExprKind):
            raise ValueError("unsupported value expression kind")
        _require_tuple("value expression values", self.values)
        if not self.values:
            raise ValueError("value expression cannot be empty")
        for value in self.values:
            _reject_mutable_value(value)
        _require_tuple("value expression source refs", self.source_refs)
        if not self.source_refs:
            raise ValueError("value expression source refs cannot be empty")


@dataclass(frozen=True)
class ElementIntent:
    target: str
    source_refs: tuple[SourceReference, ...]
    role: str = ""
    ordinal: int | None = None
    match_by_role: bool = False
    enabler: ElementIntent | None = None
    collection_scope: str = ""
    collection_cardinality: int | None = None
    operation: ElementOperationKind = ElementOperationKind.AUTO
    relative_size: Literal["", "smallest", "largest"] = ""

    def __post_init__(self) -> None:
        _require_nonblank("element intent target", self.target)
        _require_tuple("element intent source refs", self.source_refs)
        if not self.source_refs:
            raise ValueError("element intent source refs cannot be empty")
        if self.role:
            _require_nonblank("element intent role", self.role)
        if self.ordinal is not None and self.ordinal < 1:
            raise ValueError("element intent ordinal must be positive")
        if self.match_by_role and not self.role:
            raise ValueError("role-only element intent requires a role")
        if self.enabler is not None and self.enabler.enabler is not None:
            raise ValueError("element intent enablers cannot be nested")
        if self.collection_scope:
            _require_nonblank("element intent collection scope", self.collection_scope)
        if self.collection_cardinality is not None:
            if self.collection_cardinality < 1:
                raise ValueError("element intent collection cardinality must be positive")
            if not self.collection_scope:
                raise ValueError("element intent collection cardinality requires a scope")
        if not isinstance(self.operation, ElementOperationKind):
            raise ValueError("unsupported element operation")
        if self.relative_size not in {"", "smallest", "largest"}:
            raise ValueError("unsupported relative-size selector")


@dataclass(frozen=True)
class CollectionIntent:
    collection: ElementIntent
    members: ValueExpr


@dataclass(frozen=True)
class RelationIntent:
    source: ElementIntent
    destination: ElementIntent | None
    relation: str
    destination_offset: int | None = None
    destination_ordinal: int | None = None

    def __post_init__(self) -> None:
        _require_nonblank("relation intent relation", self.relation)
        destination_forms = sum(
            value is not None
            for value in (self.destination, self.destination_offset, self.destination_ordinal)
        )
        if destination_forms != 1:
            raise ValueError("relation intent requires exactly one destination form")
        if self.destination_offset == 0:
            raise ValueError("relation destination offset cannot be zero")


@dataclass(frozen=True)
class RegionIntent:
    region: str
    capability: str
    source_refs: tuple[SourceReference, ...]

    def __post_init__(self) -> None:
        _require_nonblank("region intent region", self.region)
        _require_nonblank("region intent capability", self.capability)
        _require_tuple("region intent source refs", self.source_refs)
        if not self.source_refs:
            raise ValueError("region intent source refs cannot be empty")


InteractionIntent: TypeAlias = ElementIntent | CollectionIntent | RelationIntent | RegionIntent

SPATIAL_POINT_CAPABILITY = "spatial.point.current_geometry"


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    source_unit_id: str
    claim_id: str = ""
    field_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("source_id", self.source_id)
        _require_nonblank("source_unit_id", self.source_unit_id)
        if self.claim_id:
            _require_nonblank("claim_id", self.claim_id)
        _require_tuple("field_path", self.field_path)
        _require_no_blank_values("field_path", self.field_path)


def interaction_for_state(
    subject: str,
    relation: StateCriterionRelation,
    expected_value: FrozenScalar,
    source_refs: tuple[SourceReference, ...],
    interaction_values: tuple[str, ...] = (),
    value_source: tuple[str, tuple[SourceReference, ...]] | None = None,
    interaction_relation: tuple[str, str, int | None, int | None] | None = None,
    interaction_capability: str = "",
    interaction_operation: str = "auto",
) -> InteractionIntent:
    """Project one sourced state outcome into its typed interaction intent."""

    if interaction_capability == SPATIAL_POINT_CAPABILITY:
        return RegionIntent(subject, interaction_capability, source_refs)
    target_name, element_role, role_only, ordinal = _element_identity(
        subject,
        expected_value,
    )
    is_collection = relation == StateCriterionRelation.IS_SELECTED
    target = ElementIntent(
        target_name,
        source_refs,
        role=("collection" if is_collection else element_role),
        ordinal=ordinal,
        match_by_role=is_collection or role_only,
        relative_size=_relative_size_selector(subject),
        operation=ElementOperationKind(interaction_operation),
    )
    if interaction_relation is not None and not is_collection:
        interaction_kind, destination_subject, destination_offset, destination_ordinal = interaction_relation
        destination: ElementIntent | None = None
        if destination_subject:
            projected = interaction_for_state(
                destination_subject,
                StateCriterionRelation.IS_AVAILABLE,
                None,
                source_refs,
            )
            if isinstance(projected, ElementIntent):
                destination = projected
        return RelationIntent(target, destination, interaction_kind, destination_offset, destination_ordinal)
    if value_source is not None and not is_collection:
        source_subject, value_source_refs = value_source
        source = interaction_for_state(
            source_subject,
            StateCriterionRelation.IS_AVAILABLE,
            None,
            value_source_refs,
        )
        if isinstance(source, ElementIntent):
            return RelationIntent(source, target, "value_transfer")
    if (
        relation != StateCriterionRelation.IS_SELECTED
        or expected_value is None
        or expected_value == ""
    ):
        return target
    return CollectionIntent(
        target,
        ValueExpr(
            ValueExprKind.LITERAL,
            interaction_values or (expected_value,),
            source_refs,
        ),
    )


def _relative_size_selector(subject: str) -> Literal["", "smallest", "largest"]:
    tokens = set(re.findall(r"[a-z0-9]+", subject.casefold()))
    if tokens & {"small", "smaller", "smallest"}:
        return "smallest"
    if tokens & {"large", "larger", "largest"}:
        return "largest"
    return ""


_ELEMENT_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "listbox",
        "menuitem",
        "radio",
        "searchbox",
        "slider",
        "tab",
        "textbox",
        "treeitem",
        "scroll_region",
    }
)
_ROLE_PHRASE_ALIASES = {
    "date_field": "textbox",
    "search_field": "searchbox",
    "text_field": "textbox",
    "text_input": "textbox",
    "text_input_field": "textbox",
}


def _element_identity(
    subject: str,
    expected_value: FrozenScalar,
) -> tuple[str, str, bool, int | None]:
    """Separate an explicit leading/trailing role token from a semantic label."""

    structured = _structured_element_identity(subject)
    if structured is not None:
        label, role, role_only = structured
        return label, role, role_only, None
    qualified_role = _qualified_role_identity(subject)
    if qualified_role is not None:
        return qualified_role, qualified_role, True, None
    role_ordinal = _compound_role_ordinal_identity(subject)
    if role_ordinal is not None:
        return role_ordinal
    role_value = _role_value_identity(subject, expected_value)
    if role_value is not None:
        return role_value
    semantic_identifier = _semantic_state_identifier(subject, expected_value)
    if semantic_identifier is not None:
        return semantic_identifier
    tokens = subject.replace("_", " ").split()
    if not tokens:
        return subject, "", False, None
    first = tokens[0].casefold()
    last = tokens[-1].casefold()
    role = first if first in _ELEMENT_ROLES else last if last in _ELEMENT_ROLES else ""
    if not role:
        return subject, "", False, None
    label_tokens = tokens[1:] if first == role else tokens[:-1]
    label = " ".join(label_tokens)
    return (label or role), role, not label, None


def _semantic_state_identifier(
    subject: str,
    expected_value: FrozenScalar,
) -> tuple[str, str, bool, int | None] | None:
    if subject.casefold() == "textarea":
        return "textarea", "textbox", True, None
    role_alias = _ROLE_PHRASE_ALIASES.get(subject.casefold())
    if role_alias:
        return role_alias, role_alias, True, None
    if "_" not in subject:
        return None
    tokens = tuple(item for item in subject.split("_") if item)
    roles = tuple(item.casefold() for item in tokens if item.casefold() in _ELEMENT_ROLES)
    if len(roles) != 1:
        return None
    role = roles[0]
    remaining = [item for item in tokens if item.casefold() != role]
    remaining = [item for item in remaining if item.casefold() != "state"]
    if role == "slider":
        remaining = [item for item in remaining if item.casefold() != "value"]
    expected = "" if expected_value is None else str(expected_value).casefold()
    if expected:
        remaining = [item for item in remaining if item.casefold() != expected]
    ordinal = None
    if role in {"checkbox", "radio"}:
        ordinal_token = next((item for item in remaining if item.isdigit()), "")
        if ordinal_token and int(ordinal_token) > 0:
            ordinal = int(ordinal_token)
            remaining.remove(ordinal_token)
    label = " ".join(remaining)
    return (label or role), role, not label, ordinal


def _compound_role_ordinal_identity(
    subject: str,
) -> tuple[str, str, bool, int | None] | None:
    match = re.fullmatch(
        r"(?P<role>[a-z]+)(?:_button)?(?:_(?P<ordinal>\d+)|\[(?P<bracket_ordinal>\d+)\])(?:_state)?",
        subject.casefold(),
    )
    if match is None or match.group("role") not in _ELEMENT_ROLES:
        return None
    ordinal = int(match.group("ordinal") or match.group("bracket_ordinal"))
    if ordinal < 1:
        return None
    role = match.group("role")
    return role, role, True, ordinal


def _role_value_identity(
    subject: str,
    expected_value: FrozenScalar,
) -> tuple[str, str, bool, int | None] | None:
    identity, separator, value = subject.rpartition(":")
    if not separator or expected_value is None:
        return None
    if value.strip().casefold() != str(expected_value).strip().casefold():
        return None
    return _semantic_state_identifier(identity.strip(), None)


def _structured_element_identity(subject: str) -> tuple[str, str, bool] | None:
    """Decode the bounded ``role:label=value`` semantic descriptor grammar."""

    role_text, separator, label_text = subject.partition(":label")
    role = role_text.strip().casefold()
    if not separator or role not in _ELEMENT_ROLES:
        return None
    if not label_text or label_text[0] not in {"=", ":"}:
        return None
    label = label_text[1:].strip()
    if len(label) >= 2 and label[0] == label[-1] and label[0] in {"'", '"'}:
        label = label[1:-1].strip()
    if not label or ":" in label:
        return None
    return label, role, False


def _qualified_role_identity(subject: str) -> str | None:
    """Decode a bounded semantic namespace followed by an element role."""

    match = re.fullmatch(r"[a-z][a-z0-9_.-]*:(?P<role>[a-z_]+)", subject.casefold())
    if match is None:
        return None
    role = match.group("role")
    return role if role in _ELEMENT_ROLES else None


@dataclass(frozen=True)
class _CriterionBase:
    criterion_id: str
    source_refs: tuple[SourceReference, ...]
    role: CriterionRole = "completion"

    def _validate_base(self) -> None:
        _require_nonblank("criterion_id", self.criterion_id)
        _require_tuple("source_refs", self.source_refs)
        if not self.source_refs:
            raise ValueError("criterion source refs cannot be empty")
        if self.role not in {"completion", "precondition"}:
            raise ValueError("unsupported criterion role")


@dataclass(frozen=True)
class StateCriterion(_CriterionBase):
    subject: str = ""
    relation: StateCriterionRelation = StateCriterionRelation.EQUALS
    expected_value: FrozenScalar = None
    evidence_policy: CriterionEvidencePolicy = field(
        default_factory=lambda: CriterionEvidencePolicy(
            minimum_strength=EvidenceStrength.INDEPENDENT,
            allowed_source_kinds=("dom_state",),
        ),
    )

    def __post_init__(self) -> None:
        self._validate_base()
        _require_nonblank("subject", self.subject)
        if not isinstance(self.relation, StateCriterionRelation):
            raise ValueError("unsupported relation")
        _reject_mutable_value(self.expected_value)


ValueCriterion = StateCriterion
PresenceCriterion = StateCriterion
AbsenceCriterion = StateCriterion
NavigationCriterion = StateCriterion


@dataclass(frozen=True)
class ArtifactCriterion(StateCriterion):
    artifact_ref: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_nonblank("artifact_ref", self.artifact_ref)


@dataclass(frozen=True)
class ApiCriterion(StateCriterion):
    api_ref: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_nonblank("api_ref", self.api_ref)


@dataclass(frozen=True)
class CompositeCriterion(_CriterionBase):
    operator: CompositeCriterionOperator = CompositeCriterionOperator.ALL_OF
    child_criterion_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self._validate_base()
        if not isinstance(self.operator, CompositeCriterionOperator):
            raise ValueError("unsupported composite operator")
        _require_tuple("child_criterion_ids", self.child_criterion_ids)
        if not self.child_criterion_ids:
            raise ValueError("composite criterion children cannot be empty")
        _require_unique_nonblank("child criterion ids", self.child_criterion_ids)
        if self.criterion_id in self.child_criterion_ids:
            raise ValueError("composite criterion cycle is not allowed")


Criterion: TypeAlias = (
    StateCriterion
    | ArtifactCriterion
    | ApiCriterion
    | CompositeCriterion
)


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    objective: str
    interaction: InteractionIntent
    completion_criteria: tuple[Criterion, ...]
    source_refs: tuple[SourceReference, ...]
    depends_on: tuple[str, ...] = ()
    preconditions: tuple[Criterion, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("step_id", self.step_id)
        _require_nonblank("objective", self.objective)
        if not isinstance(
            self.interaction,
            (ElementIntent, CollectionIntent, RelationIntent, RegionIntent),
        ):
            raise ValueError("unsupported interaction intent")
        _require_tuple("completion_criteria", self.completion_criteria)
        if not self.completion_criteria:
            raise ValueError("step completion criteria cannot be empty")
        _require_tuple("source_refs", self.source_refs)
        if not self.source_refs:
            raise ValueError("step source refs cannot be empty")
        _require_tuple("depends_on", self.depends_on)
        _require_unique_nonblank("step dependencies", self.depends_on)
        if self.step_id in self.depends_on:
            raise ValueError("step cannot depend on itself")
        _require_tuple("preconditions", self.preconditions)
        for criterion in self.completion_criteria:
            if criterion.role == "precondition":
                raise ValueError("precondition cannot be used as a completion criterion")
        for criterion in self.preconditions:
            if criterion.role != "precondition":
                raise ValueError("step preconditions must use precondition role")


@dataclass(frozen=True)
class TaskPlanView:
    plan_id: str
    plan_version: int
    task_spec_identity: str
    task_revision: int
    steps: tuple[StepSpec, ...]
    active_step_id: str | None

    def __post_init__(self) -> None:
        _require_nonblank("plan_id", self.plan_id)
        if self.plan_version < 1:
            raise ValueError("plan version must be positive")
        _require_nonblank("task_spec_identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        _require_tuple("steps", self.steps)
        if not self.steps:
            raise ValueError("task plan view steps cannot be empty")
        step_ids = tuple(step.step_id for step in self.steps)
        _require_unique_nonblank("step ids", step_ids)
        if self.active_step_id is not None and self.active_step_id not in step_ids:
            raise ValueError("active step must exist in task plan view")
        known = set(step_ids)
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError("step dependency is not present in task plan view")

    @property
    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.steps)


@dataclass(frozen=True)
class StepProgressView:
    plan_id: str
    plan_version: int
    active_step_id: str | None
    activity_status: StepActivityStatus = StepActivityStatus.NO_PLAN
    completed_step_ids: tuple[str, ...] = ()
    failed_step_ids: tuple[str, ...] = ()
    ready_step_ids: tuple[str, ...] = ()
    evidence_by_step_id: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("plan_id", self.plan_id)
        if self.plan_version < 1:
            raise ValueError("plan version must be positive")
        if self.active_step_id is not None:
            _require_nonblank("active_step_id", self.active_step_id)
        if not isinstance(self.activity_status, StepActivityStatus):
            raise ValueError("unsupported step activity status")
        _require_tuple("completed_step_ids", self.completed_step_ids)
        _require_tuple("failed_step_ids", self.failed_step_ids)
        _require_tuple("ready_step_ids", self.ready_step_ids)
        _require_unique_nonblank("completed step ids", self.completed_step_ids)
        _require_unique_nonblank("failed step ids", self.failed_step_ids)
        _require_unique_nonblank("ready step ids", self.ready_step_ids)
        overlap = set(self.completed_step_ids) & set(self.failed_step_ids)
        if overlap:
            raise ValueError("completed and failed step ids cannot overlap")
        if self.active_step_id is not None and (
            self.active_step_id in self.completed_step_ids
            or self.active_step_id in self.failed_step_ids
        ):
            raise ValueError("active step cannot be completed or failed")
        if (
            self.activity_status == StepActivityStatus.ACTIVE
            and self.active_step_id is None
        ):
            raise ValueError("active status requires active_step_id")
        if (
            self.activity_status != StepActivityStatus.ACTIVE
            and self.active_step_id is not None
        ):
            raise ValueError("only active status may carry active_step_id")
        if (
            self.activity_status == StepActivityStatus.READY_NOT_ACTIVATED
            and not self.ready_step_ids
        ):
            raise ValueError("ready-not-activated status requires ready steps")
        if (
            self.activity_status == StepActivityStatus.COMPLETED
            and self.ready_step_ids
        ):
            raise ValueError("completed status cannot carry ready steps")
        _validate_tuple_map("evidence_by_step_id", self.evidence_by_step_id)


@dataclass(frozen=True)
class ObservationIdentity:
    snapshot_id: str
    page_revision: str
    environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)


@dataclass(frozen=True)
class ExecutionAttempt:
    attempt_id: str
    contract_id: str
    contract_hash: str
    issued_at_state_version: int
    action_kind: str
    semantic_target_id: str
    pre_observation: ObservationIdentity
    active_step_id: str = ""

    def __post_init__(self) -> None:
        _require_nonblank("attempt_id", self.attempt_id)
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        if self.issued_at_state_version < 0:
            raise ValueError("issued state version cannot be negative")
        _require_nonblank("action_kind", self.action_kind)
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        if self.active_step_id:
            _require_nonblank("active_step_id", self.active_step_id)


@dataclass(frozen=True)
class StateDelta:
    subject_id: str
    relation: StateCriterionRelation
    before_value: FrozenScalar
    after_value: FrozenScalar
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank("subject_id", self.subject_id)
        if not isinstance(self.relation, StateCriterionRelation):
            raise ValueError("unsupported relation")
        _reject_mutable_value(self.before_value)
        _reject_mutable_value(self.after_value)
        _require_tuple("evidence_refs", self.evidence_refs)
        _require_unique_nonblank("evidence refs", self.evidence_refs)


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    contract_id: str
    contract_hash: str
    pre_snapshot_id: str
    post_observation: ObservationIdentity
    verified_criterion_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    state_deltas: tuple[StateDelta, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, VerificationStatus):
            raise ValueError("unsupported verification status")
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_tuple("verified_criterion_ids", self.verified_criterion_ids)
        _require_unique_nonblank("verified criterion ids", self.verified_criterion_ids)
        _require_tuple("evidence_refs", self.evidence_refs)
        _require_unique_nonblank("evidence refs", self.evidence_refs)
        _require_tuple("state_deltas", self.state_deltas)
        if self.status == VerificationStatus.PASSED and not self.evidence_refs:
            raise ValueError("passed verification requires evidence refs")


@dataclass(frozen=True)
class ActionOutcome:
    outcome_id: str
    attempt: ExecutionAttempt
    verification: VerificationResult
    status: ActionOutcomeStatus
    step_id: str
    receipt_contract_id: str = ""
    receipt_success: bool = False
    receipt_backend: str = ""
    receipt_error_code: str = ""
    receipt_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("outcome_id", self.outcome_id)
        if not isinstance(self.status, ActionOutcomeStatus):
            raise ValueError("unsupported action outcome status")
        _require_nonblank("step_id", self.step_id)
        if self.receipt_contract_id and self.receipt_contract_id != self.attempt.contract_id:
            raise ValueError("action outcome receipt contract mismatch")
        if self.receipt_backend:
            _require_nonblank("receipt_backend", self.receipt_backend)
        _require_tuple("receipt_evidence_refs", self.receipt_evidence_refs)
        _require_unique_nonblank("receipt evidence refs", self.receipt_evidence_refs)
        if self.attempt.contract_id != self.verification.contract_id:
            raise ValueError("action outcome contract identity mismatch")
        if self.attempt.contract_hash != self.verification.contract_hash:
            raise ValueError("action outcome contract hash mismatch")
        if self.attempt.pre_observation.snapshot_id != self.verification.pre_snapshot_id:
            raise ValueError("action outcome pre snapshot mismatch")
        if (
            self.status == ActionOutcomeStatus.VERIFIED_EFFECT
            and self.verification.status != VerificationStatus.PASSED
        ):
            raise ValueError("verified effect outcome requires passed verification")


@dataclass(frozen=True)
class ActionOutcomeSummary:
    outcome_id: str
    status: ActionOutcomeStatus
    step_id: str
    verified_criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_outcome(cls, outcome: ActionOutcome) -> ActionOutcomeSummary:
        return cls(
            outcome_id=outcome.outcome_id,
            status=outcome.status,
            step_id=outcome.step_id,
            verified_criterion_ids=outcome.verification.verified_criterion_ids,
            evidence_refs=outcome.verification.evidence_refs,
        )

    def __post_init__(self) -> None:
        _require_nonblank("outcome_id", self.outcome_id)
        if not isinstance(self.status, ActionOutcomeStatus):
            raise ValueError("unsupported action outcome status")
        _require_nonblank("step_id", self.step_id)
        _require_tuple("verified_criterion_ids", self.verified_criterion_ids)
        _require_tuple("evidence_refs", self.evidence_refs)


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
    _require_no_blank_values(label, values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _reject_mutable_value(value: object) -> None:
    if isinstance(value, (dict, list, set, bytearray)):
        raise ValueError("criterion values must be deeply immutable")
    if isinstance(value, tuple):
        for item in value:
            _reject_mutable_value(item)


def _validate_tuple_map(label: str, values: tuple[tuple[str, tuple[str, ...]], ...]) -> None:
    _require_tuple(label, values)
    seen: set[str] = set()
    for key, refs in values:
        _require_nonblank(label, key)
        if key in seen:
            raise ValueError(f"{label} keys must be unique")
        seen.add(key)
        _require_tuple(label, refs)
        _require_unique_nonblank(label, refs)
