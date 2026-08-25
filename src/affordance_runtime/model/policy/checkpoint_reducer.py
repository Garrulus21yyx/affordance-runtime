"""Stateless PydanticAI structured reducer for durable task conclusions."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.progress_checkpoint import (
    CheckpointReduction,
    ProgressCheckpoint,
)

CHECKPOINT_REDUCER_SCHEMA = "progress-checkpoint.v2"
CHECKPOINT_REDUCER_MAX_TOKENS = 3072
_CHECKPOINT_REDUCER_INSTRUCTIONS = """
You reduce completed task evidence into one bounded, complete working checkpoint.
Return only the structured reduce_progress_checkpoint output. You have no tools.

Fresh World is not supplied and remains authoritative. Preserve still-supported entries from
previous_checkpoint. Add only decision-relevant facts supported by supplied successful source
calls. Keep hypotheses explicitly unverified. Keep unresolved questions, the semantic next
intent, and failed strategies that should not be repeated. Do not narrate GUI actions. Do not
invent completion, selectors, grounding refs, call-local E/N/F/R refs, or facts absent from the
inputs. Source every verified fact with supplied tool_call_id/tool_name. Return unchanged only
when no durable field should change; otherwise return a complete replacement checkpoint.
""".strip()


class _ClosedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompletedToolResult(_ClosedInput):
    tool_call_id: str = Field(min_length=1, max_length=160)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: Mapping[str, object]
    outcome: str = Field(min_length=1, max_length=32)
    result: Mapping[str, object]


class RecentActionContext(_ClosedInput):
    tool_call_id: str = Field(min_length=1, max_length=160)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: Mapping[str, object]
    result: object | None = None
    reasoning: str = Field(default="", max_length=1200)


class CheckpointReducerInput(_ClosedInput):
    trigger: str = Field(min_length=1, max_length=80)
    task: Mapping[str, object]
    goal_plan: Mapping[str, object]
    previous_checkpoint: ProgressCheckpoint | None = None
    completed_results: tuple[CompletedToolResult, ...] = Field(default=(), max_length=3)
    recent_actions: tuple[RecentActionContext, ...] = Field(default=(), max_length=2)
    monitor_feedback: Mapping[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class CheckpointReducerRun:
    reduction: CheckpointReduction | None
    messages: tuple[object, ...] = ()
    error: str = ""
    prompt: str = ""
    latency_ms: float = 0.0


class CheckpointReducer(Protocol):
    async def reduce(self, value: CheckpointReducerInput) -> CheckpointReducerRun: ...


@dataclass(frozen=True)
class PydanticAICheckpointReducer:
    model: object
    timeout_s: float = 20.0

    async def reduce(self, value: CheckpointReducerInput) -> CheckpointReducerRun:
        from pydantic_ai import Agent, ToolOutput
        from pydantic_ai.usage import UsageLimits

        agent = Agent(
            self.model,
            name="progress-checkpoint-reducer",
            instructions=_CHECKPOINT_REDUCER_INSTRUCTIONS,
            output_type=ToolOutput(
                CheckpointReduction,
                name="reduce_progress_checkpoint",
                max_retries=1,
            ),
            retries=0,
        )
        prompt = json.dumps(
            to_json_compatible(value),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_s):
                result = await agent.run(
                    prompt,
                    model_settings={"max_tokens": CHECKPOINT_REDUCER_MAX_TOKENS},
                    usage_limits=UsageLimits(request_limit=2),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # provider/schema failure is non-fatal to ActionPolicy
            return CheckpointReducerRun(
                None,
                error=f"{type(exc).__name__}: {str(exc)[:360]}",
                prompt=prompt,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        reduction = result.output
        if not isinstance(reduction, CheckpointReduction):
            return CheckpointReducerRun(
                None,
                tuple(result.new_messages()),
                "untyped reducer output",
                prompt,
                (time.perf_counter() - started) * 1000,
            )
        return CheckpointReducerRun(
            reduction,
            tuple(result.new_messages()),
            prompt=prompt,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


def validate_reduction_sources(
    reduction: CheckpointReduction,
    *,
    successful_sources: Sequence[tuple[str, str]],
    previous_checkpoint: ProgressCheckpoint | None,
) -> ProgressCheckpoint | None:
    """Validate lineage without interpreting the model-authored fact semantics."""

    checkpoint = reduction.checkpoint
    if checkpoint is None:
        return None
    allowed = set(successful_sources)
    if previous_checkpoint is not None:
        allowed.update(previous_checkpoint.source_refs())
    if not checkpoint.source_refs().issubset(allowed):
        raise ValueError("checkpoint cites an unavailable or unsuccessful tool result")
    return checkpoint
