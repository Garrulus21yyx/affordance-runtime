"""Raw user request to verified Coordinator result without authority shortcuts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.coordinator import CoordinatorResult, RunCoordinator
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.task_intake import CompilationResult, CompilationStatus, UserRequest
from affordance_runtime.trace import TraceDag


@dataclass(frozen=True)
class TaskPipelineResult:
    status: str
    compilation: CompilationResult
    trace: TraceDag
    coordinator: CoordinatorResult | None = None


@dataclass
class GeneralistTaskPipeline:
    compiler: LLMIntentCompiler
    coordinator: RunCoordinator
    constraints: dict[str, Any] = field(default_factory=dict)
    granted_capabilities: tuple[str, ...] = ()

    async def run(self, request: UserRequest) -> TaskPipelineResult:
        trace = TraceDag(run_id=request.request_id)
        compilation = await self.compiler.compile(request, task_id=request.request_id, trace=trace)
        return self._run_compiled(compilation, trace)

    def run_sync(self, request: UserRequest) -> TaskPipelineResult:
        """Run while retaining ownership of a sync browser session on this thread."""

        trace = TraceDag(run_id=request.request_id)
        compilation = resolve_awaitable(
            self.compiler.compile(request, task_id=request.request_id, trace=trace)
        )
        return self._run_compiled(compilation, trace)

    def _run_compiled(self, compilation: CompilationResult, trace: TraceDag) -> TaskPipelineResult:
        if compilation.status != CompilationStatus.READY or compilation.task_spec is None:
            return TaskPipelineResult(
                status=compilation.status.value,
                compilation=compilation,
                trace=trace,
            )
        task_spec = compilation.task_spec
        coordinator_result = self.coordinator.run_sync(
            TaskEnvelope(
                task_spec=task_spec,
                constraints=dict(self.constraints),
                # Caller grants are independent inputs. ContractBuilder and
                # CapabilityGate intersect them with the concrete action's
                # deterministic requirements; an LM request never creates a
                # grant, but a missing request also must not erase a valid one.
                capabilities=list(self.granted_capabilities),
            ),
            trace,
        )
        return TaskPipelineResult(
            status=coordinator_result.status.value,
            compilation=compilation,
            trace=coordinator_result.trace,
            coordinator=coordinator_result,
        )
