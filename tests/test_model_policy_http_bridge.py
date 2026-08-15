import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.model_boundary import ModelFailureKind
from affordance_runtime.model_policy import ModelBackedAgentPolicy, ModelPortDecisionAdapter
from affordance_runtime.model_port import ModelConfig, OpenAICompatibleModelPort
from affordance_runtime.testing import StaticEnvironment


@dataclass
class FixtureBehavior:
    status: int = 200
    delay_s: float = 0.0
    malformed: bool = False
    requests: list[dict[str, Any]] = field(default_factory=list)


def _serve(behavior: FixtureBehavior) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            behavior.requests.append(body)
            if behavior.delay_s:
                time.sleep(behavior.delay_s)
            if behavior.status != 200:
                payload = json.dumps({"error": {"status": "fixture"}}).encode()
                self.send_response(behavior.status)
            else:
                context = json.loads(body["messages"][1]["content"])
                option = context["actions"]["options"][0]
                decision = (
                    {"type": "unknown", "context_id": context["context_id"]}
                    if behavior.malformed
                    else {
                        "type": "select_action",
                        "context_id": context["context_id"],
                        "action_id": option["action_id"],
                        "parameters": {},
                        "destination_id": "",
                    }
                )
                payload = json.dumps(
                    {
                        "id": "response:http-fixture",
                        "choices": [{"message": {"content": json.dumps(decision)}}],
                        "usage": {"prompt_tokens": 41, "completion_tokens": 12, "total_tokens": 53},
                    }
                ).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except BrokenPipeError:
                pass

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _policy(server: ThreadingHTTPServer, *, deadline: float = 2.0) -> ModelBackedAgentPolicy:
    transport = OpenAICompatibleModelPort(
        base_url=f"http://127.0.0.1:{server.server_port}",
        api_key="fixture-private-credential",
        model="fixture-model",
        provider="local-http-fixture",
        endpoint_class="local-fixture",
    )
    config = ModelConfig(
        timeout_s=max(0.01, deadline * 0.9),
        rate_limit_retries=0,
        transient_retries=0,
        prompt_version="p5-m1.1-http-fixture",
    )
    return ModelBackedAgentPolicy(ModelPortDecisionAdapter(transport, config), call_timeout_s=deadline)


def _close(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_local_http_model_port_bridge_completes_one_safe_runtime_action() -> None:
    behavior = FixtureBehavior()
    server, thread = _serve(behavior)
    policy = _policy(server)
    environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])
    try:
        result = asyncio.run(
            (AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
                environment, _task()
            )
        )
    finally:
        _close(server, thread)

    assert result.status == AgentLoopStatus.DONE
    assert len(behavior.requests) == 1
    assert result.execution_count == 1 and len(environment.executed_requests) == 1
    request = behavior.requests[0]
    assert [message["role"] for message in request["messages"]] == ["system", "user"]
    assert request["response_format"]["json_schema"]["strict"] is True
    schema = request["response_format"]["json_schema"]["schema"]
    assert schema["discriminator"]["propertyName"] == "type"
    assert policy.last_metadata is not None
    assert policy.last_metadata.total_tokens == 53
    assert policy.last_metadata.rate_limit_retry_count == 0
    assert policy.last_metadata.transient_retry_count == 0

    user_context = request["messages"][1]["content"]
    for private_field in (
        "selector",
        "coordinate",
        "bbox",
        "action_point",
        "href",
        "method",
        "backend",
        "executor",
        "credential",
        "security_ref",
        "td_digest",
    ):
        assert private_field not in user_context.casefold()
    for private_value in (
        "fixture-private-credential",
        "#toggle-selector",
        "/private/path",
        "https://private.example/action",
        "raw-artifact-value",
    ):
        assert private_value not in user_context


@pytest.mark.parametrize(
    ("behavior", "expected_kind"),
    (
        (FixtureBehavior(status=429), ModelFailureKind.PROVIDER_UNAVAILABLE),
        (FixtureBehavior(status=500), ModelFailureKind.PROVIDER_UNAVAILABLE),
        (FixtureBehavior(malformed=True), ModelFailureKind.SCHEMA_ERROR),
        (FixtureBehavior(delay_s=0.1), ModelFailureKind.TIMEOUT),
    ),
)
def test_local_http_failures_are_bounded_typed_and_zero_execution(behavior, expected_kind) -> None:
    server, thread = _serve(behavior)
    deadline = 0.02 if behavior.delay_s else 2.0
    environment = StaticEnvironment([_world("before", False)])
    try:
        result = asyncio.run(
            (
                AgentLoop(_policy(server, deadline=deadline), SharedActionEvaluator(), SharedTaskEvaluator())
            ).run(environment, _task())
        )
    finally:
        _close(server, thread)

    assert len(behavior.requests) == (2 if behavior.malformed else 1)
    assert result.status == AgentLoopStatus.FAILED
    assert result.policy_failure is not None and result.policy_failure.kind == expected_kind
    assert result.execution_count == 0 and environment.executed_requests == []
