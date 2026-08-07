"""Edge-only fixture for the isolated pre-target ActionBatch helper."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.environment_port import ObservationRequest, contract_is_current
from affordance_runtime.testing.static_environment import StaleEnvironmentBinding

ExecuteFn = Callable[[ActionContract, Observation], ExecutionReceipt]


@dataclass
class LegacyStaticEnvironment:
    observations: Sequence[Observation]
    receipts: Sequence[ExecutionReceipt] = ()
    execute_fn: ExecuteFn | None = None
    repeat_last_observation: bool = True
    task: object | None = field(default=None, init=False)
    observation_requests: list[ObservationRequest] = field(default_factory=list, init=False)
    executed_contracts: list[ActionContract] = field(default_factory=list, init=False)
    _observation_index: int = field(default=0, init=False)
    _receipt_index: int = field(default=0, init=False)
    _current_observation: Observation | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.observations = tuple(self.observations)
        self.receipts = tuple(self.receipts)
        if not self.observations:
            raise ValueError("static environment requires at least one observation")
        if self.execute_fn is not None and self.receipts:
            raise ValueError("static environment accepts either receipts or execute_fn, not both")

    async def reset(self, task: object) -> None:
        self.task = task
        self.observation_requests.clear()
        self.executed_contracts.clear()
        self._observation_index = 0
        self._receipt_index = 0
        self._current_observation = None

    async def observe(self, request: ObservationRequest) -> Observation:
        if self.task is None:
            raise RuntimeError("static environment must be reset before observation")
        self.observation_requests.append(request)
        if self._observation_index < len(self.observations):
            observation = self.observations[self._observation_index]
            self._observation_index += 1
        elif self.repeat_last_observation:
            observation = self.observations[-1]
        else:
            raise IndexError("static observation sequence exhausted")
        self._current_observation = observation
        return observation

    async def execute(self, request: ActionContract) -> ExecutionReceipt:
        if not self.is_current(request):
            raise StaleEnvironmentBinding("action contract is not current for the last observation")
        assert self._current_observation is not None
        self.executed_contracts.append(request)
        if self.execute_fn is not None:
            return self.execute_fn(request, self._current_observation)
        if self._receipt_index >= len(self.receipts):
            raise IndexError("static execution receipt sequence exhausted")
        receipt = self.receipts[self._receipt_index]
        self._receipt_index += 1
        if receipt.contract_id != request.id:
            raise ValueError("static receipt contract_id does not match the executed contract")
        return receipt

    def is_current(self, request: ActionContract) -> bool:
        return contract_is_current(request, self._current_observation)
