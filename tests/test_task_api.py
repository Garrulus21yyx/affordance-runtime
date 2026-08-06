import asyncio
import json
from dataclasses import replace
from pathlib import Path
from time import time

import pytest

from affordance_runtime.approval_contracts import ApprovalPresentation
from affordance_runtime.contracts import ActionContract, RiskLevel
from affordance_runtime.immutable import FrozenDict
from affordance_runtime.integrations import local as local_integration
from affordance_runtime.integrations import task_api as task_api_module
from affordance_runtime.integrations.local import LocalScenarioTaskIntake, LocalScenarioTaskRunner
from affordance_runtime.integrations.task_api import (
    ApprovalGrant,
    PendingApprovalRequest,
    RunView,
    ServiceRunStatus,
    TaskExecution,
    TaskRequest,
    TaskRuntimeService,
    TaskToolAdapter,
    UserTaskSubmission,
)
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task_intake import (
    OperationClass,
    RequestedEffect,
    UserRequest,
)
from affordance_runtime.task_spec_authority import MinimalIntentProposal, TaskSpecAuthority
from affordance_runtime.verification.contracts import SuccessExpression


def _pending(run_id: str, contract_hash: str) -> PendingApprovalRequest:
    return PendingApprovalRequest.from_runtime_event(
        run_id,
        {
            "contract_hash": contract_hash,
            "snapshot_id": f"snapshot:{contract_hash}",
            "page_revision": f"page:{contract_hash}",
            "environment_revision": f"environment:{contract_hash}",
            "required_capabilities": ("report.export",),
            "approval_presentation": {
                "contract_hash": contract_hash,
                "operation_ref": "external.commit@v1",
                "resource_ref": "report:quarterly",
                "destination_ref": "download:report",
                "material_parameters": {"format": "csv"},
                "effect_class": "invoke",
                "externality": "external_system",
                "reversibility": "irreversible",
                "backend": "dom",
                "source_refs": ("source:report",),
                "source_assurance": "authoritative",
                "runtime_risk": "high",
                "uncertainty_codes": (),
            },
        },
    )


def test_task_api_rebuilt_contract_requires_a_new_exact_approval(tmp_path: Path) -> None:
    trace = tmp_path / "events.jsonl"
    evidence = tmp_path / "receipt.json"
    trace.write_text(json.dumps({"event_type": "TaskCompleted"}) + "\n")
    evidence.write_text("{}")

    def runner(request: TaskRequest, approval: ApprovalGrant | None) -> TaskExecution:
        if request.scenario == "export" and approval is None:
            return TaskExecution("waiting_approval", pending_approval=_pending(request.run_id, "contract:H1"))
        if approval is not None and approval.request.contract_hash == "contract:H1":
            return TaskExecution("waiting_approval", pending_approval=_pending(request.run_id, "contract:H2"))
        return TaskExecution(
            "done",
            {"ok": True},
            artifacts=[str(trace), str(evidence)],
            trace_path=str(trace),
        )

    service = TaskRuntimeService(runner, intake=LocalScenarioTaskIntake())
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
    first_pending = adapter.call("gui_get_run", {"run_id": "run-1"})["execution"]["pending_approval"]
    rebuilt = adapter.call(
        "gui_approve_task",
        {
            "run_id": "run-1",
            "approval_request_id": first_pending["approval_request_id"],
            "contract_hash": first_pending["contract_hash"],
            "approver": "user-1",
        },
    )

    assert rebuilt["status"] == "waiting_approval"
    second_pending = rebuilt["execution"]["pending_approval"]
    assert second_pending["contract_hash"] == "contract:H2"
    assert second_pending["approval_request_id"] != first_pending["approval_request_id"]
    approved = adapter.call(
        "gui_approve_task",
        {
            "run_id": "run-1",
            "approval_request_id": second_pending["approval_request_id"],
            "approver": "user-1",
        },
    )
    assert approved["status"] == "success"
    assert adapter.call("gui_get_result", {"run_id": "run-1"}) == {"ok": True}
    assert adapter.call("gui_get_evidence", {"run_id": "run-1"}) == [str(evidence)]
    assert adapter.call("gui_get_trace", {"run_id": "run-1"}) == [{"event_type": "TaskCompleted"}]
    assert all(name not in adapter.tool_names for name in ("gui_click", "gui_type", "gui_observe"))


