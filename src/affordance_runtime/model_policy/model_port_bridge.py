"""Thin application adapter to the repository's existing model transport owner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.contracts import ModelDecisionRequest, ModelDecisionResponse, ModelMetadata
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS
from affordance_runtime.model_policy.spec import SCHEMA_VERSION, AgentDecisionPayload, decision_response_schema
from affordance_runtime.model_port import (
    FallbackModelPort,
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
)


@dataclass(frozen=True)
class ModelPortDecisionAdapter:
    port: ModelPort
    config: ModelConfig

    def __post_init__(self) -> None:
        if isinstance(self.port, FallbackModelPort):
            raise ValueError("model policy bridge does not admit provider fallback")
        if self.config.rate_limit_retries or self.config.transient_retries:
            raise ValueError("model policy bridge requires a zero retry configuration")

    async def generate(self, request: ModelDecisionRequest) -> ModelDecisionResponse | ModelFailure:
        if request.schema_version != SCHEMA_VERSION or dict(request.decision_schema) != decision_response_schema():
            return _failure(ModelFailureKind.INTERNAL_ERROR, "model decision schema is not canonical")
        messages = (
            ModelMessage(role="system", content=MODEL_POLICY_INSTRUCTIONS),
            ModelMessage(role="user", content=request.serialized_context),
        )
        try:
            payload = await self.port.generate_structured(messages, AgentDecisionPayload, self.config)
        except TimeoutError:
            return _failure(ModelFailureKind.TIMEOUT, "model transport timed out")
        except ProviderModelError as exc:
            kind = ModelFailureKind.REFUSED if exc.kind == ProviderFailureKind.QUOTA_EXHAUSTED else ModelFailureKind.PROVIDER_UNAVAILABLE
            return _failure(kind, "model provider declined the request", retryable=exc.resumable)
        except StructuredOutputError:
            return _failure(ModelFailureKind.SCHEMA_ERROR, "model provider returned invalid structured output")
        except StructuredModelError:
            return _failure(ModelFailureKind.INVALID_RESPONSE, "model provider returned an invalid response")
        except Exception:
            return _failure(ModelFailureKind.PROVIDER_UNAVAILABLE, "model provider adapter failed")
        metadata = _metadata(self.port.last_call, self.port)
        if metadata.rate_limit_retry_count or metadata.transient_retry_count:
            return _failure(ModelFailureKind.INTERNAL_ERROR, "model transport violated the one-attempt profile")
        return ModelDecisionResponse(payload.model_dump_json(), metadata)


def _metadata(record: ModelCallRecord | None, port: ModelPort) -> ModelMetadata:
    if record is None:
        return ModelMetadata(
            provider_id=_public_id(port.provider),
            model_id=_public_id(port.model),
            endpoint_class=_public_id(port.endpoint_class),
            schema_version=SCHEMA_VERSION,
        )
    return ModelMetadata(
        provider_id=_public_id(record.provider),
        model_id=_public_id(record.model),
        response_id=_public_id(record.response_id),
        endpoint_class=_public_id(record.endpoint_class),
        prompt_version=_public_id(record.prompt_version),
        schema_version=SCHEMA_VERSION,
        latency_ms=record.latency_ms,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        rate_limit_retry_count=record.rate_limit_retry_count,
        transient_retry_count=record.transient_retry_count,
    )


def _public_id(value: str) -> str:
    allowed = all(character.isalnum() or character in "._:/-" for character in value)
    if value and len(value) <= 120 and "://" not in value and allowed:
        return value
    return "" if not value else f"id-{hashlib.sha256(value.encode()).hexdigest()}"


def _failure(kind: ModelFailureKind, reason: str, *, retryable: bool = False) -> ModelFailure:
    return ModelFailure(kind, reason, retryable)
