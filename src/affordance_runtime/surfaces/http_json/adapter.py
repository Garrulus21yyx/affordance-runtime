"""Read-only registered HTTP facts projected into the unified world."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.execution.contracts import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationOffer,
    SelectedObservationRequest,
    SelectedObservationResult,
)
from affordance_runtime.world.contracts import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)

from .contracts import (
    HttpJsonFactProjection,
    HttpJsonProjectionError,
    HttpJsonProjectionErrorCode,
    HttpJsonSourceRegistration,
    JsonPathSegment,
)
from .transport import HttpJsonTransportPort, UrllibHttpJsonTransport


@dataclass
class HttpJsonSurfaceAdapter:
    registration: HttpJsonSourceRegistration
    transport: HttpJsonTransportPort = field(default_factory=UrllibHttpJsonTransport, repr=False)
    owns_physical_reset: bool = field(default=True, repr=False)
    surface: str = field(default="http_json", init=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)

    @property
    def physical_environment_id(self) -> str:
        return f"http_json_transport:{id(self.transport)}"

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        return (ObservationOffer(
            self.surface,
            "environment_state",
            "authoritative",
            "medium",
            self.surface,
        ),)

    def initialize_task(self, task: TaskGoal) -> None:
        self._task = task

    async def reset_physical(self) -> None:
        return None

    async def acquire(self, request: SelectedObservationRequest) -> SelectedObservationResult:
        if self._task is None:
            raise RuntimeError("HTTP JSON surface adapter must be reset before observation")
        payload = await self.transport.fetch_json(self.registration.endpoint)
        projected = tuple(
            (projection, _extract(payload, projection.path))
            for projection in self.registration.projections
        )
        revision = _revision(projected)
        observation_id = f"http-json:{uuid.uuid4().hex}"
        targets = _targets(projected)
        facts = tuple(
            StateFact(
                f"{observation_id}:{projection.subject_id}:{projection.predicate}",
                projection.subject_id,
                projection.predicate,
                value,
                observation_id,
            )
            for projection, value in projected
        )
        observation = SurfaceObservation(
            observation_id,
            self.surface,
            revision,
            ObservationSourceProfile.http_json(),
            targets,
            facts,
            (),
            CoverageState.COMPLETE,
            {},
            acquisition_root_id=f"http-json:{self.registration.source_id}:{revision}",
        )
        return SelectedObservationResult.acquired(
            request,
            observation,
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        del request
        return False

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        return ActionResult(
            request.request_id,
            DispatchStatus.NOT_SENT,
            self.surface,
            False,
            ActionError.UNSUPPORTED_ACTION,
        )


def _extract(value: Any, path: tuple[JsonPathSegment, ...]) -> Any:
    current = value
    for segment in path:
        if isinstance(segment, str):
            if not isinstance(current, Mapping):
                raise HttpJsonProjectionError(
                    HttpJsonProjectionErrorCode.PATH_TYPE_MISMATCH,
                    path,
                )
            if segment not in current:
                raise HttpJsonProjectionError(HttpJsonProjectionErrorCode.MISSING_KEY, path)
            current = current[segment]
        else:
            if not isinstance(current, Sequence) or isinstance(current, str | bytes | bytearray):
                raise HttpJsonProjectionError(
                    HttpJsonProjectionErrorCode.PATH_TYPE_MISMATCH,
                    path,
                )
            if segment >= len(current):
                raise HttpJsonProjectionError(
                    HttpJsonProjectionErrorCode.INDEX_OUT_OF_RANGE,
                    path,
                )
            current = current[segment]
    return to_json_compatible(current)


def _revision(projected: tuple[tuple[HttpJsonFactProjection, Any], ...]) -> str:
    public = tuple(
        (item.subject_id, item.role, item.label, item.predicate, value)
        for item, value in projected
    )
    encoded = json.dumps(public, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def _targets(
    projected: tuple[tuple[HttpJsonFactProjection, Any], ...],
) -> tuple[SemanticTarget, ...]:
    identities: dict[str, tuple[str, str]] = {}
    states: dict[str, dict[str, Any]] = {}
    for projection, value in projected:
        identities.setdefault(projection.subject_id, (projection.role, projection.label))
        states.setdefault(projection.subject_id, {})[projection.predicate] = value
    return tuple(
        SemanticTarget(subject_id, *identities[subject_id], states[subject_id])
        for subject_id in sorted(identities)
    )
