"""Typed failure raised only when logical reset cannot start an Agent session."""

from __future__ import annotations

from affordance_runtime.world.acquisition import AcquisitionOrigin, AcquisitionStatus, ObservationAcquisition
from affordance_runtime.world.contracts import WorldObservation


class AgentSessionStartError(Exception):
    def __init__(
        self,
        status: AcquisitionStatus,
        origin: AcquisitionOrigin,
        reason_code: str,
    ) -> None:
        super().__init__(reason_code)
        self.status = status
        self.origin = origin
        self.reason_code = reason_code


def require_initial_observation(acquisition: ObservationAcquisition) -> WorldObservation:
    if (
        acquisition.status is AcquisitionStatus.ACQUIRED
        and acquisition.origin is AcquisitionOrigin.RESET
        and acquisition.observation is not None
    ):
        return acquisition.observation
    code = (
        acquisition.reason_code
        if acquisition.status is not AcquisitionStatus.ACQUIRED
        else "invalid_initial_acquisition"
    )
    raise AgentSessionStartError(acquisition.status, acquisition.origin, code)
