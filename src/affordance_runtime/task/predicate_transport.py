"""Bounded normalized model transport for the Runtime predicate algebra."""

from __future__ import annotations

from collections.abc import Mapping

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
