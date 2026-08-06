import asyncio
import json
from pathlib import Path

import pytest

from affordance_runtime.integrations.task_api import (
    ApprovalGrant,
    RunView,
    ServiceRunStatus,
    TaskExecution,
    TaskRequest,
    TaskRuntimeService,
    TaskToolAdapter,
)
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task_intake import (
    OperationClass,
    RequestedEffect,
    UserRequest,
)
from affordance_runtime.task_spec_authority import MinimalIntentProposal, TaskSpecAuthority
from affordance_runtime.verification.contracts import SuccessExpression


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


def test_task_request_payloads_are_immutable_from_source_collections() -> None:
    constraints = {"require_approval_for": ["settings.write"]}
    capabilities = ["settings.write"]

    request = TaskRequest(
        run_id="run-immutable",
        scenario="settings",
        goal="Update settings",
        target="settings",
        constraints=constraints,
        capabilities=capabilities,
    )
    constraints["require_approval_for"].append("admin.override")
    capabilities.append("admin.override")

    assert request.constraints["require_approval_for"] == ["settings.write"]
    assert request.capabilities == ["settings.write"]
    with pytest.raises(TypeError):
        request.constraints["require_approval_for"][0] = "admin.override"
    with pytest.raises(AttributeError):
        request.capabilities.append("admin.override")
    assert request.to_dict()["constraints"] == {"require_approval_for": ["settings.write"]}
    assert request.to_dict()["capabilities"] == ["settings.write"]


def test_task_execution_payloads_are_immutable_from_source_collections() -> None:
    result = {"items": ["a"]}
    artifacts = ["trace.jsonl"]

    execution = TaskExecution("done", result=result, artifacts=artifacts)
    result["items"].append("polluted")
    artifacts.append("receipt.json")

    assert execution.result["items"] == ["a"]
    assert execution.artifacts == ["trace.jsonl"]
    with pytest.raises(TypeError):
        execution.result["items"][0] = "polluted"
    with pytest.raises(AttributeError):
        execution.artifacts.append("receipt.json")
    assert RunView(TaskRequest("run-immutable", "settings", "Update", "settings"), execution=execution).to_dict()[
        "execution"
    ] == {
        "status": "done",
        "result": {"items": ["a"]},
        "error_code": None,
        "artifacts": ["trace.jsonl"],
        "trace_path": "",
        "required_capability": "",
    }


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


def _admitted_task(revision: int, *, objective: str = "Update settings"):
    request = UserRequest(request_id="request-clarify", raw_text=objective)
    envelope = SourceEnvelopeBuilder().build(request)
    result = TaskSpecAuthority().admit(
        request,
        envelope,
        MinimalIntentProposal(
            objective=objective,
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="settings",
                    capability="settings.write",
                    source_ref=envelope.whole_request_anchor.anchor_id,
                ),
            ),
            success=SuccessExpression(
                expression_id="success:settings",
                operator="criterion",
                criterion_id="criterion:settings",
                requirement_refs=("requirement:effect:1",),
            ),
        ),
        revision=revision,
        task_id="clarify-run",
    )
    assert result.task_spec is not None
    return result


def test_task_api_accepts_taskspec_and_requires_monotonic_clarification_revision() -> None:
    service = TaskRuntimeService(
        lambda request, approval: TaskExecution(
            "waiting_clarification" if request.task_spec and request.task_spec.revision == 1 else "done"
        )
    )
    adapter = TaskToolAdapter(service)
    initial = _admitted_task(1)
    submitted = adapter.call(
        "gui_submit_task",
        {
            "run_id": "clarify-run",
            "scenario": "settings",
            "goal": "Update settings",
            "target": "settings",
            "capabilities": ["settings.write"],
            "task_spec": initial.task_spec.model_dump(mode="json"),
            "task_spec_admission_receipt": initial.admission_receipt,
        },
    )
    assert submitted["request"]["task_spec"]["revision"] == 1
    assert adapter.call("gui_execute_task", {"run_id": "clarify-run"})["status"] == "waiting_clarification"

    with pytest.raises(ValueError, match="must increase"):
        adapter.call(
            "gui_revise_task",
            {
                "run_id": "clarify-run",
                "task_spec": initial.task_spec.model_dump(mode="json"),
                "task_spec_admission_receipt": initial.admission_receipt,
            },
        )
    revised_admission = _admitted_task(2, objective="Update the personal settings profile")
    revised = adapter.call(
        "gui_revise_task",
        {
            "run_id": "clarify-run",
            "task_spec": revised_admission.task_spec.model_dump(mode="json"),
            "task_spec_admission_receipt": revised_admission.admission_receipt,
        },
    )
    assert revised["status"] == "queued"
    assert revised["request"]["task_spec"]["revision"] == 2
    assert adapter.call("gui_execute_task", {"run_id": "clarify-run"})["status"] == "success"


def test_taskspec_requested_capability_is_not_implicitly_granted() -> None:
    admission = _admitted_task(1)
    request = TaskRequest(
        run_id="clarify-run",
        scenario="settings",
        goal="Update settings",
        target="settings",
        task_spec=admission.task_spec,
        task_spec_admission_receipt=admission.admission_receipt,
    )

    assert request.capabilities == []

    with pytest.raises(ValueError, match="TaskSpecAuthority admission receipt"):
        TaskRequest(
            run_id="clarify-run",
            scenario="settings",
            goal="Update settings",
            target="settings",
            task_spec=admission.task_spec.model_dump(mode="json"),
            task_spec_admission_receipt=admission.task_spec.identity,
        )

    with pytest.raises(ValueError, match="grants exceed"):
        TaskRequest(
            run_id="clarify-run",
            scenario="settings",
            goal="Update settings",
            target="settings",
            capabilities=["admin.superuser"],
            task_spec=admission.task_spec,
            task_spec_admission_receipt=admission.admission_receipt,
        )
