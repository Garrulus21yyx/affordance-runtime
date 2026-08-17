"""Thin coordination of source selection, acquisition, fusion, and dispatch."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from affordance_runtime.execution.contracts import (
    ActionDispatchCancelled,
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
    ExecutionCancelled,
    ExecutionOutcome,
)
from affordance_runtime.goals.contracts import GoalSemanticContract, merge_goal_semantic_contracts
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionCancelled,
    AcquisitionOrigin,
    AcquisitionReason,
    AcquisitionReasonKind,
    AcquisitionStage,
    AcquisitionStatus,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationNeedSatisfactionStatus,
    ObservationOffer,
    ObservationRequestKind,
    ObservationSelectionPlan,
    ProviderActivation,
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
class ObservationAcquisitionCoordinator:
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
    _source_by_observation_id: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    last_acquisition: ObservationAcquisition | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)
        if not self.adapters:
            raise ValueError("world environment requires at least one surface adapter")
        if len({adapter.surface for adapter in self.adapters}) != len(self.adapters):
            raise ValueError("surface adapter names must be unique")
        registrations = tuple((offer, adapter) for adapter in self.adapters for offer in adapter.observation_offers)
        self._offers = tuple(offer for offer, _ in registrations)
        if len({offer.source for offer in self._offers}) != len(self._offers):
            raise ValueError("observation offer source identities must be unique")
        self._source_owners = {offer.source: adapter for offer, adapter in registrations}
        self._surface_owners = {}
        for adapter in self.adapters:
            execution_surfaces = tuple(getattr(adapter, "execution_surfaces", (adapter.surface,)))
            for surface in execution_surfaces:
                previous = self._surface_owners.setdefault(surface, adapter)
                if previous is not adapter:
                    raise ValueError("execution surface must have exactly one adapter owner")

    @property
    def observation_capabilities(self) -> ObservationCapabilities:
        independent = any(bool(getattr(adapter, "supports_independent_capture", True)) for adapter in self.adapters)
        return ObservationCapabilities(independent, True, self._offers)

    async def reset(self, task: TaskGoal) -> ObservationAcquisition:
        self._source_observation_ids = frozenset()
        self._world_observation_id = ""
        self._task = task
        request = WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "initial task grounding")
        acquisition_id = self._next_acquisition_id()
        selected = self.observation_orchestrator.select(self._offers, request)
        if selected.plan is None:
            return self._remember(
                self._pre_selection(
                    acquisition_id,
                    AcquisitionOrigin.RESET,
                    request,
                    selected.reason_code,
                )
            )
        try:
            for adapter in self.adapters:
                adapter.initialize_task(task)
            reset_adapters = self._physical_reset_owners()
            for adapter in reset_adapters:
                await adapter.reset_physical()
        except asyncio.CancelledError as exc:
            cancelled = self._cancelled(
                acquisition_id,
                AcquisitionOrigin.RESET,
                request,
                selected.plan,
                (),
                "initialization_cancelled",
            )
            self._remember(cancelled)
            raise AcquisitionCancelled(cancelled) from exc
        except Exception:
            return self._remember(
                self._initialization_failed(
                    acquisition_id,
                    AcquisitionOrigin.RESET,
                    request,
                    selected.plan,
                    "surface_reset_failed",
                )
            )
        return await self._acquire(
            request,
            AcquisitionOrigin.RESET,
            selected.plan,
            acquisition_id=acquisition_id,
        )

    async def revise_task(self, task: TaskGoal) -> None:
        """Update task-relative projections without resetting the physical world."""

        for adapter in self.adapters:
            adapter.initialize_task(task)
        self._task = task

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        if not self.observation_capabilities.independent_capture:
            return self._remember(
                self._pre_selection(
                    self._next_acquisition_id(),
                    AcquisitionOrigin.INDEPENDENT_CAPTURE,
                    request,
                    "independent_capture_unsupported",
                )
            )
        return await self._acquire(request, AcquisitionOrigin.INDEPENDENT_CAPTURE)

    async def _acquire(
        self,
        request: WorldObservationRequest,
        origin: AcquisitionOrigin,
        plan: ObservationSelectionPlan | None = None,
        *,
        acquisition_id: str | None = None,
    ) -> ObservationAcquisition:
        acquisition_id = acquisition_id or self._next_acquisition_id()
        if plan is None:
            selection = self.observation_orchestrator.select(self._offers, request)
            if selection.plan is None:
                return self._remember(
                    self._pre_selection(
                        acquisition_id,
                        origin,
                        request,
                        selection.reason_code,
                    )
                )
            selected = selection.plan
        else:
            selected = plan
        all_initial_requests = selected_observation_requests(selected, request, self._offers, acquisition_id)
        structural_requests = tuple(
            item
            for item in all_initial_requests
            if ObservationModality(item.offer.modality) is ObservationModality.STRUCTURAL
        )
        stage_requests = (
            structural_requests if structural_requests and len(all_initial_requests) > 1 else all_initial_requests
        )
        try:
            provider_results = list(await self._acquire_selected(stage_requests))
        except _ProviderCancellation as exc:
            cancelled_results = {item.source: item for item in exc.results}
            for pending in all_initial_requests:
                if pending.source not in cancelled_results:
                    cancelled_results[pending.source] = SelectedObservationResult.failed(
                        pending,
                        SourceAcquisitionStatus.CANCELLED,
                        "source_acquisition_cancelled",
                    )
            cancelled = self._cancelled(
                acquisition_id,
                origin,
                request,
                selected,
                self._activations(
                    all_initial_requests,
                    tuple(cancelled_results[item.source] for item in all_initial_requests),
                ),
                "source_acquisition_cancelled",
            )
            self._remember(cancelled)
            raise AcquisitionCancelled(cancelled) from exc
        acquired = [
            item.observation
            for item in provider_results
            if item.status is SourceAcquisitionStatus.ACQUIRED and item.observation is not None
        ]
        baseline = next(
            (item for item in acquired if item.source_profile.modality.value == "structural"),
            None,
        )
        if baseline is None and len(stage_requests) < len(all_initial_requests):
            deferred = tuple(item for item in all_initial_requests if item not in stage_requests)
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
            and (len(stage_requests) < len(all_initial_requests) or selected.unselected)
        )
        if should_refine:
            assert baseline is not None
            route_source = next(
                (item.source for item in selected.selections if item.reason_code == "route_source_refresh"),
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
                deferred = tuple(item for item in all_initial_requests if item not in stage_requests)
                provider_results.extend(
                    SelectedObservationResult.failed(
                        item,
                        SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                        refined.reason_code,
                    )
                    for item in deferred
                )
                activations = self._activations(all_initial_requests, tuple(provider_results))
                return self._remember(
                    self._source_failed(
                        acquisition_id,
                        origin,
                        request,
                        selected,
                        activations,
                        refined.status,
                        refined.reason_code,
                    )
                )
            selected = refined.plan
            final_requests = selected_observation_requests(selected, request, self._offers, acquisition_id)
            acquired_sources = {item.source for item in stage_requests}
            residual_requests = tuple(item for item in final_requests if item.source not in acquired_sources)
            if residual_requests:
                try:
                    provider_results.extend(await self._acquire_selected(residual_requests))
                except _ProviderCancellation as exc:
                    provider_results.extend(exc.results)
                    cancelled = self._cancelled(
                        acquisition_id,
                        origin,
                        request,
                        selected,
                        self._activations(final_requests, tuple(provider_results)),
                        "source_acquisition_cancelled",
                    )
                    self._remember(cancelled)
                    raise AcquisitionCancelled(cancelled) from exc
                acquired.extend(
                    item.observation
                    for item in provider_results[len(stage_requests) :]
                    if item.status is SourceAcquisitionStatus.ACQUIRED and item.observation is not None
                )
            stage_requests = final_requests
        activations = self._activations(stage_requests, tuple(provider_results))
        results = self._source_results(selected, stage_requests, tuple(provider_results))
        required_failures = tuple(
            item
            for item in results
            if item.requirement is SourceRequirement.REQUIRED and item.status is not SourceAcquisitionStatus.ACQUIRED
        )
        if required_failures:
            status = (
                AcquisitionStatus.CAPABILITY_UNAVAILABLE
                if all(item.status is SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE for item in required_failures)
                else AcquisitionStatus.FAILED
            )
            return self._remember(
                self._source_failed(
                    acquisition_id,
                    origin,
                    request,
                    selected,
                    activations,
                    status,
                    "required_source_exhausted",
                )
            )
        try:
            fused = self.world_fusion.fuse(tuple(acquired))
        except asyncio.CancelledError as exc:
            cancelled = self._cancelled(
                acquisition_id,
                origin,
                request,
                selected,
                activations,
                "fusion_cancelled",
            )
            self._remember(cancelled)
            raise AcquisitionCancelled(cancelled) from exc
        except Exception:
            from affordance_runtime.world.fusion import WorldFusionResult

            fused = WorldFusionResult(FusionStatus.INCONCLUSIVE, None, "fusion_call_failed")
        if fused.status is not FusionStatus.FUSED or fused.observation is None:
            return self._remember(
                self._fusion_failed(
                    acquisition_id,
                    origin,
                    request,
                    selected,
                    activations,
                    fused,
                )
            )
        world = fused.observation
        self._source_observation_ids = frozenset(source.observation_id for source in world.sources)
        self._world_observation_id = world.observation_id
        self._source_by_observation_id = {
            activation.result.observation.observation_id: activation.request.source
            for activation in activations
            if activation.result.observation is not None
        }
        if any(item.unfulfilled_need_ids for item in results):
            reason = "world_acquired_with_unresolved_need"
        elif any(
            item.requirement is SourceRequirement.OPTIONAL and item.status is not SourceAcquisitionStatus.ACQUIRED
            for item in results
        ):
            reason = "world_acquired_with_optional_gap"
        else:
            reason = "world_acquired"
        stage = (
            AcquisitionStage.ACQUIRED_WITH_UNRESOLVED_NEEDS
            if any(item.unfulfilled_need_ids for item in results)
            or any(
                item.requirement is SourceRequirement.OPTIONAL and item.status is not SourceAcquisitionStatus.ACQUIRED
                for item in results
            )
            else AcquisitionStage.ACQUIRED_ALL_NEEDS_FULFILLED
        )
        reason_kind = (
            AcquisitionReasonKind.UNRESOLVED_NEEDS
            if stage is AcquisitionStage.ACQUIRED_WITH_UNRESOLVED_NEEDS
            else AcquisitionReasonKind.ALL_NEEDS_FULFILLED
        )
        return self._remember(
            ObservationAcquisition(
                acquisition_id,
                origin,
                request,
                stage,
                selected,
                activations,
                fused,
                AcquisitionStatus.ACQUIRED,
                AcquisitionReason(
                    reason_kind,
                    reason,
                    stage,
                    need_ids=tuple(
                        need.need_id
                        for activation in activations
                        for need in activation.result.need_results
                        if need.status is not ObservationNeedSatisfactionStatus.FULFILLED
                    ),
                ),
            )
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
            if all(item is owner for item in owners) and isinstance(owner, GroupedObservationAdapter):
                try:
                    grouped_results = await owner.acquire_group(tuple(group_requests))
                    by_source = {item.source: item for item in grouped_results}
                    if len(by_source) != len(grouped_results):
                        raise ValueError("group acquisition repeated a source result")
                    for selected_request in group_requests:
                        results[selected_request.source] = self._conserve_provider_result(
                            selected_request,
                            by_source[selected_request.source],
                        )
                except asyncio.CancelledError as exc:
                    for selected_request in group_requests:
                        results.setdefault(
                            selected_request.source,
                            SelectedObservationResult.failed(
                                selected_request,
                                SourceAcquisitionStatus.CANCELLED,
                                "source_acquisition_cancelled",
                            ),
                        )
                    for pending in requests:
                        if pending.source not in results:
                            results[pending.source] = SelectedObservationResult.failed(
                                pending,
                                SourceAcquisitionStatus.CANCELLED,
                                "source_acquisition_cancelled",
                            )
                    raise _ProviderCancellation(tuple(results[item.source] for item in requests)) from exc
                except Exception:
                    for selected_request in group_requests:
                        results[selected_request.source] = SelectedObservationResult.failed(
                            selected_request,
                            SourceAcquisitionStatus.FAILED,
                            "source_acquisition_failed",
                        )
                continue
            for selected_request, selected_owner in zip(
                group_requests,
                owners,
                strict=True,
            ):
                try:
                    results[selected_request.source] = self._conserve_provider_result(
                        selected_request,
                        await selected_owner.acquire(selected_request),
                    )
                except asyncio.CancelledError as exc:
                    results[selected_request.source] = SelectedObservationResult.failed(
                        selected_request,
                        SourceAcquisitionStatus.CANCELLED,
                        "source_acquisition_cancelled",
                    )
                    for pending in requests:
                        if pending.source not in results:
                            results[pending.source] = SelectedObservationResult.failed(
                                pending,
                                SourceAcquisitionStatus.CANCELLED,
                                "source_acquisition_cancelled",
                            )
                    raise _ProviderCancellation(tuple(results[item.source] for item in requests)) from exc
                except Exception:
                    results[selected_request.source] = SelectedObservationResult.failed(
                        selected_request,
                        SourceAcquisitionStatus.FAILED,
                        "source_acquisition_failed",
                    )
        return tuple(results[item.source] for item in requests)

    @staticmethod
    def _conserve_provider_result(
        request: SelectedObservationRequest,
        result: SelectedObservationResult,
    ) -> SelectedObservationResult:
        if not isinstance(result, SelectedObservationResult):
            return SelectedObservationResult.failed(
                request,
                SourceAcquisitionStatus.FAILED,
                "source_result_contract_mismatch",
            )
        expected = {item.need_id for item in request.needs}
        actual = {item.need_id for item in result.need_results}
        if result.source != request.source or actual != expected:
            return SelectedObservationResult.failed(
                request,
                SourceAcquisitionStatus.FAILED,
                "source_result_contract_mismatch",
            )
        return result

    @staticmethod
    def _activations(
        requests: tuple[SelectedObservationRequest, ...],
        provider_results: tuple[SelectedObservationResult, ...],
    ) -> tuple[ProviderActivation, ...]:
        by_source = {item.source: item for item in provider_results}
        return tuple(
            ProviderActivation(request, by_source[request.source])
            for request in requests
            if request.source in by_source
        )

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
            identity_matches = result.source == selection.source and actual_need_ids == expected_need_ids
            if not identity_matches:
                result = SelectedObservationResult.failed(
                    selected_request,
                    SourceAcquisitionStatus.FAILED,
                    "source_result_contract_mismatch",
                )
            selected_results.append(
                SourceAcquisitionResult(
                    selection.source,
                    selection.requirement,
                    result.status,
                    result.reason_code,
                    result.observation,
                    result.need_results,
                )
            )
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

    def _next_acquisition_id(self) -> str:
        self._acquisition_sequence += 1
        return f"acquisition:{self._acquisition_sequence}"

    def _remember(self, acquisition: ObservationAcquisition) -> ObservationAcquisition:
        self.last_acquisition = acquisition
        return acquisition

    @staticmethod
    def _pre_selection(
        acquisition_id: str,
        origin: AcquisitionOrigin,
        request: WorldObservationRequest,
        reason_code: str,
    ) -> ObservationAcquisition:
        stage = AcquisitionStage.PRE_SELECTION_UNAVAILABLE
        return ObservationAcquisition(
            acquisition_id,
            origin,
            request,
            stage,
            None,
            (),
            None,
            AcquisitionStatus.CAPABILITY_UNAVAILABLE,
            AcquisitionReason(AcquisitionReasonKind.UNAVAILABLE, reason_code, stage),
        )

    @staticmethod
    def _initialization_failed(
        acquisition_id: str,
        origin: AcquisitionOrigin,
        request: WorldObservationRequest,
        plan: ObservationSelectionPlan,
        reason_code: str,
    ) -> ObservationAcquisition:
        stage = AcquisitionStage.INITIALIZATION_FAILED
        return ObservationAcquisition(
            acquisition_id,
            origin,
            request,
            stage,
            plan,
            (),
            None,
            AcquisitionStatus.FAILED,
            AcquisitionReason(
                AcquisitionReasonKind.INITIALIZATION_FAILURE,
                reason_code,
                stage,
            ),
        )

    @staticmethod
    def _source_failed(
        acquisition_id: str,
        origin: AcquisitionOrigin,
        request: WorldObservationRequest,
        plan: ObservationSelectionPlan,
        activations: tuple[ProviderActivation, ...],
        status: AcquisitionStatus,
        reason_code: str,
    ) -> ObservationAcquisition:
        stage = AcquisitionStage.SOURCE_ACQUISITION_FAILED
        failed_sources = tuple(
            item.request.source for item in activations if item.result.status is not SourceAcquisitionStatus.ACQUIRED
        )
        unresolved = tuple(
            need.need_id
            for item in activations
            for need in item.result.need_results
            if need.status is not ObservationNeedSatisfactionStatus.FULFILLED
        )
        return ObservationAcquisition(
            acquisition_id,
            origin,
            request,
            stage,
            plan,
            activations,
            None,
            status,
            AcquisitionReason(
                AcquisitionReasonKind.SOURCE_FAILURE,
                reason_code,
                stage,
                failed_sources,
                unresolved,
            ),
        )

    @staticmethod
    def _fusion_failed(
        acquisition_id: str,
        origin: AcquisitionOrigin,
        request: WorldObservationRequest,
        plan: ObservationSelectionPlan,
        activations: tuple[ProviderActivation, ...],
        fusion_outcome,
    ) -> ObservationAcquisition:
        stage = AcquisitionStage.FUSION_FAILED
        return ObservationAcquisition(
            acquisition_id,
            origin,
            request,
            stage,
            plan,
            activations,
            fusion_outcome,
            AcquisitionStatus.FAILED,
            AcquisitionReason(
                AcquisitionReasonKind.FUSION_FAILURE,
                fusion_outcome.reason_code,
                stage,
            ),
        )

    @staticmethod
    def _cancelled(
        acquisition_id: str,
        origin: AcquisitionOrigin,
        request: WorldObservationRequest,
        plan: ObservationSelectionPlan | None,
        activations: tuple[ProviderActivation, ...],
        reason_code: str,
    ) -> ObservationAcquisition:
        stage = AcquisitionStage.CANCELLED
        return ObservationAcquisition(
            acquisition_id,
            origin,
            request,
            stage,
            plan,
            activations,
            None,
            AcquisitionStatus.CANCELLED,
            AcquisitionReason(
                AcquisitionReasonKind.CANCELLATION,
                reason_code,
                stage,
                tuple(item.request.source for item in activations),
                tuple(
                    need.need_id
                    for item in activations
                    for need in item.result.need_results
                    if need.status is ObservationNeedSatisfactionStatus.CANCELLED
                ),
            ),
        )

    def _physical_reset_owners(self) -> tuple[SurfaceAdapter, ...]:
        """Choose one reset owner for every declared physical environment.

        Ownership is independent of source selection so a late-activated adapter is
        always initialized against a physical environment reset for this task.
        """

        groups: dict[str, list[SurfaceAdapter]] = {}
        for adapter in self.adapters:
            if not adapter.physical_environment_id.strip():
                raise ValueError("surface adapter requires a physical environment ID")
            groups.setdefault(adapter.physical_environment_id, []).append(adapter)
        owners: list[SurfaceAdapter] = []
        for adapters in groups.values():
            declared = tuple(adapter for adapter in adapters if adapter.owns_physical_reset)
            if len(declared) != 1:
                raise ValueError("physical environment requires exactly one reset owner")
            owners.append(declared[0])
        return tuple(owners)

    def is_current(self, request: BoundActionRequest) -> bool:
        return self._surface_adapter(request.binding.surface) is not None and (
            request.world_observation_id == self._world_observation_id
            and request.binding.world_observation_id == self._world_observation_id
            and request.binding.source_observation_id in self._source_observation_ids
        )

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        adapter = self._surface_adapter(request.binding.surface)
        if adapter is None:
            return self._not_dispatched(
                request,
                ActionResult(
                    request.request_id,
                    DispatchStatus.NOT_SENT,
                    request.binding.executor_id,
                    False,
                    ActionError.UNSUPPORTED_ACTION,
                ),
            )
        if not self.is_current(request):
            return self._not_dispatched(
                request,
                ActionResult(
                    request.request_id,
                    DispatchStatus.NOT_SENT,
                    request.binding.executor_id,
                    False,
                    ActionError.STALE_BINDING,
                ),
            )
        try:
            result = await adapter.execute(request)
        except ActionDispatchCancelled as exc:
            outcome = self._cancelled_execution(request, exc.result)
            raise ExecutionCancelled(outcome) from exc
        except asyncio.CancelledError as exc:
            result = ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.CANCELLED,
            )
            raise ExecutionCancelled(ExecutionOutcome(request, result, None)) from exc
        if result.request_id != request.request_id or result.backend != request.binding.executor_id:
            raise ValueError("execution result lineage mismatch")
        if result.dispatch_status is DispatchStatus.NOT_SENT:
            return self._not_dispatched(request, result)
        post_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action",
            request.verification_needs,
        )
        post_plan = self._post_action_plan(
            post_request,
            self._route_source_for_binding(request.binding.source_observation_id),
        )
        if isinstance(post_plan, ObservationAcquisition):
            return ExecutionOutcome(request, result, post_plan)
        try:
            post = await self._acquire(
                post_request,
                AcquisitionOrigin.POST_ACTION,
                post_plan,
            )
        except AcquisitionCancelled as exc:
            raise ExecutionCancelled(ExecutionOutcome(request, result, exc.acquisition)) from exc
        return ExecutionOutcome(request, result, post)

    def _cancelled_execution(
        self,
        request: BoundActionRequest,
        result: ActionResult,
    ) -> ExecutionOutcome:
        if result.request_id != request.request_id or result.backend != request.binding.executor_id:
            raise ValueError("cancelled execution result lineage mismatch")
        if result.dispatch_status is DispatchStatus.NOT_SENT:
            return ExecutionOutcome(request, result, None)
        post_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action cancellation",
            request.verification_needs,
        )
        acquisition_id = self._next_acquisition_id()
        selected = self.observation_orchestrator.select(
            self._offers,
            post_request,
            route_source=self._route_source_for_binding(request.binding.source_observation_id),
        )
        if selected.plan is None:
            post = self._pre_selection(
                acquisition_id,
                AcquisitionOrigin.POST_ACTION,
                post_request,
                selected.reason_code,
            )
        else:
            selected_requests = selected_observation_requests(
                selected.plan,
                post_request,
                self._offers,
                acquisition_id,
            )
            cancelled_results = tuple(
                SelectedObservationResult.failed(
                    item,
                    SourceAcquisitionStatus.CANCELLED,
                    "source_acquisition_cancelled",
                )
                for item in selected_requests
            )
            post = self._cancelled(
                acquisition_id,
                AcquisitionOrigin.POST_ACTION,
                post_request,
                selected.plan,
                self._activations(selected_requests, cancelled_results),
                "source_acquisition_cancelled",
            )
        return ExecutionOutcome(request, result, self._remember(post))

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
        return self._remember(
            self._pre_selection(
                self._next_acquisition_id(),
                AcquisitionOrigin.POST_ACTION,
                request,
                outcome.reason_code,
            )
        )

    def _source_owner(self, source: str) -> SurfaceAdapter:
        return self._source_owners[source]

    def _route_source_for_binding(self, source_observation_id: str) -> str:
        try:
            return self._source_by_observation_id[source_observation_id]
        except KeyError as exc:
            raise ValueError("binding source lineage is absent from the current world") from exc

    def _surface_adapter(self, surface: str) -> SurfaceAdapter | None:
        return self._surface_owners.get(surface)

    def _not_dispatched(
        self,
        request: BoundActionRequest,
        result: ActionResult,
    ) -> ExecutionOutcome:
        return ExecutionOutcome(request, result, None)


@dataclass(frozen=True)
class _ProviderCancellation(Exception):
    results: tuple[SelectedObservationResult, ...]


@dataclass
class UnifiedWorldEnvironment:
    """Product WorldEnvironment facade over the sole acquisition coordinator."""

    adapters: tuple[SurfaceAdapter, ...]
    observation_orchestrator: ObservationOrchestrator = field(default_factory=ObservationOrchestrator)
    world_fusion: WorldFusion = field(default_factory=WorldFusion)
    acquisition_coordinator: ObservationAcquisitionCoordinator = field(init=False)

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)
        self.acquisition_coordinator = ObservationAcquisitionCoordinator(
            self.adapters,
            self.observation_orchestrator,
            self.world_fusion,
        )

    def __getattr__(self, name: str):
        return getattr(self.acquisition_coordinator, name)

    @property
    def observation_capabilities(self) -> ObservationCapabilities:
        return self.acquisition_coordinator.observation_capabilities

    @property
    def goal_semantic_contract(self) -> GoalSemanticContract:
        return merge_goal_semantic_contracts(tuple(
            getattr(adapter, "goal_semantic_contract", GoalSemanticContract())
            for adapter in self.adapters
        ))

    @property
    def last_acquisition(self) -> ObservationAcquisition | None:
        return self.acquisition_coordinator.last_acquisition

    async def reset(self, task: TaskGoal) -> ObservationAcquisition:
        return await self.acquisition_coordinator.reset(task)

    async def revise_task(self, task: TaskGoal) -> None:
        await self.acquisition_coordinator.revise_task(task)

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        return await self.acquisition_coordinator.capture(request)

    def is_current(self, request: BoundActionRequest) -> bool:
        return self.acquisition_coordinator.is_current(request)

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        return await self.acquisition_coordinator.execute(request)
