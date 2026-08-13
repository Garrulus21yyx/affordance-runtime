from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_grounded_tools_v2 import _context

from affordance_runtime.model_boundary.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.model_policy.contracts import (
    ModelDecisionRequest,
    ModelDecisionResponse,
    ModelMetadata,
)
from affordance_runtime.model_policy.grounded_tool_port_bridge import GroundedToolDecisionAdapter
from affordance_runtime.model_policy.policy import _build_request
from affordance_runtime.model_policy.provider_orchestrator import (
    ProviderAttemptStatus,
    ProviderCallOrchestrator,
    ProviderCallPolicy,
)
from affordance_runtime.model_port import ModelConfig, OpenAICompatibleModelPort


def _request() -> ModelDecisionRequest:
    return ModelDecisionRequest("model-request:test", "{}", "v1", "decide", {})


def _response(response_id: str = "response:1") -> ModelDecisionResponse:
    return ModelDecisionResponse(
        '{"decision":"ok"}',
        ModelMetadata(response_id=response_id),
    )


@dataclass
class _Port:
    outcomes: list[ModelDecisionResponse | ModelFailure]
    provider_id: str = "provider"
    model_id: str = "model"
    compatibility_key: str = "schema:grounding"
    calls: int = field(default=0, init=False)

    async def generate(self, request):
        self.calls += 1
        return self.outcomes.pop(0)


@dataclass
class _RaisingPort:
    provider_id: str = "provider"
    model_id: str = "model"
    compatibility_key: str = "schema:grounding"

    async def generate(self, request):
        del request
        raise AssertionError("local adapter defect")


def test_retryable_rate_limit_retries_without_creating_a_new_request() -> None:
    port = _Port(
        [
            ModelFailure(
                ModelFailureKind.PROVIDER_UNAVAILABLE,
                "rate limited",
                True,
                ProviderFailureCode.RATE_LIMITED,
                0.0,
            ),
            _response(),
        ]
    )
    orchestrator = ProviderCallOrchestrator(
        (port,),
        ProviderCallPolicy(3, (0.0, 0.0), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelDecisionResponse)
    assert port.calls == 2
    assert outcome.metadata.rate_limit_retry_count == 1
    assert outcome.metadata.transient_retry_count == 0
    assert [item.policy_request_id for item in orchestrator.last_attempts] == [
        "model-request:test",
        "model-request:test",
    ]
    assert [item.status for item in orchestrator.last_attempts] == [
        ProviderAttemptStatus.RETRYABLE_FAILURE,
        ProviderAttemptStatus.ACCEPTED,
    ]


def test_nonretryable_failure_fails_immediately_without_fallback() -> None:
    primary = _Port(
        [
            ModelFailure(
                ModelFailureKind.REFUSED,
                "authentication failed",
                False,
                ProviderFailureCode.AUTHENTICATION,
            )
        ]
    )
    fallback = _Port([_response()], provider_id="fallback")
    orchestrator = ProviderCallOrchestrator(
        (primary, fallback),
        ProviderCallPolicy(3, (0.0, 0.0), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelFailure)
    assert outcome.kind is ModelFailureKind.REFUSED
    assert primary.calls == 1 and fallback.calls == 0
    assert orchestrator.last_fallback_count == 0


def test_local_adapter_exception_is_internal_not_provider_unavailable() -> None:
    orchestrator = ProviderCallOrchestrator(
        (_RaisingPort(),),
        ProviderCallPolicy(3, (0.0, 0.0), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelFailure)
    assert outcome.kind is ModelFailureKind.INTERNAL_ERROR
    assert len(orchestrator.last_attempts) == 1
    assert orchestrator.last_attempts[0].status is ProviderAttemptStatus.NON_RETRYABLE_FAILURE
    assert orchestrator.last_attempts[0].origin is ProviderAttemptOrigin.UNKNOWN


def test_exhaustion_is_typed_and_fallback_is_compatible() -> None:
    def unavailable() -> ModelFailure:
        return ModelFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            "unavailable",
            True,
            ProviderFailureCode.UNAVAILABLE,
        )

    primary = _Port([unavailable(), unavailable()], provider_id="primary")
    fallback = _Port([unavailable(), unavailable()], provider_id="fallback")
    orchestrator = ProviderCallOrchestrator(
        (primary, fallback),
        ProviderCallPolicy(2, (0.0,), 0.0, 1.0, 2.0),
    )

    outcome = asyncio.run(orchestrator.generate(_request()))

    assert isinstance(outcome, ModelFailure)
    assert outcome.kind is ModelFailureKind.PROVIDER_EXHAUSTED
    assert outcome.retryable is False
    assert len(orchestrator.last_attempts) == 4
    assert orchestrator.last_fallback_count == 1


def test_fallback_rejects_a_different_schema_or_capability_profile() -> None:
    first = _Port([])
    second = _Port([], compatibility_key="different")
    with pytest.raises(ValueError, match="schema/capability"):
        ProviderCallOrchestrator((first, second))


def test_real_model_port_503_then_200_dispatches_two_network_attempts() -> None:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib callback
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            if len(requests) == 1:
                payload = json.dumps({"error": {"status": "capacity"}}).encode()
                self.send_response(503)
            else:
                payload = json.dumps(
                    {
                        "id": "response:recovered",
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "op": "fill",
                                            "target": "E1",
                                            "text": "donovan",
                                        }
                                    )
                                }
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                        },
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
    transport = OpenAICompatibleModelPort(
        base_url=f"http://127.0.0.1:{server.server_port}",
        api_key="fixture-private-credential",
        model="glm-4.1v-thinking-flashx",
        provider="zhipu",
        endpoint_class="local-fixture",
    )
    adapter = GroundedToolDecisionAdapter(
        transport,
        ModelConfig(
            timeout_s=1.0,
            rate_limit_retries=0,
            transient_retries=0,
            provider_circuit_break_s=0.0,
        ),
    )
    orchestrator = ProviderCallOrchestrator(
        (adapter,),
        ProviderCallPolicy(2, (0.0,), 0.0, 1.0, 3.0),
    )
    try:
        outcome = asyncio.run(orchestrator.generate(_build_request(_context())))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert isinstance(outcome, ModelDecisionResponse)
    assert len(requests) == 2
    assert [item.origin for item in orchestrator.last_attempts] == [
        ProviderAttemptOrigin.NETWORK,
        ProviderAttemptOrigin.NETWORK,
    ]
    assert [item.status for item in orchestrator.last_attempts] == [
        ProviderAttemptStatus.RETRYABLE_FAILURE,
        ProviderAttemptStatus.ACCEPTED,
    ]
    assert transport.circuit_open_until_monotonic == 0.0
