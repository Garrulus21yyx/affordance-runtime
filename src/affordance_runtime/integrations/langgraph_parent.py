"""Real LangGraph parent that uses only the external task-level protocol."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from typing import Any, TypedDict

from affordance_runtime.integrations.external_protocol import PROTOCOL_VERSION


class ParentState(TypedDict, total=False):
    started: bool
    base_url: str
    tool_names: list[str]
    pricing_status: str
    pricing_result: dict[str, Any]
    pricing_evidence: list[str]
    pricing_trace: list[dict[str, Any]]
    export_preapproval_status: str
    export_status: str
    export_result: dict[str, Any]
    export_evidence: list[str]
    export_trace: list[dict[str, Any]]


class ExternalTaskClient:
    def __init__(self, artifact_root: Path) -> None:
        self._next_id = 1
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "affordance_runtime.integrations.external_protocol",
                "--artifacts",
                str(artifact_root),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    @property
    def pid(self) -> int:
        return self.process.pid

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("external task process streams are unavailable")
        request_id = self._next_id
        self._next_id += 1
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        self.process.stdin.write(json.dumps(request, sort_keys=True) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            detail = ""
            if self.process.poll() is not None and self.process.stderr is not None:
                detail = self.process.stderr.read().strip()
            raise RuntimeError(f"external task process closed without a response: {detail}")
        response = json.loads(line)
        if response.get("id") != request_id:
            raise RuntimeError(f"protocol response id mismatch: expected {request_id}, got {response.get('id')}")
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"external protocol error {error.get('type')}: {error.get('message')}")
        return response.get("result")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.request("shutdown")
            finally:
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=5)


def run_langgraph_parent(output_dir: Path) -> dict[str, Any]:
    """Complete pricing and approval export through a compiled LangGraph."""

    graph_module = import_module("langgraph.graph")
    END = graph_module.END
    START = graph_module.START
    StateGraph = graph_module.StateGraph

    output_dir.mkdir(parents=True, exist_ok=True)
    client = ExternalTaskClient(output_dir / "runtime-artifacts")

    def discover(state: ParentState) -> ParentState:
        del state
        info = client.request("runtime/info")
        tools = client.request("tools/list")
        names = [str(tool["name"]) for tool in tools]
        primitive = {"gui_click", "gui_type", "gui_observe"} & set(names)
        if primitive:
            raise RuntimeError(f"external runtime exposed primitive GUI bypasses: {sorted(primitive)}")
        if info["protocol_version"] != PROTOCOL_VERSION:
            raise RuntimeError(f"unexpected protocol version: {info['protocol_version']}")
        return {"base_url": str(info["base_url"]), "tool_names": names}

    def submit_pricing(state: ParentState) -> ParentState:
        client.call_tool(
            "gui_submit_task",
            {
                "run_id": "langgraph-pricing",
                "scenario": "pricing",
                "goal": "extract pricing with evidence",
                "target": f"{state['base_url']}/pricing",
            },
        )
        return {}

    def execute_pricing(state: ParentState) -> ParentState:
        del state
        view = client.call_tool("gui_execute_task", {"run_id": "langgraph-pricing"})
        if view["status"] != "success":
            raise RuntimeError(f"pricing task failed through external runtime: {view['status']}")
        return {"pricing_status": str(view["status"])}

    def collect_pricing(state: ParentState) -> ParentState:
        del state
        return {
            "pricing_result": client.call_tool("gui_get_result", {"run_id": "langgraph-pricing"}),
            "pricing_evidence": client.call_tool("gui_get_evidence", {"run_id": "langgraph-pricing"}),
            "pricing_trace": client.call_tool("gui_get_trace", {"run_id": "langgraph-pricing"}),
        }

    def submit_export(state: ParentState) -> ParentState:
        client.call_tool(
            "gui_submit_task",
            {
                "run_id": "langgraph-export",
                "scenario": "export",
                "goal": "export the report after explicit approval",
                "target": f"{state['base_url']}/reports",
                "constraints": {"approval_required": True},
                "capabilities": ["report.export"],
            },
        )
        return {}

    def execute_export(state: ParentState) -> ParentState:
        del state
        view = client.call_tool("gui_execute_task", {"run_id": "langgraph-export"})
        if view["status"] != "waiting_approval":
            raise RuntimeError(f"export did not stop for approval: {view['status']}")
        return {"export_preapproval_status": str(view["status"])}

    def approve_export(state: ParentState) -> ParentState:
        pending = client.call_tool("gui_get_run", {"run_id": "langgraph-export"})["execution"][
            "pending_approval"
        ]
        view = client.call_tool(
            "gui_approve_task",
            {
                "run_id": "langgraph-export",
                "approval_request_id": pending["approval_request_id"],
                "contract_hash": pending["contract_hash"],
                "approver": "langgraph-parent-user",
            },
        )
        if view["status"] not in {"success", "waiting_approval"}:
            raise RuntimeError(f"approved export failed safely: {view['status']}")
        return {"export_status": str(view["status"])}

    def collect_export(state: ParentState) -> ParentState:
        del state
        return {
            "export_result": client.call_tool("gui_get_result", {"run_id": "langgraph-export"}),
            "export_evidence": client.call_tool("gui_get_evidence", {"run_id": "langgraph-export"}),
            "export_trace": client.call_tool("gui_get_trace", {"run_id": "langgraph-export"}),
        }

    builder = StateGraph(ParentState)
    builder.add_node("discover_task_tools", discover)
    builder.add_node("submit_pricing", submit_pricing)
    builder.add_node("execute_pricing", execute_pricing)
    builder.add_node("collect_pricing", collect_pricing)
    builder.add_node("submit_export", submit_export)
    builder.add_node("execute_export", execute_export)
    builder.add_node("approve_export", approve_export)
    builder.add_node("collect_export", collect_export)
    builder.add_edge(START, "discover_task_tools")
    builder.add_edge("discover_task_tools", "submit_pricing")
    builder.add_edge("submit_pricing", "execute_pricing")
    builder.add_edge("execute_pricing", "collect_pricing")
    builder.add_edge("collect_pricing", "submit_export")
    builder.add_edge("submit_export", "execute_export")
    builder.add_edge("execute_export", "approve_export")
    builder.add_edge("approve_export", "collect_export")
    builder.add_edge("collect_export", END)
    graph = builder.compile()
    try:
        state = graph.invoke({"started": True})
        report: dict[str, Any] = {
            "framework": "langgraph",
            "framework_version": version("langgraph"),
            "protocol_version": PROTOCOL_VERSION,
            "external_server_pid": client.pid,
            "tool_names": state["tool_names"],
            "primitive_gui_tools_exposed": False,
            "runtime_authoritative": True,
            "pricing": {
                "status": state["pricing_status"],
                "result": state["pricing_result"],
                "evidence_count": len(state["pricing_evidence"]),
                "trace_event_count": len(state["pricing_trace"]),
            },
            "export": {
                "preapproval_status": state["export_preapproval_status"],
                "status": state["export_status"],
                "result": state["export_result"],
                "evidence_count": len(state["export_evidence"]),
                "trace_event_count": len(state["export_trace"]),
            },
        }
        if not report["pricing"]["result"] or not report["export"]["evidence_count"]:
            raise RuntimeError("external parent did not retrieve pricing result and export evidence")
        (output_dir / "langgraph-parent-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        markdown = [
            "# LangGraph External Parent Report",
            "",
            f"- Framework: `langgraph {report['framework_version']}`",
            f"- Protocol: `{PROTOCOL_VERSION}`",
            f"- External runtime PID: `{client.pid}`",
            f"- Task tools only: `{', '.join(state['tool_names'])}`",
            f"- Pricing status: `{state['pricing_status']}`",
            f"- Export before approval: `{state['export_preapproval_status']}`",
            f"- Export after approval: `{state['export_status']}`",
            f"- Pricing trace events: `{len(state['pricing_trace'])}`",
            f"- Export trace events: `{len(state['export_trace'])}`",
            "",
        ]
        (output_dir / "langgraph-parent-report.md").write_text("\n".join(markdown), encoding="utf-8")
        return report
    finally:
        client.close()
