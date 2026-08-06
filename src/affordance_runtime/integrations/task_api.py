"""Stable task-level API for parent agents and tool adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Callable

from affordance_runtime.approval_contracts import present_approval
from affordance_runtime.contracts import ActionContract, ApprovalToken
from affordance_runtime.immutable import FrozenSequence, freeze_json, to_json_compatible
from affordance_runtime.task_intake import TaskSpec, task_effect_targets
from affordance_runtime.task_spec_authority import AdmittedTaskSpec


class ServiceRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_CLARIFICATION = "waiting_clarification"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskRequest:
    run_id: str
    scenario: str
    target: str
    admitted_task: AdmittedTaskSpec
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)

    @property
    def goal(self) -> str:
        return self.task_spec.objective

    @property
    def task_spec(self) -> TaskSpec:
        return self.admitted_task.task_spec

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", freeze_json(self.constraints))
        object.__setattr__(self, "capabilities", FrozenSequence(self.capabilities))
        if not isinstance(self.admitted_task, AdmittedTaskSpec):
            raise ValueError("TaskRequest only accepts an Authority-issued AdmittedTaskSpec")
        task_spec = self.task_spec
        if task_spec.task_id != self.run_id:
            raise ValueError("TaskRequest run_id does not match TaskSpec task_id")
        capability_ceiling = set(task_spec.capability_ceiling)
        if not set(self.capabilities).issubset(capability_ceiling):
            raise ValueError("TaskRequest grants exceed TaskSpec capability_ceiling")

    def to_dict(self) -> dict[str, Any]:
        value = {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "goal": self.goal,
            "target": self.target,
            "constraints": to_json_compatible(self.constraints),
            "capabilities": to_json_compatible(self.capabilities),
            "task_spec": None,
            "task_spec_admission_id": self.admitted_task.admission_id,
        }
        value["task_spec"] = self.task_spec.model_dump(mode="json")
        return value


@dataclass(frozen=True)
class UserTaskSubmission:
    run_id: str
    scenario: str
    goal: str
    target: str
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.goal.strip():
            raise ValueError("user task submission requires run_id and goal")
        object.__setattr__(self, "constraints", freeze_json(self.constraints))
        object.__setattr__(self, "capabilities", FrozenSequence(self.capabilities))


def _approval_digest(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PendingApprovalRequest:
    run_id: str
    approval_request_id: str
    contract_hash: str
    snapshot_id: str
    page_revision: str
    environment_revision: str
    operation_ref: str
    resource_ref: str
    destination_ref: str
    material_parameters: dict[str, Any]
    risk: str
    reversibility: str
    required_capabilities: tuple[str, ...]
    presentation_digest: str
    issued_at_s: float
    expires_at_s: float

    def current(self) -> bool:
        return time() <= self.expires_at_s

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_parameters", freeze_json(self.material_parameters))
        object.__setattr__(self, "required_capabilities", tuple(self.required_capabilities))
        if not all(
            value.strip()
            for value in (
                self.run_id,
                self.approval_request_id,
                self.contract_hash,
                self.snapshot_id,
                self.page_revision,
                self.environment_revision,
                self.operation_ref,
                self.resource_ref,
                self.risk,
                self.reversibility,
                self.presentation_digest,
            )
        ):
            raise ValueError("pending approval requires an exact contract presentation")
        if not self.required_capabilities or any(not item.strip() for item in self.required_capabilities):
            raise ValueError("pending approval requires exact capabilities")

    @classmethod
    def from_runtime_event(
        cls,
        run_id: str,
        payload: dict[str, Any],
        *,
        ttl_s: float = 60.0,
    ) -> "PendingApprovalRequest":
        presentation = payload.get("approval_presentation")
        if not isinstance(presentation, dict):
            raise ValueError("approval event is missing typed presentation")
        issued_at = time()
        presentation_digest = _approval_digest(presentation)
        identity_payload = {
            "run_id": run_id,
            "contract_hash": payload.get("contract_hash"),
            "snapshot_id": payload.get("snapshot_id"),
            "page_revision": payload.get("page_revision"),
            "environment_revision": payload.get("environment_revision"),
            "presentation_digest": presentation_digest,
        }
        return cls(
            run_id=run_id,
            approval_request_id="approval-request:" + _approval_digest(identity_payload).removeprefix("sha256:"),
            contract_hash=str(payload.get("contract_hash") or ""),
            snapshot_id=str(payload.get("snapshot_id") or ""),
            page_revision=str(payload.get("page_revision") or ""),
            environment_revision=str(payload.get("environment_revision") or ""),
            operation_ref=str(presentation.get("operation_ref") or ""),
            resource_ref=str(presentation.get("resource_ref") or ""),
            destination_ref=str(presentation.get("destination_ref") or ""),
            material_parameters=dict(presentation.get("material_parameters") or {}),
            risk=str(presentation.get("runtime_risk") or ""),
            reversibility=str(presentation.get("reversibility") or ""),
            required_capabilities=tuple(str(item) for item in payload.get("required_capabilities") or ()),
            presentation_digest=presentation_digest,
            issued_at_s=issued_at,
            expires_at_s=issued_at + ttl_s,
        )

    @classmethod
    def from_contract(cls, contract: ActionContract, *, ttl_s: float = 60.0) -> "PendingApprovalRequest":
        return cls.from_runtime_event(
            contract.run_id,
            {
                "contract_hash": contract.contract_hash,
                "snapshot_id": contract.snapshot_id,
                "page_revision": contract.page_revision,
                "environment_revision": contract.environment_revision,
                "required_capabilities": tuple(contract.required_capabilities),
                "approval_presentation": asdict(present_approval(contract)),
            },
            ttl_s=ttl_s,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_json_compatible(asdict(self))


@dataclass(frozen=True)
class ApprovalGrant:
    request: PendingApprovalRequest
    approver: str
    issued_at_s: float
    expires_at_s: float

    @property
    def run_id(self) -> str:
        return self.request.run_id

    @property
    def approval_request_id(self) -> str:
        return self.request.approval_request_id

    def current(self) -> bool:
        return bool(self.approver) and time() <= min(self.expires_at_s, self.request.expires_at_s)

    def approve(self, contract: ActionContract) -> ApprovalToken | None:
        """Issue an internal token only for the exact externally approved contract."""

        if not self.current():
            return None
        presentation = present_approval(contract)
        if (
            contract.run_id != self.request.run_id
            or contract.contract_hash != self.request.contract_hash
            or contract.snapshot_id != self.request.snapshot_id
            or contract.page_revision != self.request.page_revision
            or contract.environment_revision != self.request.environment_revision
            or _approval_digest(asdict(presentation)) != self.request.presentation_digest
        ):
            return None
        capability = next(
            (
                item
                for item in contract.required_capabilities
                if item in self.request.required_capabilities
            ),
            "",
        )
        if not capability:
            return None
        return ApprovalToken(
            token_id=f"approval-token:{self.approval_request_id}",
            run_id=contract.run_id,
            contract_hash=contract.contract_hash,
            snapshot_id=contract.snapshot_id,
            page_revision=contract.page_revision,
            environment_revision=contract.environment_revision,
            capability=capability,
            approver=self.approver,
            issued_at_s=self.issued_at_s,
            expires_at_s=self.expires_at_s,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_request_id": self.approval_request_id,
            "approver": self.approver,
            "issued_at_s": self.issued_at_s,
            "expires_at_s": self.expires_at_s,
        }


@dataclass(frozen=True)
class TaskExecution:
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    artifacts: list[str] = field(default_factory=list)
    trace_path: str = ""
    pending_approval: PendingApprovalRequest | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", freeze_json(self.result))
        object.__setattr__(self, "artifacts", FrozenSequence(self.artifacts))
        if self.status == "waiting_approval" and self.pending_approval is None:
            raise ValueError("waiting approval requires an exact PendingApprovalRequest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result": to_json_compatible(self.result),
            "error_code": self.error_code,
            "artifacts": to_json_compatible(self.artifacts),
            "trace_path": self.trace_path,
            "pending_approval": self.pending_approval.to_dict() if self.pending_approval else None,
        }


TaskRunner = Callable[[TaskRequest, ApprovalGrant | None], TaskExecution]
TaskIntake = Callable[[UserTaskSubmission], TaskRequest]


@dataclass
class RunView:
    request: TaskRequest
    status: ServiceRunStatus = ServiceRunStatus.QUEUED
    execution: TaskExecution | None = None
    approval: ApprovalGrant | None = None
    created_at_s: float = field(default_factory=time)
    updated_at_s: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "status": self.status.value,
            "execution": self.execution.to_dict() if self.execution else None,
            "approval": self.approval.to_dict() if self.approval else None,
            "created_at_s": self.created_at_s,
            "updated_at_s": self.updated_at_s,
        }


@dataclass
class TaskRuntimeService:
    runner: TaskRunner
    intake: TaskIntake | None = None
    runs: dict[str, RunView] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def submit(self, request: TaskRequest) -> RunView:
        with self._lock:
            if request.run_id in self.runs:
                raise ValueError(f"run already exists: {request.run_id}")
            view = RunView(request)
            self.runs[request.run_id] = view
            return view

    def submit_user(self, submission: UserTaskSubmission) -> RunView:
        if self.intake is None:
            raise ValueError("user task submission requires a configured canonical intake")
        return self.submit(self.intake(submission))

    def execute(self, run_id: str) -> RunView:
        with self._lock:
            view = self._get(run_id)
            if view.status == ServiceRunStatus.CANCELLED:
                raise ValueError("cancelled run cannot execute")
            if view.approval is not None and not view.approval.current():
                view.approval = None
            view.status = ServiceRunStatus.RUNNING
            view.updated_at_s = time()
        execution = self.runner(view.request, view.approval)
        with self._lock:
            view.execution = execution
            view.status = {
                "done": ServiceRunStatus.SUCCESS,
                "success": ServiceRunStatus.SUCCESS,
                "waiting_approval": ServiceRunStatus.WAITING_APPROVAL,
                "waiting_clarification": ServiceRunStatus.WAITING_CLARIFICATION,
            }.get(execution.status, ServiceRunStatus.FAILED)
            if execution.status == "waiting_approval":
                view.approval = None
            view.updated_at_s = time()
            return view

    def revise_task(self, run_id: str, admitted_task: AdmittedTaskSpec) -> RunView:
        with self._lock:
            if not isinstance(admitted_task, AdmittedTaskSpec):
                raise ValueError("TaskSpec revision requires an Authority-issued AdmittedTaskSpec")
            task_spec = admitted_task.task_spec
            view = self._get(run_id)
            if view.status != ServiceRunStatus.WAITING_CLARIFICATION:
                raise ValueError(f"task cannot be revised in status {view.status.value}")
            previous = view.request.task_spec
            if task_spec.task_id != previous.task_id:
                raise ValueError("TaskSpec revision cannot change task_id")
            if task_spec.revision <= previous.revision:
                raise ValueError("TaskSpec revision must increase")
            if admitted_task.previous_task_identity != previous.identity:
                raise ValueError("TaskSpec revision does not extend the admitted revision lineage")
            view.request = replace(
                view.request,
                target=(task_effect_targets(task_spec) or (view.request.target,))[0],
                capabilities=[
                    capability
                    for capability in view.request.capabilities
                    if capability in set(task_spec.capability_ceiling)
                ],
                admitted_task=admitted_task,
            )
            view.execution = None
            view.approval = None
            view.status = ServiceRunStatus.QUEUED
            view.updated_at_s = time()
            return view

    async def execute_async(self, run_id: str) -> RunView:
        """Run blocking browser I/O off the caller event loop.

        The runner creates and owns its browser session inside the worker
        thread, preserving Playwright thread affinity and serial action
        semantics for the run.
        """

        return await asyncio.to_thread(self.execute, run_id)

    def approve(
        self,
        run_id: str,
        *,
        approval_request_id: str,
        approver: str,
        contract_hash: str = "",
        ttl_s: float = 60.0,
        execute: bool = True,
    ) -> RunView:
        with self._lock:
            view = self._get(run_id)
            if view.status != ServiceRunStatus.WAITING_APPROVAL:
                raise ValueError(f"run cannot be approved in status {view.status.value}")
            pending = view.execution.pending_approval if view.execution is not None else None
            if pending is None or not pending.current():
                raise ValueError("run has no current exact approval request")
            if approval_request_id != pending.approval_request_id:
                raise ValueError("approval request does not match the pending contract")
            if contract_hash and contract_hash != pending.contract_hash:
                raise ValueError("approval contract hash does not match the pending contract")
            issued_at = time()
            view.approval = ApprovalGrant(pending, approver, issued_at, min(issued_at + ttl_s, pending.expires_at_s))
            view.updated_at_s = issued_at
        return self.execute(run_id) if execute else view

    async def approve_async(
        self,
        run_id: str,
        *,
        approval_request_id: str,
        approver: str,
        contract_hash: str = "",
        ttl_s: float = 60.0,
    ) -> RunView:
        return await asyncio.to_thread(
            self.approve,
            run_id,
            approval_request_id=approval_request_id,
            approver=approver,
            contract_hash=contract_hash,
            ttl_s=ttl_s,
        )

    def cancel(self, run_id: str) -> RunView:
        with self._lock:
            view = self._get(run_id)
            if view.status in {ServiceRunStatus.SUCCESS, ServiceRunStatus.FAILED}:
                raise ValueError(f"terminal run cannot be cancelled: {view.status.value}")
            view.status = ServiceRunStatus.CANCELLED
            view.updated_at_s = time()
        cancel_runner = getattr(self.runner, "cancel", None)
        if callable(cancel_runner):
            cancel_runner(run_id)
        return view

    def get_run(self, run_id: str) -> RunView:
        with self._lock:
            return self._get(run_id)

    def get_result(self, run_id: str) -> dict[str, Any]:
        view = self.get_run(run_id)
        return to_json_compatible(view.execution.result) if view.execution else {}

    def get_evidence(self, run_id: str) -> list[str]:
        view = self.get_run(run_id)
        if view.execution is None:
            return []
        return [path for path in view.execution.artifacts if not path.endswith(("events.jsonl", "run.json"))]

    def get_trace(self, run_id: str) -> list[dict[str, Any]]:
        view = self.get_run(run_id)
        path = Path(view.execution.trace_path) if view.execution and view.execution.trace_path else None
        if path is None or not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _get(self, run_id: str) -> RunView:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise KeyError(f"unknown run: {run_id}") from exc


@dataclass(frozen=True)
class TaskToolAdapter:
    """Parent-agent adapter exposing bounded task operations only."""

    service: TaskRuntimeService

    @property
    def tool_names(self) -> tuple[str, ...]:
        return (
            "gui_submit_task",
            "gui_execute_task",
            "gui_get_run",
            "gui_approve_task",
            "gui_cancel_task",
            "gui_get_result",
            "gui_get_evidence",
            "gui_get_trace",
        )

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        if tool not in self.tool_names:
            raise KeyError(f"unknown task-level tool: {tool}")
        if tool == "gui_submit_task":
            return self.service.submit_user(UserTaskSubmission(**arguments)).to_dict()
        if tool == "gui_execute_task":
            return self.service.execute(str(arguments["run_id"])).to_dict()
        if tool == "gui_get_run":
            return self.service.get_run(str(arguments["run_id"])).to_dict()
        if tool == "gui_approve_task":
            return self.service.approve(
                str(arguments["run_id"]),
                approval_request_id=str(arguments["approval_request_id"]),
                approver=str(arguments["approver"]),
                contract_hash=str(arguments.get("contract_hash") or ""),
            ).to_dict()
        if tool == "gui_cancel_task":
            return self.service.cancel(str(arguments["run_id"])).to_dict()
        if tool == "gui_get_result":
            return self.service.get_result(str(arguments["run_id"]))
        if tool == "gui_get_evidence":
            return self.service.get_evidence(str(arguments["run_id"]))
        return self.service.get_trace(str(arguments["run_id"]))

    async def call_async(self, tool: str, arguments: dict[str, Any]) -> Any:
        if tool == "gui_execute_task":
            return (await self.service.execute_async(str(arguments["run_id"]))).to_dict()
        if tool == "gui_approve_task":
            return (
                await self.service.approve_async(
                    str(arguments["run_id"]),
                    approval_request_id=str(arguments["approval_request_id"]),
                    approver=str(arguments["approver"]),
                    contract_hash=str(arguments.get("contract_hash") or ""),
                )
            ).to_dict()
        return self.call(tool, arguments)
