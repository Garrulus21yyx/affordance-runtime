"""Typed causal post-action transition owned by the BrowserGym boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import freeze_json


class BrowserGymStabilityStatus(StrEnum):
    STABLE_NO_NAVIGATION = "stable_no_navigation"
    STABLE_NAVIGATION = "stable_navigation"
    NAVIGATION_PENDING = "navigation_pending"
    ACQUISITION_UNSTABLE = "acquisition_unstable"


@dataclass(frozen=True)
class BrowserGymTransitionTrace:
    dispatch_started: float
    dispatch_returned: float
    navigation_started: float | None
    navigation_committed: float | None
    post_capture_started: float | None
    post_capture_completed: float | None
    before_url: str
    after_url: str
    before_document_epoch: int
    after_document_epoch: int
    stability_status: BrowserGymStabilityStatus

    def __post_init__(self) -> None:
        values = (
            self.dispatch_started,
            self.dispatch_returned,
            self.navigation_started,
            self.navigation_committed,
            self.post_capture_started,
            self.post_capture_completed,
        )
        if any(
            value is not None and (
                isinstance(value, bool) or not isinstance(value, int | float) or value < 0
            )
            for value in values
        ):
            raise ValueError("BrowserGym transition timestamps must be non-negative milliseconds")
        if self.dispatch_returned < self.dispatch_started:
            raise ValueError("BrowserGym dispatch return cannot precede dispatch start")
        if self.navigation_committed is not None and self.navigation_started is None:
            raise ValueError("BrowserGym navigation commit requires navigation start")
        if self.post_capture_completed is not None and self.post_capture_started is None:
            raise ValueError("BrowserGym post capture completion requires capture start")
        if self.post_capture_started is not None and self.post_capture_started < self.dispatch_started:
            raise ValueError("BrowserGym post capture cannot precede dispatch")
        if not isinstance(self.before_url, str) or not isinstance(self.after_url, str):
            raise TypeError("BrowserGym transition URLs must be strings")
        if (
            isinstance(self.before_document_epoch, bool)
            or isinstance(self.after_document_epoch, bool)
            or not isinstance(self.before_document_epoch, int)
            or not isinstance(self.after_document_epoch, int)
            or self.before_document_epoch < 0
            or self.after_document_epoch < self.before_document_epoch
        ):
            raise ValueError("BrowserGym document epochs must be monotonic integers")
        if not isinstance(self.stability_status, BrowserGymStabilityStatus):
            raise TypeError("BrowserGym stability status must be typed")
        stable = self.stability_status in {
            BrowserGymStabilityStatus.STABLE_NO_NAVIGATION,
            BrowserGymStabilityStatus.STABLE_NAVIGATION,
        }
        if stable != (self.post_capture_completed is not None):
            raise ValueError("only a stable BrowserGym transition may complete post capture")
        if self.stability_status is BrowserGymStabilityStatus.STABLE_NO_NAVIGATION and (
            self.navigation_started is not None
            or self.navigation_committed is not None
            or self.after_document_epoch != self.before_document_epoch
        ):
            raise ValueError("stable no-navigation transition cannot contain navigation facts")
        if (
            self.stability_status is BrowserGymStabilityStatus.STABLE_NAVIGATION
            and self.navigation_committed is None
        ):
            raise ValueError("stable navigation requires a main-frame commit")
        if (
            self.stability_status is BrowserGymStabilityStatus.NAVIGATION_PENDING
            and self.navigation_started is None
        ):
            raise ValueError("pending navigation requires a navigation start")

    def as_evidence(self) -> dict[str, Any]:
        return freeze_json(
            {
                "dispatch_started": self.dispatch_started,
                "dispatch_returned": self.dispatch_returned,
                "navigation_started": self.navigation_started,
                "navigation_committed": self.navigation_committed,
                "post_capture_started": self.post_capture_started,
                "post_capture_completed": self.post_capture_completed,
                "before_url": self.before_url,
                "after_url": self.after_url,
                "before_document_epoch": self.before_document_epoch,
                "after_document_epoch": self.after_document_epoch,
                "stability_status": self.stability_status.value,
            }
        )


@dataclass(frozen=True)
class BrowserGymStepTransition:
    raw: dict[str, object] | None
    reward: object
    terminated: object
    truncated: object
    info: dict[str, object]
    trace: BrowserGymTransitionTrace

    def __post_init__(self) -> None:
        stable = self.trace.stability_status in {
            BrowserGymStabilityStatus.STABLE_NO_NAVIGATION,
            BrowserGymStabilityStatus.STABLE_NAVIGATION,
        }
        if stable != (self.raw is not None):
            raise ValueError("only a stable BrowserGym transition may carry a post observation")
        if not isinstance(self.info, dict):
            raise TypeError("BrowserGym transition info must be a mapping")

    @property
    def stable(self) -> bool:
        return self.raw is not None
