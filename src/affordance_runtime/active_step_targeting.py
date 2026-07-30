"""Compatibility active-step target resolution.

This module resolves narrow, deterministic legacy step subjects to current
semantic target ids. It never performs fuzzy label matching.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


@dataclass(frozen=True)
class ActiveStepTargetView:
    target_id: str
    role: str
    label: str
    actions: tuple[str, ...]
    state: Mapping[str, Any]


def resolve_active_step_target_ids(
    *,
    subject: str,
    targets: Iterable[str] = (),
    affordances: Iterable[ActiveStepTargetView],
) -> tuple[str, ...]:
    """Resolve a legacy active-step subject to current target ids.

    Supported mappings are intentionally narrow:
    - exact current target id;
    - checkbox ordinal, e.g. ``checkbox_3_state`` or ``3rd checkbox``;
    - unique slider target for ``slider_value`` subjects;
    - unique submit/button target for ``submit_button`` subjects.
    """

    views = tuple(affordances)
    current_ids = {item.target_id for item in views}
    if subject in current_ids:
        return (subject,)

    text = " ".join((subject, *tuple(str(item) for item in targets)))
    checkbox = _resolve_checkbox_ordinal_target_id(text, views)
    if checkbox is not None:
        return (checkbox,)

    lowered = subject.casefold()
    if "slider" in lowered:
        sliders = tuple(item.target_id for item in views if _is_slider(item))
        return sliders if len(sliders) == 1 else ()
    if "submit" in lowered and "button" in lowered:
        submits = tuple(item.target_id for item in views if _is_submit(item))
        return submits if len(submits) == 1 else ()
    return ()


def _resolve_checkbox_ordinal_target_id(
    text: str,
    affordances: tuple[ActiveStepTargetView, ...],
) -> str | None:
    ordinals = _requested_checkbox_ordinals(text)
    if len(ordinals) != 1:
        return None
    ordinal = next(iter(ordinals))
    checkboxes = tuple(item for item in affordances if _is_checkbox(item))
    if ordinal < 1 or ordinal > len(checkboxes):
        return None
    return checkboxes[ordinal - 1].target_id


def _requested_checkbox_ordinals(text: str) -> set[int]:
    lowered = text.casefold()
    ordinals = {
        int(match.group(1))
        for match in re.finditer(
            r"\bcheckbox[_\s:-]*(\d+)(?:[_\s:-]*state)?\b",
            lowered,
        )
    }
    ordinals.update(
        int(match.group(1))
        for match in re.finditer(
            r"\b(\d+)(?:st|nd|rd|th)?\s+checkbox(?:es)?\b",
            lowered,
        )
    )
    ordinals.update(
        number
        for word, number in _ORDINAL_WORDS.items()
        if re.search(rf"\b{word}\s+checkbox(?:es)?\b", lowered)
    )
    return ordinals


def _is_checkbox(item: ActiveStepTargetView) -> bool:
    state_input_type = str(item.state.get("input_type", "")).casefold()
    return item.role.casefold() == "checkbox" or state_input_type == "checkbox"


def _is_slider(item: ActiveStepTargetView) -> bool:
    role = item.role.casefold()
    state_input_type = str(item.state.get("input_type", "")).casefold()
    return role in {"slider", "range"} or state_input_type == "range"


def _is_submit(item: ActiveStepTargetView) -> bool:
    role = item.role.casefold()
    label = item.label.casefold()
    state_input_type = str(item.state.get("input_type", "")).casefold()
    if state_input_type == "submit":
        return True
    return role in {"button", "submit"} and "submit" in label
