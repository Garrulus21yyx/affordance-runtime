"""Local task runner connecting the stable task API to standalone scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.cli import _scenario_success, run_scenario
from affordance_runtime.integrations.task_api import (
    ApprovalGrant,
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
        targets = (
            ("Show Pro limits", "Show Enterprise limits") if submission.scenario == "pricing" else (submission.target,)
        )
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


@dataclass(frozen=True)
class LocalScenarioTaskRunner:
    artifact_root: Path
    headless: bool = True

    def __call__(self, request: TaskRequest, approval: ApprovalGrant | None) -> TaskExecution:
        approved = bool(approval and approval.current() and approval.capability in request.capabilities)
        value = run_scenario(
            request.scenario,
            request.target,
            self.artifact_root,
            headless=self.headless,
            approve=approved,
            run_id=request.run_id,
            approval_approver=approval.approver if approval else "",
            constraints_override=request.constraints,
            capabilities_override=request.capabilities,
            admitted_task=request.admitted_task,
        )
        raw_artifacts = value.get("artifacts")
        artifacts = [str(item) for item in raw_artifacts] if isinstance(raw_artifacts, list) else []
        raw_result = value.get("result")
        result = dict(raw_result) if isinstance(raw_result, dict) else {}
        return TaskExecution(
            status=str(value["status"]),
            result=result,
            error_code=str(value["error_code"]) if value.get("error_code") else None,
            artifacts=artifacts,
            trace_path=next((path for path in artifacts if path.endswith("events.jsonl")), ""),
            required_capability="report.export" if value["status"] == "waiting_approval" else "",
        )
