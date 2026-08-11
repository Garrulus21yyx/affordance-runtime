"""Thin application adapter to the repository's existing model transport owner."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from affordance_runtime.agent.decisions import MAX_RESULT_SUMMARY_CHARS
from affordance_runtime.model_boundary.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderFailureCode,
)
from affordance_runtime.model_policy.contracts import ModelDecisionRequest, ModelDecisionResponse, ModelMetadata
from affordance_runtime.model_policy.grounding import (
    DecisionGroundingVariant,
    build_compact_decision_guide,
    build_compact_decision_guide_v2,
    grounding_profile_version,
    serialize_compact_decision_guide,
    serialize_compact_decision_guide_v2,
)
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS
from affordance_runtime.model_policy.schema_identity import decision_schema_digest, grounding_guide_digest
from affordance_runtime.model_policy.spec import (
    SCHEMA_VERSION,
    AgentDecisionPackagePayload,
    decision_response_schema,
)
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
    grounding_variant: DecisionGroundingVariant = DecisionGroundingVariant.FORMAT_ONLY

    def __post_init__(self) -> None:
        if isinstance(self.port, FallbackModelPort):
            raise ValueError("model policy bridge does not admit provider fallback")
        if self.config.rate_limit_retries or self.config.transient_retries:
            raise ValueError("model policy bridge requires a zero retry configuration")
        object.__setattr__(self, "grounding_variant", DecisionGroundingVariant(self.grounding_variant))

    @property
    def grounding_profile_version(self) -> str:
        return grounding_profile_version(self.grounding_variant)

    @property
    def provider_id(self) -> str:
        return _public_id(self.port.provider)

    @property
    def model_id(self) -> str:
        return _public_id(self.port.model)

    @property
    def compatibility_key(self) -> str:
        return ":".join((
            SCHEMA_VERSION,
            self.grounding_profile_version,
            decision_schema_digest(),
        ))

    @property
    def transport_timeout_s(self) -> float:
        return self.config.timeout_s

    async def generate(self, request: ModelDecisionRequest) -> ModelDecisionResponse | ModelFailure:
        if request.schema_version != SCHEMA_VERSION or dict(request.decision_schema) != decision_response_schema():
            return _failure(ModelFailureKind.INTERNAL_ERROR, "model decision schema is not canonical")
        try:
            user_message = _user_message(request, self.grounding_variant)
            messages = (
                ModelMessage(role="system", content=_system_message(self.grounding_variant)),
                ModelMessage(role="user", content=user_message),
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return _failure(ModelFailureKind.INTERNAL_ERROR, "model grounding could not be built")
        try:
            payload = await self.port.generate_structured(
                messages, AgentDecisionPackagePayload, self.config,
            )
        except TimeoutError:
            return _failure(
                ModelFailureKind.TIMEOUT,
                "model transport timed out",
                retryable=True,
                provider_code=ProviderFailureCode.TIMEOUT,
            )
        except ProviderModelError as exc:
            if exc.kind is ProviderFailureKind.QUOTA_EXHAUSTED:
                return _failure(
                    ModelFailureKind.REFUSED,
                    "model provider quota is exhausted",
                    provider_code=ProviderFailureCode.QUOTA_EXHAUSTED,
                )
            provider_code = (
                ProviderFailureCode.RATE_LIMITED
                if exc.kind is ProviderFailureKind.RATE_LIMIT_TRANSIENT
                else ProviderFailureCode.UNAVAILABLE
            )
            return _failure(
                ModelFailureKind.PROVIDER_UNAVAILABLE,
                "model provider declined the request",
                retryable=exc.resumable,
                provider_code=provider_code,
                retry_after_s=exc.retry_after_s,
            )
        except StructuredOutputError:
            return _failure(ModelFailureKind.SCHEMA_ERROR, "model provider returned invalid structured output")
        except StructuredModelError:
            return _failure(ModelFailureKind.INVALID_RESPONSE, "model provider returned an invalid response")
        except Exception:
            return _failure(
                ModelFailureKind.INTERNAL_ERROR,
                "model provider adapter failed",
            )
        metadata = _metadata(
            self.port.last_call,
            self.port,
            self.grounding_variant,
            self.grounding_profile_version,
            *_guide_identity(user_message, self.grounding_variant),
        )
        if metadata.rate_limit_retry_count or metadata.transient_retry_count:
            return _failure(ModelFailureKind.INTERNAL_ERROR, "model transport violated the one-attempt profile")
        return ModelDecisionResponse(payload.model_dump_json(), metadata)


def _metadata(
    record: ModelCallRecord | None,
    port: ModelPort,
    grounding_variant: DecisionGroundingVariant,
    profile_version: str,
    guide_schema_version: str,
    guide_digest: str,
) -> ModelMetadata:
    if record is None:
        return ModelMetadata(
            provider_id=_public_id(port.provider),
            model_id=_public_id(port.model),
            endpoint_class=_public_id(port.endpoint_class),
            schema_version=SCHEMA_VERSION,
            grounding_variant=grounding_variant.value,
            grounding_profile_version=profile_version,
            grounding_guide_schema_version=guide_schema_version,
            grounding_guide_digest=guide_digest,
            decision_schema_digest=decision_schema_digest(),
            result_summary_max_chars=MAX_RESULT_SUMMARY_CHARS,
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
        grounding_variant=grounding_variant.value,
        grounding_profile_version=profile_version,
        grounding_guide_schema_version=guide_schema_version,
        grounding_guide_digest=guide_digest,
        decision_schema_digest=decision_schema_digest(),
        result_summary_max_chars=MAX_RESULT_SUMMARY_CHARS,
    )


def _public_id(value: str) -> str:
    allowed = all(character.isalnum() or character in "._:/-" for character in value)
    if value and len(value) <= 120 and "://" not in value and allowed:
        return value
    return "" if not value else f"id-{hashlib.sha256(value.encode()).hexdigest()}"


def _failure(
    kind: ModelFailureKind,
    reason: str,
    *,
    retryable: bool = False,
    provider_code: ProviderFailureCode | None = None,
    retry_after_s: float | None = None,
) -> ModelFailure:
    return ModelFailure(kind, reason, retryable, provider_code, retry_after_s)


def _user_message(request: ModelDecisionRequest, variant: DecisionGroundingVariant) -> str:
    if variant is DecisionGroundingVariant.FORMAT_ONLY:
        return request.serialized_context
    context = json.loads(request.serialized_context)
    if variant is DecisionGroundingVariant.COMPACT_CONTRACT:
        serialized_guide = serialize_compact_decision_guide(
            build_compact_decision_guide(request.serialized_context)
        )
    else:
        serialized_guide = serialize_compact_decision_guide_v2(
            build_compact_decision_guide_v2(request.serialized_context)
        )
    guide = json.loads(serialized_guide)
    return json.dumps(
        {"agent_context": context, "decision_guide": guide},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _system_message(variant: DecisionGroundingVariant) -> str:
    if variant is DecisionGroundingVariant.FORMAT_ONLY:
        return MODEL_POLICY_INSTRUCTIONS
    if variant is DecisionGroundingVariant.COMPACT_CONTRACT:
        return MODEL_POLICY_INSTRUCTIONS + (
        "\nThe provider enforces a JSON schema. The user message also contains a compact "
        "decision guide. Copy the current context_id and one currently visible action_id exactly."
        )
    return MODEL_POLICY_INSTRUCTIONS + (
        "\nUse the decision-neutral guide's current public field domains. "
        "Choose one legal decision; Runtime revalidates every proposal."
    )


def _guide_identity(user_message: str, variant: DecisionGroundingVariant) -> tuple[str, str]:
    if variant is DecisionGroundingVariant.FORMAT_ONLY:
        return "", ""
    guide = json.loads(user_message)["decision_guide"]
    serialized = json.dumps(guide, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return grounding_profile_version(variant), grounding_guide_digest(serialized)
