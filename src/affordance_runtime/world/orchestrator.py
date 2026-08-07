"""Thin composition of surface-local observations into one current world."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

from affordance_runtime.execution.contracts import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.base import SurfaceAdapter
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


@dataclass
class UnifiedWorldEnvironment:
    adapters: tuple[SurfaceAdapter, ...]
    _source_observation_ids: dict[str, str] = field(default_factory=dict, init=False)
    _world_observation_id: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)
        if not self.adapters:
            raise ValueError("world environment requires at least one surface adapter")
        if len({adapter.surface for adapter in self.adapters}) != len(self.adapters):
            raise ValueError("surface adapter names must be unique")

    async def reset(self, task: TaskGoal) -> None:
        for adapter in self.adapters:
            await adapter.reset(task)

    async def observe(self, reason: str) -> WorldObservation:
        sources = tuple([await adapter.observe(reason) for adapter in self.adapters])
        observation_id = (
            sources[0].observation_id
            if len(sources) == 1
            else "world:" + hashlib.sha256("\0".join(item.observation_id for item in sources).encode()).hexdigest()
        )
        bindings = tuple(
            replace(binding, world_observation_id=observation_id)
            for source in sources
            for binding in source.bindings
        )
        self._source_observation_ids = {source.surface: source.observation_id for source in sources}
        self._world_observation_id = observation_id
        return WorldObservation(
            observation_id,
            tuple(target for source in sources for target in source.targets),
            tuple(fact for source in sources for fact in source.facts),
            bindings,
            {source.surface: source.coverage for source in sources},
            sources=sources,
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        adapter = self._adapter(request.binding.surface)
        if adapter is None:
            return False
        return (
            request.world_observation_id == self._world_observation_id
            and request.binding.world_observation_id == self._world_observation_id
            and request.binding.source_observation_id
            == self._source_observation_ids.get(request.binding.surface, "")
            and adapter.is_current(request)
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        adapter = self._adapter(request.binding.surface)
        if adapter is None:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.UNSUPPORTED_ACTION,
            )
        if not self.is_current(request):
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.STALE_BINDING,
            )
        return await adapter.execute(request)

    def _adapter(self, surface: str) -> SurfaceAdapter | None:
        return next((adapter for adapter in self.adapters if adapter.surface == surface), None)
