"""Raw user request to verified Coordinator result without authority shortcuts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
        if compilation.status != CompilationStatus.READY or compilation.task_spec is None:
            return TaskPipelineResult(
                status=compilation.status.value,
                compilation=compilation,
                trace=trace,
            )
        task_spec = compilation.task_spec
        coordinator_result = await self.coordinator.run(
            TaskEnvelope(
                task_spec=task_spec,
                constraints=dict(self.constraints),
                capabilities=[
                    capability
                    for capability in self.granted_capabilities
                    if capability in set(task_spec.requested_capabilities)
                ],
            ),
            trace,
        )
        return TaskPipelineResult(
            status=coordinator_result.status.value,
            compilation=compilation,
            trace=coordinator_result.trace,
            coordinator=coordinator_result,
        )
