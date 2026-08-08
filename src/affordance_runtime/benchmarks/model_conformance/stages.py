"""Locate the earliest structured-decision conformance failure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.spec import (
    AbortPayload,
    AgentDecisionPayload,
    SelectActionPayload,
)
from affordance_runtime.model_policy.strict_json import StrictJsonError, strict_json_loads
from affordance_runtime.world.schema_validation import reject_private_parameter_values

from .contracts import ModelConformanceStage


@dataclass(frozen=True)
class AttributedDecision:
    stage: ModelConformanceStage
    failure_kind: str = ""
    decision_variant: str = ""


def attribute_decision_payload(
    outcome: str | ModelFailure,
    expected_context_id: str,
    visible_action_ids: Sequence[str],
    visible_destinations: Mapping[str, Sequence[str]],
    *,
    runtime_admission_error: str = "",
) -> AttributedDecision:
    if isinstance(outcome, ModelFailure):
        return _model_failure_stage(outcome)
    try:
        loaded = strict_json_loads(outcome)
    except StrictJsonError:
        return AttributedDecision(ModelConformanceStage.STRICT_JSON, "invalid_response")
    try:
        payload = AgentDecisionPayload.model_validate(loaded).root
    except (ValidationError, TypeError, ValueError):
        return AttributedDecision(ModelConformanceStage.PAYLOAD_SCHEMA, "schema_error")
    variant = str(payload.type)
    if payload.context_id != expected_context_id:
        return AttributedDecision(ModelConformanceStage.CONTEXT_ID, "stale_context", variant)
    if isinstance(payload, AbortPayload):
        return AttributedDecision(ModelConformanceStage.MODEL_ABORT, "model_abort", variant)
    if isinstance(payload, SelectActionPayload):
        if payload.action_id not in visible_action_ids:
            return AttributedDecision(ModelConformanceStage.ACTION_ID, "hidden_action", variant)
        if payload.destination_id not in visible_destinations.get(payload.action_id, ("",)):
            return AttributedDecision(ModelConformanceStage.DESTINATION_ID, "hidden_destination", variant)
        try:
            reject_private_parameter_values(payload.parameters)
        except ValueError:
            return AttributedDecision(ModelConformanceStage.PARAMETERS, "private_parameters", variant)
    if runtime_admission_error:
        return AttributedDecision(ModelConformanceStage.RUNTIME_ADMISSION, "runtime_rejected", variant)
    return AttributedDecision(ModelConformanceStage.SUCCESS, decision_variant=variant)


def _model_failure_stage(failure: ModelFailure) -> AttributedDecision:
    if failure.kind == ModelFailureKind.TIMEOUT:
        return AttributedDecision(ModelConformanceStage.TIMEOUT, failure.kind.value)
    if failure.kind == ModelFailureKind.PROVIDER_UNAVAILABLE:
        return AttributedDecision(ModelConformanceStage.TRANSPORT, failure.kind.value)
    if failure.kind == ModelFailureKind.INVALID_RESPONSE:
        return AttributedDecision(ModelConformanceStage.STRUCTURED_OUTPUT, failure.kind.value)
    return AttributedDecision(ModelConformanceStage.PAYLOAD_SCHEMA, failure.kind.value)

