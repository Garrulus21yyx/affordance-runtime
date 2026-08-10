"""Thin composition of surface-local observations into one current world."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

from affordance_runtime.execution.contracts import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.base import SurfaceAdapter
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationOffer,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation


@dataclass
class UnifiedWorldEnvironment:
    adapters: tuple[SurfaceAdapter, ...]
    _source_observation_ids: dict[str, str] = field(default_factory=dict, init=False)
    _world_observation_id: str = field(default="", init=False)
    _offers: tuple[ObservationOffer, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)
        if not self.adapters:
            raise ValueError("world environment requires at least one surface adapter")
        if len({adapter.surface for adapter in self.adapters}) != len(self.adapters):
            raise ValueError("surface adapter names must be unique")

    @property
    def observation_capabilities(self) -> ObservationCapabilities:
        return ObservationCapabilities(True, True, self._offers)

    async def reset(self, task: TaskGoal) -> ObservationAcquisition:
        self._source_observation_ids.clear()
        self._world_observation_id = ""
        self._offers = ()
        try:
            for adapter in self.adapters:
                await adapter.reset(task)
        except Exception:
            return ObservationAcquisition(
                AcquisitionStatus.FAILED, AcquisitionOrigin.RESET, None, "surface_reset_failed",
            )
        return await self._acquire("initial task grounding", AcquisitionOrigin.RESET)

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        return await self._acquire(request.reason, AcquisitionOrigin.INDEPENDENT_CAPTURE)

    async def _acquire(
        self,
        reason: str,
        origin: AcquisitionOrigin,
    ) -> ObservationAcquisition:
        try:
            sources = tuple([await adapter.observe(reason) for adapter in self.adapters])
        except Exception:
            return ObservationAcquisition(
                AcquisitionStatus.FAILED, origin, None, "surface_acquisition_failed",
            )
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
        world = WorldObservation(
            observation_id,
            tuple(target for source in sources for target in source.targets),
            tuple(fact for source in sources for fact in source.facts),
            bindings,
            {source.surface: source.coverage for source in sources},
            sources=sources,
        )
        self._source_observation_ids = {source.surface: source.observation_id for source in sources}
        self._world_observation_id = observation_id
        self._offers = _offers(sources)
        return ObservationAcquisition(AcquisitionStatus.ACQUIRED, origin, world, "world_acquired")

    def is_current(self, request: BoundActionRequest) -> bool:
        return self._adapter(request.binding.surface) is not None and (
            request.world_observation_id == self._world_observation_id
            and request.binding.world_observation_id == self._world_observation_id
            and request.binding.source_observation_id
            == self._source_observation_ids.get(request.binding.surface, "")
        )

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        adapter = self._adapter(request.binding.surface)
        if adapter is None:
            result = ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.UNSUPPORTED_ACTION,
            )
            return _not_dispatched(result)
        if not self.is_current(request):
            result = ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.STALE_BINDING,
            )
            return _not_dispatched(result)
        result = await adapter.execute(request)
        if result.dispatch_status is DispatchStatus.NOT_SENT:
            return _not_dispatched(result)
        post = await self._acquire("post action", AcquisitionOrigin.POST_ACTION)
        return ExecutionOutcome(result, post)

    def _adapter(self, surface: str) -> SurfaceAdapter | None:
        return next((adapter for adapter in self.adapters if adapter.surface == surface), None)


def _not_dispatched(result: ActionResult) -> ExecutionOutcome:
    return ExecutionOutcome(
        result,
        ObservationAcquisition(
            AcquisitionStatus.CAPABILITY_UNAVAILABLE,
            AcquisitionOrigin.POST_ACTION,
            None,
            "action_not_dispatched",
        ),
    )


def _offers(sources) -> tuple[ObservationOffer, ...]:
    values = {
        ObservationOffer(
            source.surface,
            str(source.source_profile.modality),
            str(source.source_profile.assurance),
            str(source.source_profile.acquisition_cost),
        )
        for source in sources
    }
    return tuple(sorted(values))
