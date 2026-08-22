"""Shared PydanticAI invocation boundary for typed mission roles."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Mapping

from pydantic import BaseModel

from affordance_runtime.agent.context.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.model.policy.contracts import ModelGenerationAttempt
from affordance_runtime.model.providers.port import ModelConfig, ModelMessage


class _RecordingModel:
    """Construct a PydanticAI wrapper lazily without importing optional APIs at import time."""

    @staticmethod
    def wrap(
        model: object,
        *,
        allow_transport_retry: bool,
        retry_backoff_s: float,
        attempt_sink: Callable[[list[tuple[list[object], object | None, BaseException | None, float]]], None] | None,
    ):
        from pydantic_ai.models.wrapper import WrapperModel

        class Recorder(WrapperModel):
            requests: list[tuple[list[object], object | None, BaseException | None, float]]

            def __init__(self, wrapped):
                super().__init__(wrapped)
                self.requests = []
                self.transport_retry_used = False

            async def request(self, messages, model_settings, model_request_parameters):
                while True:
                    started = time.perf_counter()
                    try:
                        response = await super().request(
                            messages,
                            model_settings,
                            model_request_parameters,
                        )
                    except asyncio.CancelledError as exc:
                        self.requests.append((list(messages), None, exc, (time.perf_counter() - started) * 1000))
                        if attempt_sink is not None:
                            attempt_sink(list(self.requests))
                        raise
                    except Exception as exc:
                        self.requests.append((list(messages), None, exc, (time.perf_counter() - started) * 1000))
                        if attempt_sink is not None:
                            attempt_sink(list(self.requests))
                        failure = classify_provider_failure(exc)
                        if allow_transport_retry and failure.retryable and not self.transport_retry_used:
                            self.transport_retry_used = True
                            await asyncio.sleep(retry_backoff_s)
                            continue
                        raise
                    else:
                        self.requests.append((list(messages), response, None, (time.perf_counter() - started) * 1000))
                        if attempt_sink is not None:
                            attempt_sink(list(self.requests))
                        return response

        return Recorder(model)


@dataclass(frozen=True)
class PydanticAIRoleInvocation:
    output: BaseModel | None
    failure: ModelFailure | None
    attempts: tuple[ModelGenerationAttempt, ...]


class ProviderFailureOrigin(StrEnum):
    HTTP = "http"
    MODEL_API = "model_api"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderFailure:
    kind: ModelFailureKind
    status: int | None
    origin: ProviderFailureOrigin
    retryable: bool
    provider_code: ProviderFailureCode

    def as_model_failure(self, *, retry_exhausted: bool = False) -> ModelFailure:
        return ModelFailure(
            self.kind,
            "mission role provider failed",
            self.retryable and not retry_exhausted,
            self.provider_code,
            attempt_origin=(
                ProviderAttemptOrigin.ORCHESTRATOR_TIMEOUT
                if self.origin is ProviderFailureOrigin.TIMEOUT
                else ProviderAttemptOrigin.NETWORK
                if self.origin
                in {
                    ProviderFailureOrigin.HTTP,
                    ProviderFailureOrigin.MODEL_API,
                    ProviderFailureOrigin.CONNECTION,
                }
                else ProviderAttemptOrigin.UNKNOWN
            ),
        )


@dataclass(frozen=True)
class PydanticAIRoleInvoker:
    """Invoke one role through one strict PydanticAI output tool."""

    model: object
    provider_id: str
    model_id: str
    endpoint_host: str
    supports_thinking_control: bool = False
    provider_retry_backoff_s: float = 1.0
    attempt_sink: Callable[[ModelGenerationAttempt], None] | None = None

    async def invoke(
        self,
        *,
        messages: tuple[ModelMessage, ...],
        schema: type[BaseModel],
        output_tool_name: str,
        config: ModelConfig,
        role: str,
        mode: str,
        schema_version: str,
        trigger: str = "",
    ) -> PydanticAIRoleInvocation:
        from pydantic_ai import Agent, ToolOutput
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        system = "\n\n".join(item.content for item in messages if item.role == "system")
        user = "\n\n".join(item.content for item in messages if item.role != "system")
        def persist_attempt(records):
            if self.attempt_sink is None:
                return
            try:
                attempts = _attempts(
                    config,
                    schema,
                    role,
                    mode,
                    schema_version,
                    trigger,
                    accepted=records[-1][1] is not None,
                    elapsed_ms=records[-1][3],
                    request_records=records,
                    terminal_exception=records[-1][2],
                )
                attempt = attempts[-1]
                self.attempt_sink(
                    replace(attempt, status="provider_returned")
                    if attempt.status == "accepted"
                    else attempt
                )
            except Exception:
                # Observation cannot become provider control flow.
                pass

        recording_model = _RecordingModel.wrap(
            self.model,
            allow_transport_retry=role in {"planner", "auditor"},
            retry_backoff_s=self.provider_retry_backoff_s,
            attempt_sink=persist_attempt,
        )
        agent = Agent(
            recording_model,
            name=f"mission-{role}",
            instructions=system,
            output_type=ToolOutput(
                schema,
                name=output_tool_name,
                strict=True,
                max_retries=1,
            ),
            retries={"tools": 0, "output": 1},
        )
        started = time.perf_counter()
        try:
            result = await agent.run(
                user,
                model_settings=_model_settings(config),
            )
            attempts = _attempts(
                config,
                schema,
                role,
                mode,
                schema_version,
                trigger,
                accepted=True,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                request_records=recording_model.requests,
            )
            return PydanticAIRoleInvocation(result.output, None, attempts)
        except UnexpectedModelBehavior:
            attempts = _attempts(
                config,
                schema,
                role,
                mode,
                schema_version,
                trigger,
                accepted=False,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                request_records=recording_model.requests,
            )
            return PydanticAIRoleInvocation(
                None,
                ModelFailure(ModelFailureKind.SCHEMA_ERROR, "role output invalid", False),
                attempts,
            )
        except Exception as exc:
            provider_failure = classify_provider_failure(exc)
            attempts = _attempts(
                config,
                schema,
                role,
                mode,
                schema_version,
                trigger,
                accepted=False,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                request_records=recording_model.requests,
                terminal_exception=exc,
            )
            return PydanticAIRoleInvocation(
                None,
                provider_failure.as_model_failure(
                    retry_exhausted=recording_model.transport_retry_used,
                ),
                attempts,
            )

    @property
    def provider(self) -> str:
        return self.provider_id

    @property
    def model_name(self) -> str:
        return self.model_id

    @property
    def endpoint_class(self) -> str:
        return "pydantic-ai"


def _model_settings(config: ModelConfig) -> dict[str, object]:
    settings: dict[str, object] = {
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "parallel_tool_calls": False,
    }
    if config.thinking_mode is not None:
        settings["thinking"] = config.thinking_mode == "enabled"
    return settings


def _attempts(
    config: ModelConfig,
    schema: type[BaseModel],
    role: str,
    mode: str,
    schema_version: str,
    trigger: str,
    *,
    accepted: bool,
    elapsed_ms: float,
    request_records: list[tuple[list[object], object | None, BaseException | None, float]],
    terminal_exception: BaseException | None = None,
) -> tuple[ModelGenerationAttempt, ...]:
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    attempts: list[ModelGenerationAttempt] = []
    for index, (request_messages, raw_response, request_exception, latency_ms) in enumerate(
        request_records,
        1,
    ):
        response = raw_response if isinstance(raw_response, ModelResponse) else None
        previous_failed = index > 1 and request_records[index - 2][2] is not None
        phase = (
            f"{role}_initial" if index == 1 else f"{role}_provider_retry" if previous_failed else f"{role}_output_retry"
        )
        if response is None:
            exc = request_exception or terminal_exception
            attempts.append(
                ModelGenerationAttempt(
                    attempt=index,
                    phase=phase,
                    schema_name=schema.__name__,
                    status="failed",
                    latency_ms=latency_ms,
                    exception_class=type(exc).__name__ if exc is not None else "",
                    max_output_tokens=config.max_tokens,
                    role=role,
                    mode=mode,
                    schema_version=schema_version,
                    thinking_requested=config.thinking_mode or "provider_default",
                    thinking_effective=config.thinking_mode or "provider_default",
                    trigger="provider_retry"
                    if previous_failed
                    else trigger or ("task_start" if mode == "initial_plan" else "meaningful_episode_boundary"),
                    transcript=_failure_transcript(request_messages, exc),
                )
            )
            continue
        usage = response.usage
        is_last = index == len(request_records)
        tool_call = any(isinstance(part, ToolCallPart) for part in response.parts)
        status = "accepted" if accepted and is_last else "schema_error"
        attempts.append(
            ModelGenerationAttempt(
                attempt=index,
                phase=phase,
                schema_name=schema.__name__,
                status=status,
                response_id=response.provider_response_id or "",
                latency_ms=latency_ms,
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                exception_class=(
                    type(terminal_exception).__name__ if terminal_exception is not None and is_last else ""
                ),
                finish_reason=response.finish_reason or "",
                max_output_tokens=config.max_tokens,
                final_content_present=bool(response.parts),
                role=role,
                mode=mode,
                schema_version=schema_version,
                thinking_requested=config.thinking_mode or "provider_default",
                thinking_effective=config.thinking_mode or "provider_default",
                trigger=(
                    "provider_retry"
                    if phase.endswith("provider_retry")
                    else "representation_error"
                    if phase.endswith("output_retry")
                    else trigger or ("task_start" if mode == "initial_plan" else "meaningful_episode_boundary")
                ),
                final_content_tokens=usage.output_tokens,
                final_tool_call_present=tool_call,
                transcript=_request_transcript(request_messages, response),
            )
        )
    if not attempts and terminal_exception is not None:
        attempts.append(
            ModelGenerationAttempt(
                attempt=1,
                phase=f"{role}_initial",
                schema_name=schema.__name__,
                status="failed",
                exception_class=type(terminal_exception).__name__,
                latency_ms=elapsed_ms,
                max_output_tokens=config.max_tokens,
                role=role,
                mode=mode,
                schema_version=schema_version,
                thinking_requested=config.thinking_mode or "provider_default",
                thinking_effective=config.thinking_mode or "provider_default",
                trigger=trigger or ("task_start" if mode == "initial_plan" else "meaningful_episode_boundary"),
            )
        )
    return tuple(attempts)


def _request_transcript(
    request_messages: list[object],
    response: object | None,
) -> Mapping[str, object]:
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    return {
        "llm.input_messages": ModelMessagesTypeAdapter.dump_python(
            request_messages,
            mode="json",
        ),
        "llm.output_messages": (
            ModelMessagesTypeAdapter.dump_python([response], mode="json") if response is not None else []
        ),
    }


def _failure_transcript(
    request_messages: list[object],
    error: BaseException | None,
) -> Mapping[str, object]:
    transcript = dict(_request_transcript(request_messages, None))
    transcript["error.class"] = type(error).__name__ if error is not None else ""
    transcript["error.http_status"] = _provider_status(error) if error is not None else None
    return transcript


def _provider_status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_provider_failure(exc: Exception) -> ProviderFailure:
    from pydantic_ai.exceptions import ModelAPIError

    status = _provider_status(exc)
    declared_retryable = bool(getattr(exc, "retryable", False))
    if status == 429:
        return ProviderFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            status,
            ProviderFailureOrigin.HTTP,
            True,
            ProviderFailureCode.RATE_LIMITED,
        )
    if status is not None:
        retryable = declared_retryable or 500 <= status < 600
        return ProviderFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            status,
            ProviderFailureOrigin.HTTP,
            retryable,
            ProviderFailureCode.UNAVAILABLE,
        )
    if isinstance(exc, ModelAPIError):
        return ProviderFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            None,
            ProviderFailureOrigin.MODEL_API,
            True,
            ProviderFailureCode.TRANSPORT,
        )
    if getattr(exc, "response", None) is not None:
        return ProviderFailure(
            ModelFailureKind.PROVIDER_UNAVAILABLE,
            None,
            ProviderFailureOrigin.UNKNOWN,
            declared_retryable,
            ProviderFailureCode.UNAVAILABLE,
        )
    name = type(exc).__name__.casefold()
    timeout = isinstance(exc, TimeoutError) or "timeout" in name
    connection = isinstance(exc, ConnectionError) or any(
        token in name for token in ("connection", "connecterror", "readerror")
    )
    return ProviderFailure(
        ModelFailureKind.PROVIDER_UNAVAILABLE,
        None,
        ProviderFailureOrigin.TIMEOUT
        if timeout
        else ProviderFailureOrigin.CONNECTION
        if connection
        else ProviderFailureOrigin.UNKNOWN,
        declared_retryable or timeout or connection,
        ProviderFailureCode.TIMEOUT
        if timeout
        else ProviderFailureCode.TRANSPORT
        if connection
        else ProviderFailureCode.UNAVAILABLE,
    )
