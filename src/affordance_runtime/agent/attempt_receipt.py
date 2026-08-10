"""Privacy-safe value for exactly one crossed physical world boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.world.acquisition import AcquisitionOrigin, AcquisitionStatus

_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")


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
        if self.exception_class and (
            len(self.exception_class) > 128
            or not self.exception_class.replace("_", "").isalnum()
        ):
            raise ValueError("attempt exception class must be bounded")
