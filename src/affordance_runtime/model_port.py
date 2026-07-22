"""Provider-neutral structured model boundary and HTTP adapters."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence, TypeVar

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
    rate_limit_retries: int = Field(default=1, ge=0, le=3)
    rate_limit_backoff_s: float = Field(default=1.0, ge=0.0, le=30.0)
    max_provider_retry_delay_s: float = Field(default=30.0, ge=0.0, le=60.0)
    provider_circuit_break_s: float = Field(default=60.0, ge=0.0, le=3_600.0)
    quota_circuit_break_s: float = Field(default=300.0, ge=0.0, le=86_400.0)
    transient_retries: int = Field(default=1, ge=0, le=3)
    transient_backoff_s: float = Field(default=0.5, ge=0.0, le=5.0)
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
    rate_limit_retry_count: int = 0
    transient_retry_count: int = 0


class StructuredModelError(RuntimeError):
    """A provider, JSON, or strict-schema failure without secret-bearing payloads."""


class ProviderFailureKind(StrEnum):
    RATE_LIMIT_TRANSIENT = "rate_limit_transient"
    QUOTA_EXHAUSTED = "quota_exhausted"
    PROVIDER_CAPACITY = "provider_capacity"


class ProviderModelError(StructuredModelError):
    """Typed, redacted provider failure which a runner may safely defer."""

    def __init__(
        self,
        kind: ProviderFailureKind,
        *,
        retry_after_s: float | None = None,
        circuit_open: bool = False,
    ) -> None:
        self.kind = kind
        self.retry_after_s = retry_after_s
        self.circuit_open = circuit_open
        self.resumable = True
        super().__init__(f"provider failure: {kind.value}")


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
class FallbackModelPort:
    """Try provider-neutral model ports in order without leaking provider payloads."""

    ports: tuple[ModelPort, ...]
    provider: str = field(default="fallback", init=False)
    model: str = field(default="ordered-profiles", init=False)
    endpoint_class: str = field(default="mixed", init=False)
    last_call: ModelCallRecord | None = field(default=None, init=False)
    failures: tuple[str, ...] = field(default=(), init=False)
    failure_details: tuple[str, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        if not self.ports:
            raise ValueError("FallbackModelPort requires at least one model port")

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        failures: list[str] = []
        failure_details: list[str] = []
        for port in self.ports:
            try:
                value = await port.generate_structured(messages, output_schema, config)
            except StructuredModelError as exc:
                failures.append(f"{port.provider}:{type(exc).__name__}")
                failure_details.append(f"{port.provider}:{_safe_failure_detail(exc)}")
                continue
            self.last_call = port.last_call
            self.failures = tuple(failures)
            self.failure_details = tuple(failure_details)
            return value
        self.last_call = None
        self.failures = tuple(failures)
        self.failure_details = tuple(failure_details)
        raise StructuredModelError("all configured model profiles failed")


@dataclass
class OpenAICompatibleModelPort:
    base_url: str
    api_key: str = field(repr=False)
    model: str = "mistral-large-3"
    provider: str = "openai-compatible"
    endpoint_class: str = "remote"
    last_call: ModelCallRecord | None = field(default=None, init=False)
    circuit_open_until_monotonic: float = field(default=0.0, init=False, repr=False)
    circuit_failure_kind: ProviderFailureKind | None = field(default=None, init=False)

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
        _raise_if_model_circuit_open(self)
        started = perf_counter()
        try:
            response, rate_limit_retry_count, transient_retry_count = _post_json(
                f"{self.base_url.rstrip('/')}/chat/completions",
                body,
                timeout_s=config.timeout_s,
                headers={"Authorization": f"Bearer {self.api_key}"},
                rate_limit_retries=config.rate_limit_retries,
                rate_limit_backoff_s=config.rate_limit_backoff_s,
                max_provider_retry_delay_s=config.max_provider_retry_delay_s,
                transient_retries=config.transient_retries,
                transient_backoff_s=config.transient_backoff_s,
            )
        except ProviderModelError as exc:
            _trip_model_circuit(self, exc, config)
            raise
        latency_ms = round((perf_counter() - started) * 1_000, 3)
        try:
            content = response["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    str(item.get("text") or "") for item in content if isinstance(item, dict)
                )
            parsed = output_schema.model_validate_json(_structured_json_content(content))
        except (KeyError, IndexError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise StructuredModelError(
                f"structured response failed {output_schema.__name__} validation: {_schema_failure_summary(exc)}"
            ) from exc
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
            rate_limit_retry_count=rate_limit_retry_count,
            transient_retry_count=transient_retry_count,
        )
        return parsed


@dataclass
class OllamaModelPort:
    model: str = "qwen2.5:7b"
    base_url: str = "http://127.0.0.1:11434"
    provider: str = "ollama"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = field(default=None, init=False)
    circuit_open_until_monotonic: float = field(default=0.0, init=False, repr=False)
    circuit_failure_kind: ProviderFailureKind | None = field(default=None, init=False)

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
        _raise_if_model_circuit_open(self)
        started = perf_counter()
        try:
            response, rate_limit_retry_count, transient_retry_count = _post_json(
                f"{self.base_url.rstrip('/')}/api/chat",
                {
                    "model": self.model,
                    "stream": False,
                    "format": schema,
                    "messages": [message.model_dump() for message in messages],
                    "options": options,
                },
                timeout_s=config.timeout_s,
                rate_limit_retries=config.rate_limit_retries,
                rate_limit_backoff_s=config.rate_limit_backoff_s,
                max_provider_retry_delay_s=config.max_provider_retry_delay_s,
                transient_retries=config.transient_retries,
                transient_backoff_s=config.transient_backoff_s,
            )
        except ProviderModelError as exc:
            _trip_model_circuit(self, exc, config)
            raise
        latency_ms = round((perf_counter() - started) * 1_000, 3)
        try:
            parsed = output_schema.model_validate_json(str(response["message"]["content"]))
        except (KeyError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise StructuredModelError(
                f"structured response failed {output_schema.__name__} validation: {_schema_failure_summary(exc)}"
            ) from exc
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
            rate_limit_retry_count=rate_limit_retry_count,
            transient_retry_count=transient_retry_count,
        )
        return parsed


def model_port_from_environment(environment: Mapping[str, str] | None = None) -> ModelPort:
    """Build the selected model profile, optionally falling back to local.

    The process environment is read only when no explicit mapping is supplied;
    loading a dotenv file remains the caller's responsibility.
    """

    env = os.environ if environment is None else environment
    active_profile = env.get("LLM_ACTIVE_PROFILE", "local").strip().lower()
    if active_profile == "local":
        return _local_model_port(env)
    if active_profile not in {"mistral", "gemini", "zhipu"}:
        raise ValueError(f"unsupported LLM_ACTIVE_PROFILE: {active_profile}")
    if active_profile == "mistral":
        remote = OpenAICompatibleModelPort(
            base_url=_required_env(env, "LLM_MISTRAL_BASE_URL"),
            api_key=_required_env(env, "LLM_MISTRAL_API_KEY"),
            model=_required_env(env, "LLM_MISTRAL_MODEL"),
            provider="mistral",
            endpoint_class="remote",
        )
    elif active_profile == "gemini":
        remote = OpenAICompatibleModelPort(
            base_url=_required_env(env, "LLM_GEMINI_BASE_URL"),
            api_key=_required_env(env, "LLM_GEMINI_API_KEY"),
            model=_required_env(env, "LLM_GEMINI_MODEL"),
            provider="gemini",
            endpoint_class="remote",
        )
    else:
        remote = OpenAICompatibleModelPort(
            base_url=_required_env(env, "LLM_ZHIPU_BASE_URL"),
            api_key=_required_env(env, "LLM_ZHIPU_API_KEY"),
            model=_required_env(env, "LLM_ZHIPU_MODEL"),
            provider="zhipu",
            endpoint_class="remote",
        )
    if _env_bool(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        return FallbackModelPort((remote, _local_model_port(env)))
    return remote


def _local_model_port(env: Mapping[str, str]) -> ModelPort:
    provider = env.get("LLM_LOCAL_PROVIDER", "ollama").strip().lower().replace("-", "_")
    base_url = env.get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434").strip()
    model = (env.get("LLM_LOCAL_MODEL_ID") or env.get("LLM_LOCAL_MODEL") or "qwen2.5:7b").strip()
    if provider == "ollama":
        return OllamaModelPort(model=model, base_url=base_url.removesuffix("/v1"))
    if provider == "openai_compatible":
        return OpenAICompatibleModelPort(
            base_url=base_url,
            api_key=env.get("LLM_LOCAL_API_KEY", ""),
            model=model,
            provider="ollama-openai-compatible",
            endpoint_class="local",
        )
    raise ValueError(f"unsupported LLM_LOCAL_PROVIDER: {provider}")


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required model configuration: {name}")
    return value


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_failure_detail(error: StructuredModelError) -> str:
    """Retain only known transport/schema classes; never relay provider text."""

    detail = str(error)
    safe_prefixes = (
        "provider failure: ",
        "model endpoint returned HTTP ",
        "model endpoint unavailable",
        "model endpoint returned invalid JSON",
        "model endpoint returned a non-object response",
        "structured response failed ",
    )
    return detail[:200] if detail.startswith(safe_prefixes) else type(error).__name__


def _structured_json_content(content: Any) -> str:
    """Normalize a complete Markdown JSON fence while keeping schema validation strict.

    Some OpenAI-compatible providers return a complete JSON object inside a
    `````json`` fence even when ``response_format`` requests JSON Schema. This
    deliberately accepts only a *whole* fenced payload; malformed prose or a
    partial fence still reaches Pydantic as invalid JSON.
    """

    text = str(content).strip()
    if not text.startswith("```") or not text.endswith("```"):
        return text
    first_newline = text.find("\n")
    if first_newline < 0:
        return text
    language = text[3:first_newline].strip().lower()
    if language not in {"", "json", "jsonc", "application/json"}:
        return text
    return text[first_newline + 1 : -3].strip()


def _schema_failure_summary(error: Exception) -> str:
    """Expose schema failure shape without retaining response field values."""

    if isinstance(error, ValidationError):
        parts = []
        for item in error.errors()[:4]:
            location = ".".join(str(part) for part in item.get("loc", ()))
            parts.append(f"{location}:{item.get('type', 'validation_error')}")
        return ",".join(parts) or "validation_error"
    if isinstance(error, json.JSONDecodeError):
        return "invalid_json"
    return type(error).__name__


def _post_json(
    url: str,
    body: dict[str, Any],
    *,
    timeout_s: float,
    headers: dict[str, str] | None = None,
    rate_limit_retries: int = 1,
    rate_limit_backoff_s: float = 1.0,
    max_provider_retry_delay_s: float = 30.0,
    transient_retries: int = 1,
    transient_backoff_s: float = 0.5,
) -> tuple[dict[str, Any], int, int]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    rate_retries = 0
    transient_retries_used = 0
    while True:
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - configured model endpoint
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            payload = _http_error_payload(exc)
            if exc.code == 429:
                retry_hint_s = _provider_retry_hint_s(
                    exc,
                    payload,
                    max_delay_s=max_provider_retry_delay_s,
                )
                kind = _rate_limit_failure_kind(payload, retry_hint_s)
                if kind == ProviderFailureKind.RATE_LIMIT_TRANSIENT and rate_retries < rate_limit_retries:
                    rate_retries += 1
                    time.sleep(retry_hint_s if retry_hint_s is not None else rate_limit_backoff_s)
                    continue
                raise ProviderModelError(kind, retry_after_s=retry_hint_s) from exc
            if exc.code in {500, 502, 503, 504} and transient_retries_used < transient_retries:
                transient_retries_used += 1
                time.sleep(transient_backoff_s)
                continue
            if exc.code in {500, 502, 503, 504}:
                raise ProviderModelError(ProviderFailureKind.PROVIDER_CAPACITY) from exc
            raise StructuredModelError(f"model endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if transient_retries_used < transient_retries:
                transient_retries_used += 1
                time.sleep(transient_backoff_s)
                continue
            raise ProviderModelError(ProviderFailureKind.PROVIDER_CAPACITY) from exc
        except json.JSONDecodeError as exc:
            raise StructuredModelError("model endpoint returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise StructuredModelError("model endpoint returned a non-object response")
        return payload, rate_retries, transient_retries_used


def _http_error_payload(error: urllib.error.HTTPError) -> dict[str, Any]:
    """Read a bounded structured error body without retaining provider text."""

    try:
        raw = error.read(65_537)
        if len(raw) > 65_536:
            return {}
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _provider_retry_hint_s(
    error: urllib.error.HTTPError,
    payload: dict[str, Any],
    *,
    max_delay_s: float,
) -> float | None:
    retry_after = error.headers.get("Retry-After", "") if error.headers else ""
    parsed = _duration_seconds(retry_after)
    if parsed is None:
        details = (payload.get("error") or {}).get("details", []) if isinstance(payload.get("error"), dict) else []
        for detail in details if isinstance(details, list) else []:
            if not isinstance(detail, dict) or not str(detail.get("@type") or "").endswith("google.rpc.RetryInfo"):
                continue
            parsed = _duration_seconds(detail.get("retryDelay"))
            if parsed is not None:
                break
    return min(max_delay_s, max(0.0, parsed)) if parsed is not None else None


def _duration_seconds(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("s"):
            text = text[:-1]
        try:
            return float(text)
        except ValueError:
            return None
    if isinstance(value, dict):
        try:
            return float(value.get("seconds") or 0) + float(value.get("nanos") or 0) / 1_000_000_000
        except (TypeError, ValueError):
            return None
    return None


def _rate_limit_failure_kind(
    payload: dict[str, Any],
    retry_hint_s: float | None,
) -> ProviderFailureKind:
    error = payload.get("error")
    details = error.get("details", []) if isinstance(error, dict) else []
    quota_failure = any(
        isinstance(detail, dict)
        and str(detail.get("@type") or "").endswith("google.rpc.QuotaFailure")
        for detail in details if isinstance(details, list)
    )
    if quota_failure and retry_hint_s is None:
        return ProviderFailureKind.QUOTA_EXHAUSTED
    return ProviderFailureKind.RATE_LIMIT_TRANSIENT


def _raise_if_model_circuit_open(port: Any) -> None:
    remaining = float(port.circuit_open_until_monotonic) - time.monotonic()
    if remaining <= 0:
        return
    kind = port.circuit_failure_kind or ProviderFailureKind.PROVIDER_CAPACITY
    raise ProviderModelError(kind, retry_after_s=round(remaining, 3), circuit_open=True)


def _trip_model_circuit(port: Any, error: ProviderModelError, config: ModelConfig) -> None:
    hold_s = (
        config.quota_circuit_break_s
        if error.kind == ProviderFailureKind.QUOTA_EXHAUSTED
        else config.provider_circuit_break_s
    )
    if error.retry_after_s is not None:
        hold_s = max(hold_s, error.retry_after_s)
    port.circuit_failure_kind = error.kind
    port.circuit_open_until_monotonic = time.monotonic() + hold_s
