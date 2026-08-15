"""Bounded recovery around one-attempt structured decision provider ports."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field, replace
from enum import StrEnum
from time import monotonic
from typing import Generic, TypeVar

from affordance_runtime.agent.context.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.agent.decision_capability import (
    DecisionCapability,
    normalize_decision_capabilities,
)
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
    ResolvedModelDecision,
)
from affordance_runtime.model.policy.port import StructuredModelPort

ResolvedT = TypeVar("ResolvedT", bound=ResolvedModelDecision)


class ProviderAttemptStatus(StrEnum):
    ACCEPTED = "accepted"
    RETRYABLE_FAILURE = "retryable_failure"
    NON_RETRYABLE_FAILURE = "non_retryable_failure"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ProviderAttemptReceipt:
    policy_request_id: str
    attempt_number: int
    profile_index: int
    provider_id: str
    model_id: str
    status: ProviderAttemptStatus
    failure_kind: ModelFailureKind | None = None
    failure_code: ProviderFailureCode | None = None
    retry_after_s: float | None = None
    scheduled_delay_s: float = 0.0
    response_id: str = ""
    origin: ProviderAttemptOrigin = ProviderAttemptOrigin.UNKNOWN

    def __post_init__(self) -> None:
        if not self.policy_request_id or self.attempt_number <= 0 or self.profile_index < 0:
            raise ValueError("provider attempt receipt identity is invalid")
        if not isinstance(self.status, ProviderAttemptStatus):
            raise TypeError("provider attempt receipt status must be typed")
        if not isinstance(self.origin, ProviderAttemptOrigin):
            raise TypeError("provider attempt receipt origin must be typed")
        if self.status is ProviderAttemptStatus.ACCEPTED:
            if self.failure_kind is not None or self.failure_code is not None:
                raise ValueError("accepted provider attempt cannot carry failure facts")
        elif self.status is not ProviderAttemptStatus.CANCELLED and self.failure_kind is None:
            raise ValueError("failed provider attempt requires a failure kind")
        for value in (self.retry_after_s, self.scheduled_delay_s):
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError("provider attempt delays must be nonnegative")


@dataclass(frozen=True)
class ProviderCallPolicy:
    max_attempts_per_profile: int = 3
    backoff_s: tuple[float, ...] = (2.0, 5.0)
    jitter_ratio: float = 0.15
    max_delay_s: float = 30.0
    total_elapsed_deadline_s: float = 88.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts_per_profile <= 4:
            raise ValueError("provider attempts must be within [1, 4]")
        if len(self.backoff_s) < self.max_attempts_per_profile - 1:
            raise ValueError("provider backoff schedule does not cover configured retries")
        if any(value < 0 for value in self.backoff_s):
            raise ValueError("provider backoff values must be nonnegative")
        if not 0 <= self.jitter_ratio <= 0.5:
            raise ValueError("provider jitter ratio must be within [0, 0.5]")
        if self.max_delay_s < 0 or self.total_elapsed_deadline_s <= 0:
            raise ValueError("provider delay and deadline bounds are invalid")


@dataclass(frozen=True)
class ProviderCallOrchestrator(Generic[ResolvedT]):
    """Retry retryable provider failures without creating GUI policy turns."""

    ports: tuple[StructuredModelPort[ResolvedT], ...]
    policy: ProviderCallPolicy = ProviderCallPolicy()
    last_attempts: tuple[ProviderAttemptReceipt, ...] = field(default=(), init=False, compare=False)
    last_fallback_count: int = field(default=0, init=False, compare=False)

    def __post_init__(self) -> None:
        if not self.ports:
            raise ValueError("provider orchestrator requires at least one port")
        keys = tuple(getattr(port, "compatibility_key", "") for port in self.ports)
        if any(not key for key in keys) or len(set(keys)) != 1:
            raise ValueError("fallback providers must share one schema/capability profile")
        context_modes = tuple(
            bool(getattr(port, "requires_serialized_context", True)) for port in self.ports
        )
        if len(set(context_modes)) != 1:
            raise ValueError("fallback providers must share one context input mode")
        declarations = tuple(getattr(port, "supported_decisions", None) for port in self.ports)
        if any(item is not None for item in declarations):
            if any(item is None for item in declarations):
                raise ValueError("fallback decision ports must all declare supported decisions")
            capabilities = tuple(
                normalize_decision_capabilities(
                    item,
                    field_name="fallback port supported_decisions",
                )
                for item in declarations
            )
            if len(set(capabilities)) != 1:
                raise ValueError("fallback providers must support the same decisions")

    @property
    def transport_timeout_s(self) -> float:
        return self.policy.total_elapsed_deadline_s

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return normalize_decision_capabilities(
            getattr(self.primary_port, "supported_decisions", frozenset()),
            field_name="primary port supported_decisions",
        )

    @property
    def requires_serialized_context(self) -> bool:
        return bool(getattr(self.primary_port, "requires_serialized_context", True))

    @property
    def primary_port(self) -> StructuredModelPort[ResolvedT]:
        return self.ports[0]

    @property
    def config(self):
        """Compatibility read of the one-attempt transport configuration."""

        return getattr(self.primary_port, "config", None)

    @property
    def grounding_variant(self):
        return getattr(self.primary_port, "grounding_variant", None)

    @property
    def grounding_profile_version(self) -> str:
        return str(getattr(self.primary_port, "grounding_profile_version", ""))

    @property
    def configured_retry_count(self) -> int:
        return self.policy.max_attempts_per_profile - 1

    @property
    def configured_fallback_count(self) -> int:
        return len(self.ports) - 1

    async def generate(self, request: ModelDecisionRequest) -> ResolvedT | ModelFailure:
        object.__setattr__(self, "last_attempts", ())
        object.__setattr__(self, "last_fallback_count", 0)
        started = monotonic()
        receipts: list[ProviderAttemptReceipt] = []
        last_retryable: ModelFailure | None = None
        accepted = False
        try:
            for profile_index, port in enumerate(self.ports):
                if profile_index:
                    object.__setattr__(self, "last_fallback_count", profile_index)
                for local_attempt in range(self.policy.max_attempts_per_profile):
                    attempt_number = len(receipts) + 1
                    remaining = self.policy.total_elapsed_deadline_s - (monotonic() - started)
                    if remaining <= 0:
                        return self._exhausted(last_retryable, receipts)
                    try:
                        outcome = await asyncio.wait_for(port.generate(request), timeout=remaining)
                    except asyncio.CancelledError:
                        receipts.append(
                            self._receipt(
                                request,
                                port,
                                attempt_number,
                                profile_index,
                                ProviderAttemptStatus.CANCELLED,
                            )
                        )
                        raise
                    except TimeoutError:
                        outcome = ModelFailure(
                            ModelFailureKind.TIMEOUT,
                            "provider attempt exceeded the orchestration deadline",
                            True,
                            ProviderFailureCode.TIMEOUT,
                            attempt_origin=ProviderAttemptOrigin.ORCHESTRATOR_TIMEOUT,
                        )
                    except Exception as exc:
                        # A local adapter/catalog defect is not provider
                        # unavailability and must never enter provider retry.
                        outcome = ModelFailure(
                            ModelFailureKind.INTERNAL_ERROR,
                            f"decision port raised {type(exc).__name__}",
                            False,
                            attempt_origin=ProviderAttemptOrigin.UNKNOWN,
                        )
                    if not isinstance(outcome, ModelFailure):
                        if accepted:
                            return ModelFailure(
                                ModelFailureKind.INTERNAL_ERROR,
                                "multiple provider responses were accepted",
                                False,
                            )
                        accepted = True
                        receipts.append(
                            self._receipt(
                                request,
                                port,
                                attempt_number,
                                profile_index,
                                ProviderAttemptStatus.ACCEPTED,
                                response_id=outcome.metadata.response_id,
                            )
                        )
                        object.__setattr__(self, "last_attempts", tuple(receipts))
                        rate_retries = sum(
                            item.failure_code is ProviderFailureCode.RATE_LIMITED for item in receipts[:-1]
                        )
                        transient_retries = len(receipts) - 1 - rate_retries
                        return replace(
                            outcome,
                            metadata=replace(
                                outcome.metadata,
                                rate_limit_retry_count=rate_retries,
                                transient_retry_count=transient_retries,
                            ),
                        )
                    if not isinstance(outcome, ModelFailure):
                        outcome = ModelFailure(
                            ModelFailureKind.INVALID_RESPONSE,
                            "provider returned an invalid envelope",
                            False,
                        )
                    if not _is_retryable_provider_failure(outcome):
                        receipts.append(
                            self._receipt(
                                request,
                                port,
                                attempt_number,
                                profile_index,
                                ProviderAttemptStatus.NON_RETRYABLE_FAILURE,
                                failure=outcome,
                            )
                        )
                        object.__setattr__(self, "last_attempts", tuple(receipts))
                        return outcome
                    last_retryable = outcome
                    can_retry_here = local_attempt + 1 < self.policy.max_attempts_per_profile
                    can_fallback = profile_index + 1 < len(self.ports)
                    delay = self._delay(request.request_id, local_attempt, outcome) if can_retry_here else 0.0
                    receipts.append(
                        self._receipt(
                            request,
                            port,
                            attempt_number,
                            profile_index,
                            ProviderAttemptStatus.RETRYABLE_FAILURE,
                            failure=outcome,
                            scheduled_delay_s=delay,
                        )
                    )
                    if can_retry_here:
                        remaining = self.policy.total_elapsed_deadline_s - (monotonic() - started)
                        if delay >= remaining:
                            return self._exhausted(last_retryable, receipts)
                        if delay:
                            await asyncio.sleep(delay)
                        continue
                    if can_fallback:
                        break
                    return self._exhausted(last_retryable, receipts)
            return self._exhausted(last_retryable, receipts)
        finally:
            object.__setattr__(self, "last_attempts", tuple(receipts))

    def _delay(self, request_id: str, local_attempt: int, failure: ModelFailure) -> float:
        if failure.retry_after_s is not None:
            return min(self.policy.max_delay_s, failure.retry_after_s)
        base = self.policy.backoff_s[local_attempt]
        digest = hashlib.sha256(f"{request_id}:{local_attempt}".encode()).digest()
        unit = int.from_bytes(digest[:2], "big") / 65_535
        factor = 1 + (unit * 2 - 1) * self.policy.jitter_ratio
        return min(self.policy.max_delay_s, round(base * factor, 3))

    def _receipt(
        self,
        request: ModelDecisionRequest,
        port: StructuredModelPort[ResolvedT],
        attempt_number: int,
        profile_index: int,
        status: ProviderAttemptStatus,
        *,
        failure: ModelFailure | None = None,
        scheduled_delay_s: float = 0.0,
        response_id: str = "",
    ) -> ProviderAttemptReceipt:
        return ProviderAttemptReceipt(
            request.request_id,
            attempt_number,
            profile_index,
            str(getattr(port, "provider_id", "")),
            str(getattr(port, "model_id", "")),
            status,
            failure.kind if failure is not None else None,
            failure.provider_code if failure is not None else None,
            failure.retry_after_s if failure is not None else None,
            scheduled_delay_s,
            response_id,
            (
                getattr(port, "last_attempt_origin", ProviderAttemptOrigin.NETWORK)
                if status is ProviderAttemptStatus.ACCEPTED
                else failure.attempt_origin
                if failure is not None
                else ProviderAttemptOrigin.UNKNOWN
            ),
        )

    def _exhausted(
        self,
        failure: ModelFailure | None,
        receipts: list[ProviderAttemptReceipt],
    ) -> ModelFailure:
        object.__setattr__(self, "last_attempts", tuple(receipts))
        return ModelFailure(
            ModelFailureKind.PROVIDER_EXHAUSTED,
            "model decision providers exhausted bounded recovery",
            False,
            failure.provider_code if failure is not None else ProviderFailureCode.UNAVAILABLE,
        )


def _is_retryable_provider_failure(failure: ModelFailure) -> bool:
    return bool(
        failure.retryable
        and failure.kind
        in {
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            ModelFailureKind.TIMEOUT,
        }
        and failure.provider_code
        in {
            ProviderFailureCode.RATE_LIMITED,
            ProviderFailureCode.TIMEOUT,
            ProviderFailureCode.TRANSPORT,
            ProviderFailureCode.UNAVAILABLE,
        }
    )
