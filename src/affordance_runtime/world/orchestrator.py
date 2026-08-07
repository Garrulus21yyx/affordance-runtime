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
            replace(binding, observation_id=observation_id)
            for source in sources
            for binding in source.bindings
        )
        self._source_observation_ids = {source.surface: source.observation_id for source in sources}
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
        if len(self.adapters) == 1:
            return adapter.is_current(request)
        source_id = self._source_observation_ids.get(request.binding.surface, "")
        source_request = _for_source(request, source_id) if source_id else None
        return source_request is not None and adapter.is_current(source_request)

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
        if len(self.adapters) == 1:
            return await adapter.execute(request)
        source_id = self._source_observation_ids.get(request.binding.surface, "")
        source_request = _for_source(request, source_id) if source_id else None
        if source_request is None:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.STALE_BINDING,
            )
        return await adapter.execute(source_request)

    def _adapter(self, surface: str) -> SurfaceAdapter | None:
        return next((adapter for adapter in self.adapters if adapter.surface == surface), None)


def _for_source(request: BoundActionRequest, observation_id: str) -> BoundActionRequest:
    return replace(
        request,
        observation_id=observation_id,
        binding=replace(request.binding, observation_id=observation_id),
    )
