"""Authority-free task action-family resolution helpers."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Set
from typing import Any

ACTION_FAMILY_ALIASES = {
    "click": "activate",
    "fill": "type_text",
    "type": "type_text",
    "select": "select_option",
    "press": "press_key",
    "drop": "drag",
}


def action_family_value(action: str) -> str:
    normalized = action.strip().lower()
    return ACTION_FAMILY_ALIASES.get(normalized, normalized)


def current_bindable_action_family_values(
    *,
    subject: str,
    relation: str,
    affordances: Iterable[Any],
    allowed_relations_by_family: Mapping[str, Set[str]],
) -> frozenset[str]:
    """Return unique currently bindable families from matching typed affordances."""
    subject_tokens = frozenset(_semantic_tokens(subject))
    if not subject_tokens:
        return frozenset()
    families: set[str] = set()
    for affordance in affordances:
        affordance_tokens = frozenset(
            _semantic_tokens(
                " ".join(
                    (
                        str(getattr(affordance, "semantic_target_id", "")),
                        str(getattr(affordance, "role", "")),
                        str(getattr(affordance, "label", "")),
                    )
                )
            )
        )
        if subject_tokens.isdisjoint(affordance_tokens):
            continue
        for action in getattr(affordance, "supported_actions", ()):
            family = action_family_value(str(action))
            if relation in allowed_relations_by_family.get(family, frozenset()):
                families.add(family)
    return frozenset(families)


def infer_obligation_action_family_value(
    *,
    obligation_kind: str,
    task_operation: str,
    subject: str,
    relation: str,
    affordances: Iterable[Any],
    allowed_relations_by_family: Mapping[str, Set[str]],
) -> str | None:
    """Infer a semantic family without taking runtime authority."""
    if obligation_kind != "effect" or task_operation != "reversible_write":
        return None
    current_affordances = tuple(affordances)
    bindable = current_bindable_action_family_values(
        subject=subject,
        relation=relation,
        affordances=current_affordances,
        allowed_relations_by_family=allowed_relations_by_family,
    )
    if len(bindable) == 1:
        return next(iter(bindable))
    if "type_text" in bindable and relation in allowed_relations_by_family["type_text"] and (
        relation != "has_changed" or _looks_like_value_entry_subject(subject)
    ):
        return "type_text"
    if bindable or current_affordances:
        return None
    if relation in allowed_relations_by_family["type_text"] and (
        relation != "has_changed" or _looks_like_value_entry_subject(subject)
    ):
        return "type_text"
    return None


def _looks_like_value_entry_subject(subject: str) -> bool:
    value_entry_subject_terms = frozenset(("field", "input", "textbox", "textarea", "text", "date", "value"))
    return bool(value_entry_subject_terms.intersection(_semantic_tokens(subject)))


def _semantic_tokens(value: str) -> tuple[str, ...]:
    return tuple(item for item in re.findall(r"[a-z0-9]+", value.casefold()) if item)
