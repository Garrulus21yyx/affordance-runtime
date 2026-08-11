import asyncio
import json
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Sequence, TypeVar

import pytest
from pydantic import BaseModel, ConfigDict

from affordance_runtime.model_capture import PrivateModelCapture
from affordance_runtime.model_port import (
    FallbackModelPort,
    ModelConfig,
    ModelImageURLPart,
    ModelMessage,
    ModelTextPart,
    OllamaModelPort,
    OpenAICompatibleModelPort,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
    model_port_from_environment,
)


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


def test_openai_compatible_adapter_serializes_multimodal_content_parts() -> None:
    server, thread, requests = _serve({
        "id": "response-vision",
        "choices": [{"message": {"content": '{"value":"seen"}'}}],
        "usage": {},
    })
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="vision-test",
        )
        answer = asyncio.run(port.generate_structured(
            [ModelMessage(role="user", content=(
                ModelTextPart(text='{"context_id":"context:vision"}'),
                ModelImageURLPart(image_url="data:image/png;base64,iVBORw0KGgo="),
            ))],
            Answer,
            ModelConfig(),
        ))
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
    server, thread, _ = _serve({
        "id": "response-private",
        "choices": [{"message": {"content": '{"value":"exact"}'}}],
        "usage": {},
    })
    capture = PrivateModelCapture(tmp_path / "private")
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
            private_capture=capture,
        )
        asyncio.run(port.generate_structured(
            [ModelMessage(role="user", content="exact prompt")], Answer, ModelConfig(),
        ))
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
    server, thread, _ = _serve({
        "id": "response-invalid",
        "choices": [{"message": {"content": '{"wrong":true}'}}],
        "usage": {},
    })
    capture = PrivateModelCapture(tmp_path / "private")
    try:
        port = OpenAICompatibleModelPort(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="secret",
            model="remote-test",
            private_capture=capture,
        )
        with pytest.raises(StructuredOutputError):
            asyncio.run(port.generate_structured([], Answer, ModelConfig()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    record = json.loads(capture.path.read_text(encoding="utf-8"))
    assert record["status"] == "schema_error"
    assert record["response_content"] == '{"wrong":true}'
    assert record["error"]


def test_openai_compatible_adapter_accepts_a_complete_json_markdown_fence() -> None:
    server, thread, _ = _serve(
        {
            "choices": [{"message": {"content": "```json\n{\"value\":\"fenced\"}\n```"}}],
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


def test_environment_factory_selects_remote_with_local_fallback_without_exposing_keys() -> None:
    port = model_port_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "mistral",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "true",
            "LLM_MISTRAL_BASE_URL": "https://mistral.invalid/v1",
            "LLM_MISTRAL_API_KEY": "remote-secret",
            "LLM_MISTRAL_MODEL": "mistral-test",
            "LLM_LOCAL_PROVIDER": "openai_compatible",
            "LLM_LOCAL_BASE_URL": "http://127.0.0.1:11434/v1",
            "LLM_LOCAL_API_KEY": "local-secret",
            "LLM_LOCAL_MODEL_ID": "qwen-test",
        }
    )

    assert isinstance(port, FallbackModelPort)
    assert [item.provider for item in port.ports] == ["mistral", "ollama-openai-compatible"]
    assert "remote-secret" not in repr(port)
    assert "local-secret" not in repr(port)


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
            "LLM_ZHIPU_MODEL": "glm-test",
        }
    )

    assert port.provider == "zhipu"
    assert port.model == "glm-test"
    assert "zhipu-secret" not in repr(port)


class _FailedPort:
    provider = "failed"
    model = "failed"
    endpoint_class = "test"
    last_call: Any = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, output_schema, config
        raise StructuredModelError("secret-bearing provider response")


class _WorkingPort(_FailedPort):
    provider = "working"

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        self.last_call = None
        return output_schema.model_validate({"value": "fallback"})


def test_fallback_model_port_uses_next_profile_and_sanitizes_failure() -> None:
    port = FallbackModelPort((_FailedPort(), _WorkingPort()))

    result = asyncio.run(port.generate_structured([], Answer, ModelConfig()))

    assert result.value == "fallback"
    assert port.failures == ("failed:StructuredModelError",)
    assert port.failure_details == ("failed:StructuredModelError",)
