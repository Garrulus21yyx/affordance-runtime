"""Legacy Coordinator client retained for compatibility during target cutover."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.coordinator import RunCoordinator
from affordance_runtime.runtime import RunRequest
from affordance_runtime.runtime_result_phase import RunResult
from affordance_runtime.trace import TraceDag


@dataclass(frozen=True)
class RuntimeClient:
    """Legacy staged-pipeline client; product consumers use TargetRuntime."""

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


LegacyRuntimeClient = RuntimeClient
"""Explicit name for the compatibility client backed by RunCoordinator."""
