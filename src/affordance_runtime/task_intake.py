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
    candidate_forbidden_effects: tuple[str, ...] = ()
    ambiguities: tuple[IntentAmbiguity, ...] = ()
    source_map: tuple[FieldProvenance, ...] = ()
    confidence_by_field: tuple[FieldConfidence, ...] = ()
    task_structure: TaskStructure = TaskStructure.FLAT


class TaskSpec(StrictModel):
    schema_version: str = "1.2"
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
    forbidden_effects: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    requested_capabilities: tuple[str, ...] = ()
    ambiguity_status: str = "resolved"
    source_request_ref: str = Field(min_length=1)
    field_provenance: tuple[FieldProvenance, ...] = ()
    created_at_s: float = Field(default_factory=time)

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
        for index, constraint in enumerate(draft.candidate_semantic_value_constraints):
            if not _source_ref_authorized(request, constraint.source_ref):
                unsupported.append(
                    CompilationIssue(
                        code="unsourced_semantic_value_constraint",
                        field=f"candidate_semantic_value_constraints[{index}]",
                        detail=constraint.source_ref,
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
