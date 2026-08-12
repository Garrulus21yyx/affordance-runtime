"""Generic compilation of mechanically mentioned public task predicates."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from affordance_runtime.task.set_objective import SetQuantifier, has_universal_quantifier

_COORDINATE = re.compile(
    r"(?:coordinate|coordinates|point)\s*(?:is|=|at)?\s*\(\s*"
    r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*,\s*"
    r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PublicCandidateEvidence:
    entity_id: str
    fields: Mapping[str, object]


@dataclass(frozen=True)
class CompiledPublicPredicate:
    field_name: str
    expected: object
    quantifier: SetQuantifier


def compile_public_task_predicate(
    instruction: str,
    candidates: Sequence[PublicCandidateEvidence],
) -> CompiledPublicPredicate | None:
    matches: dict[str, object] = {}
    for candidate in candidates:
        for field_name, value in candidate.fields.items():
            if _instruction_mentions_value(instruction, value):
                if field_name in matches and matches[field_name] != value:
                    return None
                matches[field_name] = value
    if len(matches) != 1:
        return None
    field_name, expected = next(iter(matches.items()))
    return CompiledPublicPredicate(
        field_name,
        expected,
        SetQuantifier.ALL_IN_CLOSED_SCOPE
        if has_universal_quantifier(instruction)
        else SetQuantifier.EXACTLY_ONE,
    )


def _instruction_mentions_value(instruction: str, value: object) -> bool:
    if isinstance(value, str) and value.strip() and len(value) <= 80:
        return re.search(rf"(?<!\w){re.escape(value)}(?!\w)", instruction, re.IGNORECASE) is not None
    if isinstance(value, Mapping) and set(value) == {"x", "y"}:
        matches = tuple(_COORDINATE.finditer(instruction))
        if len(matches) != 1:
            return False
        return (_number(matches[0].group(1)), _number(matches[0].group(2))) == (value["x"], value["y"])
    return False


def _number(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed
