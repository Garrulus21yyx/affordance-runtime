"""Deterministic target WorldEnvironment with source-specific acquisition queues."""

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
    AcquisitionOrigin,
    AcquisitionStatus,
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationOffer,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation

ExecuteFn = Callable[[BoundActionRequest, WorldObservation], ActionResult]


class StaleEnvironmentBinding(RuntimeError):
    pass


@dataclass
class StaticEnvironment:
    # `observations` remains a compatibility input. New tests should use the explicit
    # initial/independent/post fields below.
    observations: Sequence[WorldObservation] = ()
    results: Sequence[ActionResult] = ()
    execute_fn: ExecuteFn | None = None
    repeat_last_observation: bool = True
    initial_observation: WorldObservation | None = None
    independent_observations: Sequence[WorldObservation] = ()
    post_observations: Sequence[WorldObservation] = ()
    post_acquisitions: Sequence[ObservationAcquisition] = ()
    observation_capabilities: ObservationCapabilities = ObservationCapabilities(
        True,
        True,
        (ObservationOffer("static", "structural", "structural", "low"),),
    )
    task: TaskGoal | None = field(default=None, init=False)
    capture_requests: list[WorldObservationRequest] = field(default_factory=list, init=False)
    executed_requests: list[BoundActionRequest] = field(default_factory=list, init=False)
    reset_calls: int = field(default=0, init=False)
    capture_calls: int = field(default=0, init=False)
    execute_calls: int = field(default=0, init=False)
    _capture_index: int = field(default=0, init=False)
    _post_index: int = field(default=0, init=False)
    _result_index: int = field(default=0, init=False)
    _current_observation: WorldObservation | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        legacy = tuple(self.observations)
        self.results = tuple(self.results)
        self.independent_observations = tuple(self.independent_observations)
        self.post_observations = tuple(self.post_observations)
        self.post_acquisitions = tuple(self.post_acquisitions)
        if self.initial_observation is None:
            if not legacy:
                raise ValueError("static environment requires an initial observation")
            self.initial_observation = legacy[0]
            remainder = legacy[1:]
            if not self.independent_observations and not self.post_observations:
                post_count = min(len(remainder), len(self.results))
                if self.execute_fn is not None and remainder:
                    post_count = 1
                if post_count:
                    self.independent_observations = remainder[:-post_count]
                    self.post_observations = remainder[-post_count:]
                else:
                    self.independent_observations = remainder
        if self.execute_fn is not None and self.results:
            raise ValueError("static environment accepts either results or execute_fn, not both")

    async def reset(self, task: TaskGoal) -> ObservationAcquisition:
        self.reset_calls += 1
        self.task = task
        self.capture_requests.clear()
        self.executed_requests.clear()
        self.capture_calls = 0
        self.execute_calls = 0
        self._capture_index = self._post_index = self._result_index = 0
        self._current_observation = self.initial_observation
        return ObservationAcquisition(
            AcquisitionStatus.ACQUIRED,
            AcquisitionOrigin.RESET,
            self.initial_observation,
            "static_reset_acquired",
        )

    async def revise_task(self, task: TaskGoal) -> None:
        if self.task is None:
            raise RuntimeError("static environment must be reset before task revision")
        self.task = task

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        if self.task is None:
            raise RuntimeError("static environment must be reset before capture")
        if not self.observation_capabilities.independent_capture:
            return ObservationAcquisition(
                AcquisitionStatus.CAPABILITY_UNAVAILABLE,
                AcquisitionOrigin.INDEPENDENT_CAPTURE,
                None,
                "independent_capture_unsupported",
            )
        self.capture_calls += 1
        self.capture_requests.append(request)
        observation = self._next_independent()
        if observation is None:
            return ObservationAcquisition(
                AcquisitionStatus.FAILED,
                AcquisitionOrigin.INDEPENDENT_CAPTURE,
                None,
                "static_capture_failed",
            )
        self._current_observation = observation
        return ObservationAcquisition(
            AcquisitionStatus.ACQUIRED,
            AcquisitionOrigin.INDEPENDENT_CAPTURE,
            observation,
            "static_capture_acquired",
        )

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        self.execute_calls += 1
        if not self.is_current(request):
            result = ActionResult(
                request.request_id, DispatchStatus.NOT_SENT, request.binding.executor_id,
                False, ActionError.STALE_BINDING,
            )
            return ExecutionOutcome(result, _unavailable_post("action_not_dispatched"))
        assert self._current_observation is not None
        self.executed_requests.append(request)
        result = self._action_result(request)
        if result.dispatch_status is DispatchStatus.NOT_SENT:
            return ExecutionOutcome(result, _unavailable_post("action_not_dispatched"))
        post = self._next_post()
        if post.status is AcquisitionStatus.ACQUIRED:
            self._current_observation = post.observation
        return ExecutionOutcome(result, post)

    def is_current(self, request: BoundActionRequest) -> bool:
        return bool(
            self._current_observation
            and request.world_observation_id == self._current_observation.observation_id
            and request.binding.world_observation_id == self._current_observation.observation_id
        )

    def _next_independent(self) -> WorldObservation | None:
        values = tuple(self.independent_observations)
        if self._capture_index < len(values):
            value = values[self._capture_index]
            self._capture_index += 1
            return value
        if self.repeat_last_observation and values:
            return values[-1]
        return None

    def _action_result(self, request: BoundActionRequest) -> ActionResult:
        assert self._current_observation is not None
        if self.execute_fn is not None:
            return self.execute_fn(request, self._current_observation)
        if self._result_index >= len(self.results):
            raise IndexError("static action result sequence exhausted")
        result = self.results[self._result_index]
        self._result_index += 1
        if result.request_id != "*":
            return result
        return ActionResult(
            request.request_id, result.dispatch_status, result.backend,
            result.transport_success, result.error, dict(result.adapter_evidence),
        )

    def _next_post(self) -> ObservationAcquisition:
        if self._post_index < len(self.post_acquisitions):
            value = self.post_acquisitions[self._post_index]
            self._post_index += 1
            return value
        if self._post_index < len(self.post_observations):
            observation = self.post_observations[self._post_index]
            self._post_index += 1
            return ObservationAcquisition(
                AcquisitionStatus.ACQUIRED,
                AcquisitionOrigin.POST_ACTION,
                observation,
                "static_post_acquired",
            )
        return _unavailable_post("post_action_observation_unavailable")


def _unavailable_post(reason_code: str) -> ObservationAcquisition:
    return ObservationAcquisition(
        AcquisitionStatus.CAPABILITY_UNAVAILABLE,
        AcquisitionOrigin.POST_ACTION,
        None,
        reason_code,
    )
