"""Unified PydanticAI transport boundary for bounded visual inference roles."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from affordance_runtime.model.policy.pydantic_ai_bridge import (
    ConfiguredPydanticAIModel,
    pydantic_ai_model_from_environment,
)
from affordance_runtime.model.providers.port import StructuredModelError

VisualOutputT = TypeVar("VisualOutputT", bound=BaseModel)


@dataclass(frozen=True)
class VisualImage:
    data: bytes = field(repr=False)
    label: str = ""

    def __post_init__(self) -> None:
        if not self.data or len(self.label) > 120:
            raise ValueError("visual image input is invalid")


class _VisualEventLoopWorker:
    """One stable async loop behind synchronous Surface visual ports."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="pydantic-ai-visual-provider",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("PydanticAI visual provider loop did not start")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        loop.run_forever()

    def submit(self, coroutine_factory: Callable[[], Any], timeout_s: float) -> Any:
        loop = self._loop
        if loop is None:
            raise RuntimeError("PydanticAI visual provider loop is unavailable")
        future = asyncio.run_coroutine_threadsafe(coroutine_factory(), loop)
        try:
            return future.result(timeout=timeout_s + 5)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError("PydanticAI visual provider deadline exceeded") from exc

    def close(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        loop.call_soon_threadsafe(loop.stop)
        self._thread.join(timeout=5)


@dataclass
class PydanticAIVisualInference:
    """Provider-neutral typed image inference over one configured PydanticAI model."""

    configured: ConfiguredPydanticAIModel = field(repr=False)
    timeout_s: float = 90.0
    _worker: _VisualEventLoopWorker | None = field(default=None, init=False, repr=False)
    _worker_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0 < self.timeout_s <= 300:
            raise ValueError("PydanticAI visual timeout must be in (0, 300]")
        if not self.configured.supports_multimodal:
            raise ValueError("PydanticAI visual role requires a multimodal model")

    @property
    def provider(self) -> str:
        return self.configured.provider_id

    @property
    def model(self) -> str:
        return self.configured.model_id

    def infer(
        self,
        output_type: type[VisualOutputT],
        *,
        system_prompt: str,
        content: Sequence[str | VisualImage],
        max_tokens: int = 2_048,
        retries: int = 1,
    ) -> VisualOutputT:
        if not system_prompt.strip() or not content or not 1 <= max_tokens <= 16_384:
            raise ValueError("PydanticAI visual inference request is invalid")
        if not 0 <= retries <= 2:
            raise ValueError("PydanticAI visual retry budget is invalid")

        async def invoke() -> VisualOutputT:
            from pydantic_ai import Agent, BinaryContent, PromptedOutput
            from pydantic_ai.exceptions import UnexpectedModelBehavior

            user_content: list[object] = []
            for item in content:
                if isinstance(item, VisualImage):
                    if item.label:
                        user_content.append(item.label)
                    user_content.append(BinaryContent(data=item.data, media_type="image/png"))
                else:
                    user_content.append(item)
            agent = Agent(
                self.configured.model,
                output_type=PromptedOutput(output_type),
                system_prompt=system_prompt,
                retries=retries,
                model_settings={
                    "temperature": 0.0,
                    "max_tokens": max_tokens,
                    "timeout": self.timeout_s,
                },
                name="visual_evidence_provider",
            )
            try:
                result = await agent.run(user_content)  # type: ignore[arg-type]
            except UnexpectedModelBehavior as exc:
                raise StructuredModelError(
                    "PydanticAI visual structured output validation failed"
                ) from exc
            output = result.output
            if not isinstance(output, output_type):
                raise StructuredModelError("PydanticAI visual output type is invalid")
            return output

        with self._worker_lock:
            if self._closed:
                raise RuntimeError("PydanticAI visual inference is closed")
            if self._worker is None:
                self._worker = _VisualEventLoopWorker()
            worker = self._worker
        return worker.submit(invoke, self.timeout_s)

    def close(self) -> None:
        with self._worker_lock:
            if self._closed:
                return
            self._closed = True
            worker = self._worker
            self._worker = None
        if worker is not None:
            worker.close()

    def __del__(self) -> None:
        self.close()


def pydantic_ai_visual_inference_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    timeout_s: float = 90.0,
) -> PydanticAIVisualInference:
    env = dict(environment or {})
    if environment is None:
        import os

        env = dict(os.environ)
    profile, model = _visual_profile(env)
    prefix = {
        "zhipu": "LLM_ZHIPU",
        "gemini": "LLM_GEMINI",
        "deepseek": "LLM_DEEPSEEK",
    }[profile]
    configured_env = {
        **env,
        "LLM_ACTIVE_PROFILE": profile,
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
        f"{prefix}_MODEL": model,
    }
    configured = pydantic_ai_model_from_environment(
        configured_env,
        call_timeout_s=timeout_s,
    )
    return PydanticAIVisualInference(configured, timeout_s)


def pydantic_ai_visual_inference_from_explicit_config(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_s: float = 90.0,
) -> PydanticAIVisualInference:
    profile = provider.strip().casefold()
    if profile not in {"zhipu", "gemini", "deepseek"}:
        raise ValueError("PydanticAI visual provider is unsupported")
    prefix = {
        "zhipu": "LLM_ZHIPU",
        "gemini": "LLM_GEMINI",
        "deepseek": "LLM_DEEPSEEK",
    }[profile]
    return pydantic_ai_visual_inference_from_environment(
        {
            "LLM_VISUAL_PROFILE": profile,
            f"{prefix}_BASE_URL": base_url,
            f"{prefix}_API_KEY": api_key,
            f"{prefix}_VISION_MODEL": model,
            f"{prefix}_MODEL": model,
        },
        timeout_s=timeout_s,
    )


def _visual_profile(environment: Mapping[str, str]) -> tuple[str, str]:
    profile = environment.get("LLM_VISUAL_PROFILE", "zhipu").strip().casefold()
    if profile == "zhipu":
        model = environment.get("LLM_ZHIPU_VISION_MODEL", "glm-4.6v-flash").strip()
    elif profile == "gemini":
        model = (
            environment.get("LLM_GEMINI_VISION_MODEL", "").strip()
            or environment.get("LLM_GEMINI_MODEL", "").strip()
        )
    elif profile == "deepseek":
        model = environment.get("LLM_DEEPSEEK_VISION_MODEL", "").strip()
    else:
        raise ValueError(f"unsupported LLM_VISUAL_PROFILE: {profile}")
    if not model:
        raise ValueError(f"missing required {profile} visual model configuration")
    return profile, model


__all__ = [
    "PydanticAIVisualInference",
    "VisualImage",
    "pydantic_ai_visual_inference_from_environment",
    "pydantic_ai_visual_inference_from_explicit_config",
]
