"""Canonical-branch-derived schemas with current public-domain narrowing."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel

from affordance_runtime.model_policy.spec import (
    AbortPayload,
    AskUserPayload,
    ProposeDonePayload,
    RequestActionPagePayload,
    RequestObservationPayload,
    SelectActionPayload,
    WaitPayload,
)
from affordance_runtime.model_policy.strict_json import strict_json_loads

from .contracts import DecisionKind

BRANCH_MODELS: Mapping[DecisionKind, type[BaseModel]] = {
    DecisionKind.SELECT_ACTION: SelectActionPayload,
    DecisionKind.REQUEST_OBSERVATION: RequestObservationPayload,
    DecisionKind.REQUEST_ACTION_PAGE: RequestActionPagePayload,
    DecisionKind.ASK_USER: AskUserPayload,
    DecisionKind.PROPOSE_DONE: ProposeDonePayload,
    DecisionKind.WAIT: WaitPayload,
    DecisionKind.ABORT: AbortPayload,
}


def build_variant_payload_schema(
    decision_kind: DecisionKind,
    serialized_context: str,
) -> dict[str, object]:
    kind = DecisionKind(decision_kind)
    context = json.loads(serialized_context)
    schema = copy.deepcopy(BRANCH_MODELS[kind].model_json_schema())
    properties = cast(dict[str, Any], schema["properties"])
    properties["type"] = {"type": "string", "const": kind.value}
    properties["context_id"] = {"type": "string", "const": context["context_id"]}
    _bind_public_domains(kind, properties, context)
    schema["additionalProperties"] = False
    return schema


def payload_output_model(decision_kind: DecisionKind, serialized_context: str) -> type[Any]:
    kind = DecisionKind(decision_kind)
    schema = build_variant_payload_schema(kind, serialized_context)
    branch_model = BRANCH_MODELS[kind]

    class BoundVariantPayload:
        @classmethod
        def model_json_schema(cls) -> dict[str, object]:
            return schema

        @classmethod
        def model_validate_json(cls, raw: str | bytes | bytearray) -> BaseModel:
            value = strict_json_loads(raw.decode() if isinstance(raw, bytes | bytearray) else raw)
            payload = branch_model.model_validate(value)
            _validate_bound_properties(payload.model_dump(), cast(dict[str, Any], schema["properties"]))
            return payload

    BoundVariantPayload.__name__ = f"Bound{branch_model.__name__}"
    return BoundVariantPayload


def _bind_public_domains(kind: DecisionKind, properties: dict[str, Any], context: dict[str, Any]) -> None:
    actions = context["actions"]
    world = context["world"]
    if kind is DecisionKind.SELECT_ACTION:
        options = actions["options"]
        properties["action_id"] = _enum(item["action_id"] for item in options)
        destination_ids = [
            destination["destination_id"]
            for option in options for destination in option["destinations"]["items"]
        ]
        if any(not option["destination_required"] for option in options):
            destination_ids.append("")
        properties["destination_id"] = _enum(destination_ids)
    elif kind is DecisionKind.REQUEST_OBSERVATION:
        properties["subject_id"] = _enum(_subject_ids(context))
        capabilities = world["observation_capabilities"]
        properties["modality"] = _enum(item["modality"] for item in capabilities)
        properties["required_assurance"] = _enum(item["assurance"] for item in capabilities)
    elif kind is DecisionKind.REQUEST_ACTION_PAGE:
        properties["cursor"] = _const(actions["next_cursor"])
        properties["query"] = _const(actions["active_query"])
        properties["target_id"] = _const(actions["active_target_filter"])
        properties["relevance_role"] = _const(actions["active_relevance_filter"])
    elif kind is DecisionKind.ASK_USER:
        missing = [key for key, value in context["task"]["public_inputs"].items() if value is None]
        if missing:
            properties["requested_fields"]["items"] = _enum(missing)
    elif kind is DecisionKind.PROPOSE_DONE:
        criteria = [item["criterion_id"] for item in context["task"]["success_criteria"]["items"]]
        properties["claimed_criteria"]["items"] = _enum(criteria)
        properties["evidence_refs"]["items"] = _enum(_evidence_refs(context))
        properties["unresolved_items"]["items"] = _enum(_unresolved_items(context))
    elif kind is DecisionKind.WAIT:
        maximum = min(60_000, int(context["budgets"]["remaining_wait_ms"]))
        properties["max_wait_ms"] = {"type": "integer", "minimum": 1, "maximum": maximum}


def _subject_ids(context: dict[str, Any]) -> list[str]:
    ids = [item["target_id"] for item in context["world"]["targets"]["items"]]
    ids.extend(item["target_id"] for item in context["actions"]["options"])
    ids.extend(item["subject_id"] for item in context["world"]["facts"]["items"])
    return list(dict.fromkeys(ids))


def _evidence_refs(context: dict[str, Any]) -> list[str]:
    refs = [item["fact_ref"] for item in context["world"]["facts"]["items"]]
    refs.extend(item["evidence_ref"] for item in context["world"]["artifact_summaries"]["items"])
    refs.extend(item["fact_ref"] for item in context["progress"]["verified_public_facts"])
    return list(dict.fromkeys(refs))


def _unresolved_items(context: dict[str, Any]) -> list[str]:
    progress = context["progress"]
    return [*progress["unresolved_criteria"]["items"], *progress["unresolved_outputs"]["items"]]


def _enum(values) -> dict[str, object]:
    return {"type": "string", "enum": list(dict.fromkeys(values))}


def _const(value: object) -> dict[str, object]:
    return {"type": "string", "const": value}


def _validate_bound_properties(payload: dict[str, Any], properties: dict[str, Any]) -> None:
    for name, rule in properties.items():
        if name not in payload:
            continue
        value = payload[name]
        if "const" in rule and value != rule["const"]:
            raise ValueError(f"{name} differs from the bound public value")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"{name} is outside the bound public domain")
        if isinstance(value, list) and isinstance(rule.get("items"), dict):
            allowed = rule["items"].get("enum")
            if allowed is not None and any(item not in allowed for item in value):
                raise ValueError(f"{name} contains an item outside the bound public domain")
        if isinstance(value, int):
            if "minimum" in rule and value < rule["minimum"]:
                raise ValueError(f"{name} is below the bound minimum")
            if "maximum" in rule and value > rule["maximum"]:
                raise ValueError(f"{name} exceeds the bound maximum")
