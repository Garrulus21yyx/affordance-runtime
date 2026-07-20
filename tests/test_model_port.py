import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict

from affordance_runtime.model_port import (
    FallbackModelPort,
    ModelConfig,
    ModelMessage,
    OllamaModelPort,
    OpenAICompatibleModelPort,
    StructuredModelError,
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
