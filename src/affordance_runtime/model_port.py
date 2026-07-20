"""Provider-neutral structured model boundary and HTTP adapters."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

T = TypeVar("T", bound=BaseModel)


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    content: str


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = None
    max_tokens: int = Field(default=2_048, ge=1)
    timeout_s: float = Field(default=90.0, gt=0.0)
    prompt_version: str = "1.0"


class ModelCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    endpoint_class: str
    prompt_version: str
    schema_name: str
    schema_version: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    response_id: str = ""


class StructuredModelError(RuntimeError):
    """A provider, JSON, or strict-schema failure without secret-bearing payloads."""


class ModelPort(Protocol):
    provider: str
    model: str
    endpoint_class: str
    last_call: ModelCallRecord | None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T: ...


@dataclass
class OpenAICompatibleModelPort:
    base_url: str
    api_key: str = field(repr=False)
    model: str = "mistral-large-3"
    provider: str = "openai-compatible"
    endpoint_class: str = "remote"
    last_call: ModelCallRecord | None = field(default=None, init=False)

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        return await asyncio.to_thread(self._generate, messages, output_schema, config)

    def _generate(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        schema = output_schema.model_json_schema()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        if config.seed is not None:
            body["seed"] = config.seed
        started = perf_counter()
        response = _post_json(
            f"{self.base_url.rstrip('/')}/chat/completions",
            body,
            timeout_s=config.timeout_s,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        latency_ms = round((perf_counter() - started) * 1_000, 3)
        try:
            content = response["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    str(item.get("text") or "") for item in content if isinstance(item, dict)
                )
            parsed = output_schema.model_validate_json(str(content))
        except (KeyError, IndexError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise StructuredModelError(f"structured response failed {output_schema.__name__} validation") from exc
        usage = response.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name=output_schema.__name__,
            schema_version=str(schema.get("title") or output_schema.__name__),
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
            response_id=str(response.get("id") or ""),
        )
        return parsed


@dataclass
class OllamaModelPort:
    model: str = "qwen2.5:7b"
    base_url: str = "http://127.0.0.1:11434"
    provider: str = "ollama"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = field(default=None, init=False)

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        return await asyncio.to_thread(self._generate, messages, output_schema, config)

    def _generate(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        schema = output_schema.model_json_schema()
        options: dict[str, Any] = {
            "temperature": config.temperature,
            "num_predict": config.max_tokens,
        }
        if config.seed is not None:
            options["seed"] = config.seed
        started = perf_counter()
        response = _post_json(
            f"{self.base_url.rstrip('/')}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": schema,
                "messages": [message.model_dump() for message in messages],
                "options": options,
            },
            timeout_s=config.timeout_s,
        )
        latency_ms = round((perf_counter() - started) * 1_000, 3)
        try:
            parsed = output_schema.model_validate_json(str(response["message"]["content"]))
        except (KeyError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise StructuredModelError(f"structured response failed {output_schema.__name__} validation") from exc
        prompt_tokens = int(response.get("prompt_eval_count") or 0)
        completion_tokens = int(response.get("eval_count") or 0)
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name=output_schema.__name__,
            schema_version=str(schema.get("title") or output_schema.__name__),
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        return parsed


def _post_json(
    url: str,
    body: dict[str, Any],
    *,
    timeout_s: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - configured model endpoint
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise StructuredModelError(f"model endpoint returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise StructuredModelError("model endpoint unavailable") from exc
    except json.JSONDecodeError as exc:
        raise StructuredModelError("model endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredModelError("model endpoint returned a non-object response")
    return payload
