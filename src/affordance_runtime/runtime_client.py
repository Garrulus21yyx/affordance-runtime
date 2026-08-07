"""Stable client boundary for executing runtime requests."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.coordinator import RunCoordinator
from affordance_runtime.runtime import RunRequest
from affordance_runtime.runtime_result_phase import RunResult
from affordance_runtime.trace import TraceDag


@dataclass(frozen=True)
class RuntimeClient:
    coordinator: RunCoordinator

    async def run(
        self,
        request: RunRequest,
        upstream_trace: TraceDag | None = None,
    ) -> RunResult:
        return await self.coordinator.run(request, upstream_trace)

    def run_sync(
        self,
        request: RunRequest,
        upstream_trace: TraceDag | None = None,
    ) -> RunResult:
        return self.coordinator.run_sync(request, upstream_trace)
