"""Unified world port consumed by the target AgentLoop."""

from typing import Protocol

from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    WorldObservationRequest,
)


class WorldEnvironment(Protocol):
    @property
    def observation_capabilities(self) -> ObservationCapabilities: ...

    async def reset(self, task: TaskGoal) -> ObservationAcquisition: ...

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition: ...

    def is_current(self, request: BoundActionRequest) -> bool: ...

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome: ...
