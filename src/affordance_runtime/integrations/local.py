"""Local task runner connecting the stable task API to standalone scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.cli import run_scenario
from affordance_runtime.integrations.task_api import ApprovalGrant, TaskExecution, TaskRequest


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
