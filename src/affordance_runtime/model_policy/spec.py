"""Canonical closed structured model decision specification."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel, StrictInt, StringConstraints, field_validator

from affordance_runtime.agent.decisions import (
    MAX_RESULT_SUMMARY_CHARS,
    Abort,
    AgentDecision,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.model_policy.strict_json import strict_json_loads, validate_json_tree
from affordance_runtime.world.schema_validation import reject_private_parameter_values

SCHEMA_VERSION = "agent-decision.v3"

ContextId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Id240 = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Optional120 = Annotated[str, StringConstraints(max_length=120)]
Optional240 = Annotated[str, StringConstraints(max_length=240)]
Optional512 = Annotated[str, StringConstraints(max_length=512)]
Reason500 = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Question1000 = Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
Summary1024 = Annotated[str, StringConstraints(min_length=1, max_length=MAX_RESULT_SUMMARY_CHARS)]
Item120 = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Item240 = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Item500 = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Item512 = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class _Payload(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    context_id: ContextId


class SelectActionPayload(_Payload):
    type: Literal["select_action"]
    action_id: Id240
    parameters: dict[str, Any]
    destination_id: Optional240

    @field_validator("parameters")
    @classmethod
    def _bounded_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value)
        return value


class RequestObservationPayload(_Payload):
    type: Literal["request_observation"]
    subject_id: Id240
    modality: Literal["structural", "visual", "environment_state", "user"]
    required_assurance: Literal["weak", "structural", "authoritative"]
    reason: Reason500
    cursor: Optional512 = ""


class RequestActionPagePayload(_Payload):
    type: Literal["request_action_page"]
    query: Optional120
    target_id: Optional240
    relevance_role: Literal["direct", "enabling", "information", "other", ""]
    cursor: Optional512


class AskUserPayload(_Payload):
    type: Literal["ask_user"]
    question: Question1000
    requested_fields: Annotated[list[Item120], Field(max_length=32)]


class ProposeDonePayload(_Payload):
    type: Literal["propose_done"]
    claimed_criteria: Annotated[list[Item240], Field(max_length=32)]
    evidence_refs: Annotated[list[Item512], Field(max_length=32)]
    result_summary: Summary1024
    unresolved_items: Annotated[list[Item500], Field(max_length=32)]


class WaitPayload(_Payload):
    type: Literal["wait"]
    reason: Reason500
    max_wait_ms: Annotated[StrictInt, Field(ge=1, le=60_000)]

    @field_validator("max_wait_ms", mode="before")
    @classmethod
    def _strict_wait_duration(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("wait duration must be a JSON integer")
        return value


class AbortPayload(_Payload):
    type: Literal["abort"]
    reason: Reason500
    category: Literal["policy", "safety", "unsupported", "no_progress", "user_request"]


DecisionPayload: TypeAlias = Annotated[
    SelectActionPayload
    | RequestObservationPayload
    | RequestActionPagePayload
    | AskUserPayload
    | ProposeDonePayload
    | WaitPayload
    | AbortPayload,
    Field(discriminator="type"),
]


class AgentDecisionPayload(RootModel[DecisionPayload]):
    model_config = ConfigDict(
        frozen=True,
        revalidate_instances="always",
    )

    @classmethod
    def model_validate(cls, obj, **kwargs):
        # The discriminated union must first construct its strict frozen payload
        # model from a JSON object (or an immutable mapping used by deterministic
        # ports). Field contracts remain strict; no legacy object fallback exists.
        _require_json_collection_types(obj)
        kwargs.setdefault("strict", False)
        return super().model_validate(obj, **kwargs)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs):
        del kwargs
        raw = bytes(json_data).decode() if isinstance(json_data, bytes | bytearray) else json_data
        return cls.model_validate(strict_json_loads(raw))


def decision_response_schema() -> dict[str, Any]:
    return AgentDecisionPayload.model_json_schema()


def _require_json_collection_types(value: object) -> None:
    """Allow immutable mappings at deterministic ports, but never sequence coercion."""

    from collections.abc import Mapping, Sequence

    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            raise TypeError("structured decision arrays must be JSON lists")
        elif isinstance(item, set | frozenset):
            raise TypeError("structured decision arrays must be JSON lists")


def payload_to_decision(payload: AgentDecisionPayload, expected_context_id: str) -> AgentDecision:
    value = payload.root
    if value.context_id != expected_context_id:
        raise ValueError("decision context is stale")
    if isinstance(value, SelectActionPayload):
        return SelectAction(value.context_id, value.action_id, value.parameters, value.destination_id)
    if isinstance(value, RequestObservationPayload):
        return RequestObservation(
            value.context_id,
            value.subject_id,
            value.modality,
            value.required_assurance,
            value.reason,
            value.cursor,
        )
    if isinstance(value, RequestActionPagePayload):
        return RequestActionPage(
            value.context_id,
            value.query,
            value.target_id,
            value.relevance_role,
            value.cursor,
        )
    if isinstance(value, AskUserPayload):
        return AskUser(value.context_id, value.question, tuple(value.requested_fields))
    if isinstance(value, ProposeDonePayload):
        return ProposeDone(
            value.context_id,
            tuple(value.claimed_criteria),
            tuple(value.evidence_refs),
            value.result_summary,
            tuple(value.unresolved_items),
        )
    if isinstance(value, WaitPayload):
        return Wait(value.context_id, value.reason, value.max_wait_ms)
    return Abort(value.context_id, value.reason, value.category)
