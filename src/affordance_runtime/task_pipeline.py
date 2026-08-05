"""Raw user request to verified Coordinator result without authority shortcuts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any

from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.coordinator import RunCoordinator, RunResult
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_recovery import recovery_dispatcher_for_model
from affordance_runtime.recovery_protocol import classify_failure
from affordance_runtime.runtime import RunRequest
from affordance_runtime.semantic_audit import SemanticAudit, SemanticAuditStatus
from affordance_runtime.source_envelope import SourceEnvelope, SourceEnvelopeBuilder
from affordance_runtime.stage_protocol import (
    TerminalResult,
    UserInputRequest,
    build_failure_owner_handoff,
)
from affordance_runtime.task_intake import CompilationIssue, CompilationStatus, TaskStructure, UserRequest
from affordance_runtime.task_planning import LLMTaskPlanner, PlanningRouter
from affordance_runtime.task_spec_authority import TaskSpecAdmissionResult, TaskSpecAuthority
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class TaskPipelineResult:
    status: str
    compilation: TaskSpecAdmissionResult
    trace: TraceDag
    coordinator: RunResult | None = None


@dataclass
class GeneralistTaskPipeline:
    compiler: LLMIntentCompiler
    coordinator: RunCoordinator
    constraints: dict[str, Any] = field(default_factory=dict)
    granted_capabilities: tuple[str, ...] = ()
    source_builder: SourceEnvelopeBuilder = field(default_factory=SourceEnvelopeBuilder)
    semantic_audit: SemanticAudit = field(default_factory=SemanticAudit)
    task_spec_authority: TaskSpecAuthority = field(default_factory=TaskSpecAuthority)

    def __post_init__(self) -> None:
        """Attach only a real configured model fallback to this normal entrypoint."""

        model = getattr(self.compiler, "model", None)
        if model is None:
            return
        model_dispatcher = recovery_dispatcher_for_model(
            model, planner=self.coordinator.planning_stage.planner
        )
        if not model_dispatcher.available_kinds:
            return
        handlers = dict(self.coordinator.recovery_stage.owner_dispatcher.handlers)
        for kind, handler in model_dispatcher.handlers.items():
            handlers.setdefault(kind, handler)
        dispatcher = type(self.coordinator.recovery_stage.owner_dispatcher)(handlers)
        self.coordinator = replace(
            self.coordinator,
            recovery_stage=replace(
                self.coordinator.recovery_stage, owner_dispatcher=dispatcher
            ),
        )

    async def run(self, request: UserRequest) -> TaskPipelineResult:
        trace = TraceDag(run_id=request.request_id)
        envelope, parent = self._build_source_envelope(request, trace)
        proposal = await self.compiler.propose(request, envelope, trace=trace, parent=parent)
        compilation = self._audit_and_admit(request, envelope, proposal, trace)
        return self._run_compiled(compilation, trace)

    def run_sync(self, request: UserRequest) -> TaskPipelineResult:
        """Run while retaining ownership of a sync browser session on this thread."""

        trace = TraceDag(run_id=request.request_id)
        envelope, parent = self._build_source_envelope(request, trace)
        proposal = resolve_awaitable(
            self.compiler.propose(request, envelope, trace=trace, parent=parent)
        )
        compilation = self._audit_and_admit(request, envelope, proposal, trace)
        return self._run_compiled(compilation, trace)

    def _run_compiled(self, compilation: TaskSpecAdmissionResult, trace: TraceDag) -> TaskPipelineResult:
        if compilation.status != CompilationStatus.READY or compilation.task_spec is None:
            self._trace_intake_recovery(compilation, trace)
            return TaskPipelineResult(
                status=compilation.status.value,
                compilation=compilation,
                trace=trace,
            )
        task_spec = compilation.task_spec
        coordinator = self.coordinator
        flow = coordinator.planning_stage.task_plan_flow
        task_planner = flow.lifecycle.planner if flow is not None else None
        if (
            task_spec.task_structure == TaskStructure.MULTI_STAGE
            and isinstance(task_planner, PlanningRouter)
            and task_planner.complex_planner is None
        ):
            assert flow is not None
            coordinator = replace(
                coordinator,
                planning_stage=replace(
                    coordinator.planning_stage,
                    task_plan_flow=replace(
                        flow,
                        lifecycle=replace(
                            flow.lifecycle,
                            planner=replace(
                                task_planner,
                                complex_planner=LLMTaskPlanner(self.compiler.model),
                            ),
                        ),
                    ),
                ),
            )
        coordinator_result = coordinator.run_sync(
            RunRequest(
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
        compilation: TaskSpecAdmissionResult,
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
        classification = classify_failure(failure)
        handoff = build_failure_owner_handoff(
            failure,
            classification.owner,
            classification.reason_code,
        )
        parent = trace.nodes[-1] if trace.nodes else None
        parent = trace.add(
            "FailureDetected",
            {"state": "intake", "failure": failure.model_dump(mode="json")},
            parents=[parent.id] if parent is not None else None,
        )
        parent = trace.add(
            "FailureOwnerRouted",
            {
                "state": "intake",
                "failure_id": failure.failure_id,
                "owner": handoff.owner.value,
                "reason_code": handoff.reason_code,
                "handoff_type": type(handoff).__name__,
            },
            parents=[parent.id],
        )
        if isinstance(handoff, UserInputRequest):
            trace.add(
                "UserInputRequested",
                {
                    "state": "waiting_clarification",
                    "failure_id": handoff.failure_id,
                    "question": handoff.question,
                },
                parents=[parent.id],
            )
        elif isinstance(handoff, TerminalResult):
            trace.add(
                "TerminalResultRecorded",
                {
                    "state": handoff.status,
                    "failure_id": handoff.failure_id,
                    "reason_code": handoff.reason_code,
                },
                parents=[parent.id],
            )

    def _build_source_envelope(
        self,
        request: UserRequest,
        trace: TraceDag,
    ) -> tuple[SourceEnvelope, TraceNode]:
        parent = trace.add(
            "UserRequestReceived",
            {
                "request_id": request.request_id,
                "raw_text_sha256": hashlib.sha256(request.raw_text.encode()).hexdigest(),
                "raw_text_length": len(request.raw_text),
            },
        )
        envelope = self.source_builder.build(request)
        parent = trace.add(
            "SourceEnvelopeBuilt",
            {
                "source_envelope_ref": envelope.identity,
                "source_binding_digest": envelope.binding_digest,
                "content_digest": envelope.content_digest,
                "content_length": envelope.content_length,
                "source_count": len(envelope.sources),
                "anchor_count": len(envelope.anchors),
            },
            parents=[parent.id],
        )
        return envelope, parent

    def _audit_and_admit(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        proposal: object,
        trace: TraceDag,
    ) -> TaskSpecAdmissionResult:
        from affordance_runtime.task_spec_authority import MinimalIntentProposal

        if not isinstance(proposal, MinimalIntentProposal):
            raise TypeError("intent compiler returned a non-canonical proposal")
        audit = self.semantic_audit.evaluate(envelope, proposal)
        parent = trace.nodes[-1]
        parent = trace.add(
            "SemanticAuditEvaluated",
            audit.model_dump(mode="json"),
            parents=[parent.id],
        )
        if audit.status != SemanticAuditStatus.PASS:
            status = (
                CompilationStatus.NEEDS_CLARIFICATION
                if audit.status == SemanticAuditStatus.CLARIFICATION_REQUIRED
                else CompilationStatus.POLICY_CONFLICT
            )
            result = TaskSpecAdmissionResult(
                status=status,
                request_id=request.request_id,
                proposal=proposal,
                issues=tuple(
                    CompilationIssue(code=code, field="semantic_audit")
                    for code in audit.issue_codes
                ),
            )
        else:
            result = self.task_spec_authority.admit(
                request,
                envelope,
                proposal,
                task_id=request.request_id,
            )
        trace.add(
            "TaskSpecAdmissionDecided",
            {
                "status": result.status.value,
                "task_spec_identity": result.task_spec.identity if result.task_spec else "",
                "authority": type(self.task_spec_authority).__name__,
            },
            parents=[parent.id],
        )
        return result
