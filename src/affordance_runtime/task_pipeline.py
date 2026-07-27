"""Raw user request to verified Coordinator result without authority shortcuts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.coordinator import CoordinatorResult, RunCoordinator
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_recovery import recovery_dispatcher_for_model
from affordance_runtime.recovery_commands import (
    RecoveryChangeDimension,
    RecoveryCommandKind,
    RecoveryDelta,
    RecoveryReceipt,
)
from affordance_runtime.recovery_coordinator import RecoverySelectionContext
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.task_intake import CompilationResult, CompilationStatus, TaskStructure, UserRequest
from affordance_runtime.task_planning import LLMTaskPlanner, PlanningRouter
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

    def __post_init__(self) -> None:
        """Attach only a real configured model fallback to this normal entrypoint."""

        model = getattr(self.compiler, "model", None)
        if model is None:
            return
        model_dispatcher = recovery_dispatcher_for_model(model, planner=self.coordinator.planner)
        if not model_dispatcher.available_commands:
            return
        handlers = dict(self.coordinator.recovery_command_dispatcher.handlers)
        for kind, handler in model_dispatcher.handlers.items():
            handlers.setdefault(kind, handler)
        self.coordinator = replace(
            self.coordinator,
            recovery_command_dispatcher=type(self.coordinator.recovery_command_dispatcher)(handlers),
        )

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
            self._trace_intake_recovery(compilation, trace)
            return TaskPipelineResult(
                status=compilation.status.value,
                compilation=compilation,
                trace=trace,
            )
        task_spec = compilation.task_spec
        coordinator = self.coordinator
        task_planner = coordinator.task_planner
        if (
            task_spec.task_structure == TaskStructure.MULTI_STAGE
            and isinstance(task_planner, PlanningRouter)
            and task_planner.complex_planner is None
        ):
            coordinator = replace(
                coordinator,
                task_planner=replace(
                    task_planner,
                    complex_planner=LLMTaskPlanner(self.compiler.model),
                ),
            )
        coordinator_result = coordinator.run_sync(
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

    def _trace_intake_recovery(
        self,
        compilation: CompilationResult,
        trace: TraceDag,
    ) -> None:
        clarification = compilation.status == CompilationStatus.NEEDS_CLARIFICATION
        message = "; ".join(
            f"{item.code}:{item.field}:{item.detail}" for item in compilation.issues
        ) or compilation.status.value
        failure = make_failure_envelope(
            run_id=compilation.request_id,
            phase=FailurePhase.INTAKE,
            failure_class=(
                FailureClass.INVALID_INPUT
                if clarification
                else FailureClass.AUTHORITY
                if compilation.status == CompilationStatus.POLICY_CONFLICT
                else FailureClass.VALIDATION
            ),
            error_code=compilation.status.value,
            message=message,
            state_version=0,
            expected_effect=compilation.draft.objective,
            remaining_budgets=RemainingRecoveryBudgets(
                recoveries=1,
                user_escalations=1,
                timeout_ms=5_000,
            ),
            recoverable=clarification,
            progress_fingerprint="intake:uncompiled",
        )
        plan = self.coordinator.recovery_coordinator.plan(
            failure,
            RecoverySelectionContext(
                available_commands=(
                    frozenset(
                        {
                            RecoveryCommandKind.CLARIFY_INTENT,
                            RecoveryCommandKind.ASK_USER,
                            RecoveryCommandKind.ABORT,
                        }
                    )
                    if clarification
                    else frozenset({RecoveryCommandKind.ABORT})
                ),
                current_attempt_fingerprint=failure.progress_fingerprint,
                user_question=message,
                accepted_profile_digest=self.coordinator.runtime_profile_digest,
                accepted_profile_artifact_ids=frozenset(
                    self.coordinator.loaded_profile_artifact_ids
                ),
            ),
            current_state_version=0,
        )
        command = plan.commands[0]
        parent = trace.nodes[-1] if trace.nodes else None
        parent = trace.add(
            "FailureDetected",
            {"state": "intake", "failure": failure.model_dump(mode="json")},
            parents=[parent.id] if parent is not None else None,
        )
        parent = trace.add(
            "RecoveryStrategySelected",
            {"state": "intake", "plan": plan.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryCommandStarted",
            {"state": "intake", "command": command.model_dump(mode="json")},
            parents=[parent.id],
        )
        next_state = (
            "waiting_clarification"
            if command.kind
            in {RecoveryCommandKind.CLARIFY_INTENT, RecoveryCommandKind.ASK_USER}
            else "aborted"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=failure.progress_fingerprint,
            next_attempt_fingerprint=f"{command.strategy_id}:{next_state}",
            changed_dimensions=command.changed_dimensions,
            explanation=command.expected_change,
        )
        receipt = RecoveryReceipt(
            command_id=command.command_id,
            success=True,
            state_before="intake:0",
            state_after=next_state,
            changed_dimensions=command.changed_dimensions,
            delta=delta,
        )
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": next_state, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": next_state, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        trace.add(
            (
                "RecoveryEscalatedToUser"
                if RecoveryChangeDimension.USER_INFORMATION in command.changed_dimensions
                else "RecoveryAborted"
            ),
            {"state": next_state, "reentry_phase": command.reentry_phase.value},
            parents=[parent.id],
        )
