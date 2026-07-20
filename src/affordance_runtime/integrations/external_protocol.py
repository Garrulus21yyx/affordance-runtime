"""Newline-delimited JSON-RPC task protocol for external parent processes."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from affordance_runtime.fixtures import create_fixture_server
from affordance_runtime.integrations.local import LocalScenarioTaskRunner
from affordance_runtime.integrations.task_api import TaskRuntimeService, TaskToolAdapter

PROTOCOL_VERSION = "affordance-task-rpc/1.0"

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "gui_submit_task": {
        "required": ["run_id", "scenario", "goal", "target"],
        "properties": {
            "run_id": {"type": "string"},
            "scenario": {"enum": ["pricing", "settings", "export"]},
            "goal": {"type": "string"},
            "target": {"type": "string"},
            "constraints": {"type": "object"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
        },
    },
    "gui_execute_task": {"required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
    "gui_get_run": {"required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
    "gui_approve_task": {
        "required": ["run_id", "capability", "approver"],
        "properties": {
            "run_id": {"type": "string"},
            "capability": {"type": "string"},
            "approver": {"type": "string"},
        },
    },
    "gui_cancel_task": {"required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
    "gui_get_result": {"required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
    "gui_get_evidence": {"required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
    "gui_get_trace": {"required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
}


@dataclass(frozen=True)
class ExternalTaskProtocol:
    adapter: TaskToolAdapter
    base_url: str

    def dispatch(self, method: str, params: dict[str, Any]) -> tuple[Any, bool]:
        if method == "runtime/info":
            return {
                "protocol_version": PROTOCOL_VERSION,
                "base_url": self.base_url,
                "execution_authority": "affordance_runtime",
            }, False
        if method == "tools/list":
            return [
                {"name": name, "input_schema": {"type": "object", **TOOL_SCHEMAS[name]}}
                for name in self.adapter.tool_names
            ], False
        if method == "tools/call":
            name = str(params.get("name", ""))
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            return self.adapter.call(name, arguments), False
        if method == "shutdown":
            return {"status": "shutting_down"}, True
        raise KeyError(f"unknown protocol method: {method}")


def serve_stream(protocol: ExternalTaskProtocol, input_stream: TextIO, output_stream: TextIO) -> None:
    for line in input_stream:
        if not line.strip():
            continue
        request_id: Any = None
        should_stop = False
        try:
            request = json.loads(line)
            request_id = request.get("id")
            if request.get("jsonrpc") != "2.0":
                raise ValueError("jsonrpc must be 2.0")
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            result, should_stop = protocol.dispatch(str(request.get("method", "")), params)
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        output_stream.write(json.dumps(response, sort_keys=True, default=str) + "\n")
        output_stream.flush()
        if should_stop:
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args(argv)
    fixture = create_fixture_server(port=0)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{fixture.server_name}:{fixture.server_port}"
        service = TaskRuntimeService(LocalScenarioTaskRunner(args.artifacts))
        serve_stream(ExternalTaskProtocol(TaskToolAdapter(service), base_url), sys.stdin, sys.stdout)
        return 0
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
