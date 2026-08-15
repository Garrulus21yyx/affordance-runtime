"""Thin coordination of source selection, acquisition, fusion, and dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from affordance_runtime.execution.contracts import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationOffer,
    ObservationRequestKind,
    ObservationSelectionPlan,
    SourceAcquisitionResult,
    SourceAcquisitionStatus,
    SourceRequirement,
    SourceSelection,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import SurfaceObservation
from affordance_runtime.world.fusion import FusionStatus, WorldFusion
from affordance_runtime.world.observation_orchestrator import ObservationOrchestrator
from affordance_runtime.world.surface_adapter import SurfaceAdapter


@dataclass
class UnifiedWorldEnvironment:
    adapters: tuple[SurfaceAdapter, ...]
    observation_orchestrator: ObservationOrchestrator = field(default_factory=ObservationOrchestrator)
    world_fusion: WorldFusion = field(default_factory=WorldFusion)
    _source_observation_ids: frozenset[str] = field(default_factory=frozenset, init=False)
    _world_observation_id: str = field(default="", init=False)
    _offers: tuple[ObservationOffer, ...] = field(default=(), init=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)
        if not self.adapters:
            raise ValueError("world environment requires at least one surface adapter")
        if len({adapter.surface for adapter in self.adapters}) != len(self.adapters):
            raise ValueError("surface adapter names must be unique")
        self._offers = tuple(
            offer
            for adapter in self.adapters
            for offer in adapter.observation_offers
        )
        if len({offer.source for offer in self._offers}) != len(self._offers):
            raise ValueError("observation offer source identities must be unique")

    @property
    def observation_capabilities(self) -> ObservationCapabilities:
        return ObservationCapabilities(True, True, self._offers)

    async def reset(self, task: TaskGoal) -> ObservationAcquisition:
        self._source_observation_ids = frozenset()
        self._world_observation_id = ""
        self._task = task
        request = WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "initial task grounding")
        selected = self._select(request)
        if isinstance(selected, ObservationAcquisition):
            return replace(selected, origin=AcquisitionOrigin.RESET)
        try:
            for adapter in self.adapters:
                prepare = getattr(adapter, "prepare", None)
                if prepare is not None:
                    prepare(task)
            reset_adapters = self._physical_reset_owners(selected)
            for adapter in reset_adapters:
                await adapter.reset(task)
        except Exception:
            return ObservationAcquisition(
                AcquisitionStatus.FAILED, AcquisitionOrigin.RESET, None, "surface_reset_failed",
                selected,
            )
        return await self._acquire(request, AcquisitionOrigin.RESET, selected)

    async def revise_task(self, task: TaskGoal) -> None:
        """Update task-relative projections without resetting the physical world."""

        for adapter in self.adapters:
            prepare = getattr(adapter, "prepare", None)
            if prepare is not None:
                prepare(task)
        self._task = task

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        return await self._acquire(request, AcquisitionOrigin.INDEPENDENT_CAPTURE)

    async def _acquire(
        self,
        request: WorldObservationRequest,
        origin: AcquisitionOrigin,
        plan: ObservationSelectionPlan | None = None,
    ) -> ObservationAcquisition:
        selected = plan or self._select(request)
        if isinstance(selected, ObservationAcquisition):
            return replace(selected, origin=origin)
        results: list[SourceAcquisitionResult] = [
            SourceAcquisitionResult(
                item.source,
                SourceRequirement.UNSELECTED,
                SourceAcquisitionStatus.NOT_ACQUIRED,
                "source_not_selected",
            )
            for item in selected.unselected
        ]
        acquired: list[SurfaceObservation] = []
        projected: dict[str, SurfaceObservation | None] = {}
        grouped: dict[str, list[SourceSelection]] = {}
        for item in selected.selections:
            offer = self._offer_for(item.source)
            grouped.setdefault(offer.acquisition_group or offer.source, []).append(item)
        for items in grouped.values():
            owner = self._adapter(items[0].source)
            acquire_group = getattr(owner, "observe_group", None)
            if len(items) > 1 and acquire_group is not None:
                try:
                    group_result = await acquire_group(
                        request.reason, tuple(item.source for item in items),
                    )
                    projected.update(dict(group_result))
                except Exception:
                    projected.update({item.source: None for item in items})
        for item in selected.selections:
            adapter = self._adapter(item.source)
            if adapter is None:
                results.append(SourceAcquisitionResult(
                    item.source, item.requirement, SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                    "selected_source_unavailable",
                ))
                continue
            try:
                if item.source in projected:
                    source = projected[item.source]
                    if source is None:
                        raise RuntimeError("shared acquisition failed")
                else:
                    source = await adapter.observe(request.reason)
            except Exception:
                results.append(SourceAcquisitionResult(
                    item.source, item.requirement, SourceAcquisitionStatus.FAILED,
                    "source_acquisition_failed",
                ))
                continue
            if source.surface != item.source:
                results.append(SourceAcquisitionResult(
                    item.source, item.requirement, SourceAcquisitionStatus.FAILED,
                    "source_identity_mismatch",
                ))
                continue
            acquired.append(source)
            results.append(SourceAcquisitionResult(
                item.source, item.requirement, SourceAcquisitionStatus.ACQUIRED,
                "source_acquired", source,
            ))
        required_failures = tuple(
            item for item in results
            if item.requirement is SourceRequirement.REQUIRED
            and item.status is not SourceAcquisitionStatus.ACQUIRED
        )
        if required_failures:
            status = (
                AcquisitionStatus.CAPABILITY_UNAVAILABLE
                if all(item.status is SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE for item in required_failures)
                else AcquisitionStatus.FAILED
            )
            return ObservationAcquisition(
                status, origin, None, "required_source_exhausted", selected, tuple(results),
            )
        fused = self.world_fusion.fuse(tuple(acquired))
        if fused.status is not FusionStatus.FUSED or fused.observation is None:
            return ObservationAcquisition(
                AcquisitionStatus.FAILED, origin, None, fused.reason_code, selected, tuple(results),
            )
        world = fused.observation
        self._source_observation_ids = frozenset(
            source.observation_id for source in world.sources
        )
        self._world_observation_id = world.observation_id
        reason = "world_acquired_with_optional_gap" if any(
            item.requirement is SourceRequirement.OPTIONAL
            and item.status is not SourceAcquisitionStatus.ACQUIRED
            for item in results
        ) else "world_acquired"
        return ObservationAcquisition(
            AcquisitionStatus.ACQUIRED, origin, world, reason, selected, tuple(results),
        )

    def _select(self, request: WorldObservationRequest) -> ObservationSelectionPlan | ObservationAcquisition:
        outcome = self.observation_orchestrator.select(self._offers, request)
        if outcome.plan is None:
            return ObservationAcquisition(
                outcome.status, AcquisitionOrigin.INDEPENDENT_CAPTURE, None, outcome.reason_code,
            )
        return outcome.plan

    def _physical_reset_owners(self, plan: ObservationSelectionPlan) -> tuple[SurfaceAdapter, ...]:
        selected: list[SurfaceAdapter] = []
        for item in plan.selections:
            adapter = self._adapter(item.source)
            if adapter is not None:
                selected.append(adapter)
        groups: dict[str, SurfaceAdapter] = {}
        for adapter in selected:
            offer = next(item for item in self._offers if item.source == adapter.surface)
            group = offer.acquisition_group or offer.source
            groups.setdefault(group, adapter)
        return tuple(groups.values())

    def is_current(self, request: BoundActionRequest) -> bool:
        return self._adapter(request.binding.surface) is not None and (
            request.world_observation_id == self._world_observation_id
            and request.binding.world_observation_id == self._world_observation_id
            and request.binding.source_observation_id in self._source_observation_ids
        )

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        adapter = self._adapter(request.binding.surface)
        if adapter is None:
            return _not_dispatched(ActionResult(
                request.request_id, DispatchStatus.NOT_SENT, request.binding.executor_id,
                False, ActionError.UNSUPPORTED_ACTION,
            ))
        if not self.is_current(request):
            return _not_dispatched(ActionResult(
                request.request_id, DispatchStatus.NOT_SENT, request.binding.executor_id,
                False, ActionError.STALE_BINDING,
            ))
        result = await adapter.execute(request)
        if result.dispatch_status is DispatchStatus.NOT_SENT:
            return _not_dispatched(result)
        post_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action",
            request.verification_needs,
        )
        post_plan = self._post_action_plan(post_request, request.binding.surface)
        if isinstance(post_plan, ObservationAcquisition):
            return ExecutionOutcome(result, post_plan)
        post = await self._acquire(
            post_request, AcquisitionOrigin.POST_ACTION, post_plan,
        )
        return ExecutionOutcome(result, post)

    def _post_action_plan(
        self,
        request: WorldObservationRequest,
        route_source: str,
    ) -> ObservationSelectionPlan | ObservationAcquisition:
        outcome = self.observation_orchestrator.select(
            self._offers,
            request,
            route_source=route_source,
        )
        if outcome.plan is not None:
            return outcome.plan
        return ObservationAcquisition(
            outcome.status,
            AcquisitionOrigin.POST_ACTION,
            None,
            outcome.reason_code,
        )

    def _offer_for(self, source: str) -> ObservationOffer:
        return next(item for item in self._offers if item.source == source)

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
