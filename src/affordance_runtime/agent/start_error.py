"""Typed failure raised only when logical reset cannot start an Agent session."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.accounting import RunAccountingSnapshot
from affordance_runtime.agent.attempt_receipt import AttemptReceipt
from affordance_runtime.world.acquisition import AcquisitionOrigin, AcquisitionStatus, ObservationAcquisition
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class StartBoundaryEvidence:
    receipt: AttemptReceipt
    accounting: RunAccountingSnapshot


class AgentSessionStartError(Exception):
    def __init__(
        self,
        status: AcquisitionStatus,
        origin: AcquisitionOrigin,
        reason_code: str,
        start_evidence: StartBoundaryEvidence,
    ) -> None:
        super().__init__(reason_code)
        self.status = status
        self.origin = origin
        self.reason_code = reason_code
        self.start_evidence = start_evidence


def require_initial_observation(
    acquisition: ObservationAcquisition,
    evidence: StartBoundaryEvidence,
) -> WorldObservation:
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
    raise AgentSessionStartError(acquisition.status, acquisition.origin, code, evidence)


def attach_start_boundary_evidence(
    error: BaseException,
    evidence: StartBoundaryEvidence,
) -> None:
    """Attach typed truth while preserving the public exception/cancellation type."""

    setattr(error, "start_boundary_evidence", evidence)
