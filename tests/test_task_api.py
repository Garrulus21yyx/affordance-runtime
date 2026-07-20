import asyncio
import json
from pathlib import Path

from affordance_runtime.integrations.task_api import (
    ApprovalGrant,
    ServiceRunStatus,
    TaskExecution,
    TaskRequest,
    TaskRuntimeService,
    TaskToolAdapter,
)


def test_task_api_approval_result_evidence_and_trace_flow(tmp_path: Path) -> None:
    trace = tmp_path / "events.jsonl"
    evidence = tmp_path / "receipt.json"
    trace.write_text(json.dumps({"event_type": "TaskCompleted"}) + "\n")
    evidence.write_text("{}")

    def runner(request: TaskRequest, approval: ApprovalGrant | None) -> TaskExecution:
        if request.scenario == "export" and approval is None:
            return TaskExecution("waiting_approval", required_capability="report.export")
        return TaskExecution(
            "done",
            {"ok": True},
            artifacts=[str(trace), str(evidence)],
            trace_path=str(trace),
        )

    service = TaskRuntimeService(runner)
    adapter = TaskToolAdapter(service)
    adapter.call(
        "gui_submit_task",
        {
            "run_id": "run-1",
            "scenario": "export",
            "goal": "export report",
            "target": "http://fixture/reports",
            "capabilities": ["report.export"],
        },
    )

    assert adapter.call("gui_execute_task", {"run_id": "run-1"})["status"] == "waiting_approval"
    approved = adapter.call(
        "gui_approve_task",
        {"run_id": "run-1", "capability": "report.export", "approver": "user-1"},
    )

    assert approved["status"] == "success"
    assert adapter.call("gui_get_result", {"run_id": "run-1"}) == {"ok": True}
    assert adapter.call("gui_get_evidence", {"run_id": "run-1"}) == [str(evidence)]
    assert adapter.call("gui_get_trace", {"run_id": "run-1"}) == [{"event_type": "TaskCompleted"}]
    assert all(name not in adapter.tool_names for name in ("gui_click", "gui_type", "gui_observe"))


def test_task_api_cancel_and_capability_scope() -> None:
    service = TaskRuntimeService(lambda request, approval: TaskExecution("done"))
    service.submit(TaskRequest("run-2", "pricing", "extract", "http://fixture", capabilities=[]))

    try:
        service.approve("run-2", capability="report.export", approver="user")
    except ValueError as exc:
        assert "outside task scope" in str(exc)
    else:
        raise AssertionError("out-of-scope approval should fail")

    assert service.cancel("run-2").status == ServiceRunStatus.CANCELLED
    try:
        service.execute("run-2")
    except ValueError as exc:
        assert "cancelled" in str(exc)
    else:
        raise AssertionError("cancelled run should not execute")


def test_task_adapter_async_execution_keeps_event_loop_interface() -> None:
    service = TaskRuntimeService(lambda request, approval: TaskExecution("done", {"run_id": request.run_id}))
    adapter = TaskToolAdapter(service)
    adapter.call(
        "gui_submit_task",
        {"run_id": "async-run", "scenario": "pricing", "goal": "extract", "target": "http://fixture"},
    )

    value = asyncio.run(adapter.call_async("gui_execute_task", {"run_id": "async-run"}))

    assert value["status"] == "success"
