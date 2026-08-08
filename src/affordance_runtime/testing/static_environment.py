"""Deterministic target WorldEnvironment for focused loop tests."""

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
from affordance_runtime.world.contracts import WorldObservation

ExecuteFn = Callable[[BoundActionRequest, WorldObservation], ActionResult]


class StaleEnvironmentBinding(RuntimeError):
    pass


@dataclass
class StaticEnvironment:
    observations: Sequence[WorldObservation]
    results: Sequence[ActionResult] = ()
    execute_fn: ExecuteFn | None = None
    repeat_last_observation: bool = True
    task: TaskGoal | None = field(default=None, init=False)
    observation_reasons: list[str] = field(default_factory=list, init=False)
    executed_requests: list[BoundActionRequest] = field(default_factory=list, init=False)
    _observation_index: int = field(default=0, init=False)
    _result_index: int = field(default=0, init=False)
    _current_observation: WorldObservation | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.observations = tuple(self.observations)
        self.results = tuple(self.results)
        if not self.observations:
            raise ValueError("static environment requires at least one observation")
        if self.execute_fn is not None and self.results:
            raise ValueError("static environment accepts either results or execute_fn, not both")

    async def reset(self, task: TaskGoal) -> None:
        self.task = task
        self.observation_reasons.clear()
        self.executed_requests.clear()
        self._observation_index = 0
        self._result_index = 0
        self._current_observation = None

    async def observe(self, reason: str) -> WorldObservation:
        if self.task is None:
            raise RuntimeError("static environment must be reset before observation")
        self.observation_reasons.append(reason)
        if self._observation_index < len(self.observations):
            observation = self.observations[self._observation_index]
            self._observation_index += 1
        elif self.repeat_last_observation:
            observation = self.observations[-1]
        else:
            raise IndexError("static observation sequence exhausted")
        self._current_observation = observation
        return observation

    async def execute(self, request: BoundActionRequest) -> ActionResult:
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
            return self.execute_fn(request, self._current_observation)
        if self._result_index >= len(self.results):
            raise IndexError("static action result sequence exhausted")
        result = self.results[self._result_index]
        self._result_index += 1
        if result.request_id == "*":
            return ActionResult(
                request.request_id,
                result.dispatch_status,
                result.backend,
                result.transport_success,
                result.error,
                dict(result.adapter_evidence),
            )
        return result

    def is_current(self, request: BoundActionRequest) -> bool:
        return bool(
            self._current_observation
            and request.world_observation_id == self._current_observation.observation_id
            and request.binding.world_observation_id == self._current_observation.observation_id
        )
