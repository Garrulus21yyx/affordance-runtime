"""Local HTTP existing-ModelPort profile for fixed shared-state cases."""

import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.benchmarks.target_loop.support import shared_environment
from affordance_runtime.model.policy import ModelBackedAgentPolicy, model_policy_from_environment
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind


@dataclass
class ModelPolicyHttpEnvironment(ScriptedEnvironment):
    server: ThreadingHTTPServer | None = field(default=None, init=False)
    thread: threading.Thread | None = field(default=None, init=False)
    http_requests: int = field(default=0, init=False)

    def start_server(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                owner.http_requests += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                option = body["tools"][0]["function"]
                schema = option["parameters"]
                properties = schema["properties"]
                arguments = {
                    name: properties[name]["enum"][0]
                    for name in schema.get("required", ())
                    if properties[name].get("enum")
                }
                if "target" in schema.get("required", ()) and "target" not in arguments:
                    operation = re.escape(option["name"])
                    context_text = "\n".join(
                        str(message.get("content", ""))
                        for message in body["messages"]
                    )
                    matches = re.findall(
                        rf"\[([^\]\n]+)\][^\n]*verbs=[^\n]*\b{operation}\b",
                        context_text,
                    )
                    target_ref = next(
                        (
                            value
                            for value in matches
                            if PublicRefCodec.accepts(value, expected=PublicRefKind.EXECUTABLE)
                        ),
                        "",
                    )
                    if not target_ref:
                        raise ValueError("fixture model could not find a delivered executable target")
                    arguments["target"] = target_ref
                payload = json.dumps(
                    {
                        "id": "response:m3-http-policy",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "fixture-native-tool",
                        "choices": [{
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": "call:fixture-native",
                                    "type": "function",
                                    "function": {
                                        "name": option["name"],
                                        "arguments": json.dumps(arguments),
                                    },
                                }],
                            },
                        }],
                        "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
                    }
                ).encode()
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
    environment = ModelPolicyHttpEnvironment(
        initial_observation=fixture.initial_observation,
        post_observations=fixture.post_observations,
        results=fixture.results,
    )
    environment.start_server()
    return environment


def local_http_policy(environment: ModelPolicyHttpEnvironment) -> ModelBackedAgentPolicy:
    assert environment.server is not None
    return model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "local",
            "LLM_LOCAL_PROVIDER": "openai_compatible",
            "LLM_LOCAL_BASE_URL": f"http://127.0.0.1:{environment.server.server_port}/v1",
            "LLM_LOCAL_API_KEY": "fixture-key",
            "LLM_LOCAL_MODEL": "fixture-native-tool",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=2.0,
    )
