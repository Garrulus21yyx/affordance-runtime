"""Privacy-safe value for exactly one crossed physical world boundary."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.world.acquisition import AcquisitionOrigin, AcquisitionStatus

_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")
_EXCEPTION_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


def safe_exception_class(error: BaseException) -> str:
    """Return a stable bounded token without trusting a foreign class name."""

    name = type(error).__name__
    if _EXCEPTION_CLASS.fullmatch(name) is not None:
        return name
    digest = hashlib.sha256(name.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"ExceptionClass_{digest}"


def safe_boundary_identity(actual: str, expected: str, *, kind: str) -> str:
    """Retain equality truth while making a foreign mismatch opaque."""

    if actual == expected:
        return expected
    digest = hashlib.sha256(
        f"{kind}\0{actual}".encode("utf-8", errors="surrogatepass")
    ).hexdigest()
    return f"{kind}_sha256_{digest}"


class AttemptOperation(StrEnum):
    RESET = "reset"
    CAPTURE = "capture"
    EXECUTE = "execute"


class AttemptDisposition(StrEnum):
    RETURNED = "returned"
    THREW = "threw"
    CANCELLED = "cancelled"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class AttemptReceipt:
    attempt_id: str
    operation: AttemptOperation
    request_kind: str
    expected_origin: AcquisitionOrigin | None
    actual_origin: AcquisitionOrigin | None
    disposition: AttemptDisposition
    reason_code: str
    acquisition_attempts: int
    execution_attempts: int
    effectful_dispatches: int
    currentness_probe_count: int
    dispatch_status: DispatchStatus | None = None
    expected_request_id: str = ""
    actual_request_id: str = ""
    request_lineage_valid: bool | None = None
    exception_class: str = ""
    acquisition_status: AcquisitionStatus | None = None

    def __post_init__(self) -> None:
        if not self.attempt_id.startswith("attempt:"):
            raise ValueError("attempt receipt identity is invalid")
        if _CODE.fullmatch(self.reason_code) is None:
            raise ValueError("attempt reason code must be bounded stable snake-case")
        values = (
            self.acquisition_attempts,
            self.execution_attempts,
            self.effectful_dispatches,
            self.currentness_probe_count,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("attempt receipt scalars must be non-negative integers")
        if self.effectful_dispatches > self.execution_attempts:
            raise ValueError("effectful dispatches cannot exceed execution attempts")
        if self.exception_class and _EXCEPTION_CLASS.fullmatch(self.exception_class) is None:
            raise ValueError("attempt exception class must be bounded")
