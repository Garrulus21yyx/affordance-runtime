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

MAX_ANY_GROUPS = 4
MAX_ALL_ATOMS = 8
MAX_PUBLIC_PREDICATE_DEPTH = 3


def predicate_from_transport(payload: Mapping[str, object]) -> PredicateExpr:
    """Convert bounded DNF transport to the closed internal predicate AST."""

    if set(payload) != {"any_of"} or not isinstance(payload["any_of"], list | tuple):
        raise ValueError("predicate transport must contain any_of")
    groups = payload["any_of"]
    if not 1 <= len(groups) <= MAX_ANY_GROUPS:
        raise ValueError("predicate transport group bound exceeded")
    expressions: list[PredicateExpr] = []
    for group in groups:
        if not isinstance(group, Mapping) or set(group) != {"all_of"}:
            raise ValueError("predicate transport group is invalid")
        atoms = group["all_of"]
        if not isinstance(atoms, list | tuple) or not 1 <= len(atoms) <= MAX_ALL_ATOMS:
            raise ValueError("predicate transport atom bound exceeded")
        parsed = tuple(_atom(item) for item in atoms)
        expressions.append(parsed[0] if len(parsed) == 1 else And(parsed))
    return expressions[0] if len(expressions) == 1 else Or(tuple(expressions))


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


def _atom(value: object) -> PredicateExpr:
    if not isinstance(value, Mapping):
        raise ValueError("predicate atom must be an object")
    negated = value.get("negated", False)
    if type(negated) is not bool:
        raise ValueError("predicate negation must be boolean")
    kind = value.get("kind")
    if (
        kind == "fact_equals"
        and set(value) <= {"kind", "field_name", "expected", "negated"}
        and {"kind", "field_name", "expected"} <= set(value)
    ):
        expression: PredicateExpr = FactEquals(_model_field_name(value["field_name"]), value["expected"])
    elif (
        kind == "compare"
        and set(value) <= {"kind", "field_name", "operator", "expected", "negated"}
        and {"kind", "field_name", "operator", "expected"} <= set(value)
    ):
        expression = Compare(
            _model_field_name(value["field_name"]),
            CompareOperator(str(value["operator"])),
            value["expected"],
        )
    elif kind == "visual_concept" and set(value) <= {"kind", "text", "negated"} and {"kind", "text"} <= set(value):
        expression = VisualConcept(str(value["text"]))
    elif kind == "visual_attribute" and set(value) <= {"kind", "text", "negated"} and {"kind", "text"} <= set(value):
        expression = VisualAttribute(str(value["text"]))
    else:
        raise ValueError("predicate atom is unsupported")
    return Not(expression) if negated else expression


def _model_field_name(value: object) -> str:
    """Map public view names to canonical selector fields; reject opaque identity."""

    name = str(value).strip()
    if name in {"entity_id", "identity.entity_id"}:
        raise ValueError("model predicate cannot address opaque entity identity")
    return {
        "label": "identity.label",
        "role": "identity.role",
    }.get(name, name)
