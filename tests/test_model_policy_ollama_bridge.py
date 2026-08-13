import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.model_policy import ModelBackedAgentPolicy, ModelPortDecisionAdapter
from affordance_runtime.model_policy.spec import AgentDecisionPayload
from affordance_runtime.model_port import ModelConfig, OllamaModelPort
from affordance_runtime.testing import StaticEnvironment


def _serve() -> tuple[ThreadingHTTPServer, threading.Thread, list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            context = json.loads(request["messages"][1]["content"])
            option = context["actions"]["options"][0]
            decision = {
                "type": "select_action",
                "context_id": context["context_id"],
                "action_id": option["action_id"],
                "parameters": {},
                "destination_id": "",
            }
            payload = json.dumps(
                {
                    "message": {"content": json.dumps(decision)},
                    "prompt_eval_count": 33,
                    "eval_count": 9,
                }
            ).encode()
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
    return server, thread, requests


def test_exact_ollama_agent_decision_schema_completes_one_runtime_action() -> None:
    server, thread, requests = _serve()
    transport = OllamaModelPort(model="fixture-model", base_url=f"http://127.0.0.1:{server.server_port}")
    config = ModelConfig(
        timeout_s=1,
        rate_limit_retries=0,
        transient_retries=0,
        prompt_version="p5-m2-ollama-fixture",
    )
    policy = ModelBackedAgentPolicy(ModelPortDecisionAdapter(transport, config), call_timeout_s=2)
    environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])
    try:
        result = asyncio.run(
            AgentEpisodeRunner(AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
                environment, _task()
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == AgentLoopStatus.DONE
    assert len(requests) == 1 and result.execution_count == 1
    assert requests[0]["format"] == AgentDecisionPayload.model_json_schema()
    assert config.rate_limit_retries == config.transient_retries == 0
    assert policy.last_metadata is not None and policy.last_metadata.total_tokens == 42
    captured = json.dumps(requests[0], sort_keys=True)
    assert "fixture-private-credential" not in captured
    assert "selector" not in requests[0]["messages"][1]["content"].casefold()
