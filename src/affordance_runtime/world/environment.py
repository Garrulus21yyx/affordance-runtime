"""Unified world port consumed by the target AgentLoop."""

from typing import Protocol

from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


class WorldEnvironment(Protocol):
    async def reset(self, task: TaskGoal) -> None: ...

    async def observe(self, reason: str) -> WorldObservation: ...

    def is_current(self, request: BoundActionRequest) -> bool: ...

    async def execute(self, request: BoundActionRequest) -> ActionResult: ...
