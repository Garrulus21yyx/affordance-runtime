"""Provider-neutral structured model boundary and HTTP adapters."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from time import perf_counter
from typing import Any, Literal, Mapping, Protocol, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from affordance_runtime.model.providers.capture import (
    PrivateModelCapture,
    private_capture_from_environment,
)

T = TypeVar("T", bound=BaseModel)


class ModelTextPart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=128 * 1024)


class ModelImageURLPart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["image_url"] = "image_url"
    image_url: str = Field(min_length=32, max_length=7 * 1024 * 1024)

    @field_validator("image_url")
    @classmethod
    def _bounded_data_image(cls, value: str) -> str:
        if re.fullmatch(r"data:image/(?:png|jpeg);base64,[A-Za-z0-9+/]+={0,2}", value) is None:
            raise ValueError("model image must be a bounded PNG/JPEG data URL")
        return value


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    content: str | tuple[ModelTextPart | ModelImageURLPart, ...]

    @field_validator("content")
    @classmethod
    def _content_is_nonempty(cls, value):
        if isinstance(value, str):
            if not value:
                raise ValueError("model message content cannot be empty")
            return value
        if not value or not any(isinstance(item, ModelTextPart) for item in value):
            raise ValueError("multimodal model message requires a text part")
        return tuple(value)


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
    structured_output_mode: Literal[
        "native_json_schema",
        "json_object_prompt_schema",
        "prompt_json_local_validation",
    ] | None = None


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


@dataclass(frozen=True)
class StructuredOutputViolation:
    """One bounded response-schema location safe to return to the model."""

    field_path: str
    code: str

    def __post_init__(self) -> None:
        if (
            not self.field_path
            or len(self.field_path) > 160
            or re.fullmatch(r"[$A-Za-z0-9_.\[\]-]+", self.field_path) is None
            or not self.code
            or len(self.code) > 80
            or re.fullmatch(r"[A-Za-z0-9_.-]+", self.code) is None
        ):
            raise ValueError("structured output violation is not safely bounded")


class StructuredOutputError(StructuredModelError):
    """A redacted response-content failure eligible for one bounded schema retry."""

    def __init__(
        self,
        message: str,
        *,
        violations: tuple[StructuredOutputViolation, ...] = (),
    ) -> None:
        if len(violations) > 4 or any(
            not isinstance(item, StructuredOutputViolation) for item in violations
        ):
            raise ValueError("structured output violations must be bounded and typed")
        self.violations = tuple(violations)
        super().__init__(message)


def structured_output_repair_contract(error: StructuredOutputError) -> dict[str, object]:
    """Build the one public, value-free schema-repair contract."""

    return {
        "repair_kind": "structured_output_schema",
        "violations": [
            {"field_path": item.field_path, "code": item.code}
            for item in error.violations
        ],
    }


class StructuredOutputMode(StrEnum):
    """Provider-declared mechanism for requesting one schema-valid object."""

    NATIVE_JSON_SCHEMA = "native_json_schema"
    JSON_OBJECT_PROMPT_SCHEMA = "json_object_prompt_schema"
    PROMPT_JSON_LOCAL_VALIDATION = "prompt_json_local_validation"


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

    @property
    def supports_multimodal(self) -> bool: ...

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
    supports_multimodal: bool = True
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NATIVE_JSON_SCHEMA
    thinking_mode: Literal["enabled", "disabled"] | None = None
    private_capture: PrivateModelCapture | None = field(default=None, repr=False)
    last_call: ModelCallRecord | None = field(default=None, init=False)
    last_transcript: Mapping[str, object] | None = field(default=None, init=False, repr=False)
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
        self.last_call = None
        self.last_transcript = None
        schema = output_schema.model_json_schema()
        selected_output_mode = (
            self.structured_output_mode
            if config.structured_output_mode is None
            else StructuredOutputMode(config.structured_output_mode)
        )
        request_messages = _messages_with_structured_output_contract(
            messages,
            schema,
            selected_output_mode,
        )
        serialized_messages = _serialize_openai_compatible_messages(
            request_messages,
            nested_image_url=self.provider == "zhipu",
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": serialized_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if selected_output_mode is StructuredOutputMode.NATIVE_JSON_SCHEMA:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": schema,
                },
            }
        elif selected_output_mode is StructuredOutputMode.JSON_OBJECT_PROMPT_SCHEMA:
            body["response_format"] = {"type": "json_object"}
        if self.thinking_mode is not None:
            body["thinking"] = {"type": self.thinking_mode}
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
            self._capture(
                serialized_messages,
                output_schema,
                "provider_failure",
                error=exc.kind.value,
            )
            _trip_model_circuit(self, exc, config)
            raise
        latency_ms = round((perf_counter() - started) * 1_000, 3)
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
        try:
            content = response["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
            parsed = output_schema.model_validate_json(
                _structured_json_content(content, output_schema),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            violations = _schema_failure_violations(exc)
            self._capture(
                serialized_messages,
                output_schema,
                "schema_error",
                response_content=locals().get("content"),
                response_id=str(response.get("id") or ""),
                error=_schema_failure_summary(exc),
            )
            raise StructuredOutputError(
                f"structured response failed {output_schema.__name__} validation: {_schema_failure_summary(exc)}",
                violations=violations,
            ) from exc
        self._capture(
            serialized_messages,
            output_schema,
            "accepted",
            response_content=content,
            response_id=str(response.get("id") or ""),
        )
        return parsed

    def _capture(
        self,
        messages: Sequence[ModelMessage | Mapping[str, Any]],
        output_schema: type[BaseModel],
        status: str,
        *,
        response_content: object | None = None,
        response_id: str = "",
        error: str = "",
    ) -> None:
        self.last_transcript = _openinference_llm_transcript(
            provider=self.provider,
            model=self.model,
            messages=messages,
            output_schema=output_schema,
            status=status,
            response_content=response_content,
            response_id=response_id,
            error=error,
            record=self.last_call,
        )
        if self.private_capture is not None:
            self.private_capture.record(
                provider=self.provider,
                model=self.model,
                schema_name=output_schema.__name__,
                messages=messages,
                status=status,
                response_content=response_content,
                response_id=response_id,
                error=error,
            )

@dataclass
class OllamaModelPort:
    model: str = "qwen2.5:7b"
    base_url: str = "http://127.0.0.1:11434"
    provider: str = "ollama"
    endpoint_class: str = "local"
    supports_multimodal: bool = field(default=False, init=False)
    private_capture: PrivateModelCapture | None = field(default=None, repr=False)
    last_transcript: Mapping[str, object] | None = field(default=None, init=False, repr=False)
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
        self.last_call = None
        self.last_transcript = None
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
            self._capture(messages, output_schema, "provider_failure", error=exc.kind.value)
            _trip_model_circuit(self, exc, config)
            raise
        latency_ms = round((perf_counter() - started) * 1_000, 3)
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
        try:
            content = str(response["message"]["content"])
            parsed = output_schema.model_validate_json(content)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            violations = _schema_failure_violations(exc)
            self._capture(
                messages,
                output_schema,
                "schema_error",
                response_content=locals().get("content"),
                error=_schema_failure_summary(exc),
            )
            raise StructuredOutputError(
                f"structured response failed {output_schema.__name__} validation: {_schema_failure_summary(exc)}",
                violations=violations,
            ) from exc
        self._capture(messages, output_schema, "accepted", response_content=content)
        return parsed

    def _capture(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[BaseModel],
        status: str,
        *,
        response_content: object | None = None,
        error: str = "",
    ) -> None:
        self.last_transcript = _openinference_llm_transcript(
            provider=self.provider,
            model=self.model,
            messages=messages,
            output_schema=output_schema,
            status=status,
            response_content=response_content,
            error=error,
            record=self.last_call,
        )
        if self.private_capture is not None:
            self.private_capture.record(
                provider=self.provider,
                model=self.model,
                schema_name=output_schema.__name__,
                messages=messages,
                status=status,
                response_content=response_content,
                error=error,
            )


def _openinference_llm_transcript(
    *,
    provider: str,
    model: str,
    messages: Sequence[ModelMessage | Mapping[str, Any]],
    output_schema: type[BaseModel],
    status: str,
    response_content: object | None,
    response_id: str = "",
    error: str = "",
    record: ModelCallRecord | None = None,
) -> dict[str, object]:
    """Project one provider exchange using OpenInference LLM span semantics."""

    input_messages = [
        dict(message) if isinstance(message, Mapping) else message.model_dump()
        for message in messages
    ]
    output_messages = (
        [{"role": "assistant", "content": response_content}]
        if response_content is not None
        else []
    )
    return {
        "openinference.span.kind": "LLM",
        "llm.system": provider,
        "llm.model_name": model,
        "llm.input_messages": input_messages,
        "llm.output_messages": output_messages,
        "llm.tools": [{"tool.json_schema": output_schema.model_json_schema()}],
        "llm.token_count.prompt": int(getattr(record, "prompt_tokens", 0)),
        "llm.token_count.completion": int(getattr(record, "completion_tokens", 0)),
        "llm.token_count.total": int(getattr(record, "total_tokens", 0)),
        "response.id": response_id,
        "status": status,
        "error": error,
    }

def _messages_with_structured_output_contract(
    messages: Sequence[ModelMessage],
    schema: Mapping[str, Any],
    mode: StructuredOutputMode,
) -> tuple[ModelMessage, ...]:
    if mode is StructuredOutputMode.NATIVE_JSON_SCHEMA:
        return tuple(messages)
    encoded_schema = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    contract = (
        "Return exactly one JSON object and no Markdown or explanatory text. "
        "Return a data instance that satisfies the schema, never the JSON Schema definition itself. "
        "Do not copy schema keywords such as oneOf, properties, required, const, or type into the "
        "response unless the schema explicitly declares one of them as a data property. "
        "Unknown fields are forbidden. JSON Schema: "
        f"{encoded_schema}"
    )
    if messages and messages[0].role == "system" and isinstance(messages[0].content, str):
        return (
            ModelMessage(
                role="system",
                content=f"{messages[0].content}\n\n{contract}",
            ),
            *messages[1:],
        )
    instruction = ModelMessage(role="system", content=contract)
    return (instruction, *messages)


def _serialize_openai_compatible_messages(
    messages: Sequence[ModelMessage],
    *,
    nested_image_url: bool,
) -> list[dict[str, Any]]:
    serialized = [message.model_dump() for message in messages]
    if not nested_image_url:
        return serialized
    for message in serialized:
        content = message.get("content")
        if not isinstance(content, (list, tuple)):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            image_url = part.get("image_url")
            if isinstance(image_url, str):
                part["image_url"] = {"url": image_url}
    return serialized


def _zhipu_model_supports_multimodal(model: str) -> bool:
    """Recognize the declared GLM visual-model naming families fail-closed."""

    normalized = model.strip().casefold()
    return re.match(r"^glm-\d+(?:\.\d+)?v(?:-|$)", normalized) is not None


def model_port_from_environment(environment: Mapping[str, str] | None = None) -> ModelPort:
    """Build the selected model profile, optionally falling back to local.

    The process environment is read only when no explicit mapping is supplied;
    loading a dotenv file remains the caller's responsibility.
    """

    env = os.environ if environment is None else environment
    private_capture = private_capture_from_environment(env)
    active_profile = env.get("LLM_ACTIVE_PROFILE", "local").strip().lower()
    if active_profile == "local":
        return _local_model_port(env, private_capture)
    if active_profile not in {"mistral", "gemini", "zhipu"}:
        raise ValueError(f"unsupported LLM_ACTIVE_PROFILE: {active_profile}")
    if active_profile == "mistral":
        remote = OpenAICompatibleModelPort(
            base_url=_required_env(env, "LLM_MISTRAL_BASE_URL"),
            api_key=_required_env(env, "LLM_MISTRAL_API_KEY"),
            model=_required_env(env, "LLM_MISTRAL_MODEL"),
            provider="mistral",
            endpoint_class="remote",
            private_capture=private_capture,
        )
    elif active_profile == "gemini":
        remote = OpenAICompatibleModelPort(
            base_url=_required_env(env, "LLM_GEMINI_BASE_URL"),
            api_key=_required_env(env, "LLM_GEMINI_API_KEY"),
            model=_required_env(env, "LLM_GEMINI_MODEL"),
            provider="gemini",
            endpoint_class="remote",
            private_capture=private_capture,
        )
    else:
        model = _required_env(env, "LLM_ZHIPU_MODEL")
        supports_multimodal = _zhipu_model_supports_multimodal(model)
        remote = OpenAICompatibleModelPort(
            base_url=_required_env(env, "LLM_ZHIPU_BASE_URL"),
            api_key=_required_env(env, "LLM_ZHIPU_API_KEY"),
            model=model,
            provider="zhipu",
            endpoint_class="remote",
            supports_multimodal=supports_multimodal,
            structured_output_mode=(
                StructuredOutputMode.PROMPT_JSON_LOCAL_VALIDATION
                if supports_multimodal
                else StructuredOutputMode.JSON_OBJECT_PROMPT_SCHEMA
            ),
            thinking_mode=None if supports_multimodal else "disabled",
            private_capture=private_capture,
        )
    if _env_bool(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("automatic model profile fallback is not supported")
    return remote


def _local_model_port(
    env: Mapping[str, str],
    private_capture: PrivateModelCapture | None = None,
) -> ModelPort:
    provider = env.get("LLM_LOCAL_PROVIDER", "ollama").strip().lower().replace("-", "_")
    base_url = env.get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434").strip()
    model = (env.get("LLM_LOCAL_MODEL_ID") or env.get("LLM_LOCAL_MODEL") or "qwen2.5:7b").strip()
    if provider == "ollama":
        return OllamaModelPort(
            model=model,
            base_url=base_url.removesuffix("/v1"),
            private_capture=private_capture,
        )
    if provider == "openai_compatible":
        return OpenAICompatibleModelPort(
            base_url=base_url,
            api_key=env.get("LLM_LOCAL_API_KEY", ""),
            model=model,
            provider="ollama-openai-compatible",
            endpoint_class="local",
            private_capture=private_capture,
        )
    raise ValueError(f"unsupported LLM_LOCAL_PROVIDER: {provider}")


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required model configuration: {name}")
    return value


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _structured_json_content(
    content: Any,
    output_schema: type[BaseModel] | None = None,
) -> str:
    """Normalize a complete Markdown JSON fence while keeping schema validation strict.

    Some OpenAI-compatible providers return a complete JSON object inside a
    `````json`` fence even when ``response_format`` requests JSON Schema. This
    deliberately accepts only a *whole* fenced payload; malformed prose or a
    partial fence still reaches Pydantic as invalid JSON.
    """

    text = str(content).strip()
    if text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        if first_newline >= 0:
            language = text[3:first_newline].strip().lower()
            if language in {"", "json", "jsonc", "application/json"}:
                text = text[first_newline + 1 : -3].strip()
    text = _strip_surplus_closing_braces(text)
    if output_schema is None:
        return text
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return text
    if not isinstance(value, dict) or len(value) != 1:
        return text
    wrapper_name, wrapped = next(iter(value.items()))
    if wrapper_name not in _schema_wrapper_names(output_schema) or not isinstance(wrapped, dict):
        return text
    return json.dumps(wrapped, ensure_ascii=False, separators=(",", ":"))


def _strip_surplus_closing_braces(text: str) -> str:
    """Accept one complete object followed only by redundant closing braces."""

    try:
        value, end = json.JSONDecoder(
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        ).raw_decode(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text
    trailing = text[end:].strip()
    if isinstance(value, dict) and trailing and set(trailing) == {"}"}:
        return text[:end]
    return text


def _schema_wrapper_names(output_schema: type[BaseModel]) -> frozenset[str]:
    names = {
        item.__name__
        for item in output_schema.mro()
        if isinstance(item, type) and issubclass(item, BaseModel) and item is not BaseModel
    }
    try:
        title = output_schema.model_json_schema().get("title")
    except (AttributeError, TypeError, ValueError):
        title = None
    if isinstance(title, str) and title:
        names.add(title)
    return frozenset({*names, *(_snake_case(name) for name in names)})


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate structured response key")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard structured response constant: {value}")


def _schema_failure_summary(error: Exception) -> str:
    """Expose schema failure shape without retaining response field values."""

    violations = _schema_failure_violations(error)
    if violations:
        return ",".join(f"{item.field_path}:{item.code}" for item in violations)
    return type(error).__name__


def _schema_failure_violations(error: Exception) -> tuple[StructuredOutputViolation, ...]:
    if isinstance(error, ValidationError):
        violations: list[StructuredOutputViolation] = []
        for item in error.errors():
            context = item.get("ctx")
            field_paths = context.get("field_paths") if isinstance(context, dict) else None
            argument_code = context.get("argument_code") if isinstance(context, dict) else None
            if isinstance(field_paths, tuple | list) and field_paths:
                violations.extend(
                    StructuredOutputViolation(
                        _safe_schema_token(str(path), "$", 160),
                        _safe_schema_token(str(argument_code or item.get("type")), "validation_error", 80),
                    )
                    for path in field_paths
                )
            else:
                violations.append(StructuredOutputViolation(
                    _safe_schema_token(".".join(str(part) for part in item.get("loc", ())), "$", 160),
                    _safe_schema_token(str(item.get("type") or "validation_error"), "validation_error", 80),
                ))
            if len(violations) >= 4:
                break
        return tuple(violations[:4])
    if isinstance(error, json.JSONDecodeError):
        return (StructuredOutputViolation("$", "invalid_json"),)
    return ()


def _safe_schema_token(value: str, fallback: str, limit: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.\[\]$-]+", "_", value).strip("_")
    return (normalized or fallback)[:limit]


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
        isinstance(detail, dict) and str(detail.get("@type") or "").endswith("google.rpc.QuotaFailure")
        for detail in details
        if isinstance(details, list)
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
    if error.kind is not ProviderFailureKind.QUOTA_EXHAUSTED and config.provider_circuit_break_s <= 0:
        # Zero delegates transient recovery to the caller. Retry-After remains
        # failure data and must not silently recreate a second recovery owner.
        return
    hold_s = (
        config.quota_circuit_break_s
        if error.kind == ProviderFailureKind.QUOTA_EXHAUSTED
        else config.provider_circuit_break_s
    )
    if error.retry_after_s is not None:
        hold_s = max(hold_s, error.retry_after_s)
    port.circuit_failure_kind = error.kind
    port.circuit_open_until_monotonic = time.monotonic() + hold_s
