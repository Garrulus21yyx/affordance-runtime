"""Diagnostic prompt/schema variants and evidence-based adoption rule."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel

from affordance_runtime.model_policy.grounding import (
    build_compact_decision_guide,
    build_compact_decision_guide_v2,
    serialize_compact_decision_guide,
    serialize_compact_decision_guide_v2,
)
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS


class GroundingVariant(StrEnum):
    FORMAT_ONLY = "format-only"
    COMPACT_CONTRACT = "compact-contract"
    COMPACT_CONTRACT_V2 = "compact-contract-v2"
    FULL_SCHEMA_TEXT = "full-schema-text"
    CONTEXT_BOUND_SCHEMA = "context-bound-schema"


@dataclass(frozen=True)
class GroundedInput:
    system_message: str
    user_message: str
    provider_schema: dict[str, object]
    prompt_delta_bytes: int


@dataclass(frozen=True)
class CompactGroundingEvidence:
    mistral_no_regression: bool
    fixture_no_regression: bool
    parser_unchanged: bool
    runtime_admission_unchanged: bool
    privacy_passed: bool
    prompt_delta_bytes: int
    ollama_improved: bool
    zero_retry_fallback: bool
    action_space_unchanged: bool
    model_specific_branches: bool


def build_grounded_input(
    serialized_context: str,
    schema: dict[str, object],
    variant: GroundingVariant,
    *,
    guide_context: str | None = None,
) -> GroundedInput:
    if variant == GroundingVariant.FORMAT_ONLY:
        return GroundedInput(MODEL_POLICY_INSTRUCTIONS, serialized_context, schema, 0)
    context = json.loads(serialized_context)
    public_guide_context = guide_context or serialized_context
    if variant in {GroundingVariant.COMPACT_CONTRACT, GroundingVariant.COMPACT_CONTRACT_V2}:
        guide = json.loads(
            serialize_compact_decision_guide(build_compact_decision_guide(public_guide_context))
            if variant is GroundingVariant.COMPACT_CONTRACT
            else serialize_compact_decision_guide_v2(
                build_compact_decision_guide_v2(public_guide_context)
            )
        )
        user = _json({"agent_context": context, "decision_guide": guide})
        system = MODEL_POLICY_INSTRUCTIONS + (
            "\nThe provider enforces a JSON schema. Use the compact public decision guide."
            if variant is GroundingVariant.COMPACT_CONTRACT_V2
            else "\nThe provider enforces a JSON schema. The user message also contains a compact "
                 "decision guide. Copy the current context_id and one currently visible action_id exactly."
        )
        return GroundedInput(system, user, schema, len(user.encode()) - len(serialized_context.encode()))
    if variant == GroundingVariant.FULL_SCHEMA_TEXT:
        user = _json({"agent_context": context, "decision_schema": schema})
        return GroundedInput(
            MODEL_POLICY_INSTRUCTIONS, user, schema,
            len(user.encode()) - len(serialized_context.encode()),
        )
    if variant == GroundingVariant.CONTEXT_BOUND_SCHEMA:
        guide_value = json.loads(public_guide_context)
        action_ids = tuple(
            str(item.get("action_id") or "")
            for item in guide_value.get("actions", {}).get("options", ()) if isinstance(item, dict)
        )
        bound = context_bound_schema(
            schema, str(guide_value.get("context_id") or context.get("context_id") or ""), action_ids,
        )
        return GroundedInput(MODEL_POLICY_INSTRUCTIONS, serialized_context, bound, 0)
    raise ValueError(f"unsupported grounding variant: {variant}")


def context_bound_schema(
    schema: dict[str, object], context_id: str, action_ids: tuple[str, ...],
) -> dict[str, object]:
    bound = deepcopy(schema)
    definitions = bound.get("$defs", {})
    if not isinstance(definitions, dict):
        definitions = {}
    for definition in definitions.values():
        properties = definition.get("properties", {}) if isinstance(definition, dict) else {}
        if isinstance(properties, dict) and "context_id" in properties:
            properties["context_id"] = {"const": context_id, "type": "string"}
    root_properties = bound.get("properties", {})
    if isinstance(root_properties, dict) and "context_id" in root_properties:
        root_properties["context_id"] = {"const": context_id, "type": "string"}
    select = definitions.get("SelectActionPayload", bound)
    properties = select.get("properties", {}) if isinstance(select, dict) else {}
    if not isinstance(properties, dict) or "action_id" not in properties:
        raise ValueError("canonical SelectAction schema is absent")
    properties["action_id"] = {"enum": list(action_ids), "type": "string"}
    return bound


PayloadT = TypeVar("PayloadT", bound=BaseModel)


def diagnostic_schema_model(base: type[PayloadT], schema: dict[str, object]) -> type[PayloadT]:
    class DiagnosticPayload(base):  # type: ignore[misc, valid-type]
        @classmethod
        def model_json_schema(cls, *args, **kwargs):
            del cls, args, kwargs
            return deepcopy(schema)

    DiagnosticPayload.__name__ = f"ContextBound{base.__name__}"
    return DiagnosticPayload


def evaluate_compact_grounding_adoption(evidence: CompactGroundingEvidence) -> str:
    gates = (
        evidence.mistral_no_regression, evidence.fixture_no_regression,
        evidence.parser_unchanged, evidence.runtime_admission_unchanged,
        evidence.privacy_passed, evidence.prompt_delta_bytes <= 4_096,
        evidence.ollama_improved, evidence.zero_retry_fallback,
        evidence.action_space_unchanged, not evidence.model_specific_branches,
    )
    return "adoptable" if all(gates) else "diagnostic_only"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
