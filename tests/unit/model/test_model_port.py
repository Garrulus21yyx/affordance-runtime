import asyncio
import io
import json
import stat
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel, ConfigDict

from affordance_runtime.model.providers import port as provider_port
from affordance_runtime.model.providers.capture import PrivateModelCapture
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ModelImageURLPart,
    ModelMessage,
    ModelTextPart,
    OllamaModelPort,
    OpenAICompatibleModelPort,
    ProviderFailureKind,
    ProviderModelError,
    ProviderTransportErrorCategory,
    StructuredModelError,
    StructuredOutputError,
    StructuredOutputFailureKind,
    StructuredOutputMode,
    model_port_from_environment,
)
from tests.support.legacy_compact_json_decision_port import GroundedToolCommandPayload


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str


T = TypeVar("T", bound=BaseModel)


def _serve(response: dict[str, Any]) -> tuple[ThreadingHTTPServer, threading.Thread, list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
            payload = json.dumps(response).encode()
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


def test_ollama_adapter_requests_json_schema_and_records_manifest() -> None:
    server, thread, requests = _serve(
        {
            "message": {"content": '{"value":"ok"}'},
            "prompt_eval_count": 12,
            "eval_count": 4,
        }
    )
    try:
        port = OllamaModelPort(model="local-test", base_url=f"http://127.0.0.1:{server.server_port}")
        answer = asyncio.run(
            port.generate_structured(
                [ModelMessage(role="user", content="answer")],
                Answer,
                ModelConfig(seed=7, prompt_version="test-1"),
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "ok"
    assert requests[0]["format"]["properties"]["value"]["type"] == "string"
    assert requests[0]["options"]["seed"] == 7
    assert port.last_call is not None
    assert port.last_call.endpoint_class == "local"
    assert port.last_call.total_tokens == 16


def test_openai_compatible_adapter_never_exposes_key_and_validates_schema() -> None:
    server, thread, requests = _serve(
        {
            "id": "response-1",
            "choices": [{"message": {"content": '{"value":"remote"}'}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret-value",
            model="remote-test",
        )
        answer = asyncio.run(
            port.generate_structured(
                [ModelMessage(role="user", content="answer")],
                Answer,
                ModelConfig(prompt_version="test-2"),
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "remote"
    assert "secret-value" not in repr(port)
    assert requests[0]["response_format"]["json_schema"]["strict"] is True
    assert port.last_call is not None
    assert port.last_call.provider == "openai-compatible"
    assert port.last_call.total_tokens == 11
    assert port.last_transcript is not None
    assert port.last_transcript["openinference.span.kind"] == "LLM"
    assert port.last_transcript["llm.input_messages"] == [
        {"role": "user", "content": "answer"}
    ]
    assert port.last_transcript["llm.output_messages"] == [
        {"role": "assistant", "content": '{"value":"remote"}'}
    ]
    assert port.last_transcript["llm.token_count.total"] == 11


def test_openai_compatible_adapter_serializes_multimodal_content_parts() -> None:
    server, thread, requests = _serve(
        {
            "id": "response-vision",
            "choices": [{"message": {"content": '{"value":"seen"}'}}],
            "usage": {},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="vision-test",
        )
        answer = asyncio.run(
            port.generate_structured(
                [
                    ModelMessage(
                        role="user",
                        content=(
                            ModelTextPart(text='{"context_id":"context:vision"}'),
                            ModelImageURLPart(image_url="data:image/png;base64,iVBORw0KGgo="),
                        ),
                    )
                ],
                Answer,
                ModelConfig(),
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "seen"
    assert requests[0]["messages"][0]["content"] == [
        {"type": "text", "text": '{"context_id":"context:vision"}'},
        {"type": "image_url", "image_url": "data:image/png;base64,iVBORw0KGgo="},
    ]


def test_private_capture_preserves_exact_accepted_exchange_outside_public_evidence(
    tmp_path,
) -> None:
    server, thread, _ = _serve(
        {
            "id": "response-private",
            "choices": [{"message": {"content": '{"value":"exact"}'}}],
            "usage": {},
        }
    )
    capture = PrivateModelCapture(tmp_path / "private")
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
            private_capture=capture,
        )
        asyncio.run(
            port.generate_structured(
                [ModelMessage(role="user", content="exact prompt")],
                Answer,
                ModelConfig(),
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    record = json.loads(capture.path.read_text(encoding="utf-8"))
    assert record["status"] == "accepted"
    assert record["request_messages"][0]["content"] == "exact prompt"
    assert record["response_content"] == '{"value":"exact"}'
    assert record["response_id"] == "response-private"
    assert stat.S_IMODE(capture.path.stat().st_mode) == 0o600


def test_private_capture_preserves_schema_invalid_provider_content(tmp_path) -> None:
    server, thread, _ = _serve(
        {
            "id": "response-invalid",
            "choices": [{"message": {"content": '{"wrong":true}'}}],
            "usage": {},
        }
    )
    capture = PrivateModelCapture(tmp_path / "private")
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
            private_capture=capture,
        )
        with pytest.raises(StructuredOutputError) as captured:
            asyncio.run(port.generate_structured([], Answer, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    record = json.loads(capture.path.read_text(encoding="utf-8"))
    assert record["status"] == "json_invalid"
    assert record["response_content"] == '{"wrong":true}'
    assert record["error"]
    assert {(item.field_path, item.code) for item in captured.value.violations} == {
        ("value", "missing"),
        ("wrong", "extra_forbidden"),
    }
    assert captured.value.kind is StructuredOutputFailureKind.JSON_INVALID
    assert record["response_metadata"]["final_content_present"] is True
    assert port.last_transcript is not None
    assert port.last_transcript["status"] == "json_invalid"
    assert port.last_transcript["llm.output_messages"] == [
        {"role": "assistant", "content": '{"wrong":true}'}
    ]


def test_openai_adapter_classifies_budget_exhaustion_and_records_response_shape() -> None:
    server, thread, requests = _serve({
        "id": "response-truncated",
        "choices": [{
            "finish_reason": "length",
            "message": {"content": "", "reasoning_content": "private reasoning"},
        }],
        "usage": {"prompt_tokens": 11_383, "completion_tokens": 2_048, "total_tokens": 13_431},
    })
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="reasoning-test",
            supports_thinking_control=True,
        )
        with pytest.raises(StructuredOutputError) as captured:
            asyncio.run(port.generate_structured(
                [ModelMessage(role="user", content="one command")],
                Answer,
                ModelConfig(max_tokens=2_048),
            ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert captured.value.kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED
    assert port.last_call is not None
    assert port.last_call.finish_reason == "length"
    assert port.last_call.completion_tokens == 2_048
    assert port.last_call.max_output_tokens == 2_048
    assert port.last_call.final_content_present is False
    assert port.last_call.reasoning_content_present is True
    assert "message.reasoning_content" in port.last_call.response_fields
    assert port.last_transcript is not None
    assert port.last_transcript["status"] == "output_truncated"
    assert port.last_transcript["llm.output.reasoning_content_present"] is True
    assert "private reasoning" not in json.dumps(port.last_transcript)
    assert requests[0]["max_tokens"] == 2_048


def test_openai_adapter_separates_empty_final_content_from_json_invalid() -> None:
    cases = (
        (
            {"choices": [{"finish_reason": "stop", "message": {"content": ""}}], "usage": {}},
            StructuredOutputFailureKind.EMPTY_FINAL_CONTENT,
        ),
        (
            {"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}], "usage": {}},
            StructuredOutputFailureKind.JSON_INVALID,
        ),
    )
    for response, expected in cases:
        server, thread, _ = _serve(response)
        try:
            port = OpenAICompatibleModelPort(
                base_url=f"http://127.0.0.1:{server.server_port}",
                api_key="secret",
                model="remote-test",
            )
            with pytest.raises(StructuredOutputError) as captured:
                asyncio.run(port.generate_structured([], Answer, ModelConfig()))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        assert captured.value.kind is expected


def test_openai_adapter_confirms_truncation_from_exact_usage_without_finish_reason() -> None:
    server, thread, _ = _serve({
        "choices": [{"message": {"content": ""}}],
        "usage": {"completion_tokens": 4_096},
    })
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="reasoning-test",
        )
        with pytest.raises(StructuredOutputError) as captured:
            asyncio.run(port.generate_structured(
                [],
                Answer,
                ModelConfig(max_tokens=4_096),
            ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert captured.value.kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED


def test_openai_adapter_applies_explicit_thinking_mode_only_when_supported() -> None:
    server, thread, requests = _serve({
        "choices": [{"finish_reason": "stop", "message": {"content": '{"value":"ok"}'}}],
        "usage": {},
    })
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="reasoning-test",
            supports_thinking_control=True,
        )
        answer = asyncio.run(port.generate_structured(
            [],
            Answer,
            ModelConfig(thinking_mode="disabled"),
        ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "ok"
    assert requests[0]["thinking"] == {"type": "disabled"}


def test_openai_adapter_rejects_port_thinking_default_without_capability() -> None:
    port = OpenAICompatibleModelPort(
        base_url="https://provider.invalid",
        api_key="secret",
        model="unsupported-thinking-control",
        thinking_mode="disabled",
        supports_thinking_control=False,
    )

    with pytest.raises(StructuredModelError, match="does not declare thinking-mode control"):
        asyncio.run(port.generate_structured([], Answer, ModelConfig()))

    per_call_port = OpenAICompatibleModelPort(
        base_url="https://provider.invalid",
        api_key="secret",
        model="unsupported-thinking-control",
        supports_thinking_control=False,
    )
    with pytest.raises(StructuredModelError, match="does not declare thinking-mode control"):
        asyncio.run(
            per_call_port.generate_structured(
                [],
                Answer,
                ModelConfig(thinking_mode="disabled"),
            )
        )


def test_provider_transport_preserves_arguments_without_owning_tool_semantics() -> None:
    payload_type = GroundedToolCommandPayload
    server, thread, _ = _serve({
        "id": "response-transport",
        "choices": [{"message": {"content": '{"name":"activate","arguments":{"target":"E1","details":"x"}}'}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    })
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
        )
        payload = asyncio.run(port.generate_structured([], payload_type, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert payload.name == "activate"
    assert payload.arguments == {"target": "E1", "details": "x"}
    assert port.last_transcript is not None
    assert port.last_transcript["llm.token_count.total"] == 7


def test_openai_compatible_adapter_accepts_a_complete_json_markdown_fence() -> None:
    server, thread, _ = _serve(
        {
            "choices": [{"message": {"content": '```json\n{"value":"fenced"}\n```'}}],
            "usage": {},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="remote-test"
        )
        answer = asyncio.run(port.generate_structured([], Answer, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "fenced"


def test_openai_compatible_adapter_strips_only_surplus_closing_braces() -> None:
    server, thread, _ = _serve(
        {
            "choices": [{"message": {"content": '{"value":"bounded"}\n}\n'}}],
            "usage": {},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
        )
        answer = asyncio.run(port.generate_structured([], Answer, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "bounded"


def test_openai_compatible_adapter_unwraps_one_exact_schema_named_object() -> None:
    server, thread, _ = _serve(
        {
            "choices": [{"message": {"content": '{"answer":{"value":"wrapped"}}'}}],
            "usage": {},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="remote-test"
        )
        answer = asyncio.run(port.generate_structured([], Answer, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "wrapped"


@pytest.mark.parametrize(
    "content",
    (
        '{"answer":{"value":"wrapped"},"extra":true}',
        '{"wrong":{"value":"wrapped"}}',
        '{"answer":{"answer":{"value":"nested"}}}',
    ),
)
def test_schema_wrapper_normalization_rejects_ambiguous_or_unsupported_shapes(content) -> None:
    server, thread, _ = _serve(
        {
            "choices": [{"message": {"content": content}}],
            "usage": {},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="remote-test"
        )
        with pytest.raises(StructuredOutputError):
            asyncio.run(port.generate_structured([], Answer, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_openai_compatible_adapter_retries_a_bounded_rate_limit_response() -> None:
    requests = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            nonlocal requests
            requests += 1
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            if requests == 1:
                self.send_response(429)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return
            payload = json.dumps({"choices": [{"message": {"content": '{"value":"retried"}'}}], "usage": {}}).encode()
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
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="remote-test"
        )
        answer = asyncio.run(
            port.generate_structured([], Answer, ModelConfig(rate_limit_retries=1, rate_limit_backoff_s=0))
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "retried"
    assert requests == 2
    assert port.last_call is not None
    assert port.last_call.rate_limit_retry_count == 1
    assert port.last_call.transient_retry_count == 0


def test_gemini_retry_info_is_parsed_without_exposing_quota_payload() -> None:
    requests = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            nonlocal requests
            requests += 1
            self.rfile.read(int(self.headers["Content-Length"]))
            if requests == 1:
                payload = json.dumps(
                    {
                        "error": {
                            "code": 429,
                            "status": "RESOURCE_EXHAUSTED",
                            "details": [
                                {"@type": "type.googleapis.com/google.rpc.QuotaFailure"},
                                {
                                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                    "retryDelay": "0s",
                                },
                            ],
                        }
                    }
                ).encode()
                self.send_response(429)
            else:
                payload = json.dumps(
                    {"choices": [{"message": {"content": '{"value":"retried"}'}}], "usage": {}}
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
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="gemini-test",
            provider="gemini",
        )
        answer = asyncio.run(port.generate_structured([], Answer, ModelConfig(rate_limit_retries=1)))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "retried"
    assert requests == 2
    assert port.last_call is not None and port.last_call.rate_limit_retry_count == 1


def test_quota_exhaustion_trips_circuit_and_defers_without_retry() -> None:
    requests = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            nonlocal requests
            requests += 1
            self.rfile.read(int(self.headers["Content-Length"]))
            payload = json.dumps(
                {
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure"}],
                    }
                }
            ).encode()
            self.send_response(429)
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
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="gemini-test"
        )
        config = ModelConfig(rate_limit_retries=3, quota_circuit_break_s=60)
        with pytest.raises(ProviderModelError) as first:
            asyncio.run(port.generate_structured([], Answer, config))
        with pytest.raises(ProviderModelError) as second:
            asyncio.run(port.generate_structured([], Answer, config))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first.value.kind == ProviderFailureKind.QUOTA_EXHAUSTED
    assert first.value.circuit_open is False
    assert second.value.kind == ProviderFailureKind.QUOTA_EXHAUSTED
    assert second.value.circuit_open is True
    assert second.value.retry_after_s is not None
    assert requests == 1


def test_openai_compatible_adapter_retries_a_bounded_transient_response() -> None:
    requests = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            nonlocal requests
            requests += 1
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            if requests == 1:
                self.send_response(503)
                self.end_headers()
                return
            payload = json.dumps({"choices": [{"message": {"content": '{"value":"retried"}'}}], "usage": {}}).encode()
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
            base_url=f"http://127.0.0.1:{server.server_port}", api_key="secret", model="remote-test"
        )
        answer = asyncio.run(
            port.generate_structured([], Answer, ModelConfig(transient_retries=1, transient_backoff_s=0))
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "retried"
    assert requests == 2
    assert port.last_call is not None
    assert port.last_call.rate_limit_retry_count == 0
    assert port.last_call.transient_retry_count == 1


def test_provider_retry_budget_is_shared_across_rate_limit_and_capacity() -> None:
    requests = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            nonlocal requests
            requests += 1
            self.rfile.read(int(self.headers["Content-Length"]))
            if requests == 1:
                self.send_response(429)
                self.send_header("Retry-After", "0")
            else:
                self.send_response(503)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
        )
        with pytest.raises(ProviderModelError) as failure:
            asyncio.run(
                port.generate_structured(
                    [],
                    Answer,
                    ModelConfig(
                        rate_limit_retries=1,
                        rate_limit_backoff_s=0,
                        transient_retries=1,
                        transient_backoff_s=0,
                    ),
                )
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    error = failure.value
    assert requests == 2
    assert error.kind is ProviderFailureKind.PROVIDER_CAPACITY
    assert error.http_status == 503
    assert error.error_category.value == "http_5xx"
    assert error.exception_class == "HTTPError"
    assert error.physical_attempt_count == 2
    assert error.rate_limit_retry_count == 1
    assert error.transient_retry_count == 0
    assert error.latency_ms > 0
    assert port.last_transcript is not None
    assert port.last_transcript["network.second_request_sent"] is True
    assert port.last_transcript["network.physical_attempt_count"] == 2
    assert port.last_transcript["error.http_status"] == 503
    assert port.last_transcript["error.category"] == "http_5xx"
    assert port.last_transcript["error.latency_ms"] == error.latency_ms


def test_provider_retry_uses_remaining_transport_deadline(monkeypatch) -> None:
    clock = [100.0]
    timeouts: list[float] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"ok":true}'

    def urlopen(_request, *, timeout: float):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            raise urllib.error.HTTPError(
                "https://provider.invalid",
                503,
                "unavailable",
                {},
                io.BytesIO(b"{}"),
            )
        return Response()

    monkeypatch.setattr(provider_port, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(provider_port.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        provider_port.time,
        "sleep",
        lambda delay: clock.__setitem__(0, clock[0] + delay),
    )

    payload, rate_retries, transient_retries = provider_port._post_json(
        "https://provider.invalid",
        {"request": "fixture"},
        timeout_s=10,
        total_timeout_s=10,
        rate_limit_retries=1,
        transient_retries=1,
        transient_backoff_s=2,
    )

    assert payload == {"ok": True}
    assert (rate_retries, transient_retries) == (0, 1)
    assert timeouts == [10, 8]


def test_provider_timeout_after_full_attempt_still_sends_second_request(monkeypatch) -> None:
    clock = [100.0]
    timeouts: list[float] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"ok":true}'

    def urlopen(_request, *, timeout: float):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            clock[0] += timeout
            raise TimeoutError("first physical request timed out")
        return Response()

    monkeypatch.setattr(provider_port, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(provider_port.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        provider_port.time,
        "sleep",
        lambda delay: clock.__setitem__(0, clock[0] + delay),
    )

    payload, rate_retries, transient_retries = provider_port._post_json(
        "https://provider.invalid",
        {"request": "fixture"},
        timeout_s=30,
        total_timeout_s=89,
        rate_limit_retries=1,
        transient_retries=1,
        transient_backoff_s=0.5,
    )

    assert payload == {"ok": True}
    assert (rate_retries, transient_retries) == (0, 1)
    assert timeouts == [30, 30]


def test_provider_timeout_can_be_reserved_for_semantic_fast_retry(monkeypatch) -> None:
    requests = [0]

    def urlopen(_request, *, timeout: float):
        requests[0] += 1
        assert 54 < timeout <= 55
        raise TimeoutError("semantic owner must select the retry representation")

    monkeypatch.setattr(provider_port.urllib.request, "urlopen", urlopen)

    with pytest.raises(ProviderModelError) as failure:
        provider_port._post_json(
            "https://provider.invalid",
            {"request": "fixture"},
            timeout_s=55,
            total_timeout_s=55,
            rate_limit_retries=1,
            transient_retries=1,
            timeout_retries=0,
        )

    assert requests == [1]
    assert failure.value.error_category is ProviderTransportErrorCategory.TIMEOUT
    assert failure.value.physical_attempt_count == 1
    assert failure.value.transient_retry_count == 0


def test_structured_schema_failure_has_no_response_value() -> None:
    server, thread, _ = _serve(
        {
            "choices": [{"message": {"content": '{"value": 7}'}}],
            "usage": {},
        }
    )
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret-value",
            model="remote-test",
        )
        try:
            asyncio.run(port.generate_structured([], Answer, ModelConfig()))
        except StructuredModelError as exc:
            detail = str(exc)
        else:
            raise AssertionError("invalid structured output should fail")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert "value:string_type" in detail
    assert '"value": 7' not in detail


def test_environment_factory_rejects_automatic_profile_fallback() -> None:
    with pytest.raises(ValueError, match="fallback"):
        model_port_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "mistral",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "true",
                "LLM_MISTRAL_BASE_URL": "https://mistral.invalid/v1",
                "LLM_MISTRAL_API_KEY": "remote-secret",
                "LLM_MISTRAL_MODEL": "mistral-test",
            }
        )


def test_environment_factory_selects_gemini_profile_without_exposing_key() -> None:
    port = model_port_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "gemini",
            "LLM_GEMINI_BASE_URL": "https://gemini.invalid/openai",
            "LLM_GEMINI_API_KEY": "gemini-secret",
            "LLM_GEMINI_MODEL": "gemini-test",
        }
    )

    assert isinstance(port, OpenAICompatibleModelPort)
    assert port.provider == "gemini"
    assert port.model == "gemini-test"
    assert "gemini-secret" not in repr(port)


def test_environment_factory_selects_zhipu_profile_without_exposing_key() -> None:
    port = model_port_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "zhipu",
            "LLM_ZHIPU_BASE_URL": "https://zhipu.invalid/v4/",
            "LLM_ZHIPU_API_KEY": "zhipu-secret",
            "LLM_ZHIPU_MODEL": "glm-4.7-flash",
        }
    )

    assert port.provider == "zhipu"
    assert port.model == "glm-4.7-flash"
    assert port.supports_multimodal is False
    assert port.structured_output_mode is StructuredOutputMode.JSON_OBJECT_PROMPT_SCHEMA
    assert port.thinking_mode is None
    assert "zhipu-secret" not in repr(port)


def test_environment_factory_selects_aliyun_profile_without_exposing_key() -> None:
    port = model_port_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "aliyun",
            "LLM_ALIYUN_BASE_URL": "https://aliyun.invalid/compatible-mode/v1",
            "LLM_ALIYUN_API_KEY": "aliyun-secret",
            "LLM_ALIYUN_MODEL": "glm-5.2",
        }
    )

    assert port.provider == "aliyun"
    assert port.model == "glm-5.2"
    assert port.supports_multimodal is False
    assert port.structured_output_mode is StructuredOutputMode.JSON_OBJECT_PROMPT_SCHEMA
    assert "aliyun-secret" not in repr(port)


def test_environment_factory_selects_deepseek_profile_without_exposing_key() -> None:
    port = model_port_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "deepseek",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY": "deepseek-secret",
            "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
        }
    )

    assert port.provider == "deepseek"
    assert port.model == "deepseek-v4-flash"
    assert port.supports_multimodal is False
    assert port.structured_output_mode is StructuredOutputMode.JSON_OBJECT_PROMPT_SCHEMA
    assert port.thinking_mode is None
    assert port.supports_thinking_control is True
    assert "deepseek-secret" not in repr(port)


def test_zhipu_text_profile_requests_json_object_and_embeds_schema_in_prompt() -> None:
    server, thread, requests = _serve(
        {
            "id": "response-zhipu-text",
            "choices": [{"message": {"content": '{"value":"zhipu"}'}}],
            "usage": {},
        }
    )
    try:
        port = model_port_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "zhipu",
                "LLM_ZHIPU_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "LLM_ZHIPU_API_KEY": "zhipu-secret",
                "LLM_ZHIPU_MODEL": "glm-4.7-flash",
            }
        )
        answer = asyncio.run(
            port.generate_structured(
                [ModelMessage(role="user", content="answer")],
                Answer,
                ModelConfig(),
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "zhipu"
    request = requests[0]
    assert request["response_format"] == {"type": "json_object"}
    assert "never the JSON Schema definition itself" in request["messages"][0]["content"]
    assert "thinking" not in request
    assert request["messages"][0]["role"] == "system"
    assert '"value"' in request["messages"][0]["content"]
    assert request["messages"][1] == {"role": "user", "content": "answer"}


def test_zhipu_visual_profile_uses_prompt_schema_without_text_only_response_format(tmp_path) -> None:
    server, thread, requests = _serve(
        {
            "id": "response-zhipu-vlm",
            "choices": [{"message": {"content": '{"value":"seen"}'}}],
            "usage": {},
        }
    )
    try:
        port = model_port_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "zhipu",
                "LLM_ZHIPU_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "LLM_ZHIPU_API_KEY": "zhipu-secret",
                "LLM_ZHIPU_MODEL": "glm-4.1v-thinking-flashx",
                "LLM_ENABLE_PRIVATE_MODEL_CAPTURE": "true",
                "LLM_PRIVATE_MODEL_CAPTURE_DIR": str(tmp_path / "zhipu-private"),
            }
        )
        answer = asyncio.run(
            port.generate_structured(
                [
                    ModelMessage(role="system", content="You are a GUI agent."),
                    ModelMessage(
                        role="user",
                        content=(
                            ModelTextPart(text="answer from the screenshot"),
                            ModelImageURLPart(image_url="data:image/png;base64,iVBORw0KGgo="),
                        ),
                    )
                ],
                Answer,
                ModelConfig(),
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert answer.value == "seen"
    assert port.supports_multimodal is True
    assert port.structured_output_mode is StructuredOutputMode.PROMPT_JSON_LOCAL_VALIDATION
    request = requests[0]
    assert "response_format" not in request
    assert "thinking" not in request
    assert request["messages"][0]["role"] == "system"
    assert request["messages"][0]["content"].startswith("You are a GUI agent.\n\n")
    assert request["messages"][0]["content"].index("You are a GUI agent.") < request["messages"][0][
        "content"
    ].index("Return exactly one JSON object")
    assert '"value"' in request["messages"][0]["content"]
    assert request["messages"][1]["content"][0]["type"] == "text"
    assert request["messages"][1]["content"][1]["type"] == "image_url"
    assert request["messages"][1]["content"][1]["image_url"] == {"url": "data:image/png;base64,iVBORw0KGgo="}
    capture = json.loads((tmp_path / "zhipu-private/model-exchanges.jsonl").read_text())
    assert capture["request_messages"] == request["messages"]
