"""Pure canonical criterion expression contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, TypeAlias

from affordance_runtime.immutable import freeze_json
from affordance_runtime.verification.contracts import CriterionPolicy


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    STRONG = "strong"


class PredicateOperator(StrEnum):
    """Registered vocabulary; registration does not imply provider coverage."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES_REGEX = "matches_regex"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    BETWEEN = "between"
    IN_SET = "in_set"
    EXISTS = "exists"
    ABSENT = "absent"
    VISIBLE = "visible"
    AVAILABLE = "available"
    ENABLED = "enabled"
    SELECTED = "selected"
    CHECKED = "checked"
    EXPANDED = "expanded"
    ORDERED_AS = "ordered_as"
    CHANGED = "changed"
    CONTAINS_ENTITY = "contains_entity"


MECHANICAL_BASELINE_OPERATORS = frozenset(
    {
        PredicateOperator.EQUALS,
        PredicateOperator.CONTAINS,
        PredicateOperator.STARTS_WITH,
        PredicateOperator.ENDS_WITH,
        PredicateOperator.BETWEEN,
        PredicateOperator.EXISTS,
        PredicateOperator.ABSENT,
        PredicateOperator.SELECTED,
        PredicateOperator.CHECKED,
        PredicateOperator.CHANGED,
    }
)


@dataclass(frozen=True)
class SubjectExpr:
    kind: str
    reference: str
    field: str = ""

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.reference.strip():
            raise ValueError("criterion subject requires typed kind and reference")


@dataclass(frozen=True)
class LiteralValue:
    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ReferenceValue:
    kind: str
    reference: str

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.reference.strip():
            raise ValueError("criterion value reference cannot be blank")


ValueExpression: TypeAlias = LiteralValue | ReferenceValue


@dataclass(frozen=True)
class PredicateExpr:
    criterion_id: str
    subject: SubjectExpr
    operator: PredicateOperator
    policy: CriterionPolicy
    value: ValueExpression | None = None
    source_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("predicate criterion_id cannot be blank")
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "effect_refs", tuple(self.effect_refs))


@dataclass(frozen=True)
class AllOf:
    criterion_id: str
    children: tuple[CriterionExpr, ...]

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.children:
            raise ValueError("all_of requires identity and children")


@dataclass(frozen=True)
class AnyOf:
    criterion_id: str
    children: tuple[CriterionExpr, ...]

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.children:
            raise ValueError("any_of requires identity and children")


@dataclass(frozen=True)
class Not:
    criterion_id: str
    child: CriterionExpr

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("not requires identity")


@dataclass(frozen=True)
class OpenSemanticCriterion:
    criterion_id: str
    operator_name: str
    typed_arguments: tuple[tuple[str, Any], ...]
    source_refs: tuple[str, ...]
    policy: CriterionPolicy

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.operator_name.strip():
            raise ValueError("open semantic criterion requires stable identity")
        if not self.source_refs:
            raise ValueError("open semantic criterion must remain source-bound")
        object.__setattr__(
            self,
            "typed_arguments",
            tuple((key, freeze_json(value)) for key, value in self.typed_arguments),
        )


CriterionExpr: TypeAlias = PredicateExpr | AllOf | AnyOf | Not | OpenSemanticCriterion


def criterion_nodes(expression: CriterionExpr) -> tuple[CriterionExpr, ...]:
    """Return one canonical expression tree in stable pre-order."""

    if isinstance(expression, (AllOf, AnyOf)):
        return (expression, *(node for child in expression.children for node in criterion_nodes(child)))
    if isinstance(expression, Not):
        return (expression, *criterion_nodes(expression.child))
    return (expression,)


def criterion_ids(expressions: Iterable[CriterionExpr]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            node.criterion_id
            for expression in expressions
            for node in criterion_nodes(expression)
        )
    )


def criterion_id(owner_kind: str, owner_id: str, index: int) -> str:
    """Return the stable identity a verifier must explicitly claim."""

    return f"{owner_kind}:{owner_id}:criterion:{index}"


def evidence_requirement_id(owner_kind: str, owner_id: str, index: int) -> str:
    """Return the stable identity of an independent-evidence requirement."""

    return f"{owner_kind}:{owner_id}:evidence-requirement:{index}"


def skill_step_owner_id(skill_id: str, skill_version: str, step_id: str) -> str:
    return f"{skill_id}@{skill_version}:{step_id}"
