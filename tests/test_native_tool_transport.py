from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.model.providers.port import ModelConfig, ModelMessage, OpenAICompatibleModelPort


def test_openai_compatible_native_tool_transport_requires_one_nonparallel_call() -> None:
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            payload = json.dumps({
                "id": "response:native-tool",
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "provider-call:1",
                            "type": "function",
                            "function": {"name": "act_01", "arguments": "{}"},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = OpenAICompatibleModelPort(
            f"http://127.0.0.1:{server.server_port}",
            "secret",
            "mistral-medium-3-5",
            provider="mistral",
        )
        calls = asyncio.run(port.generate_tool_calls(
            (ModelMessage(role="user", content="choose"),),
            (ToolSpec(
                "act_01",
                "Activate the button.",
                {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            ),),
            ModelConfig(rate_limit_retries=0, transient_retries=0),
            require_one=True,
        ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(calls) == 1
    assert calls[0].name == "act_01"
    assert dict(calls[0].arguments) == {}
    assert requests[0]["tool_choice"] == "any"
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[0]["tools"][0]["function"]["name"] == "act_01"
    assert port.last_call is not None
    assert port.last_call.schema_name == "dynamic_tools.v1"
