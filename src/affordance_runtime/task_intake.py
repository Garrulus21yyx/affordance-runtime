"""Typed task-intake schemas and deterministic compilation gates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.effect_authority_contracts import (
    EffectAuthorizationScope,
    EffectClass,
    Externality,
    ResourceScopeRef,
    Reversibility,
)
from affordance_runtime.material_contracts import MaterialBinding, MaterialEffectKind
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceValidityMode,
    OutputSpec,
    SatisfactionMode,
    SuccessExpression,
)


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
            if not self.destination.strip() or self.relative_offset is not None or self.destination_ordinal is not None:
                raise ValueError("drag-to relation requires only a destination")
        elif self.kind == TaskInteractionRelationKind.RELATIVE_POSITION:
            if self.destination or self.relative_offset in {None, 0} or self.destination_ordinal is not None:
                raise ValueError("relative-position relation requires only a nonzero offset")
        elif self.destination or self.relative_offset is not None or self.destination_ordinal is None:
            raise ValueError("absolute-position relation requires only a destination ordinal")
        return self


class TaskInteractionOperationKind(StrEnum):
    AUTO = "auto"
    FOCUS = "focus"


class RequestedEffect(StrictModel):
    effect_id: str = Field(default="", max_length=240)
    operation_class: OperationClass
    material_effect_kind: MaterialEffectKind = MaterialEffectKind.NONE
    target: str = Field(min_length=1)
    capability: str = ""
    description: str = ""
    source_ref: str = Field(min_length=1)
    interaction_relation: TaskInteractionRelationSpec | None = None
    interaction_operation: TaskInteractionOperationKind = TaskInteractionOperationKind.AUTO
    operation_ref: str = Field(default="", max_length=240)


class IntentAmbiguity(StrictModel):
    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    blocking: bool = False
    risk: AmbiguityRisk = AmbiguityRisk.LOW


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


class TaskSemanticPayload(StrictModel):
    """Typed admitted meaning carried by one flat requirement row."""

    kind: Literal["effect", "entity", "constraint", "preference", "output"]
    subject: str = Field(min_length=1, max_length=480)
    target_identity: str = Field(default="", max_length=480)
    destination_identity: str = Field(default="", max_length=480)
    relation: str = Field(default="", max_length=120)
    value: str = Field(default="", max_length=2_000)
    operation_class: OperationClass | None = None
    material_effect_kind: MaterialEffectKind = MaterialEffectKind.NONE
    capability: str = Field(default="", max_length=240)
    effect_authorization_scope: EffectAuthorizationScope | None = None


class TaskRequirement(StrictModel):
    """One admitted semantic row; never a progress or dependency node."""

    requirement_id: str = Field(min_length=1, max_length=240)
    payload: TaskSemanticPayload
    source_anchor_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> "TaskRequirement":
        if len(self.source_anchor_refs) != len(set(self.source_anchor_refs)):
            raise ValueError("requirement source anchor refs must be unique")
        if any(not item.strip() for item in self.source_anchor_refs):
            raise ValueError("requirement source anchor refs cannot be blank")
        return self


class CriterionSourceBinding(StrictModel):
    """Admitted link from one criterion identity to canonical requirements."""

    criterion_id: str = Field(min_length=1, max_length=240)
    requirement_refs: tuple[str, ...] = Field(min_length=1)


class InputBinding(StrictModel):
    """Stable typed input value with its admitted source lineage."""

    binding_id: str = Field(min_length=1, max_length=240)
    requirement_ref: str = Field(min_length=1, max_length=240)
    field: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2_000)
    source_ref: str = Field(min_length=1, max_length=480)
    lineage_kind: str = Field(min_length=1, max_length=120)
    source_anchor_ref: str = Field(default="", max_length=240)
    external_field_ref: str = Field(default="", max_length=480)
    confirmation_ref: str = Field(default="", max_length=480)
    material_binding_ref: str = Field(default="", max_length=240)
    material_binding_digest: str = Field(default="", max_length=80)

    @classmethod
    def from_material(cls, binding: MaterialBinding) -> "InputBinding":
        payload = binding.model_dump(mode="json")
        digest = (
            "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        )
        return cls(
            binding_id=binding.binding_id,
            requirement_ref=binding.effect_ref,
            field=binding.field.value,
            value=binding.value,
            source_ref=binding.source_ref,
            lineage_kind=binding.binding_kind.value,
            source_anchor_ref=binding.source_anchor_ref,
            external_field_ref=binding.external_field_ref,
            confirmation_ref=binding.confirmation_ref,
            material_binding_ref=binding.binding_id,
            material_binding_digest=digest,
        )


class TaskRiskPolicy(StrictModel):
    maximum_operation_class: OperationClass
    approval_required: bool = False
    authoritative_final_recheck_required: bool = False


class TaskSpec(StrictModel):
    schema_version: str = "2.0"
    task_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    objective: str = Field(min_length=1)
    operation_class: OperationClass
    requirements: tuple[TaskRequirement, ...] = ()
    inputs: tuple[InputBinding, ...] = ()
    allowed_effect_refs: tuple[str, ...] = ()
    hard_constraint_refs: tuple[str, ...] = ()
    preference_refs: tuple[str, ...] = ()
    forbidden_effect_refs: tuple[str, ...] = ()
    capability_ceiling: tuple[str, ...] = ()
    risk_policy: TaskRiskPolicy | None = None
    success: SuccessExpression
    required_outputs: tuple[OutputSpec, ...] = ()
    criterion_source_bindings: tuple[CriterionSourceBinding, ...] = ()
    constraint_criterion_ids: tuple[str, ...] = ()
    external_effect_criterion_ids: tuple[str, ...] = ()
    final_recheck_criterion_ids: tuple[str, ...] = ()
    source_request_ref: str = Field(min_length=1)
    source_envelope_ref: str = ""
    source_binding_digest: str = ""
    created_at_s: float = Field(default_factory=time)

    @model_validator(mode="after")
    def validate_canonical_refs(self) -> "TaskSpec":
        requirement_ids = tuple(item.requirement_id for item in self.requirements)
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("task requirement ids must be unique")
        known = set(requirement_ids)
        by_id = {item.requirement_id: item for item in self.requirements}
        for label, refs in (
            ("allowed effect", self.allowed_effect_refs),
            ("hard constraint", self.hard_constraint_refs),
            ("preference", self.preference_refs),
            ("forbidden effect", self.forbidden_effect_refs),
        ):
            if len(refs) != len(set(refs)):
                raise ValueError(f"{label} refs must be unique")
            if set(refs) - known:
                raise ValueError(f"{label} refs must name admitted requirements")
        role_checks = (
            (
                "allowed effect",
                self.allowed_effect_refs,
                lambda item: item.payload.kind == "effect" and item.payload.relation != "forbidden",
            ),
            (
                "forbidden effect",
                self.forbidden_effect_refs,
                lambda item: item.payload.kind == "effect" and item.payload.relation == "forbidden",
            ),
            ("hard constraint", self.hard_constraint_refs, lambda item: item.payload.kind == "constraint"),
            ("preference", self.preference_refs, lambda item: item.payload.kind == "preference"),
        )
        for label, refs, predicate in role_checks:
            if any(not predicate(by_id[ref]) for ref in refs):
                raise ValueError(f"{label} refs must name requirements with the matching semantic role")
        if any(not by_id[ref].payload.target_identity.strip() for ref in self.allowed_effect_refs):
            raise ValueError("allowed effect requirements require an exact target identity")
        role_ref_sets = [set(refs) for _, refs, _ in role_checks]
        if any(left & right for index, left in enumerate(role_ref_sets) for right in role_ref_sets[index + 1 :]):
            raise ValueError("task semantic role refs must be mutually exclusive")
        canonical_role_refs = (
            {
                item.requirement_id
                for item in self.requirements
                if item.payload.kind == "effect" and item.payload.relation != "forbidden"
            },
            {item.requirement_id for item in self.requirements if item.payload.kind == "constraint"},
            {item.requirement_id for item in self.requirements if item.payload.kind == "preference"},
            {
                item.requirement_id
                for item in self.requirements
                if item.payload.kind == "effect" and item.payload.relation == "forbidden"
            },
        )
        supplied_role_refs = (
            set(self.allowed_effect_refs),
            set(self.hard_constraint_refs),
            set(self.preference_refs),
            set(self.forbidden_effect_refs),
        )
        if supplied_role_refs != canonical_role_refs:
            raise ValueError("every canonical role requirement must appear exactly in its matching ref container")
        binding_ids = tuple(item.binding_id for item in self.inputs)
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("task input binding ids must be unique")
        if any(item.requirement_ref not in known for item in self.inputs):
            raise ValueError("task input binding must name an admitted requirement")
        if any(output.requirement_ref and output.requirement_ref not in known for output in self.required_outputs):
            raise ValueError("required output must name an admitted requirement")
        output_refs = tuple(output.requirement_ref for output in self.required_outputs)
        if any(not ref for ref in output_refs) or len(output_refs) != len(set(output_refs)):
            raise ValueError("required outputs must have unique canonical requirement refs")
        canonical_output_refs = {item.requirement_id for item in self.requirements if item.payload.kind == "output"}
        if set(output_refs) != canonical_output_refs:
            raise ValueError("every canonical output requirement must have exactly one required OutputSpec")
        success_bindings = success_criterion_requirement_bindings(self.success)
        if any(set(refs) - known for refs in success_bindings.values()):
            raise ValueError("success criterion requirement refs must name admitted requirements")
        criterion_ids = tuple(item.criterion_id for item in self.criterion_source_bindings)
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("criterion source binding ids must be unique")
        if any(
            not binding.requirement_refs or set(binding.requirement_refs) - known
            for binding in self.criterion_source_bindings
        ):
            raise ValueError("criterion source binding must name admitted requirements")
        if set(criterion_ids) & set(success_bindings):
            raise ValueError("success criterion source identity is owned by its exact leaf requirement_refs")
        allowed_requirements = tuple(by_id[ref] for ref in self.allowed_effect_refs)
        expected_operation = max(
            (item.payload.operation_class or OperationClass.READ_ONLY for item in allowed_requirements),
            key=operation_class_rank,
            default=OperationClass.READ_ONLY,
        )
        if self.operation_class != expected_operation:
            raise ValueError("TaskSpec operation_class must equal the maximum allowed effect operation class")
        expected_capabilities = tuple(
            dict.fromkeys(item.payload.capability for item in allowed_requirements if item.payload.capability)
        )
        if self.capability_ceiling != expected_capabilities:
            raise ValueError("TaskSpec capability_ceiling must equal canonical effect capabilities")
        if self.risk_policy is not None:
            if self.risk_policy.maximum_operation_class != self.operation_class:
                raise ValueError("TaskSpec risk policy operation class must match canonical effects")
            high_risk = self.operation_class in {
                OperationClass.EXTERNAL_SIDE_EFFECT,
                OperationClass.IRREVERSIBLE,
            }
            if high_risk and not self.risk_policy.approval_required:
                raise ValueError("TaskSpec approval policy cannot weaken canonical effect risk")
            if high_risk and not self.risk_policy.authoritative_final_recheck_required:
                raise ValueError("TaskSpec final recheck policy cannot weaken canonical effect risk")
        high_risk = self.operation_class in {
            OperationClass.EXTERNAL_SIDE_EFFECT,
            OperationClass.IRREVERSIBLE,
        }
        if high_risk:
            if not self.external_effect_criterion_ids:
                raise ValueError("high-risk TaskSpec requires external-effect criteria")
            if not self.final_recheck_criterion_ids:
                raise ValueError("high-risk TaskSpec requires final-recheck criteria")
            if set(self.external_effect_criterion_ids) & set(self.final_recheck_criterion_ids):
                raise ValueError("high-risk external-effect and final-recheck criteria must be distinct")
            policies = success_criterion_policies(self.success)
            for criterion_id in (*self.external_effect_criterion_ids, *self.final_recheck_criterion_ids):
                refs = success_bindings.get(criterion_id, ())
                if not refs or not set(refs).intersection(self.allowed_effect_refs):
                    raise ValueError("high-risk criterion must be a success leaf bound to an allowed effect")
            for criterion_id in self.external_effect_criterion_ids:
                policy = policies.get(criterion_id)
                if policy is None or (
                    policy.satisfaction != SatisfactionMode.ACTION_CAUSED
                    or policy.validity != EvidenceValidityMode.RECENT_ACTION
                    or not policy.causal_lineage_required
                ):
                    raise ValueError("external-effect criterion requires ACTION_CAUSED RECENT_ACTION causal policy")
            for criterion_id in self.final_recheck_criterion_ids:
                policy = policies.get(criterion_id)
                if policy is None or (
                    policy.validity != EvidenceValidityMode.FINAL_RECHECK
                    or policy.minimum_assurance != AssuranceLevel.AUTHORITATIVE
                ):
                    raise ValueError("final-recheck criterion requires FINAL_RECHECK and AUTHORITATIVE policy")
        return self

    @property
    def identity(self) -> str:
        payload = self.model_dump_json(exclude={"created_at_s"})
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def success_criterion_requirement_bindings(expression: SuccessExpression) -> dict[str, tuple[str, ...]]:
    """Return the exact admitted requirement refs declared by every success leaf."""

    if expression.operator == "criterion":
        return {expression.criterion_id: expression.requirement_refs}
    rows: dict[str, tuple[str, ...]] = {}
    for child in expression.children:
        for criterion_id, refs in success_criterion_requirement_bindings(child).items():
            previous = rows.get(criterion_id)
            if previous is not None and previous != refs:
                raise ValueError("success criterion identity cannot bind different requirements")
            rows[criterion_id] = refs
    return rows


def success_criterion_policies(expression: SuccessExpression) -> dict[str, CriterionPolicy]:
    """Return the exact typed policy owned by every success leaf."""

    if expression.operator == "criterion":
        assert expression.policy is not None
        return {expression.criterion_id: expression.policy}
    rows: dict[str, CriterionPolicy] = {}
    for child in expression.children:
        for criterion_id, policy in success_criterion_policies(child).items():
            previous = rows.get(criterion_id)
            if previous is not None and previous != policy:
                raise ValueError("success criterion identity cannot own different policies")
            rows[criterion_id] = policy
    return rows


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


def operation_class_rank(operation: OperationClass) -> int:
    return {
        OperationClass.READ_ONLY: 0,
        OperationClass.NAVIGATION: 1,
        OperationClass.REVERSIBLE_WRITE: 2,
        OperationClass.EXTERNAL_SIDE_EFFECT: 3,
        OperationClass.IRREVERSIBLE: 4,
    }[operation]


def task_requirements_by_kind(
    task_spec: TaskSpec,
    kind: Literal["effect", "entity", "constraint", "preference", "output"],
) -> tuple[TaskRequirement, ...]:
    return tuple(item for item in task_spec.requirements if item.payload.kind == kind)


def task_allowed_effects(task_spec: TaskSpec) -> tuple[TaskRequirement, ...]:
    allowed = set(task_spec.allowed_effect_refs)
    return tuple(item for item in task_spec.requirements if item.requirement_id in allowed)


def task_effect_targets(task_spec: TaskSpec) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.payload.subject for item in task_allowed_effects(task_spec)))


def task_constraint_values(task_spec: TaskSpec) -> tuple[str, ...]:
    refs = set(task_spec.hard_constraint_refs)
    return tuple(item.payload.subject for item in task_spec.requirements if item.requirement_id in refs)


def task_semantic_scope_terms(task_spec: TaskSpec) -> tuple[str, ...]:
    """Typed admitted semantics used for scope, never objective prose."""

    forbidden = set(task_spec.forbidden_effect_refs)
    return tuple(
        dict.fromkeys(
            value
            for item in task_spec.requirements
            if item.requirement_id not in forbidden
            for value in (item.payload.subject, item.payload.value)
            if value.strip()
        )
    )


def task_requires_decomposition(task_spec: TaskSpec) -> bool:
    """Derive planning complexity from admitted semantics, not intake shape hints."""

    return len(task_spec.allowed_effect_refs) > 1 or len(task_spec.required_outputs) > 1


def canonical_effect_requirements(
    subjects: Iterable[str],
    operation_class: OperationClass,
    source_anchor_ref: str,
    capabilities: Iterable[str] = (),
    *,
    resource_refs: Iterable[str] | None = None,
    operation_ref_override: str = "",
    effect_class_override: EffectClass | None = None,
) -> tuple[TaskRequirement, ...]:
    """Build explicit canonical effect rows for internal fixtures and adapters."""

    capability = next(iter(capabilities), "")
    effect_class = {
        OperationClass.READ_ONLY: EffectClass.READ,
        OperationClass.NAVIGATION: EffectClass.NAVIGATE,
        OperationClass.REVERSIBLE_WRITE: EffectClass.UPDATE,
        OperationClass.EXTERNAL_SIDE_EFFECT: EffectClass.INVOKE,
        OperationClass.IRREVERSIBLE: EffectClass.DELETE,
    }[operation_class]
    operation_ref = {
        OperationClass.READ_ONLY: "resource.read@v1",
        OperationClass.NAVIGATION: "navigation.navigate@v1",
        OperationClass.REVERSIBLE_WRITE: "resource.update@v1",
        OperationClass.EXTERNAL_SIDE_EFFECT: "external.commit@v1",
        OperationClass.IRREVERSIBLE: "resource.delete@v1",
    }[operation_class]
    externality = (
        Externality.EXTERNAL_SYSTEM
        if operation_class == OperationClass.EXTERNAL_SIDE_EFFECT
        else Externality.LOCAL
    )
    reversibility = (
        Reversibility.IRREVERSIBLE
        if operation_class == OperationClass.IRREVERSIBLE
        else Reversibility.REVERSIBLE
    )
    subject_values = tuple(str(subject) for subject in subjects)
    resource_values = tuple(str(value) for value in resource_refs) if resource_refs is not None else subject_values
    if len(subject_values) != len(resource_values):
        raise ValueError("canonical effect subjects and resource refs must have equal length")
    return tuple(
        TaskRequirement(
            requirement_id=f"requirement:effect:{index}",
            payload=TaskSemanticPayload(
                kind="effect",
                subject=subject,
                target_identity=resource_ref,
                operation_class=operation_class,
                capability=capability,
                effect_authorization_scope=EffectAuthorizationScope(
                    requirement_ref=f"requirement:effect:{index}",
                    effect_class=effect_class_override or effect_class,
                    resource_scope=ResourceScopeRef(resource_ref, (source_anchor_ref,)),
                    operation_constraint=operation_ref_override or operation_ref,
                    externality=externality,
                    reversibility=reversibility,
                    minimum_source_assurance=(
                        AssuranceLevel.AUTHORITATIVE
                        if externality == Externality.EXTERNAL_SYSTEM or reversibility == Reversibility.IRREVERSIBLE
                        else AssuranceLevel.STRUCTURAL
                    ),
                    required_capabilities=frozenset({capability} if capability else ()),
                    approval_policy_ref=(
                        "exact-contract@v1"
                        if externality == Externality.EXTERNAL_SYSTEM or reversibility == Reversibility.IRREVERSIBLE
                        else ""
                    ),
                    completion_policy_ref=f"task-success:requirement:effect:{index}",
                ),
            ),
            source_anchor_refs=(source_anchor_ref,),
        )
        for index, (subject, resource_ref) in enumerate(
            zip(subject_values, resource_values, strict=True),
            start=1,
        )
    )


def canonical_effect_requirement_refs(subjects: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"requirement:effect:{index}" for index, _ in enumerate(subjects, start=1))
