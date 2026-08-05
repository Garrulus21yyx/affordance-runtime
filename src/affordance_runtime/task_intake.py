"""Typed task-intake schemas and deterministic compilation gates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from time import time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.verification.contracts import OutputSpec, SuccessExpression


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OperationClass(StrEnum):
    READ_ONLY = "read_only"
    NAVIGATION = "navigation"
    REVERSIBLE_WRITE = "reversible_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    IRREVERSIBLE = "irreversible"


class TaskStructure(StrEnum):
    FLAT = "flat"
    MULTI_STAGE = "multi_stage"


class CompilationStatus(StrEnum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    POLICY_CONFLICT = "policy_conflict"
    UNSUPPORTED = "unsupported"


class AmbiguityRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UserRequest(StrictModel):
    request_id: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    conversation_refs: tuple[str, ...] = ()
    attachment_refs: tuple[str, ...] = ()
    target_refs: tuple[str, ...] = ()
    caller_identity: str = ""
    channel: str = "standalone"
    profile_context_refs: tuple[str, ...] = ()
    locale: str = ""
    time_context: str = ""


class IntentEntity(StrictModel):
    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)


class TaskInteractionRelationKind(StrEnum):
    DRAG_TO = "drag_to"
    RELATIVE_POSITION = "relative_position"
    ABSOLUTE_POSITION = "absolute_position"


class TaskInteractionRelationSpec(StrictModel):
    """Source-authorized relation semantics; observed endpoints remain runtime-bound."""

    kind: TaskInteractionRelationKind
    destination: str = Field(default="", max_length=480)
    relative_offset: int | None = Field(default=None, ge=-100, le=100)
    destination_ordinal: int | None = Field(default=None, ge=1, le=10_000)

    @property
    def runtime_tuple(self) -> tuple[str, str, int | None, int | None]:
        return self.kind.value, self.destination, self.relative_offset, self.destination_ordinal

    @model_validator(mode="after")
    def validate_endpoint_form(self) -> "TaskInteractionRelationSpec":
        if self.kind == TaskInteractionRelationKind.DRAG_TO:
            if (
                not self.destination.strip()
                or self.relative_offset is not None
                or self.destination_ordinal is not None
            ):
                raise ValueError("drag-to relation requires only a destination")
        elif self.kind == TaskInteractionRelationKind.RELATIVE_POSITION:
            if (
                self.destination
                or self.relative_offset in {None, 0}
                or self.destination_ordinal is not None
            ):
                raise ValueError("relative-position relation requires only a nonzero offset")
        elif self.destination or self.relative_offset is not None or self.destination_ordinal is None:
            raise ValueError("absolute-position relation requires only a destination ordinal")
        return self


class TaskInteractionOperationKind(StrEnum):
    AUTO = "auto"
    FOCUS = "focus"


class RequestedEffect(StrictModel):
    operation_class: OperationClass
    target: str = Field(min_length=1)
    capability: str = ""
    description: str = ""
    source_ref: str = Field(min_length=1)
    interaction_relation: TaskInteractionRelationSpec | None = None
    interaction_operation: TaskInteractionOperationKind = TaskInteractionOperationKind.AUTO


class IntentAmbiguity(StrictModel):
    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    blocking: bool = False
    risk: AmbiguityRisk = AmbiguityRisk.LOW


class FieldProvenance(StrictModel):
    field: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_kind: str = "user"


class FieldConfidence(StrictModel):
    field: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class SemanticValueRelation(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"
    SUFFIX = "suffix"


class TaskClaimKind(StrEnum):
    EFFECT = "effect"
    VALUE = "value"
    DEPENDENCY = "dependency"
    TERMINAL = "terminal"
    CONSTRAINT = "constraint"


class TaskObligationKind(StrEnum):
    PREDICATE = "predicate"
    EFFECT = "effect"


TaskObligationRelation = CriterionRelation


class TaskObligationValueSource(StrEnum):
    NONE = "none"
    LITERAL = "literal"
    OBSERVATION = "observation"
    OBLIGATION_OUTPUT = "obligation_output"


class EvidenceKind(StrEnum):
    DOM_STATE = "dom_state"
    ACCESSIBILITY_STATE = "accessibility_state"
    VISUAL_STATE = "visual_state"
    API_STATE = "api_state"
    FILE_RECEIPT = "file_receipt"
    DOWNLOAD_RECEIPT = "download_receipt"
    DEVICE_STATE = "device_state"
    HUMAN_CONFIRMATION = "human_confirmation"


class EvidenceRequirement(StrictModel):
    kind: EvidenceKind
    subject: str = Field(min_length=1, max_length=480)
    relation: TaskObligationRelation
    value_ref: str = Field(default="", max_length=240)
    minimum_strength: str = Field(min_length=1, max_length=80)
    source_constraints: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_constraints(self) -> "EvidenceRequirement":
        if len(self.source_constraints) != len(set(self.source_constraints)):
            raise ValueError("evidence requirement source constraints must be unique")
        if any(not value.strip() for value in self.source_constraints):
            raise ValueError("evidence requirement source constraints cannot be blank")
        return self


class GraphConstructionSource(StrEnum):
    COMPATIBILITY = "compatibility"
    CANONICAL_COMPILER = "canonical_compiler"
    MODEL_PROPOSAL = "model_proposal"
    PARENT = "parent"


class SourcedTaskClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=120)
    kind: TaskClaimKind
    statement: str = Field(min_length=1, max_length=480)
    source_ref: str = Field(min_length=1, max_length=240)
    required: bool = True
    source_unit_ids: tuple[str, ...] = ()
    construction_source: GraphConstructionSource = GraphConstructionSource.COMPATIBILITY

    @model_validator(mode="after")
    def reject_blank_claim(self) -> "SourcedTaskClaim":
        if not self.claim_id.strip() or not self.statement.strip():
            raise ValueError("task claim identity and statement cannot be blank")
        return self


class TaskObligationSpec(StrictModel):
    """One sourced desired state or effect in an immutable dependency graph."""

    obligation_id: str = Field(min_length=1, max_length=120)
    kind: TaskObligationKind
    subject: str = Field(min_length=1, max_length=480)
    relation: TaskObligationRelation
    value_source: TaskObligationValueSource = TaskObligationValueSource.NONE
    expected_value: str = Field(default="", max_length=480)
    interaction_values: tuple[str, ...] = ()
    interaction_relation: TaskInteractionRelationSpec | None = None
    interaction_capability: str = Field(default="", max_length=120)
    interaction_operation: TaskInteractionOperationKind = TaskInteractionOperationKind.AUTO
    value_obligation_id: str = Field(default="", max_length=120)
    claim_ids: tuple[str, ...] = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    typed_evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    blocking: bool = True
    terminal: bool = False
    construction_source: GraphConstructionSource = GraphConstructionSource.COMPATIBILITY

    @model_validator(mode="after")
    def validate_value_and_identity(self) -> "TaskObligationSpec":
        if not self.obligation_id.strip() or not self.subject.strip():
            raise ValueError("task obligation identity and subject cannot be blank")
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("task obligation claim ids must be unique")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("task obligation dependencies must be unique")
        if self.obligation_id in self.depends_on:
            raise ValueError("task obligation cannot depend on itself")
        if any(not item.strip() for item in (*self.claim_ids, *self.depends_on)):
            raise ValueError("task obligation references cannot be blank")
        if any(not item.strip() for item in self.evidence_requirements):
            raise ValueError("task obligation evidence requirements cannot be blank")
        if len(self.interaction_values) != len(set(self.interaction_values)) or any(
            not item.strip() for item in self.interaction_values
        ):
            raise ValueError("task obligation interaction values must be unique and nonblank")
        if self.interaction_values and (
            self.relation != TaskObligationRelation.IS_SELECTED
            or self.value_source != TaskObligationValueSource.LITERAL
        ):
            raise ValueError("interaction values require a literal selection obligation")
        if self.interaction_relation is not None and (
            self.kind != TaskObligationKind.EFFECT
            or self.relation != TaskObligationRelation.HAS_CHANGED
            or self.value_source != TaskObligationValueSource.NONE
        ):
            raise ValueError("interaction relation requires a value-free changed effect")
        if self.interaction_capability and not self.interaction_capability.strip():
            raise ValueError("interaction capability cannot be blank")
        if self.construction_source == GraphConstructionSource.CANONICAL_COMPILER and not self.typed_evidence_requirements:
            raise ValueError("canonical task obligation requires typed evidence")
        if self.blocking and not self.evidence_requirements:
            raise ValueError("blocking task obligation requires independent evidence")
        if self.terminal and not self.blocking:
            raise ValueError("terminal task obligation must be blocking")

        value_relations = {
            TaskObligationRelation.EQUALS,
            TaskObligationRelation.CONTAINS,
            TaskObligationRelation.MATCHES,
            TaskObligationRelation.IS_ORDERED_AS,
        }
        if self.relation in value_relations and self.value_source not in {
            TaskObligationValueSource.LITERAL,
            TaskObligationValueSource.OBLIGATION_OUTPUT,
        }:
            raise ValueError("value relation requires a literal or obligation output")
        if self.value_source == TaskObligationValueSource.LITERAL:
            if not self.expected_value.strip() or self.value_obligation_id:
                raise ValueError("literal obligation value requires only expected_value")
        elif self.value_source == TaskObligationValueSource.OBLIGATION_OUTPUT:
            if (
                not self.value_obligation_id
                or self.value_obligation_id not in self.depends_on
                or self.expected_value
            ):
                raise ValueError(
                    "obligation output value must name one declared dependency"
                )
        elif self.value_source == TaskObligationValueSource.OBSERVATION:
            if (
                self.kind != TaskObligationKind.PREDICATE
                or self.relation != TaskObligationRelation.IS_AVAILABLE
                or self.expected_value
                or self.value_obligation_id
            ):
                raise ValueError(
                    "observation value must be an available predicate without a supplied value"
                )
        elif self.expected_value or self.value_obligation_id:
            raise ValueError("value-free obligation cannot carry a value")

        if (
            self.relation not in value_relations
            and self.relation != TaskObligationRelation.IS_SELECTED
            and self.value_source
            not in {
                TaskObligationValueSource.NONE,
                TaskObligationValueSource.OBSERVATION,
            }
        ):
            raise ValueError("unary obligation relation cannot carry a supplied value")
        return self


class SemanticValueConstraint(StrictModel):
    relation: SemanticValueRelation
    value: str = Field(min_length=1, max_length=240)
    target: str = Field(default="", max_length=240)
    source_ref: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def reject_blank_semantics(self) -> "SemanticValueConstraint":
        if not self.value.strip():
            raise ValueError("semantic value constraint cannot be blank")
        return self



class TaskSpec(StrictModel):
    schema_version: str = "1.3"
    task_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    objective: str = Field(min_length=1)
    operation_class: OperationClass
    task_structure: TaskStructure = TaskStructure.FLAT
    targets: tuple[str, ...]
    requested_effects: tuple[RequestedEffect, ...] = ()
    entities: tuple[IntentEntity, ...] = ()
    preferences: tuple[str, ...] = ()
    desired_outputs: tuple[str, ...] = ()
    success_criteria: tuple[str, ...]
    success: SuccessExpression | None = None
    required_outputs: tuple[OutputSpec, ...] = ()
    constraint_criterion_ids: tuple[str, ...] = ()
    external_effect_criterion_ids: tuple[str, ...] = ()
    final_recheck_criterion_ids: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    semantic_value_constraints: tuple[SemanticValueConstraint, ...] = ()
    source_claims: tuple[SourcedTaskClaim, ...] = ()
    obligations: tuple[TaskObligationSpec, ...] = ()
    forbidden_effects: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    requested_capabilities: tuple[str, ...] = ()
    ambiguity_status: str = "resolved"
    source_request_ref: str = Field(min_length=1)
    # Canonical intake binds accepted meaning to the thin source envelope.
    # The graph-shaped compatibility fields above remain only until P3-4.
    source_envelope_ref: str = ""
    source_binding_digest: str = ""
    field_provenance: tuple[FieldProvenance, ...] = ()
    created_at_s: float = Field(default_factory=time)

    @model_validator(mode="after")
    def validate_obligation_graph(self) -> "TaskSpec":
        _validate_task_obligation_graph(self.source_claims, self.obligations)
        return self

    @property
    def identity(self) -> str:
        payload = self.model_dump_json(exclude={"created_at_s"})
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class CompilationIssue(StrictModel):
    code: str = Field(min_length=1)
    field: str = ""
    detail: str = ""



@dataclass(frozen=True)
class CompilationPolicy:
    allowed_operations: frozenset[OperationClass] = field(default_factory=lambda: frozenset(OperationClass))
    allowed_requested_capabilities: frozenset[str] | None = None
    denied_capabilities: frozenset[str] = frozenset()
    forbidden_effects: frozenset[str] = frozenset()
def _validate_task_obligation_graph(
    claims: tuple[SourcedTaskClaim, ...],
    obligations: tuple[TaskObligationSpec, ...],
) -> None:
    if not claims and not obligations:
        return
    if not claims or not obligations:
        raise ValueError("task claims and obligations must be supplied together")
    if len(obligations) > 8:
        raise ValueError("task obligation graph exceeds task plan limit")

    claim_by_id = {item.claim_id: item for item in claims}
    if len(claim_by_id) != len(claims):
        raise ValueError("task claim ids must be unique")
    obligation_by_id = {item.obligation_id: item for item in obligations}
    if len(obligation_by_id) != len(obligations):
        raise ValueError("task obligation ids must be unique")

    known_claim_ids = set(claim_by_id)
    known_obligation_ids = set(obligation_by_id)
    covered_claim_ids: set[str] = set()
    terminal_ids = {
        item.obligation_id for item in obligations if item.terminal
    }
    if not terminal_ids:
        raise ValueError("task obligation graph requires a terminal obligation")

    dependencies: dict[str, set[str]] = {}
    for obligation in obligations:
        unknown_claims = set(obligation.claim_ids) - known_claim_ids
        if unknown_claims:
            raise ValueError("task obligation references an unknown claim")
        unknown_dependencies = set(obligation.depends_on) - known_obligation_ids
        if unknown_dependencies:
            raise ValueError("task obligation references an unknown dependency")
        if (
            obligation.value_obligation_id
            and obligation.value_obligation_id not in known_obligation_ids
        ):
            raise ValueError("task obligation references an unknown value dependency")
        covered_claim_ids.update(obligation.claim_ids)
        dependencies[obligation.obligation_id] = set(obligation.depends_on)

    required_claim_ids = {
        item.claim_id for item in claims if item.required
    }
    if required_claim_ids - covered_claim_ids:
        raise ValueError("required task claim is not covered by an obligation")
    if any(terminal_id in values for values in dependencies.values() for terminal_id in terminal_ids):
        raise ValueError("terminal task obligation must be a graph sink")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError("task obligation graph cannot contain a cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in dependencies[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for obligation_id in obligation_by_id:
        visit(obligation_id)

    terminal_ancestors = set(terminal_ids)
    pending = list(terminal_ids)
    while pending:
        current = pending.pop()
        for dependency in dependencies[current]:
            if dependency not in terminal_ancestors:
                terminal_ancestors.add(dependency)
                pending.append(dependency)
    blocking_ids = {
        item.obligation_id for item in obligations if item.blocking
    }
    if blocking_ids - terminal_ancestors:
        raise ValueError("blocking task obligation must lead to a terminal obligation")


def operation_class_rank(operation: OperationClass) -> int:
    return {
        OperationClass.READ_ONLY: 0,
        OperationClass.NAVIGATION: 1,
        OperationClass.REVERSIBLE_WRITE: 2,
        OperationClass.EXTERNAL_SIDE_EFFECT: 3,
        OperationClass.IRREVERSIBLE: 4,
    }[operation]
