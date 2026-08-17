"""Environment-owned public semantic vocabulary used by World surfaces.

Goal planning no longer compiles this vocabulary into a query AST. The contract remains
owned by observation adapters for public fact/relation naming and future typed evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.immutable import freeze_json

MAX_GOAL_SEMANTIC_NAME_LENGTH = 120
_STRUCTURAL_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_FORBIDDEN_SEMANTIC_NAMES = frozenset({
    "selector", "selectors", "coordinate", "coordinates", "x", "y", "dom_id",
    "action_ref", "entity_ref", "binding_ref", "target_id", "current_action_ref",
    "current_entity_ref", "current_binding_ref",
})


class GoalPredicateValueType(StrEnum):
    STRING = "string"
    BOOLEAN = "boolean"
    NUMBER = "number"


def is_private_goal_semantic_name(value: str) -> bool:
    folded = value.casefold()
    if folded in _FORBIDDEN_SEMANTIC_NAMES:
        return True
    components = frozenset(item for item in re.split(r"[._-]+", folded) if item)
    if components & {"selector", "selectors", "coordinate", "coordinates", "x", "y"}:
        return True
    if {"dom", "id"} <= components:
        return True
    if "current" in components and "ref" in components and components & {"action", "entity", "binding"}:
        return True
    return bool("target" in components and components & {"id", "ref"})


def _validate_name(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_GOAL_SEMANTIC_NAME_LENGTH
        or _STRUCTURAL_IDENTIFIER.fullmatch(value) is None
    ):
        raise ValueError(f"goal semantic {label} is invalid")
    if is_private_goal_semantic_name(value):
        raise ValueError(f"goal semantic contract cannot expose private {label}s")


@dataclass(frozen=True)
class GoalSemanticContract:
    entity_kinds: frozenset[str] = frozenset()
    predicates: Mapping[str, GoalPredicateValueType] = field(default_factory=dict)
    relations: frozenset[str] = frozenset()
    finalizer_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_kinds", frozenset(self.entity_kinds))
        object.__setattr__(self, "relations", frozenset(self.relations))
        object.__setattr__(self, "finalizer_capabilities", frozenset(self.finalizer_capabilities))
        predicates: dict[str, GoalPredicateValueType] = {}
        for name, value_type in self.predicates.items():
            _validate_name(name, "predicate")
            predicates[name] = GoalPredicateValueType(value_type)
        for label, values in (
            ("entity kind", self.entity_kinds),
            ("relation", self.relations),
            ("finalizer capability", self.finalizer_capabilities),
        ):
            for value in values:
                _validate_name(value, label)
        object.__setattr__(self, "predicates", freeze_json(predicates))

    def to_public_dict(self) -> dict[str, object]:
        return {
            "entity_kinds": tuple(sorted(self.entity_kinds)),
            "predicates": {name: value.value for name, value in sorted(self.predicates.items())},
            "relations": tuple(sorted(self.relations)),
            "finalizer_capabilities": tuple(sorted(self.finalizer_capabilities)),
        }


def merge_goal_semantic_contracts(contracts: tuple[GoalSemanticContract, ...]) -> GoalSemanticContract:
    predicates: dict[str, GoalPredicateValueType] = {}
    for contract in contracts:
        for name, value_type in contract.predicates.items():
            previous = predicates.setdefault(name, value_type)
            if previous is not value_type:
                raise ValueError(f"goal semantic predicate type conflict: {name}")
    return GoalSemanticContract(
        frozenset(kind for contract in contracts for kind in contract.entity_kinds),
        predicates,
        frozenset(edge for contract in contracts for edge in contract.relations),
        frozenset(capability for contract in contracts for capability in contract.finalizer_capabilities),
    )
