"""Unified world port consumed by CoreAgentLoop."""

from typing import Protocol

from affordance_runtime.execution.contracts import BoundActionRequest, ExecutionOutcome
from affordance_runtime.goals.contracts import GoalSemanticContract
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationAcquisition,
    ObservationCapabilities,
    WorldObservationRequest,
)


class WorldEnvironment(Protocol):
    @property
    def goal_semantic_contract(self) -> GoalSemanticContract: ...

    @property
    def observation_capabilities(self) -> ObservationCapabilities: ...

    async def reset(self, task: TaskGoal) -> ObservationAcquisition: ...

    async def revise_task(self, task: TaskGoal) -> None: ...

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition: ...

    def is_current(self, request: BoundActionRequest) -> bool: ...

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome: ...
