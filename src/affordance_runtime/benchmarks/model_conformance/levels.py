"""Fixed structured-decision conformance levels."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Level0Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["select_action"]


class Level1SelectActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["select_action"]
    context_id: str
    action_id: str
    parameters: dict[str, Any]
    destination_id: str


def minimal_select_context(
    context_id: str,
    action_id: str,
    semantic_action: str,
    target_id: str,
    target_label: str,
    destination_id: str,
) -> str:
    return _json({
        "context_id": context_id,
        "task": "Enable the shared state.",
        "visible_action": {
            "action_id": action_id,
            "semantic_action": semantic_action,
            "target_id": target_id,
            "target": target_label,
            "parameters": {},
            "destination_id": destination_id,
        },
        "required_output": {
            "type": "select_action", "context_id": context_id, "action_id": action_id,
            "parameters": {}, "destination_id": destination_id,
        },
    })


def minimal_union_context(
    context_id: str,
    action_id: str,
    semantic_action: str,
    target_id: str,
    target_label: str,
    destination_id: str,
) -> str:
    return _json({
        "context_id": context_id,
        "task": "Enable the shared state.",
        "visible_actions": [{
            "action_id": action_id,
            "semantic_action": semantic_action,
            "target_id": target_id,
            "target": target_label,
            "parameters": {},
            "destination_id": destination_id,
        }],
    })


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

