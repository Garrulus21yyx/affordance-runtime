"""Narrow environment boundary for short observe/execute loops.

The environment owns backend composition.  Runtime loops receive no executor
registry and therefore cannot turn backend availability into a second routing
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation


@dataclass(frozen=True)
class ObservationRequest:
    reason: str
    require_fresh: bool = True
    required_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("observation request reason cannot be blank")
        object.__setattr__(self, "required_sources", tuple(self.required_sources))


class EnvironmentPort(Protocol):
    async def reset(self, task: object) -> None: ...

    async def observe(self, request: ObservationRequest) -> Observation: ...

    async def execute(self, request: ActionContract) -> ExecutionReceipt: ...

    def is_current(self, request: ActionContract) -> bool: ...


def contract_is_current(
    contract: ActionContract,
    observation: Observation | None,
    *,
    now_s: float | None = None,
) -> bool:
    """Check only observation identity/freshness; this is not authorization."""

    if observation is None:
        return False
    current_time = time() if now_s is None else now_s
    if contract.expires_at_s and current_time > contract.expires_at_s:
        return False
    if contract.environment_revision != observation.environment_revision:
        return False
    if contract.page_revision and contract.page_revision != observation.page_revision:
        return False
    if contract.snapshot_id and contract.snapshot_id != observation.snapshot_id:
        return False
    if contract.target_fingerprint:
        key = contract.target_fingerprint_key or contract.affordance_id
        observed = observation.target_fingerprints.get(key)
        if observed != contract.target_fingerprint:
            return False
    return True