def test_local_task_api_resumes_the_exact_paused_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = ActionContract(
        id="contract:H1",
        run_id="exact-export",
        intent="export report",
        affordance_id="export-button",
        action="click",
        backend="dom",
        environment_revision="environment:H1",
        snapshot_id="snapshot:H1",
        page_revision="page:H1",
        locator={"selector": "#export"},
        required_capabilities=["report.export"],
        risk=RiskLevel.HIGH,
    )
    presentation = ApprovalPresentation(
        contract.contract_hash,
        "external.commit@v1",
        "report:quarterly",
        "download:report",
        FrozenDict({"format": "csv"}),
        "invoke",
        "external_system",
        "irreversible",
        "dom",
        ("source:report",),
        "authoritative",
        "high",
        (),
    )
    monkeypatch.setattr(task_api_module, "present_approval", lambda value: presentation)

    def paused_run_scenario(*args, approval_provider_override=None, **kwargs):
        del args, kwargs
        token = approval_provider_override.approve(contract)
        return {
            "status": "done" if token is not None else "waiting_approval",
            "result": {"contract_hash": contract.contract_hash} if token is not None else {},
            "error_code": None,
            "artifacts": [],
            "pending_approval": None,
        }

    monkeypatch.setattr(local_integration, "run_scenario", paused_run_scenario)
    service = TaskRuntimeService(
        LocalScenarioTaskRunner(tmp_path / "artifacts"),
        intake=LocalScenarioTaskIntake(),
    )
    service.submit_user(
        UserTaskSubmission(
            "exact-export",
            "export",
            "Export the report",
            "http://fixture/reports",
            capabilities=["report.export"],
        )
    )
    waiting = service.execute("exact-export")
    assert waiting.execution is not None
    pending = waiting.execution.pending_approval
    assert pending is not None
    issued_at = time()
    stale_grant = ApprovalGrant(pending, "user-1", issued_at, issued_at + 30)
    rebuilt = replace(
        contract,
        id="contract:H2",
        snapshot_id="snapshot:H2",
        contract_hash="",
    )
    assert stale_grant.approve(rebuilt) is None

    approved = service.approve(
        "exact-export",
        approval_request_id=pending.approval_request_id,
        contract_hash=pending.contract_hash,
        approver="user-1",
    )

    assert approved.status == ServiceRunStatus.SUCCESS
    assert approved.approval is not None
    assert approved.approval.request.contract_hash == pending.contract_hash


def test_task_request_payloads_are_immutable_from_source_collections() -> None:
    constraints = {"require_approval_for": ["settings.write"]}
    capabilities = ["settings.write.reversible"]

    request = LocalScenarioTaskIntake()(
        UserTaskSubmission(
            run_id="run-immutable",
            scenario="settings",
            goal="Update settings",
            target="settings",
            constraints=constraints,
            capabilities=capabilities,
        )
    )
    constraints["require_approval_for"].append("admin.override")
    capabilities.append("admin.override")

    assert request.constraints["require_approval_for"] == ["settings.write"]
    assert request.capabilities == ["settings.write.reversible"]
    with pytest.raises(TypeError):
        request.constraints["require_approval_for"][0] = "admin.override"
    with pytest.raises(AttributeError):
        request.capabilities.append("admin.override")
    assert request.to_dict()["constraints"] == {"require_approval_for": ["settings.write"]}
    assert request.to_dict()["capabilities"] == ["settings.write.reversible"]


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
    request = LocalScenarioTaskIntake()(UserTaskSubmission("run-immutable", "settings", "Update", "settings"))
    assert RunView(request, execution=execution).to_dict()["execution"] == {
        "status": "done",
        "result": {"items": ["a"]},
        "error_code": None,
        "artifacts": ["trace.jsonl"],
        "trace_path": "",
        "pending_approval": None,
    }


