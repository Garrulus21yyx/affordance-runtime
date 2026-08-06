"""Local task runner connecting the stable task API to standalone scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, RLock, Thread

from affordance_runtime.cli import _scenario_success, run_scenario
from affordance_runtime.contracts import ActionContract, ApprovalToken
from affordance_runtime.integrations.task_api import (
    ApprovalGrant,
    PendingApprovalRequest,
    TaskExecution,
    TaskRequest,
    UserTaskSubmission,
)
from affordance_runtime.material_contracts import (
    MaterialBinding,
    MaterialBindingKind,
    MaterialEffectKind,
    MaterialField,
)
from affordance_runtime.planners import pricing_required_outputs, pricing_success_expression
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task_intake import CompilationStatus, OperationClass, RequestedEffect, UserRequest
from affordance_runtime.task_spec_authority import MinimalIntentProposal, TaskSpecAuthority


@dataclass(frozen=True)
class LocalScenarioTaskIntake:
    """Canonical deterministic intake for the local reference scenarios."""

    def __call__(self, submission: UserTaskSubmission) -> TaskRequest:
        request = UserRequest(
            request_id=submission.run_id,
            raw_text=f"{submission.goal}\nTarget: {submission.target}",
            channel="external-task-rpc",
            target_refs=(submission.target,),
        )
        envelope = SourceEnvelopeBuilder().build(request)
        source_ref = envelope.whole_request_anchor.anchor_id
        operation = {
            "pricing": OperationClass.READ_ONLY,
            "settings": OperationClass.REVERSIBLE_WRITE,
            "export": OperationClass.EXTERNAL_SIDE_EFFECT,
        }[submission.scenario]
        capability = {
            "pricing": "",
            "settings": "settings.write.reversible",
            "export": "report.export",
        }[submission.scenario]
        targets = {
            "pricing": ("Show Pro limits", "Show Enterprise limits"),
            "settings": ("Enable notifications",),
            "export": ("Export report",),
        }[submission.scenario]
        effect_id = "requirement:effect:1" if submission.scenario == "export" else ""
        proposal = MinimalIntentProposal(
            objective=submission.goal,
            requested_effects=tuple(
                RequestedEffect(
                    operation_class=operation,
                    effect_id=effect_id,
                    material_effect_kind=(
                        MaterialEffectKind.EXTERNAL_ACTION
                        if submission.scenario == "export"
                        else MaterialEffectKind.NONE
                    ),
                    target=target,
                    capability=capability,
                    source_ref=source_ref,
                )
                for target in targets
            ),
            success=(
                pricing_success_expression()
                if submission.scenario == "pricing"
                else _scenario_success("requirement:effect:1", submission.scenario)
            ),
            required_outputs=(pricing_required_outputs() if submission.scenario == "pricing" else ()),
            external_effect_criterion_ids=(("criterion:export-effect",) if submission.scenario == "export" else ()),
            final_recheck_criterion_ids=(("criterion:export-final",) if submission.scenario == "export" else ()),
            material_bindings=(
                (
                    MaterialBinding(
                        binding_id="binding:export-destination",
                        effect_ref=effect_id,
                        field=MaterialField.EXTERNAL_DESTINATION,
                        value=submission.target,
                        source_ref=source_ref,
                        binding_kind=MaterialBindingKind.DIRECT_USER_EXPLICIT,
                    ),
                )
                if submission.scenario == "export"
                else ()
            ),
        )
        admission = TaskSpecAuthority().admit(request, envelope, proposal)
        if admission.status != CompilationStatus.READY or admission.admitted_task is None:
            codes = ",".join(item.code for item in admission.issues)
            raise ValueError(f"task intake {admission.status.value}: {codes}")
        return TaskRequest(
            run_id=submission.run_id,
            scenario=submission.scenario,
            target=submission.target,
            admitted_task=admission.admitted_task,
            constraints=dict(submission.constraints),
            capabilities=list(submission.capabilities),
        )


@dataclass
class LocalScenarioTaskRunner:
    artifact_root: Path
    headless: bool = True
    _sessions: dict[str, "_PendingLocalRun"] = field(default_factory=dict, init=False)
    _lock: RLock = field(default_factory=RLock, init=False)

    def __call__(self, request: TaskRequest, approval: ApprovalGrant | None) -> TaskExecution:
        with self._lock:
            session = self._sessions.get(request.run_id)
            if session is None and approval is None:
                session = _PendingLocalRun(self, request)
                self._sessions[request.run_id] = session
                session.start()
        if session is not None:
            if approval is not None:
                session.submit(approval)
            execution = session.wait_for_boundary()
            if session.completed.is_set():
                with self._lock:
                    self._sessions.pop(request.run_id, None)
            return execution
        # The service process lost the paused H1 continuation. Rebuilding is
        # allowed only with the exact grant as provider; H2 cannot consume it.
        assert approval is not None
        return self._run_once(request, approval)

    def cancel(self, run_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(run_id, None)
        if session is not None:
            session.cancel()

    def _run_once(self, request: TaskRequest, approval: ApprovalGrant | None) -> TaskExecution:
        value = run_scenario(
            request.scenario,
            request.target,
            self.artifact_root,
            headless=self.headless,
            approval_provider_override=approval,
            run_id=request.run_id,
            approval_approver=approval.approver if approval else "",
            constraints_override=request.constraints,
            capabilities_override=request.capabilities,
            admitted_task=request.admitted_task,
        )
        return _task_execution(request, value)


@dataclass
class _PendingLocalRun:
    owner: LocalScenarioTaskRunner
    request: TaskRequest
    pending: PendingApprovalRequest | None = None
    grant: ApprovalGrant | None = None
    value: dict[str, object] | None = None
    error: BaseException | None = None
    pending_ready: Event = field(default_factory=Event)
    grant_ready: Event = field(default_factory=Event)
    completed: Event = field(default_factory=Event)

    def start(self) -> None:
        Thread(target=self._run, name=f"runtime-{self.request.run_id}", daemon=True).start()

    def approve(self, contract: ActionContract) -> ApprovalToken | None:
        self.pending = PendingApprovalRequest.from_contract(contract)
        self.pending_ready.set()
        remaining = max(0.0, self.pending.expires_at_s - self.pending.issued_at_s)
        if not self.grant_ready.wait(timeout=remaining):
            return None
        return self.grant.approve(contract) if self.grant is not None else None

    def submit(self, grant: ApprovalGrant) -> None:
        if self.pending is None or grant.approval_request_id != self.pending.approval_request_id:
            raise ValueError("approval does not match the paused local contract")
        self.grant = grant
        self.grant_ready.set()

    def cancel(self) -> None:
        self.grant = None
        self.grant_ready.set()

    def wait_for_boundary(self) -> TaskExecution:
        while not self.pending_ready.wait(timeout=0.05):
            if self.completed.is_set():
                return self._completed_execution()
        if self.completed.is_set():
            return self._completed_execution()
        if not self.grant_ready.is_set():
            assert self.pending is not None
            return TaskExecution("waiting_approval", pending_approval=self.pending)
        self.completed.wait()
        return self._completed_execution()

    def _completed_execution(self) -> TaskExecution:
        if self.error is not None:
            raise RuntimeError("local scenario worker failed") from self.error
        assert self.value is not None
        return _task_execution(self.request, self.value)

    def _run(self) -> None:
        try:
            self.value = run_scenario(
                self.request.scenario,
                self.request.target,
                self.owner.artifact_root,
                headless=self.owner.headless,
                approval_provider_override=self,
                run_id=self.request.run_id,
                constraints_override=self.request.constraints,
                capabilities_override=self.request.capabilities,
                admitted_task=self.request.admitted_task,
            )
        except BaseException as exc:
            self.error = exc
        finally:
            self.completed.set()


def _task_execution(request: TaskRequest, value: dict[str, object]) -> TaskExecution:
    raw_artifacts = value.get("artifacts")
    artifacts = [str(item) for item in raw_artifacts] if isinstance(raw_artifacts, list) else []
    raw_result = value.get("result")
    result = dict(raw_result) if isinstance(raw_result, dict) else {}
    raw_pending = value.get("pending_approval")
    pending = (
        PendingApprovalRequest.from_runtime_event(request.run_id, raw_pending)
        if isinstance(raw_pending, dict) and value["status"] == "waiting_approval"
        else None
    )
    return TaskExecution(
        status=str(value["status"]),
        result=result,
        error_code=str(value["error_code"]) if value.get("error_code") else None,
        artifacts=artifacts,
        trace_path=next((path for path in artifacts if path.endswith("events.jsonl")), ""),
        pending_approval=pending,
    )
