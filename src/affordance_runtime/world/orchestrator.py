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
    SelectedObservationRequest,
    SelectedObservationResult,
    SourceAcquisitionResult,
    SourceAcquisitionStatus,
    SourceRequirement,
    WorldObservationRequest,
    selected_observation_requests,
)
from affordance_runtime.world.fusion import FusionStatus, WorldFusion
from affordance_runtime.world.observation_orchestrator import ObservationOrchestrator
from affordance_runtime.world.source_profile import ObservationModality
from affordance_runtime.world.surface_adapter import GroupedObservationAdapter, SurfaceAdapter


@dataclass
class UnifiedWorldEnvironment:
    adapters: tuple[SurfaceAdapter, ...]
    observation_orchestrator: ObservationOrchestrator = field(default_factory=ObservationOrchestrator)
    world_fusion: WorldFusion = field(default_factory=WorldFusion)
    _source_observation_ids: frozenset[str] = field(default_factory=frozenset, init=False)
    _world_observation_id: str = field(default="", init=False)
    _acquisition_sequence: int = field(default=0, init=False)
    _offers: tuple[ObservationOffer, ...] = field(default=(), init=False)
    _source_owners: dict[str, SurfaceAdapter] = field(default_factory=dict, init=False, repr=False)
    _surface_owners: dict[str, SurfaceAdapter] = field(default_factory=dict, init=False, repr=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)
        if not self.adapters:
            raise ValueError("world environment requires at least one surface adapter")
        if len({adapter.surface for adapter in self.adapters}) != len(self.adapters):
            raise ValueError("surface adapter names must be unique")
        registrations = tuple(
            (offer, adapter)
            for adapter in self.adapters
            for offer in adapter.observation_offers
        )
        self._offers = tuple(offer for offer, _ in registrations)
        if len({offer.source for offer in self._offers}) != len(self._offers):
            raise ValueError("observation offer source identities must be unique")
        self._source_owners = {offer.source: adapter for offer, adapter in registrations}
        self._surface_owners = {adapter.surface: adapter for adapter in self.adapters}

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
        self._acquisition_sequence += 1
        acquisition_id = f"acquisition:{self._acquisition_sequence}"
        all_initial_requests = selected_observation_requests(
            selected, request, self._offers, acquisition_id
        )
        structural_requests = tuple(
            item
            for item in all_initial_requests
            if ObservationModality(item.offer.modality) is ObservationModality.STRUCTURAL
        )
        stage_requests = (
            structural_requests
            if structural_requests and len(all_initial_requests) > 1
            else all_initial_requests
        )
        provider_results = list(await self._acquire_selected(stage_requests))
        acquired = [
            item.observation
            for item in provider_results
            if item.status is SourceAcquisitionStatus.ACQUIRED and item.observation is not None
        ]
        baseline = next(
            (
                item
                for item in acquired
                if item.source_profile.modality.value == "structural"
            ),
            None,
        )
        if baseline is None and len(stage_requests) < len(all_initial_requests):
            deferred = tuple(
                item for item in all_initial_requests if item not in stage_requests
            )
            provider_results.extend(
                SelectedObservationResult.failed(
                    item,
                    SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                    "baseline_dependency_unavailable",
                )
                for item in deferred
            )
            stage_requests = all_initial_requests
        should_refine = bool(
            baseline is not None
            and len(stage_requests) < selected.acquisition_budget
            and (
                len(stage_requests) < len(all_initial_requests)
                or selected.unselected
            )
        )
        if should_refine:
            assert baseline is not None
            route_source = next(
                (
                    item.source
                    for item in selected.selections
                    if item.reason_code == "route_source_refresh"
                ),
                "",
            )
            refined = self.observation_orchestrator.select_after_baseline(
                self._offers,
                request,
                baseline,
                terminal=False,
                route_source=route_source,
            )
            if refined.plan is None:
                deferred = tuple(
                    item for item in all_initial_requests if item not in stage_requests
                )
                provider_results.extend(
                    SelectedObservationResult.failed(
                        item,
                        SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                        refined.reason_code,
                    )
                    for item in deferred
                )
                return ObservationAcquisition(
                    refined.status,
                    origin,
                    None,
                    refined.reason_code,
                    selected,
                    self._source_results(
                        selected, all_initial_requests, tuple(provider_results)
                    ),
                )
            selected = refined.plan
            final_requests = selected_observation_requests(
                selected, request, self._offers, acquisition_id
            )
            acquired_sources = {item.source for item in stage_requests}
            residual_requests = tuple(
                item for item in final_requests if item.source not in acquired_sources
            )
            if residual_requests:
                provider_results.extend(await self._acquire_selected(residual_requests))
                acquired.extend(
                    item.observation
                    for item in provider_results[len(stage_requests) :]
                    if item.status is SourceAcquisitionStatus.ACQUIRED
                    and item.observation is not None
                )
            stage_requests = final_requests
        results = self._source_results(selected, stage_requests, tuple(provider_results))
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

    async def _acquire_selected(
        self,
        requests: tuple[SelectedObservationRequest, ...],
    ) -> tuple[SelectedObservationResult, ...]:
        results: dict[str, SelectedObservationResult] = {}
        grouped: dict[str, list[SelectedObservationRequest]] = {}
        for request in requests:
            grouped.setdefault(request.acquisition_group or request.source, []).append(request)
        for group_requests in grouped.values():
            owners = tuple(self._source_owner(item.source) for item in group_requests)
            owner = owners[0]
            if (
                all(item is owner for item in owners)
                and isinstance(owner, GroupedObservationAdapter)
            ):
                try:
                    grouped_results = await owner.acquire_group(tuple(group_requests))
                    by_source = {item.source: item for item in grouped_results}
                    if len(by_source) != len(grouped_results):
                        raise ValueError("group acquisition repeated a source result")
                    for selected_request in group_requests:
                        results[selected_request.source] = by_source[selected_request.source]
                except Exception:
                    for selected_request in group_requests:
                        results[selected_request.source] = SelectedObservationResult.failed(
                            selected_request,
                            SourceAcquisitionStatus.FAILED,
                            "source_acquisition_failed",
                        )
                continue
            for selected_request, selected_owner in zip(
                group_requests, owners, strict=True,
            ):
                try:
                    results[selected_request.source] = await selected_owner.acquire(
                        selected_request
                    )
                except Exception:
                    results[selected_request.source] = SelectedObservationResult.failed(
                        selected_request,
                        SourceAcquisitionStatus.FAILED,
                        "source_acquisition_failed",
                    )
        return tuple(results[item.source] for item in requests)

    def _source_results(
        self,
        plan: ObservationSelectionPlan,
        requests: tuple[SelectedObservationRequest, ...],
        provider_results: tuple[SelectedObservationResult, ...],
    ) -> tuple[SourceAcquisitionResult, ...]:
        request_by_source = {item.source: item for item in requests}
        provider_by_source = {item.source: item for item in provider_results}
        selected_results: list[SourceAcquisitionResult] = []
        for selection in plan.selections:
            selected_request = request_by_source[selection.source]
            result = provider_by_source[selection.source]
            expected_need_ids = {item.need_id for item in selected_request.needs}
            actual_need_ids = set(result.fulfilled_need_ids) | set(result.unfulfilled_need_ids)
            identity_matches = (
                result.source == selection.source
                and actual_need_ids == expected_need_ids
            )
            if not identity_matches:
                result = SelectedObservationResult.failed(
                    selected_request,
                    SourceAcquisitionStatus.FAILED,
                    "source_result_contract_mismatch",
                )
            selected_results.append(SourceAcquisitionResult(
                selection.source,
                selection.requirement,
                result.status,
                result.reason_code,
                result.observation,
                result.fulfilled_need_ids,
                result.unfulfilled_need_ids,
            ))
        unselected_results = tuple(
            SourceAcquisitionResult(
                item.source,
                SourceRequirement.UNSELECTED,
                SourceAcquisitionStatus.NOT_ACQUIRED,
                "source_not_selected",
            )
            for item in plan.unselected
        )
        return (*unselected_results, *selected_results)

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
            selected.append(self._source_owner(item.source))
        groups: dict[str, SurfaceAdapter] = {}
        for selection, adapter in zip(plan.selections, selected, strict=True):
            offer = self._offer_for(selection.source)
            group = offer.acquisition_group or offer.source
            groups.setdefault(group, adapter)
        return tuple(groups.values())

    def is_current(self, request: BoundActionRequest) -> bool:
        return self._surface_adapter(request.binding.surface) is not None and (
            request.world_observation_id == self._world_observation_id
            and request.binding.world_observation_id == self._world_observation_id
            and request.binding.source_observation_id in self._source_observation_ids
        )

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        adapter = self._surface_adapter(request.binding.surface)
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
        post_plan = self._post_action_plan(
            post_request,
            self._route_source_for_surface(request.binding.surface),
        )
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

    def _source_owner(self, source: str) -> SurfaceAdapter:
        return self._source_owners[source]

    def _route_source_for_surface(self, surface: str) -> str:
        adapter = self._surface_owners[surface]
        owned = tuple(
            offer for offer in self._offers if self._source_owners[offer.source] is adapter
        )
        if not owned:
            raise ValueError("executing surface has no observation source")
        return min(owned, key=lambda item: (item.acquisition_cost, item.source)).source

    def _surface_adapter(self, surface: str) -> SurfaceAdapter | None:
        return self._surface_owners.get(surface)


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
