"""Bounded provider-neutral decision grounding from public AgentContext JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model_policy.grounding_v2 import (
    COMPACT_CONTRACT_V2_PROFILE_VERSION,
    MAX_COMPACT_GUIDE_BYTES,
    CompactActionDomain,
    CompactBudgetDomain,
    CompactCompletionDomain,
    CompactDecisionContract,
    CompactDecisionGuideV2,
    CompactObservationDomain,
    CompactPagingDomain,
    build_compact_decision_guide_v2,
    serialize_compact_decision_guide_v2,
)
from affordance_runtime.model_policy.spec import SCHEMA_VERSION

FORMAT_ONLY_PROFILE_VERSION = "format-only.v1"
COMPACT_CONTRACT_PROFILE_VERSION = "compact-contract.v1"
_DECISION_TYPES = (
    "select_action", "request_observation", "request_action_page", "ask_user",
    "propose_done", "wait", "abort",
)
__all__ = [
    "COMPACT_CONTRACT_PROFILE_VERSION", "COMPACT_CONTRACT_V2_PROFILE_VERSION",
    "FORMAT_ONLY_PROFILE_VERSION", "MAX_COMPACT_GUIDE_BYTES", "CompactActionDomain",
    "CompactActionGuide", "CompactBudgetDomain", "CompactCompletionDomain",
    "CompactDecisionContract", "CompactDecisionGuide", "CompactDecisionGuideV2",
    "CompactObservationDomain", "CompactPagingDomain", "DecisionGroundingVariant",
    "build_compact_decision_guide", "build_compact_decision_guide_v2",
    "grounding_profile_version", "serialize_compact_decision_guide",
    "serialize_compact_decision_guide_v2",
]


class DecisionGroundingVariant(StrEnum):
    FORMAT_ONLY = "format-only"
    COMPACT_CONTRACT = "compact-contract"
    COMPACT_CONTRACT_V2 = "compact-contract-v2"


def grounding_profile_version(variant: DecisionGroundingVariant | str) -> str:
    selected = DecisionGroundingVariant(variant)
    if selected is DecisionGroundingVariant.FORMAT_ONLY:
        return FORMAT_ONLY_PROFILE_VERSION
    if selected is DecisionGroundingVariant.COMPACT_CONTRACT:
        return COMPACT_CONTRACT_PROFILE_VERSION
    return COMPACT_CONTRACT_V2_PROFILE_VERSION


@dataclass(frozen=True)
class CompactActionGuide:
    action_id: str
    semantic_action: str
    target_id: str
    target_label: str
    visible_destination_ids: tuple[str, ...]
    required_parameter_names: tuple[str, ...]


@dataclass(frozen=True)
class CompactDecisionGuide:
    schema_version: str
    current_context_id: str
    decision_types: tuple[str, ...]
    visible_actions: tuple[CompactActionGuide, ...]
    visible_actions_total: int
    truncated: bool
    next_page_available: bool
    select_action_example: Mapping[str, object] | None

    def __post_init__(self) -> None:
        if self.select_action_example is not None:
            object.__setattr__(self, "select_action_example", freeze_json(self.select_action_example))


def build_compact_decision_guide(serialized_context: str) -> CompactDecisionGuide:
    context = json.loads(serialized_context)
    if not isinstance(context, dict):
        raise ValueError("serialized AgentContext must be an object")
    actions = context.get("actions", {})
    options = actions.get("options", ()) if isinstance(actions, dict) else ()
    if not isinstance(options, list):
        raise ValueError("AgentContext action options must be a list")
    projected: list[CompactActionGuide] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        candidate = _action_guide(option)
        tentative = _guide(context, options, (*projected, candidate))
        if len(serialize_compact_decision_guide(tentative).encode()) > MAX_COMPACT_GUIDE_BYTES:
            break
        projected.append(candidate)
    guide = _guide(context, options, tuple(projected))
    if len(serialize_compact_decision_guide(guide).encode()) > MAX_COMPACT_GUIDE_BYTES:
        raise ValueError("compact decision guide cannot fit its fixed metadata bound")
    return guide


def serialize_compact_decision_guide(guide: CompactDecisionGuide) -> str:
    return json.dumps(
        to_json_compatible(guide), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _guide(context, options, projected) -> CompactDecisionGuide:
    first = projected[0] if projected else None
    destination = first.visible_destination_ids[0] if first and first.visible_destination_ids else ""
    example = None if first is None else {
        "objective_operation": {"kind": "none"},
        "decision": {
            "type": "select_action",
            "context_id": str(context.get("context_id") or ""),
            "action_id": first.action_id,
            "parameters": {},
            "destination_id": destination,
        },
    }
    actions = context.get("actions", {})
    return CompactDecisionGuide(
        SCHEMA_VERSION, str(context.get("context_id") or ""), _DECISION_TYPES,
        tuple(projected), len(options), len(projected) < len(options),
        bool(actions.get("has_more")) if isinstance(actions, dict) else False, example,
    )


def _action_guide(option: dict[str, object]) -> CompactActionGuide:
    destinations = option.get("destinations", {})
    destination_items = destinations.get("items", ()) if isinstance(destinations, dict) else ()
    schema = option.get("parameter_schema", {})
    required = schema.get("required", ()) if isinstance(schema, dict) else ()
    return CompactActionGuide(
        str(option.get("action_id") or ""), str(option.get("semantic_action") or ""),
        str(option.get("target_id") or ""), str(option.get("target_label") or ""),
        tuple(
            str(item.get("destination_id") or "")
            for item in destination_items if isinstance(item, dict)
        ),
        tuple(str(item) for item in required) if isinstance(required, list) else (),
    )
