"""Low-risk same-backend action batches without observation barriers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    RiskLevel,
    TransportState,
)

_OBSERVATION_BARRIER_ACTIONS = frozenset({"download", "navigate", "submit"})


class BatchEnvironment(Protocol):
    async def execute(self, request: ActionContract) -> ExecutionReceipt: ...

    def is_current(self, request: ActionContract) -> bool: ...


@dataclass(frozen=True)
class ActionBatch:
    batch_id: str
    actions: tuple[ActionContract, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))
        if not self.batch_id or not 1 <= len(self.actions) <= 3:
            raise ValueError("action batch requires an id and one to three actions")
        if any(action.risk != RiskLevel.LOW for action in self.actions):
            raise ValueError("action batch accepts only low-risk actions")
        if len({action.backend for action in self.actions}) != 1:
            raise ValueError("action batch actions must use one backend")
        if len({action.environment_revision for action in self.actions}) != 1:
            raise ValueError("action batch actions must share an environment revision")
        if len({action.snapshot_id for action in self.actions}) != 1:
            raise ValueError("action batch actions must share an observation snapshot")
        if any(not action.snapshot_id for action in self.actions):
            raise ValueError("action batch actions require an observation snapshot")
        if len({action.page_revision for action in self.actions}) != 1:
            raise ValueError("action batch actions must share a page revision")
        if any(
            action.action in _OBSERVATION_BARRIER_ACTIONS
            or bool(action.parameters.get("requires_observation_barrier"))
            for action in self.actions
        ):
            raise ValueError("action batch cannot cross an observation barrier")

    @property
    def backend(self) -> str:
        return self.actions[0].backend


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    receipts: tuple[ExecutionReceipt, ...]
    success: bool
    failed_action_index: int | None = None
    requires_reobservation: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipts", tuple(self.receipts))


async def execute_action_batch(environment: BatchEnvironment, batch: ActionBatch) -> BatchResult:
    receipts: list[ExecutionReceipt] = []
    for index, action in enumerate(batch.actions):
        if not environment.is_current(action):
            return BatchResult(batch.batch_id, tuple(receipts), False, index)
        receipt = await environment.execute(action)
        receipts.append(receipt)
        if not receipt.success or receipt.transport_state != TransportState.SENT:
            return BatchResult(batch.batch_id, tuple(receipts), False, index)
    return BatchResult(batch.batch_id, tuple(receipts), True)
