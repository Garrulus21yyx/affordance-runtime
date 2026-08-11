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
_ATTEMPT_ID = re.compile(r"attempt:[1-9][0-9]{0,9}")


def safe_exception_class(error: BaseException) -> str:
    """Return a stable bounded token without trusting a foreign class name."""

    name = type(error).__name__
    if _EXCEPTION_CLASS.fullmatch(name) is not None:
        return name
    digest = hashlib.sha256(name.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"ExceptionClass_{digest}"


def safe_boundary_identity(actual: str, expected: str, *, kind: str) -> str:
    """Retain equality truth while making a foreign mismatch opaque."""

    if actual == expected and kind == "request":
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
        if not isinstance(self.operation, AttemptOperation):
            raise TypeError("attempt operation must be typed")
        if not isinstance(self.disposition, AttemptDisposition):
            raise TypeError("attempt disposition must be typed")
        if self.expected_origin is not None and not isinstance(
            self.expected_origin, AcquisitionOrigin
        ):
            raise TypeError("expected acquisition origin must be typed")
        if self.actual_origin is not None and not isinstance(
            self.actual_origin, AcquisitionOrigin
        ):
            raise TypeError("actual acquisition origin must be typed")
        if self.dispatch_status is not None and not isinstance(
            self.dispatch_status, DispatchStatus
        ):
            raise TypeError("attempt dispatch status must be typed")
        if self.request_lineage_valid is not None and type(
            self.request_lineage_valid
        ) is not bool:
            raise TypeError("attempt request lineage must be boolean")
        if self.acquisition_status is not None and not isinstance(
            self.acquisition_status, AcquisitionStatus
        ):
            raise TypeError("attempt acquisition status must be typed")
        if _ATTEMPT_ID.fullmatch(self.attempt_id) is None:
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
        self._validate_operation_matrix()

    def _validate_operation_matrix(self) -> None:
        returned = self.disposition is AttemptDisposition.RETURNED
        exceptional = self.disposition in {
            AttemptDisposition.THREW,
            AttemptDisposition.CANCELLED,
        }
        if exceptional != bool(self.exception_class):
            raise ValueError("attempt exception class does not match disposition")
        if self.disposition is AttemptDisposition.MALFORMED and self.exception_class:
            raise ValueError("malformed return cannot carry an exception class")

        if self.operation is AttemptOperation.RESET:
            if (
                self.request_kind != "reset"
                or self.expected_origin is not AcquisitionOrigin.RESET
                or (
                    self.acquisition_attempts,
                    self.execution_attempts,
                    self.effectful_dispatches,
                    self.currentness_probe_count,
                )
                != (1, 0, 0, 0)
                or self.dispatch_status is not None
                or self.expected_request_id
                or self.actual_request_id
                or self.request_lineage_valid is not None
            ):
                raise ValueError("reset attempt violates the physical operation matrix")
            if returned:
                if (
                    self.actual_origin is None
                    or self.acquisition_status is None
                ):
                    raise ValueError("returned reset requires typed acquisition truth")
            elif self.actual_origin is not None or self.acquisition_status is not None:
                raise ValueError("failed reset cannot fabricate acquisition truth")
            return

        if self.operation is AttemptOperation.CAPTURE:
            if (
                self.expected_origin is not AcquisitionOrigin.INDEPENDENT_CAPTURE
                or (
                    self.acquisition_attempts,
                    self.execution_attempts,
                    self.effectful_dispatches,
                    self.currentness_probe_count,
                )
                != (1, 0, 0, 0)
                or self.dispatch_status is not None
                or self.expected_request_id
                or self.actual_request_id
                or self.request_lineage_valid is not None
            ):
                raise ValueError("capture attempt violates the physical operation matrix")
            if returned:
                if self.actual_origin is None or self.acquisition_status is None:
                    raise ValueError("returned capture requires typed acquisition truth")
            elif (
                self.actual_origin is not None
                or self.acquisition_status is not AcquisitionStatus.FAILED
            ):
                raise ValueError("failed capture requires explicit failed acquisition truth")
            return

        if (
            self.operation is not AttemptOperation.EXECUTE
            or self.expected_origin is not AcquisitionOrigin.POST_ACTION
            or self.execution_attempts != 1
            or not self.expected_request_id
        ):
            raise ValueError("execute attempt violates the physical operation matrix")
        if returned:
            expected_dispatches = int(self.dispatch_status is not DispatchStatus.NOT_SENT)
            if (
                self.dispatch_status is None
                or self.effectful_dispatches != expected_dispatches
                or self.acquisition_attempts not in {0, 1}
                or not self.actual_request_id
                or self.request_lineage_valid is None
                or self.acquisition_status is None
            ):
                raise ValueError("returned execute violates the disposition matrix")
            if self.request_lineage_valid and (
                self.actual_request_id != self.expected_request_id
            ):
                raise ValueError("valid execute lineage requires matching request identity")
            expected_acquisition_attempts = {
                AcquisitionStatus.ACQUIRED: 1,
                AcquisitionStatus.FAILED: 1,
                AcquisitionStatus.CAPABILITY_UNAVAILABLE: 0,
            }[self.acquisition_status]
            if (
                self.actual_origin is not AcquisitionOrigin.POST_ACTION
                or self.acquisition_attempts != expected_acquisition_attempts
            ):
                raise ValueError(
                    "returned execute acquisition truth violates its status matrix"
                )
        elif (
            self.acquisition_attempts,
            self.effectful_dispatches,
            self.currentness_probe_count,
        ) != (0, 0, 0) or any(
            (
                self.dispatch_status is not None,
                bool(self.actual_request_id),
                self.request_lineage_valid is not None,
                self.acquisition_status is not None,
                self.actual_origin is not None,
            )
        ):
            raise ValueError("failed execute cannot fabricate returned facts")
