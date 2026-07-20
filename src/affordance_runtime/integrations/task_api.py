"""Stable task-level API for parent agents and tool adapters."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Callable


class ServiceRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskRequest:
    run_id: str
    scenario: str
    goal: str
    target: str
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ApprovalGrant:
    run_id: str
    capability: str
    approver: str
    issued_at_s: float
    expires_at_s: float

    def current(self) -> bool:
        return bool(self.approver) and time() <= self.expires_at_s


@dataclass(frozen=True)
class TaskExecution:
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    artifacts: list[str] = field(default_factory=list)
    trace_path: str = ""
    required_capability: str = ""


TaskRunner = Callable[[TaskRequest, ApprovalGrant | None], TaskExecution]


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
            "request": asdict(self.request),
            "status": self.status.value,
            "execution": asdict(self.execution) if self.execution else None,
            "approval": asdict(self.approval) if self.approval else None,
            "created_at_s": self.created_at_s,
            "updated_at_s": self.updated_at_s,
        }


@dataclass
class TaskRuntimeService:
    runner: TaskRunner
    runs: dict[str, RunView] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def submit(self, request: TaskRequest) -> RunView:
        with self._lock:
            if request.run_id in self.runs:
                raise ValueError(f"run already exists: {request.run_id}")
            view = RunView(request)
            self.runs[request.run_id] = view
            return view

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
            }.get(execution.status, ServiceRunStatus.FAILED)
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
        capability: str,
        approver: str,
        ttl_s: float = 60.0,
        execute: bool = True,
    ) -> RunView:
        with self._lock:
            view = self._get(run_id)
            if view.status not in {ServiceRunStatus.QUEUED, ServiceRunStatus.WAITING_APPROVAL}:
                raise ValueError(f"run cannot be approved in status {view.status.value}")
            if capability not in view.request.capabilities:
                raise ValueError(f"capability is outside task scope: {capability}")
            issued_at = time()
            view.approval = ApprovalGrant(run_id, capability, approver, issued_at, issued_at + ttl_s)
            view.updated_at_s = issued_at
        return self.execute(run_id) if execute else view

    async def approve_async(
        self,
        run_id: str,
        *,
        capability: str,
        approver: str,
        ttl_s: float = 60.0,
    ) -> RunView:
        return await asyncio.to_thread(
            self.approve,
            run_id,
            capability=capability,
            approver=approver,
            ttl_s=ttl_s,
        )

    def cancel(self, run_id: str) -> RunView:
        with self._lock:
            view = self._get(run_id)
            if view.status in {ServiceRunStatus.SUCCESS, ServiceRunStatus.FAILED}:
                raise ValueError(f"terminal run cannot be cancelled: {view.status.value}")
            view.status = ServiceRunStatus.CANCELLED
            view.updated_at_s = time()
            return view

    def get_run(self, run_id: str) -> RunView:
        with self._lock:
            return self._get(run_id)

    def get_result(self, run_id: str) -> dict[str, Any]:
        view = self.get_run(run_id)
        return dict(view.execution.result) if view.execution else {}

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
            return self.service.submit(TaskRequest(**arguments)).to_dict()
        if tool == "gui_execute_task":
            return self.service.execute(str(arguments["run_id"])).to_dict()
        if tool == "gui_get_run":
            return self.service.get_run(str(arguments["run_id"])).to_dict()
        if tool == "gui_approve_task":
            return self.service.approve(
                str(arguments["run_id"]),
                capability=str(arguments["capability"]),
                approver=str(arguments["approver"]),
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
                    capability=str(arguments["capability"]),
                    approver=str(arguments["approver"]),
                )
            ).to_dict()
        return self.call(tool, arguments)
