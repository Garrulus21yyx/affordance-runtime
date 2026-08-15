"""Local HTTP existing-ModelPort profile for fixed shared-state cases."""

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from affordance_runtime.benchmarks.target_loop.support import shared_environment
from affordance_runtime.model.policy import ModelBackedAgentPolicy, ModelPortDecisionAdapter
from affordance_runtime.model.providers.port import ModelConfig, OpenAICompatibleModelPort
from affordance_runtime.testing import StaticEnvironment


@dataclass
class ModelPolicyHttpEnvironment(StaticEnvironment):
    server: ThreadingHTTPServer | None = field(default=None, init=False)
    thread: threading.Thread | None = field(default=None, init=False)
    http_requests: int = field(default=0, init=False)

    def start_server(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                owner.http_requests += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                context = json.loads(body["messages"][1]["content"])
                option = context["actions"]["options"][0]
                decision = {
                    "type": "select_action", "context_id": context["context_id"],
                    "action_id": option["action_id"], "parameters": {}, "destination_id": "",
                }
                payload = json.dumps({
                    "id": "response:m3-http-policy",
                    "choices": [{"message": {"content": json.dumps(decision)}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                del format, args

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    async def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


def local_http_policy_environment(surface: str) -> ModelPolicyHttpEnvironment:
    fixture = shared_environment(surface)
    environment = ModelPolicyHttpEnvironment(fixture.observations, fixture.results)
    environment.start_server()
    return environment


def local_http_policy(environment: ModelPolicyHttpEnvironment) -> ModelBackedAgentPolicy:
    assert environment.server is not None
    transport = OpenAICompatibleModelPort(
        f"http://127.0.0.1:{environment.server.server_port}", "fixture-key",
        "fixture-model", "local-http-fixture", "local-fixture",
    )
    config = ModelConfig(
        timeout_s=1.0, rate_limit_retries=0, transient_retries=0,
        prompt_version="p5-m3-http-policy",
    )
    return ModelBackedAgentPolicy(ModelPortDecisionAdapter(transport, config), call_timeout_s=2.0)
