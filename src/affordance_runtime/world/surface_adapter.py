"""Consumer-owned port implemented by concrete surface adapters."""

from typing import Protocol

from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import ObservationOffer
from affordance_runtime.world.contracts import SurfaceObservation


class SurfaceAdapter(Protocol):
    surface: str

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]: ...

    async def reset(self, task: TaskGoal) -> None: ...

    async def observe(self, reason: str) -> SurfaceObservation: ...

    def is_current(self, request: BoundActionRequest) -> bool: ...

    async def execute(self, request: BoundActionRequest) -> ActionResult: ...
