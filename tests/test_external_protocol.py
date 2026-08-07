import io
import json

from affordance_runtime.integrations.external_protocol import PROTOCOL_VERSION, ExternalTaskProtocol, serve_stream
from affordance_runtime.integrations.local import LocalScenarioTaskIntake
from affordance_runtime.integrations.task_api import TaskExecution, TaskRuntimeService, TaskToolAdapter


def test_external_json_rpc_exposes_only_task_level_operations() -> None:
    service = TaskRuntimeService(
        lambda request, approval: TaskExecution("done", {"run_id": request.run_id}),
        intake=LocalScenarioTaskIntake(),
    )
    protocol = ExternalTaskProtocol(TaskToolAdapter(service), "http://fixture")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "runtime/info", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "gui_submit_task",
                "arguments": {
                    "run_id": "external-run",
                    "scenario": "pricing",
                    "goal": "extract",
                    "target": "http://fixture/pricing",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "gui_execute_task", "arguments": {"run_id": "external-run"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "gui_click", "arguments": {"selector": "#unsafe"}},
        },
        {"jsonrpc": "2.0", "id": 6, "method": "shutdown", "params": {}},
    ]
    input_stream = io.StringIO("".join(json.dumps(request) + "\n" for request in requests))
    output_stream = io.StringIO()

    serve_stream(protocol, input_stream, output_stream)

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert responses[0]["result"]["protocol_version"] == PROTOCOL_VERSION
    names = {tool["name"] for tool in responses[1]["result"]}
    assert names == set(TaskToolAdapter(service).tool_names)
    assert not {"gui_click", "gui_type", "gui_observe"} & names
    assert "gui_revise_task" not in names
    submit_schema = next(item["input_schema"] for item in responses[1]["result"] if item["name"] == "gui_submit_task")
    assert "task_spec" not in submit_schema["properties"]
    approval_schema = next(
        item["input_schema"] for item in responses[1]["result"] if item["name"] == "gui_approve_task"
    )
    assert approval_schema["required"] == ["run_id", "approval_request_id", "approver"]
    assert "capability" not in approval_schema["properties"]
    assert responses[2]["result"]["request"]["task_spec"]["objective"] == "extract"
    assert responses[3]["result"]["status"] == "success"
    assert responses[4]["error"]["type"] == "KeyError"
    assert responses[5]["result"] == {"status": "shutting_down"}
