"""Typed future provider failures; no provider integration lives here."""

from dataclasses import dataclass
from enum import StrEnum

_MAX_REASON = 240
_SENSITIVE_PATTERNS = ("bearer ", "sk-", "api_key=", "apikey=", "token=", "credential=")


class ModelFailureKind(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_EXHAUSTED = "provider_exhausted"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    SCHEMA_ERROR = "schema_error"
    REFUSED = "refused"
    INTERNAL_ERROR = "internal_error"


class ProviderFailureCode(StrEnum):
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    UNAVAILABLE = "unavailable"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"


class ProviderAttemptOrigin(StrEnum):
    """Where one provider-attempt outcome was produced."""

    NETWORK = "network"
    LOCAL_RUNTIME = "local_runtime"
    LOCAL_CIRCUIT = "local_circuit"
    ORCHESTRATOR_TIMEOUT = "orchestrator_timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ModelFailure:
    kind: ModelFailureKind
    reason: str
    retryable: bool
    provider_code: ProviderFailureCode | None = None
    retry_after_s: float | None = None
    attempt_origin: ProviderAttemptOrigin = ProviderAttemptOrigin.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ModelFailureKind):
            raise TypeError("model failure kind must be typed")
        if type(self.retryable) is not bool:
            raise TypeError("model failure retryable flag must be boolean")
        if self.provider_code is not None and not isinstance(self.provider_code, ProviderFailureCode):
            raise TypeError("provider failure code must be typed")
        if not isinstance(self.attempt_origin, ProviderAttemptOrigin):
            raise TypeError("provider attempt origin must be typed")
        if self.retry_after_s is not None and (isinstance(self.retry_after_s, bool) or self.retry_after_s < 0):
            raise ValueError("provider retry delay must be nonnegative")
        if self.provider_code is None and self.retry_after_s is not None:
            raise ValueError("retry delay requires a provider failure code")
        if self.kind is ModelFailureKind.PROVIDER_EXHAUSTED and self.retryable:
            raise ValueError("provider exhaustion is terminal at the policy boundary")
        reason = self.reason.strip()
        if not reason:
            raise ValueError("model failure reason cannot be blank")
        if any(pattern in reason.casefold() for pattern in _SENSITIVE_PATTERNS):
            raise ValueError("model failure reason contains sensitive provider material")
        object.__setattr__(self, "reason", reason[:_MAX_REASON])
