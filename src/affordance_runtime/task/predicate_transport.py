"""One bounded normalized model transport for the Runtime predicate algebra."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.set_objective import (
    And,
    Compare,
    CompareOperator,
    FactEquals,
    Not,
    Or,
    PredicateExpr,
    SpatialRelation,
    VisualAttribute,
    VisualConcept,
)

MAX_ALL_ATOMS = 8
MAX_PUBLIC_PREDICATE_DEPTH = 3
MAX_ANY_CLAUSES = 4

FieldName = Annotated[str, StringConstraints(min_length=1, max_length=96)]
ConceptText = Annotated[str, StringConstraints(min_length=1, max_length=160)]


class _Atom(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    negated: bool = False


class FactEqualsAtom(_Atom):
    kind: Literal["fact_equals"]
    field_name: FieldName
    expected: Any

    @field_validator("expected")
    @classmethod
    def _json_value(cls, value: Any) -> Any:
        freeze_json(value)
        return value


class CompareAtom(_Atom):
    kind: Literal["compare"]
    field_name: FieldName
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in"]
    expected: Any

    @field_validator("expected")
    @classmethod
    def _json_value(cls, value: Any) -> Any:
        freeze_json(value)
        return value


class SpatialRelationAtom(_Atom):
    kind: Literal["spatial_relation"]
    relation: FieldName
    argument: Any

    @field_validator("argument")
    @classmethod
    def _json_value(cls, value: Any) -> Any:
        freeze_json(value)
        return value


class VisualConceptAtom(_Atom):
    kind: Literal["visual_concept"]
    concept: ConceptText


class VisualAttributeAtom(_Atom):
    kind: Literal["visual_attribute"]
    attribute: ConceptText


PredicateAtomPayload: TypeAlias = Annotated[
    FactEqualsAtom | CompareAtom | SpatialRelationAtom | VisualConceptAtom | VisualAttributeAtom,
    Field(discriminator="kind"),
]


class PredicateClausePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    all_of: Annotated[list[PredicateAtomPayload], Field(min_length=1, max_length=MAX_ALL_ATOMS)]


class NormalizedPredicatePayload(BaseModel):
    """Bounded DNF: any_of clauses, each containing all_of atomic predicates."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    any_of: Annotated[list[PredicateClausePayload], Field(min_length=1, max_length=MAX_ANY_CLAUSES)]


def predicate_from_transport(payload: NormalizedPredicatePayload) -> PredicateExpr:
    clauses: list[PredicateExpr] = []
    for clause in payload.any_of:
        atoms = tuple(_atom_from_payload(item) for item in clause.all_of)
        clauses.append(atoms[0] if len(atoms) == 1 else And(atoms))
    return clauses[0] if len(clauses) == 1 else Or(tuple(clauses))


def _atom_from_payload(payload: PredicateAtomPayload) -> PredicateExpr:
    if isinstance(payload, FactEqualsAtom):
        value: PredicateExpr = FactEquals(payload.field_name, payload.expected)
    elif isinstance(payload, CompareAtom):
        value = Compare(payload.field_name, CompareOperator(payload.operator), payload.expected)
    elif isinstance(payload, SpatialRelationAtom):
        value = SpatialRelation(payload.relation, payload.argument)
    elif isinstance(payload, VisualConceptAtom):
        value = VisualConcept(payload.concept)
    else:
        value = VisualAttribute(payload.attribute)
    return Not(value) if payload.negated else value


def predicate_from_public_value(payload: Mapping[str, object], *, _depth: int = 0) -> PredicateExpr:
    """Parse the canonical bounded public AST emitted by predicate_public_value."""

    if _depth > MAX_PUBLIC_PREDICATE_DEPTH:
        raise ValueError("public predicate depth exceeded")
    kind = payload.get("kind")
    if kind == "fact_equals" and set(payload) == {"kind", "field_name", "expected"}:
        return FactEquals(str(payload["field_name"]), payload["expected"])
    if kind == "compare" and set(payload) == {"kind", "field_name", "operator", "expected"}:
        return Compare(
            str(payload["field_name"]),
            CompareOperator(str(payload["operator"])),
            payload["expected"],
        )
    if kind == "spatial_relation" and set(payload) == {"kind", "relation", "argument"}:
        return SpatialRelation(str(payload["relation"]), payload["argument"])
    if kind == "visual_concept" and set(payload) == {"kind", "concept"}:
        return VisualConcept(str(payload["concept"]))
    if kind == "visual_attribute" and set(payload) == {"kind", "attribute"}:
        return VisualAttribute(str(payload["attribute"]))
    if kind == "not" and set(payload) == {"kind", "operand"} and isinstance(payload["operand"], Mapping):
        return Not(predicate_from_public_value(payload["operand"], _depth=_depth + 1))
    if kind in {"and", "or"} and set(payload) == {"kind", "operands"}:
        raw = payload["operands"]
        if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_ALL_ATOMS:
            raise ValueError("public predicate operands are invalid")
        values = tuple(
            predicate_from_public_value(item, _depth=_depth + 1) for item in raw if isinstance(item, Mapping)
        )
        if len(values) != len(raw):
            raise ValueError("public predicate operand is invalid")
        return And(values) if kind == "and" else Or(values)
    raise ValueError("public predicate is unsupported")
