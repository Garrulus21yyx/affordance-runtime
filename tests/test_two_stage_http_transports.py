import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.benchmarks.model_conformance.two_stage.cases import build_recurrent_cases
from affordance_runtime.benchmarks.model_conformance.two_stage.contracts import TwoStageRunMode
from affordance_runtime.benchmarks.model_conformance.two_stage.runner import run_two_stage_matrix
from affordance_runtime.model_port import OllamaModelPort, OpenAICompatibleModelPort


def _response(request: dict, openai: bool) -> dict:
    schema = request["response_format"]["json_schema"]["schema"] if openai else request["format"]
    messages = request["messages"]
    context = json.loads(messages[1]["content"])["agent_context"]
    if set(schema["properties"]) == {"context_id", "decision_type"}:
        content = {"context_id": context["context_id"], "decision_type": "select_action"}
    else:
        option = context["actions"]["options"][0]
        destinations = option["destinations"]["items"]
        content = {
            "type": "select_action", "context_id": context["context_id"],
            "action_id": option["action_id"], "parameters": {},
            "destination_id": destinations[0]["destination_id"] if destinations else "",
        }
    if openai:
        return {"choices": [{"message": {"content": json.dumps(content)}}], "usage": {}}
    return {"message": {"content": json.dumps(content)}, "prompt_eval_count": 1, "eval_count": 1}


def _serve(openai: bool):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            requests.append(request)
            encoded = json.dumps(_response(request, openai)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, requests


@pytest.mark.parametrize("profile", ("openai", "ollama"))
def test_local_http_shapes_close_a_two_stage_runtime_decision(profile: str, tmp_path: Path) -> None:
    openai = profile == "openai"
    server, thread, requests = _serve(openai)
    base_url = f"http://127.0.0.1:{server.server_port}"
    factory = (
        (lambda: OpenAICompatibleModelPort(base_url, "secret", "fixture"))
        if openai else (lambda: OllamaModelPort("fixture", base_url))
    )
    scenario = asyncio.run(build_live_dom_scenario())
    select = (build_recurrent_cases(scenario.serialized_context)[0],)
    try:
        result = asyncio.run(run_two_stage_matrix(
            run_id=f"run:{profile}", mode=TwoStageRunMode.END_TO_END,
            port_factory=factory, cases=select, repetitions=1, output_dir=tmp_path,
        ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert result.success_count == 1
    assert result.provider_calls == 2
    assert len(requests) == 2