def test_task_api_cancel_and_rejects_approval_without_pending_contract() -> None:
    intake = LocalScenarioTaskIntake()
    service = TaskRuntimeService(lambda request, approval: TaskExecution("done"), intake=intake)
    service.submit_user(UserTaskSubmission("run-2", "pricing", "extract", "http://fixture"))

    try:
        service.approve("run-2", approval_request_id="approval-request:missing", approver="user")
    except ValueError as exc:
        assert "cannot be approved" in str(exc)
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
    service = TaskRuntimeService(
        lambda request, approval: TaskExecution("done", {"run_id": request.run_id}),
        intake=LocalScenarioTaskIntake(),
    )
    adapter = TaskToolAdapter(service)
    adapter.call(
        "gui_submit_task",
        {"run_id": "async-run", "scenario": "pricing", "goal": "extract", "target": "http://fixture"},
    )

    value = asyncio.run(adapter.call_async("gui_execute_task", {"run_id": "async-run"}))

    assert value["status"] == "success"


def _admitted_task(revision: int, *, objective: str = "Update settings", previous=None):
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
        previous_admitted_task=previous,
    )
    assert result.task_spec is not None
    return result


def test_task_api_accepts_taskspec_and_requires_monotonic_clarification_revision() -> None:
    service = TaskRuntimeService(
        lambda request, approval: TaskExecution(
            "waiting_clarification" if request.task_spec and request.task_spec.revision == 1 else "done"
        )
    )
    initial = _admitted_task(1)
    assert initial.admitted_task is not None
    submitted = service.submit(
        TaskRequest(
            run_id="clarify-run",
            scenario="settings",
            target="settings",
            capabilities=["settings.write"],
            admitted_task=initial.admitted_task,
        )
    )
    assert submitted.request.task_spec is not None
    assert submitted.request.task_spec.revision == 1
    assert service.execute("clarify-run").status == ServiceRunStatus.WAITING_CLARIFICATION

    with pytest.raises(ValueError, match="must increase"):
        service.revise_task("clarify-run", initial.admitted_task)
    revised_admission = _admitted_task(
        2,
        objective="Update the personal settings profile",
        previous=initial.admitted_task,
    )
    assert revised_admission.admitted_task is not None
    revised = service.revise_task("clarify-run", revised_admission.admitted_task)
    assert revised.status == ServiceRunStatus.QUEUED
    assert revised.request.task_spec is not None
    assert revised.request.task_spec.revision == 2
    assert service.execute("clarify-run").status == ServiceRunStatus.SUCCESS


def test_taskspec_requested_capability_is_not_implicitly_granted() -> None:
    admission = _admitted_task(1)
    request = TaskRequest(
        run_id="clarify-run",
        scenario="settings",
        target="settings",
        admitted_task=admission.admitted_task,
    )

    assert request.capabilities == []

    with pytest.raises(TypeError):
        TaskRequest(
            run_id="clarify-run",
            scenario="settings",
            target="settings",
            task_spec=admission.task_spec,  # type: ignore[call-arg]
        )

    with pytest.raises(ValueError, match="grants exceed"):
        TaskRequest(
            run_id="clarify-run",
            scenario="settings",
            target="settings",
            capabilities=["admin.superuser"],
            admitted_task=admission.admitted_task,
        )


def test_json_tool_adapter_cannot_inject_a_canonical_taskspec() -> None:
    admission = _admitted_task(1)
    adapter = TaskToolAdapter(
        TaskRuntimeService(
            lambda request, approval: TaskExecution("done"),
            intake=LocalScenarioTaskIntake(),
        )
    )

    with pytest.raises(TypeError):
        TaskRequest(run_id="raw", scenario="pricing", target="pricing")  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        adapter.call(
            "gui_submit_task",
            {
                "run_id": "clarify-run",
                "scenario": "settings",
                "goal": "Update settings",
                "target": "settings",
                "task_spec": admission.task_spec.model_dump(mode="json"),
            },
        )
