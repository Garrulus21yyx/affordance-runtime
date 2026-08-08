"""Typed future provider failures; no provider integration lives here."""

from dataclasses import dataclass
from enum import StrEnum

_MAX_REASON = 240
_SENSITIVE_PATTERNS = ("bearer ", "sk-", "api_key=", "apikey=", "token=", "credential=")


class ModelFailureKind(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    SCHEMA_ERROR = "schema_error"
    REFUSED = "refused"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class ModelFailure:
    kind: ModelFailureKind
    reason: str
    retryable: bool

    def __post_init__(self) -> None:
        reason = self.reason.strip()
        if not reason:
            raise ValueError("model failure reason cannot be blank")
        if any(pattern in reason.casefold() for pattern in _SENSITIVE_PATTERNS):
            raise ValueError("model failure reason contains sensitive provider material")
        object.__setattr__(self, "reason", reason[:_MAX_REASON])
