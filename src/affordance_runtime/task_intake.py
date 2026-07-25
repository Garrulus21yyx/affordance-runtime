"""Typed task-intake schemas and deterministic compilation gates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RequestedEffect(StrictModel):
    operation_class: OperationClass
    target: str = Field(min_length=1)
    capability: str = ""
    description: str = ""
    source_ref: str = Field(min_length=1)


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


class TaskObligationRelation(StrEnum):
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


class TaskObligationValueSource(StrEnum):
    NONE = "none"
    LITERAL = "literal"
    OBSERVATION = "observation"
    OBLIGATION_OUTPUT = "obligation_output"


class SourcedTaskClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=120)
    kind: TaskClaimKind
    statement: str = Field(min_length=1, max_length=480)
    source_ref: str = Field(min_length=1, max_length=240)
    required: bool = True

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
    value_obligation_id: str = Field(default="", max_length=120)
    claim_ids: tuple[str, ...] = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    blocking: bool = True
    terminal: bool = False

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


class IntentDraft(StrictModel):
    objective: str = ""
    entities: tuple[IntentEntity, ...] = ()
    requested_effects: tuple[RequestedEffect, ...] = ()
    preferences: tuple[str, ...] = ()
    desired_outputs: tuple[str, ...] = ()
    candidate_success_criteria: tuple[str, ...] = ()
    candidate_evidence_requirements: tuple[str, ...] = ()
    candidate_constraints: tuple[str, ...] = ()
    candidate_semantic_value_constraints: tuple[SemanticValueConstraint, ...] = ()
    candidate_source_claims: tuple[SourcedTaskClaim, ...] = ()
    candidate_obligations: tuple[TaskObligationSpec, ...] = ()
    candidate_forbidden_effects: tuple[str, ...] = ()
    ambiguities: tuple[IntentAmbiguity, ...] = ()
    source_map: tuple[FieldProvenance, ...] = ()
    confidence_by_field: tuple[FieldConfidence, ...] = ()
    task_structure: TaskStructure = TaskStructure.FLAT

    @model_validator(mode="after")
    def validate_candidate_obligation_graph(self) -> "IntentDraft":
        _validate_task_obligation_graph(
            self.candidate_source_claims,
            self.candidate_obligations,
        )
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
    constraints: tuple[str, ...] = ()
    semantic_value_constraints: tuple[SemanticValueConstraint, ...] = ()
    source_claims: tuple[SourcedTaskClaim, ...] = ()
    obligations: tuple[TaskObligationSpec, ...] = ()
    forbidden_effects: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    requested_capabilities: tuple[str, ...] = ()
    ambiguity_status: str = "resolved"
    source_request_ref: str = Field(min_length=1)
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


class CompilationResult(StrictModel):
    status: CompilationStatus
    request_id: str
    draft: IntentDraft
    task_spec: TaskSpec | None = None
    issues: tuple[CompilationIssue, ...] = ()


@dataclass(frozen=True)
class CompilationPolicy:
    allowed_operations: frozenset[OperationClass] = field(default_factory=lambda: frozenset(OperationClass))
    allowed_requested_capabilities: frozenset[str] | None = None
    denied_capabilities: frozenset[str] = frozenset()
    forbidden_effects: frozenset[str] = frozenset()


@dataclass(frozen=True)
class IntentDraftValidator:
    policy: CompilationPolicy = field(default_factory=CompilationPolicy)

    def compile(
        self,
        request: UserRequest,
        draft: IntentDraft,
        *,
        revision: int = 1,
        task_id: str | None = None,
    ) -> CompilationResult:
        unsupported: list[CompilationIssue] = []
        if not draft.objective.strip():
            unsupported.append(CompilationIssue(code="missing_objective", field="objective"))
        if not draft.requested_effects:
            unsupported.append(CompilationIssue(code="missing_effect", field="requested_effects"))
        if not draft.candidate_success_criteria:
            unsupported.append(CompilationIssue(code="missing_success_criteria", field="candidate_success_criteria"))
        for index, effect in enumerate(draft.requested_effects):
            if not _source_ref_authorized(request, effect.source_ref):
                unsupported.append(
                    CompilationIssue(
                        code="unsourced_requested_effect",
                        field=f"requested_effects[{index}]",
                        detail=effect.source_ref,
                    )
                )
        for index, entity in enumerate(draft.entities):
            if not _source_ref_authorized(request, entity.source_ref):
                unsupported.append(
                    CompilationIssue(
                        code="unsourced_intent_entity",
                        field=f"entities[{index}]",
                        detail=entity.source_ref,
                    )
                )
        for index, constraint in enumerate(draft.candidate_semantic_value_constraints):
            if not _source_ref_authorized(request, constraint.source_ref):
                unsupported.append(
                    CompilationIssue(
                        code="unsourced_semantic_value_constraint",
                        field=f"candidate_semantic_value_constraints[{index}]",
                        detail=constraint.source_ref,
                    )
                )
        for index, claim in enumerate(draft.candidate_source_claims):
            if not _source_ref_authorized(request, claim.source_ref):
                unsupported.append(
                    CompilationIssue(
                        code="unsourced_task_claim",
                        field=f"candidate_source_claims[{index}]",
                        detail=claim.source_ref,
                    )
                )
        if any(issue.code in {"missing_objective", "missing_effect"} for issue in unsupported):
            return CompilationResult(
                status=CompilationStatus.UNSUPPORTED,
                request_id=request.request_id,
                draft=draft,
                issues=tuple(unsupported),
            )

        blocking = [item for item in draft.ambiguities if item.blocking or item.risk == AmbiguityRisk.HIGH]
        if blocking:
            return CompilationResult(
                status=CompilationStatus.NEEDS_CLARIFICATION,
                request_id=request.request_id,
                draft=draft,
                issues=tuple(
                    CompilationIssue(code="blocking_ambiguity", field=item.field, detail=item.reason)
                    for item in blocking
                ),
            )

        if unsupported:
            return CompilationResult(
                status=CompilationStatus.UNSUPPORTED,
                request_id=request.request_id,
                draft=draft,
                issues=tuple(unsupported),
            )

        conflicts: list[CompilationIssue] = []
        forbidden = {_normalized(item) for item in self.policy.forbidden_effects}
        forbidden.update(_normalized(item) for item in draft.candidate_forbidden_effects)
        for effect in draft.requested_effects:
            if effect.operation_class not in self.policy.allowed_operations:
                conflicts.append(
                    CompilationIssue(
                        code="operation_denied",
                        field="requested_effects",
                        detail=effect.operation_class.value,
                    )
                )
            if effect.capability and effect.capability in self.policy.denied_capabilities:
                conflicts.append(
                    CompilationIssue(
                        code="capability_denied",
                        field="requested_effects",
                        detail=effect.capability,
                    )
                )
            if (
                effect.capability
                and self.policy.allowed_requested_capabilities is not None
                and effect.capability not in self.policy.allowed_requested_capabilities
            ):
                conflicts.append(
                    CompilationIssue(
                        code="capability_not_allowed",
                        field="requested_effects",
                        detail=effect.capability,
                    )
                )
            effect_terms = {_normalized(effect.target), _normalized(effect.description)}
            if forbidden.intersection(effect_terms):
                conflicts.append(
                    CompilationIssue(
                        code="forbidden_effect",
                        field="requested_effects",
                        detail=effect.target,
                    )
                )
        if conflicts:
            return CompilationResult(
                status=CompilationStatus.POLICY_CONFLICT,
                request_id=request.request_id,
                draft=draft,
                issues=tuple(conflicts),
            )

        operation = max(
            (effect.operation_class for effect in draft.requested_effects),
            key=_operation_rank,
        )
        task_spec = TaskSpec(
            task_id=task_id or request.request_id,
            revision=revision,
            objective=draft.objective.strip(),
            operation_class=operation,
            task_structure=draft.task_structure,
            targets=_ordered_unique(effect.target for effect in draft.requested_effects),
            requested_effects=draft.requested_effects,
            entities=draft.entities,
            preferences=draft.preferences,
            desired_outputs=draft.desired_outputs,
            success_criteria=draft.candidate_success_criteria,
            constraints=draft.candidate_constraints,
            semantic_value_constraints=draft.candidate_semantic_value_constraints,
            source_claims=draft.candidate_source_claims,
            obligations=draft.candidate_obligations,
            forbidden_effects=draft.candidate_forbidden_effects,
            evidence_requirements=draft.candidate_evidence_requirements,
            requested_capabilities=_ordered_unique(
                effect.capability for effect in draft.requested_effects if effect.capability
            ),
            ambiguity_status="resolved" if not draft.ambiguities else "non_blocking",
            source_request_ref=request.request_id,
            field_provenance=draft.source_map,
        )
        return CompilationResult(
            status=CompilationStatus.READY,
            request_id=request.request_id,
            draft=draft,
            task_spec=task_spec,
        )


def _validate_task_obligation_graph(
    claims: tuple[SourcedTaskClaim, ...],
    obligations: tuple[TaskObligationSpec, ...],
) -> None:
    if not claims and not obligations:
        return
    if not claims or not obligations:
        raise ValueError("task claims and obligations must be supplied together")

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


def _operation_rank(operation: OperationClass) -> int:
    return {
        OperationClass.READ_ONLY: 0,
        OperationClass.NAVIGATION: 1,
        OperationClass.REVERSIBLE_WRITE: 2,
        OperationClass.EXTERNAL_SIDE_EFFECT: 3,
        OperationClass.IRREVERSIBLE: 4,
    }[operation]


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _ordered_unique(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if str(item)))


def _source_ref_authorized(request: UserRequest, source_ref: str) -> bool:
    sources = (
        request.request_id,
        *request.conversation_refs,
        *request.attachment_refs,
        *request.target_refs,
        *request.profile_context_refs,
    )
    return any(source_ref == item or source_ref.startswith(f"{item}:") for item in sources)
