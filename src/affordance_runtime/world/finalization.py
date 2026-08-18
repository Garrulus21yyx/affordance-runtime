"""Optional environment finalization capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.world.acquisition import ObservationAcquisition


@dataclass(frozen=True)
class EnvironmentFinalization:
    result: ActionResult
    post_acquisition: ObservationAcquisition | None = None


class FinalizingEnvironment(Protocol):
    @property
    def supports_finalization(self) -> bool: ...

    async def finalize(self, content: str) -> EnvironmentFinalization: ...
