"""Public-only destination-domain grounding ladder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .scenario import LiveDomScenario

_ACTION_ID = "action:destination-ladder"
_TARGET_ID = "target:control"


@dataclass(frozen=True)
class DestinationLadderCase:
    level: str
    serialized_context: str
    action_id: str
    target_id: str
    visible_destinations: Mapping[str, tuple[str, ...]]


def build_destination_case(level: str, scenario: LiveDomScenario) -> DestinationLadderCase:
    if level in {"D0", "D1", "D2"}:
        return _synthetic_case(level, scenario.context.context_id)
    if level in {"D3", "D4"}:
        return _real_context_case(level, scenario)
    raise ValueError(f"unsupported destination ladder level: {level}")


def _synthetic_case(level: str, context_id: str) -> DestinationLadderCase:
    destinations = {
        "D0": (),
        "D1": (("destination:primary", "Primary destination"),),
        "D2": (
            ("destination:primary", "Primary destination"),
            ("destination:secondary", "Secondary destination"),
        ),
    }[level]
    required = bool(destinations)
    instruction = (
        "Select the visible action without a destination."
        if not required
        else "Select the visible action and copy one offered destination_id exactly."
    )
    action = {
        "action_id": _ACTION_ID,
        "semantic_action": "activate",
        "target_id": _TARGET_ID,
        "target_label": "Destination ladder control",
        "destination_required": required,
        "destinations": {
            "items": [
                {"destination_id": destination_id, "label": label}
                for destination_id, label in destinations
            ],
            "total_count": len(destinations),
            "truncated": False,
        },
        "parameter_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "description": "activate destination ladder control",
    }
    context = {
        "context_id": context_id,
        "task": {"instruction": instruction},
        "actions": {
            "options": [action],
            "total_count": 1,
            "page_size": 1,
            "truncated": False,
            "has_more": False,
        },
    }
    allowed = tuple(item[0] for item in destinations) if required else ("",)
    return DestinationLadderCase(
        level,
        _json(context),
        _ACTION_ID,
        _TARGET_ID,
        MappingProxyType({_ACTION_ID: allowed}),
    )


def _real_context_case(level: str, scenario: LiveDomScenario) -> DestinationLadderCase:
    full = json.loads(scenario.serialized_context)
    option = scenario.context.actions.options[0]
    serialized = (
        scenario.serialized_context
        if level == "D4"
        else _json({
            "context_id": scenario.context.context_id,
            "task": {"instruction": "Select the current visible action."},
            "actions": full["actions"],
        })
    )
    allowed = (
        tuple(item.destination_id for item in option.destinations.items)
        if option.destination_required
        else ("",)
    )
    return DestinationLadderCase(
        level,
        serialized,
        option.action_id,
        option.target_id,
        MappingProxyType({option.action_id: allowed}),
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
