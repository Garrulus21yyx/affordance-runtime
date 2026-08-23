"""Unified world port consumed by CoreAgentLoop."""

from typing import Protocol

from affordance_runtime.execution.contracts import (
    BoundActionRequest,
    ExecutionObservationRecovery,
    ExecutionOutcome,
    SessionHealth,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationAcquisition,
    ObservationCapabilities,
    WorldObservationRequest,
)
from affordance_runtime.world.finalization import EnvironmentFinalization, FinalResponseCodec


class WorldEnvironment(Protocol):
    @property
    def final_response_codec(self) -> FinalResponseCodec: ...

    @property
    def observation_capabilities(self) -> ObservationCapabilities: ...

    async def reset(self, task: TaskGoal) -> ObservationAcquisition: ...

    async def revise_task(self, task: TaskGoal) -> None: ...

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition: ...

    def is_current(self, request: BoundActionRequest) -> bool: ...

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome: ...

    async def session_health(self, request: BoundActionRequest) -> SessionHealth: ...

    async def recover_execution_observation(
        self,
        action_request: BoundActionRequest,
        observation_request: WorldObservationRequest,
    ) -> ExecutionObservationRecovery: ...

    @property
    def supports_finalization(self) -> bool: ...

    async def finalize(self, content: str) -> EnvironmentFinalization: ...
