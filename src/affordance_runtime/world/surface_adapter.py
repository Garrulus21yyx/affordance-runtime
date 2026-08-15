"""Consumer-owned port implemented by concrete surface adapters."""

from typing import Protocol, runtime_checkable

from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationOffer,
    SelectedObservationRequest,
    SelectedObservationResult,
)


class SurfaceAdapter(Protocol):
    surface: str

    @property
    def physical_environment_id(self) -> str: ...

    @property
    def owns_physical_reset(self) -> bool: ...

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]: ...

    def initialize_task(self, task: TaskGoal) -> None: ...

    async def reset_physical(self) -> None: ...

    async def acquire(self, request: SelectedObservationRequest) -> SelectedObservationResult: ...

    def is_current(self, request: BoundActionRequest) -> bool: ...

    async def execute(self, request: BoundActionRequest) -> ActionResult: ...


@runtime_checkable
class GroupedObservationAdapter(Protocol):
    """Provider port for semantic activations sharing one physical acquisition ID."""

    async def acquire_group(
        self,
        requests: tuple[SelectedObservationRequest, ...],
    ) -> tuple[SelectedObservationResult, ...]: ...
