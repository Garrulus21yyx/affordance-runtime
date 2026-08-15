"""Deterministic surface backend composed through the product world environment."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from affordance_runtime.execution.contracts import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationCapabilities,
    ObservationOffer,
    SelectedObservationRequest,
    SelectedObservationResult,
    SourceAcquisitionStatus,
)
from affordance_runtime.world.contracts import SurfaceObservation, WorldObservation
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

ExecuteFn = Callable[[BoundActionRequest, WorldObservation], ActionResult]


class StaleEnvironmentBinding(RuntimeError):
    pass


@dataclass
class ScriptedSurfaceAdapter:
    initial_observation: WorldObservation
    independent_observations: Sequence[WorldObservation] = ()
    post_observations: Sequence[WorldObservation] = ()
    results: Sequence[ActionResult] = ()
    execute_fn: ExecuteFn | None = None
    repeat_last_observation: bool = True
    independent_capture: bool = True
    post_action_observation: bool = True
    surface: str = field(default="scripted", init=False)
    task: TaskGoal | None = field(default=None, init=False)
    capture_requests: list[SelectedObservationRequest] = field(default_factory=list, init=False)
    executed_requests: list[BoundActionRequest] = field(default_factory=list, init=False)
    dispatched_requests: list[BoundActionRequest] = field(default_factory=list, init=False)
    reset_calls: int = field(default=0, init=False)
    capture_calls: int = field(default=0, init=False)
    execute_calls: int = field(default=0, init=False)
    _capture_index: int = field(default=0, init=False)
    _post_index: int = field(default=0, init=False)
    _result_index: int = field(default=0, init=False)
    _current_observation: WorldObservation | None = field(default=None, init=False)
    _pending_reset: bool = field(default=False, init=False)
    _post_pending: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.independent_observations = tuple(self.independent_observations)
        self.post_observations = tuple(self.post_observations)
        self.results = tuple(self.results)
        if self.execute_fn is not None and self.results:
            raise ValueError("scripted adapter accepts either results or execute_fn")
        surfaces = {
            binding.surface
            for world in (
                self.initial_observation,
                *self.independent_observations,
                *self.post_observations,
            )
            for binding in world.bindings
        }
        self.execution_surfaces = tuple(sorted(surfaces | {self.surface}))

    @property
    def physical_environment_id(self) -> str:
        return f"scripted:{id(self)}"

    @property
    def owns_physical_reset(self) -> bool:
        return True

    @property
    def supports_independent_capture(self) -> bool:
        return self.independent_capture

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        source = self._source_for(self.initial_observation)
        return (
            ObservationOffer(
                source.surface,
                source.source_profile.modality,
                source.source_profile.assurance,
                "low",
            ),
        )

    def initialize_task(self, task: TaskGoal) -> None:
        self.task = task

    async def reset_physical(self) -> None:
        self.reset_calls += 1
        self.capture_requests.clear()
        self.executed_requests.clear()
        self.dispatched_requests.clear()
        self.capture_calls = self.execute_calls = 0
        self._capture_index = self._post_index = self._result_index = 0
        self._current_observation = self.initial_observation
        self._pending_reset = True
        self._post_pending = False

    async def acquire(self, request: SelectedObservationRequest) -> SelectedObservationResult:
        self.capture_requests.append(request)
        world: WorldObservation | None
        if self._pending_reset:
            self._pending_reset = False
            world = self.initial_observation
        elif self._post_pending:
            self._post_pending = False
            if not self.post_action_observation:
                return SelectedObservationResult.failed(
                    request,
                    SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                    "post_action_observation_unsupported",
                )
            world = self._next_post()
        else:
            self.capture_calls += 1
            if not self.independent_capture:
                return SelectedObservationResult.failed(
                    request,
                    SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                    "independent_capture_unsupported",
                )
            world = self._next_independent()
        if world is None:
            return SelectedObservationResult.failed(
                request,
                SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                "scripted_observation_unavailable",
            )
        source = self._source_for(world)
        self._current_observation = world
        return SelectedObservationResult.acquired(
            request,
            source,
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        return bool(
            self._current_observation
            and request.world_observation_id == self._current_observation.observation_id
            and request.binding.world_observation_id == self._current_observation.observation_id
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        self.execute_calls += 1
        if not self.is_current(request):
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.STALE_BINDING,
            )
        assert self._current_observation is not None
        self.executed_requests.append(request)
        if self.execute_fn is not None:
            result = self.execute_fn(request, self._current_observation)
            self._post_pending = result.dispatch_status is not DispatchStatus.NOT_SENT
            if self._post_pending:
                self.dispatched_requests.append(request)
            return result
        if self._result_index >= len(self.results):
            raise IndexError("scripted action result sequence exhausted")
        result = self.results[self._result_index]
        self._result_index += 1
        if result.request_id == "*":
            result = ActionResult(
                request.request_id,
                result.dispatch_status,
                result.backend,
                result.transport_success,
                result.error,
                dict(result.adapter_evidence),
            )
        self._post_pending = result.dispatch_status is not DispatchStatus.NOT_SENT
        if self._post_pending:
            self.dispatched_requests.append(request)
        return result

    def _next_independent(self) -> WorldObservation | None:
        values = tuple(self.independent_observations)
        if self._capture_index < len(values):
            value = values[self._capture_index]
            self._capture_index += 1
            return value
        if self.repeat_last_observation and values:
            return values[-1]
        return None

    def _next_post(self) -> WorldObservation | None:
        values = tuple(self.post_observations)
        if self._post_index < len(values):
            value = values[self._post_index]
            self._post_index += 1
            return value
        return None

    @staticmethod
    def _source_for(world: WorldObservation) -> SurfaceObservation:
        if len(world.sources) != 1:
            raise ValueError("scripted fixture requires exactly one original source observation")
        return world.sources[0]


@dataclass
class ScriptedEnvironment:
    """Contract-faithful fixture; every acquisition uses the product coordinator."""

    initial_observation: WorldObservation
    results: Sequence[ActionResult] = ()
    execute_fn: ExecuteFn | None = None
    repeat_last_observation: bool = True
    independent_observations: Sequence[WorldObservation] = ()
    post_observations: Sequence[WorldObservation] = ()
    observation_capabilities: ObservationCapabilities = field(
        default_factory=lambda: ObservationCapabilities(True, True)
    )
    adapter: ScriptedSurfaceAdapter = field(init=False)
    world: UnifiedWorldEnvironment = field(init=False)
    capture_requests: list = field(default_factory=list, init=False)
    executed_requests: list = field(default_factory=list, init=False)
    dispatched_requests: list = field(default_factory=list, init=False)
    reset_calls: int = field(default=0, init=False)
    capture_calls: int = field(default=0, init=False)
    execute_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.adapter = ScriptedSurfaceAdapter(
            self.initial_observation,
            self.independent_observations,
            self.post_observations,
            self.results,
            self.execute_fn,
            self.repeat_last_observation,
            self.observation_capabilities.independent_capture,
            self.observation_capabilities.post_action_observation,
        )
        self.world = UnifiedWorldEnvironment((self.adapter,))
        self.observation_capabilities = self.world.observation_capabilities

    def __getattr__(self, name: str):
        return getattr(self.adapter, name)

    async def reset(self, task):
        self.reset_calls += 1
        self.capture_requests.clear()
        self.executed_requests.clear()
        self.dispatched_requests.clear()
        self.capture_calls = self.execute_calls = 0
        return await self.world.reset(task)

    async def revise_task(self, task):
        return await self.world.revise_task(task)

    async def capture(self, request):
        before = self.adapter.capture_calls
        acquisition = await self.world.capture(request)
        self.capture_calls = self.adapter.capture_calls
        if self.adapter.capture_calls > before:
            self.capture_requests.append(request)
        return acquisition

    async def execute(self, request):
        self.execute_calls += 1
        outcome = await self.world.execute(request)
        self.executed_requests[:] = self.adapter.executed_requests
        self.dispatched_requests[:] = self.adapter.dispatched_requests
        return outcome

    def is_current(self, request):
        return self.world.is_current(request)
