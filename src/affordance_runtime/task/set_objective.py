"""Scope-relative quantified objective contracts and deterministic reduction.

Parsers and perception providers contribute candidates or predicate evidence.
Only the scope owner may declare enumeration complete, and only this reducer
may turn that evidence into an executable member or completion certificate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, TypeAlias

from affordance_runtime.immutable import freeze_json, to_json_compatible

_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,95}")
class ScopeExtent(StrEnum):
    CURRENT_VIEWPORT = "current_viewport"
    CURRENT_CONTAINER = "current_container"
    CURRENT_DOCUMENT = "current_document"
    CURRENT_APPLICATION_STATE = "current_application_state"


class ScopeCoverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    FAILED = "failed"


class SetQuantifier(StrEnum):
    EXACTLY_ONE = "exactly_one"
    ALL_IN_CLOSED_SCOPE = "all_in_closed_scope"
    ALL_CURRENTLY_VISIBLE = "all_currently_visible"
    ALL_DISCOVERED_UNDER_BUDGET = "all_discovered_under_budget"


class PredicateTruth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class PredicateAssurance(StrEnum):
    STRUCTURAL = "structural"
    DERIVED = "derived"
    VISUAL = "visual"
    SEMANTIC = "semantic"
    SEMANTIC_UNCALIBRATED = "semantic_uncalibrated"
    SEMANTIC_CALIBRATED = "semantic_calibrated"


@dataclass(frozen=True)
class FactEquals:
    field_name: str
    expected: object

    def __post_init__(self) -> None:
        if _FIELD.fullmatch(self.field_name) is None:
            raise ValueError("predicate fact field is invalid")
        object.__setattr__(self, "expected", freeze_json(self.expected))


@dataclass(frozen=True)
class VisualConcept:
    concept: str

    def __post_init__(self) -> None:
        if not self.concept.strip() or len(self.concept) > 160:
            raise ValueError("visual concept is invalid")


@dataclass(frozen=True)
class VisualAttribute:
    attribute: str

    def __post_init__(self) -> None:
        if not self.attribute.strip() or len(self.attribute) > 160:
            raise ValueError("visual attribute is invalid")


@dataclass(frozen=True)
class SpatialRelation:
    relation: str
    argument: object

    def __post_init__(self) -> None:
        if _FIELD.fullmatch(self.relation) is None:
            raise ValueError("spatial relation is invalid")
        object.__setattr__(self, "argument", freeze_json(self.argument))


@dataclass(frozen=True)
class And:
    operands: tuple["PredicateExpr", ...]

    def __post_init__(self) -> None:
        values = tuple(self.operands)
        if len(values) < 2 or any(not isinstance(item, _PREDICATE_TYPES) for item in values):
            raise ValueError("and predicate requires at least two typed operands")
        object.__setattr__(self, "operands", values)


@dataclass(frozen=True)
class Or:
    operands: tuple["PredicateExpr", ...]

    def __post_init__(self) -> None:
        values = tuple(self.operands)
        if len(values) < 2 or any(not isinstance(item, _PREDICATE_TYPES) for item in values):
            raise ValueError("or predicate requires at least two typed operands")
        object.__setattr__(self, "operands", values)


@dataclass(frozen=True)
class Not:
    operand: "PredicateExpr"

    def __post_init__(self) -> None:
        if not isinstance(self.operand, _PREDICATE_TYPES):
            raise TypeError("not predicate requires one typed operand")


PredicateExpr: TypeAlias = FactEquals | VisualConcept | VisualAttribute | SpatialRelation | And | Or | Not
_PREDICATE_TYPES = (FactEquals, VisualConcept, VisualAttribute, SpatialRelation, And, Or, Not)


def predicate_public_value(predicate: PredicateExpr) -> dict[str, object]:
    """Return the closed, type-discriminated public predicate algebra."""

    if isinstance(predicate, FactEquals):
        return {
            "kind": "fact_equals",
            "field_name": predicate.field_name,
            "expected": to_json_compatible(predicate.expected),
        }
    if isinstance(predicate, VisualConcept):
        return {"kind": "visual_concept", "concept": predicate.concept}
    if isinstance(predicate, VisualAttribute):
        return {"kind": "visual_attribute", "attribute": predicate.attribute}
    if isinstance(predicate, SpatialRelation):
        return {
            "kind": "spatial_relation",
            "relation": predicate.relation,
            "argument": to_json_compatible(predicate.argument),
        }
    if isinstance(predicate, Not):
        return {"kind": "not", "operand": predicate_public_value(predicate.operand)}
    return {
        "kind": "and" if isinstance(predicate, And) else "or",
        "operands": [predicate_public_value(item) for item in predicate.operands],
    }


def predicate_digest(predicate: PredicateExpr) -> str:
    payload = json.dumps(
        predicate_public_value(predicate),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluate_predicate(
    predicate: PredicateExpr,
    public_fields: Mapping[str, object],
    semantic_evidence: Mapping[str, PredicateTruth] | None = None,
) -> PredicateTruth:
    """Evaluate the supported predicate algebra using strong Kleene logic."""

    if isinstance(predicate, FactEquals):
        if predicate.field_name not in public_fields:
            return PredicateTruth.UNKNOWN
        return (
            PredicateTruth.TRUE
            if public_fields[predicate.field_name] == predicate.expected
            else PredicateTruth.FALSE
        )
    if isinstance(predicate, SpatialRelation):
        if predicate.relation not in public_fields:
            return PredicateTruth.UNKNOWN
        return (
            PredicateTruth.TRUE
            if public_fields[predicate.relation] == predicate.argument
            else PredicateTruth.FALSE
        )
    if isinstance(predicate, VisualConcept | VisualAttribute):
        evidence = semantic_evidence or {}
        return evidence.get(predicate_digest(predicate), PredicateTruth.UNKNOWN)
    if isinstance(predicate, Not):
        return {
            PredicateTruth.TRUE: PredicateTruth.FALSE,
            PredicateTruth.FALSE: PredicateTruth.TRUE,
            PredicateTruth.UNKNOWN: PredicateTruth.UNKNOWN,
        }[evaluate_predicate(predicate.operand, public_fields, semantic_evidence)]
    values = tuple(
        evaluate_predicate(item, public_fields, semantic_evidence)
        for item in predicate.operands
    )
    if isinstance(predicate, And):
        if PredicateTruth.FALSE in values:
            return PredicateTruth.FALSE
        return PredicateTruth.UNKNOWN if PredicateTruth.UNKNOWN in values else PredicateTruth.TRUE
    if PredicateTruth.TRUE in values:
        return PredicateTruth.TRUE
    return PredicateTruth.UNKNOWN if PredicateTruth.UNKNOWN in values else PredicateTruth.FALSE


@dataclass(frozen=True)
class ScopeSpec:
    scope_id: str
    root_entity_id: str
    extent: ScopeExtent
    traversal_policy: str = "current_snapshot"
    dynamic_policy: str = "invalidate_after_effect"

    def __post_init__(self) -> None:
        if not self.scope_id.startswith("scope:") or not self.root_entity_id.strip():
            raise ValueError("scope identity is invalid")
        if not isinstance(self.extent, ScopeExtent):
            raise TypeError("scope extent must be typed")


@dataclass(frozen=True)
class ActionTemplate:
    semantic_action: str
    item_postcondition: PredicateExpr | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.semantic_action.strip():
            raise ValueError("action template requires a semantic action")
        if self.item_postcondition is not None and not isinstance(
            self.item_postcondition, _PREDICATE_TYPES
        ):
            raise TypeError("item postcondition must be a typed predicate")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


class SchedulingMode(StrEnum):
    RUNTIME_SEQUENTIAL = "runtime_sequential"
    AGENT_SELECT_NEXT = "agent_select_next"


class MemberOrdering(StrEnum):
    DOCUMENT_ORDER = "document_order"
    SPATIAL_ORDER = "spatial_order"
    STABLE_ENTITY_ORDER = "stable_entity_order"


@dataclass(frozen=True)
class SchedulingPolicy:
    mode: SchedulingMode = SchedulingMode.RUNTIME_SEQUENTIAL
    ordering: MemberOrdering = MemberOrdering.DOCUMENT_ORDER
    members_independent: bool = True
    order_sensitive: bool = False

    def __post_init__(self) -> None:
        if self.mode is SchedulingMode.RUNTIME_SEQUENTIAL and (
            not self.members_independent or self.order_sensitive
        ):
            raise ValueError("runtime scheduling requires independent order-insensitive members")


@dataclass(frozen=True)
class SetObjective:
    objective_id: str
    scope: ScopeSpec
    predicate: PredicateExpr
    quantifier: SetQuantifier
    action_template: ActionTemplate
    scheduling_policy: SchedulingPolicy = field(default_factory=SchedulingPolicy)

    def __post_init__(self) -> None:
        if not self.objective_id.startswith("set-objective:"):
            raise ValueError("set objective identity is invalid")
        if not isinstance(self.predicate, _PREDICATE_TYPES):
            raise TypeError("set objective predicate must be typed")

    @property
    def predicate_digest(self) -> str:
        return predicate_digest(self.predicate)


@dataclass(frozen=True)
class CandidateUniverse:
    scope_id: str
    observation_epoch: str
    entity_ids: tuple[str, ...]
    coverage: ScopeCoverage
    coverage_basis: tuple[str, ...]

    def __post_init__(self) -> None:
        values = tuple(self.entity_ids)
        if (
            not self.scope_id.startswith("scope:")
            or not self.observation_epoch.strip()
            or len(values) != len(set(values))
            or any(not item.strip() for item in values)
        ):
            raise ValueError("candidate universe is invalid")
        if self.coverage is ScopeCoverage.COMPLETE and not self.coverage_basis:
            raise ValueError("complete scope requires owner evidence")
        object.__setattr__(self, "entity_ids", values)
        object.__setattr__(self, "coverage_basis", tuple(self.coverage_basis))


@dataclass(frozen=True)
class PredicateAssessment:
    entity_id: str
    predicate_digest: str
    truth: PredicateTruth
    assurance: PredicateAssurance
    evaluator_id: str
    observation_epoch: str
    evidence_refs: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        if (
            not self.entity_id.strip()
            or len(self.predicate_digest) != 64
            or not self.evaluator_id.strip()
            or not self.observation_epoch.strip()
            or (
                self.confidence is not None
                and not 0 <= self.confidence <= 1
            )
        ):
            raise ValueError("predicate assessment is invalid")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


class ActionObligationStatus(StrEnum):
    UNACTED = "unacted"
    ACTION_IN_FLIGHT = "action_in_flight"
    EFFECT_CONFIRMED = "effect_confirmed"
    ALREADY_SATISFIED = "already_satisfied"
    NO_EFFECT_CONFIRMED = "no_effect_confirmed"
    EFFECT_UNKNOWN = "effect_unknown"
    BLOCKED = "blocked"


_LEGAL_OBLIGATION_TRANSITIONS = {
    ActionObligationStatus.UNACTED: frozenset({ActionObligationStatus.ACTION_IN_FLIGHT, ActionObligationStatus.ALREADY_SATISFIED, ActionObligationStatus.BLOCKED}),
    ActionObligationStatus.ACTION_IN_FLIGHT: frozenset({ActionObligationStatus.EFFECT_CONFIRMED, ActionObligationStatus.NO_EFFECT_CONFIRMED, ActionObligationStatus.EFFECT_UNKNOWN, ActionObligationStatus.BLOCKED}),
    ActionObligationStatus.NO_EFFECT_CONFIRMED: frozenset({ActionObligationStatus.ACTION_IN_FLIGHT, ActionObligationStatus.BLOCKED}),
    ActionObligationStatus.EFFECT_UNKNOWN: frozenset({ActionObligationStatus.ACTION_IN_FLIGHT, ActionObligationStatus.EFFECT_CONFIRMED, ActionObligationStatus.NO_EFFECT_CONFIRMED, ActionObligationStatus.BLOCKED}),
    ActionObligationStatus.EFFECT_CONFIRMED: frozenset(),
    ActionObligationStatus.ALREADY_SATISFIED: frozenset(),
    ActionObligationStatus.BLOCKED: frozenset(),
}


@dataclass(frozen=True)
class SetMemberObligation:
    entity_id: str
    first_true_epoch: str
    membership_status: PredicateTruth
    action_status: ActionObligationStatus
    effect_evidence_refs: tuple[str, ...] = ()
    effect_epoch: str = ""

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.first_true_epoch.strip():
            raise ValueError("set member obligation identity is invalid")
        if self.action_status in {
            ActionObligationStatus.EFFECT_CONFIRMED,
            ActionObligationStatus.ALREADY_SATISFIED,
        } and not self.effect_evidence_refs:
            raise ValueError("settled obligation requires effect evidence")
        object.__setattr__(self, "effect_evidence_refs", tuple(self.effect_evidence_refs))


def transition_obligation(
    obligation: SetMemberObligation,
    status: ActionObligationStatus,
    *,
    observation_epoch: str,
    evidence_refs: tuple[str, ...] = (),
) -> SetMemberObligation:
    if status not in _LEGAL_OBLIGATION_TRANSITIONS[obligation.action_status]:
        raise ValueError(f"illegal obligation transition: {obligation.action_status}->{status}")
    return SetMemberObligation(
        obligation.entity_id,
        obligation.first_true_epoch,
        obligation.membership_status,
        status,
        tuple(evidence_refs),
        observation_epoch,
    )


class StabilityStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class SetDisposition(StrEnum):
    NEED_SCOPE_CLOSURE = "need_scope_closure"
    NEED_CLASSIFICATION = "need_classification"
    NEED_UNKNOWN_RESOLUTION = "need_unknown_resolution"
    READY_FOR_NEXT_MEMBER = "ready_for_next_member"
    AGENT_SELECT_NEXT = "agent_select_next"
    NEED_EFFECT_RESOLUTION = "need_effect_resolution"
    NEED_STABILITY_CHECK = "need_stability_check"
    CERTIFIED = "certified"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SetCompletionCertificate:
    objective_id: str
    scope_id: str
    predicate_digest: str
    closure_epoch: str
    closure_evidence_refs: tuple[str, ...]
    candidate_count: int
    predicate_false_count: int
    stability_status: StabilityStatus = StabilityStatus.PASSED
    predicate_unknown_count: int = 0
    true_unacted_count: int = 0
    pending_effect_count: int = 0
    unresolved_correspondence_count: int = 0


@dataclass(frozen=True)
class SetObjectiveReduction:
    disposition: SetDisposition
    reason_code: str
    true_entity_ids: tuple[str, ...] = ()
    next_entity_id: str = ""
    certificate: SetCompletionCertificate | None = None


def reduce_set_objective(
    objective: SetObjective,
    universe: CandidateUniverse,
    assessments: tuple[PredicateAssessment, ...],
    obligations: tuple[SetMemberObligation, ...],
    *,
    stability_status: StabilityStatus = StabilityStatus.PENDING,
    unresolved_correspondence_count: int = 0,
) -> SetObjectiveReduction:
    """Reduce one frozen snapshot; unsupported or contradictory inputs fail closed."""

    if universe.scope_id != objective.scope.scope_id:
        return _blocked("scope_identity_mismatch")
    if universe.coverage is not ScopeCoverage.COMPLETE and objective.quantifier is not SetQuantifier.ALL_DISCOVERED_UNDER_BUDGET:
        return SetObjectiveReduction(SetDisposition.NEED_SCOPE_CLOSURE, "scope_not_closed")
    by_entity: dict[str, PredicateAssessment] = {}
    for item in assessments:
        if (
            item.entity_id not in universe.entity_ids
            or item.predicate_digest != objective.predicate_digest
            or item.observation_epoch != universe.observation_epoch
            or item.entity_id in by_entity
        ):
            return _blocked("assessment_snapshot_invalid")
        by_entity[item.entity_id] = item
    missing = tuple(item for item in universe.entity_ids if item not in by_entity)
    if missing:
        return SetObjectiveReduction(SetDisposition.NEED_CLASSIFICATION, "classification_incomplete")
    unknown = tuple(item for item in universe.entity_ids if by_entity[item].truth is PredicateTruth.UNKNOWN)
    if unknown:
        return SetObjectiveReduction(SetDisposition.NEED_UNKNOWN_RESOLUTION, "predicate_unknown")
    current_true_ids = tuple(item for item in universe.entity_ids if by_entity[item].truth is PredicateTruth.TRUE)
    obligations_by_id = {item.entity_id: item for item in obligations}
    if len(obligations_by_id) != len(obligations):
        return _blocked("obligation_membership_invalid", current_true_ids)
    member_ids = tuple(dict.fromkeys((
        *(item for item in universe.entity_ids if item in current_true_ids or item in obligations_by_id),
        *(item.entity_id for item in obligations),
    )))
    if objective.quantifier is SetQuantifier.EXACTLY_ONE and len(member_ids) != 1:
        return _blocked("exactly_one_cardinality_violation", member_ids)
    missing_obligations = tuple(item for item in current_true_ids if item not in obligations_by_id)
    if missing_obligations:
        return _blocked("true_member_without_obligation", member_ids)
    pending_effect = tuple(
        item.entity_id for item in obligations
        if item.action_status in {
            ActionObligationStatus.ACTION_IN_FLIGHT,
            ActionObligationStatus.NO_EFFECT_CONFIRMED,
            ActionObligationStatus.EFFECT_UNKNOWN,
        }
    )
    if pending_effect:
        return SetObjectiveReduction(SetDisposition.NEED_EFFECT_RESOLUTION, "member_effect_unsettled", member_ids)
    if any(item.action_status is ActionObligationStatus.BLOCKED for item in obligations):
        return _blocked("member_blocked", member_ids)
    unacted = tuple(
        item for item in member_ids
        if obligations_by_id[item].action_status is ActionObligationStatus.UNACTED
    )
    if unacted:
        disposition = (
            SetDisposition.READY_FOR_NEXT_MEMBER
            if objective.scheduling_policy.mode is SchedulingMode.RUNTIME_SEQUENTIAL
            else SetDisposition.AGENT_SELECT_NEXT
        )
        return SetObjectiveReduction(disposition, "member_action_required", member_ids, unacted[0])
    if unresolved_correspondence_count:
        return SetObjectiveReduction(SetDisposition.NEED_UNKNOWN_RESOLUTION, "correspondence_unresolved", member_ids)
    if stability_status is not StabilityStatus.PASSED:
        return SetObjectiveReduction(SetDisposition.NEED_STABILITY_CHECK, "fresh_scope_stability_required", member_ids)
    false_count = len(universe.entity_ids) - len(current_true_ids)
    certificate = SetCompletionCertificate(
        objective.objective_id,
        objective.scope.scope_id,
        objective.predicate_digest,
        universe.observation_epoch,
        universe.coverage_basis,
        len(universe.entity_ids),
        false_count,
    )
    return SetObjectiveReduction(SetDisposition.CERTIFIED, "closed_scope_set_complete", member_ids, certificate=certificate)


def _blocked(reason: str, true_ids: tuple[str, ...] = ()) -> SetObjectiveReduction:
    return SetObjectiveReduction(SetDisposition.BLOCKED, reason, true_ids)
