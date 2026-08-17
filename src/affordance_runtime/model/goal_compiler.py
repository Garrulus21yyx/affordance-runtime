"""Model-backed adapter for bounded, tolerant semantic GoalPlan proposals."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.goals.compiler import GoalCompilerRequest
from affordance_runtime.goals.plan import (
    MAX_GOAL_PLAN_ITEMS,
    MAX_GOAL_PLAN_TEXT_LENGTH,
    Failed,
    GoalCompilerOutcome,
    GoalPlanProposal,
    NeedsInput,
    NotRequired,
    Unsupported,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import ModelGenerationAttempt
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
    model_port_from_environment,
    structured_output_repair_contract,
)

_MAX_COMPILER_TEXT_BYTES = 16 * 1024
_MAX_PROVIDER_RETRY_DELAY_S = 5.0
_PRIVATE_TASK_KEYS = frozenset({
    "action_ref", "binding_ref", "coordinates", "dom_id", "entity_ref", "selector", "target_id",
})


def _load_prompt() -> tuple[str, str]:
    resource = files("affordance_runtime.model").joinpath("policy/prompts/goal_compiler.yaml")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", "compiler"}:
        raise ValueError("goal-compiler prompt bundle has an invalid shape")
    version, compiler = str(raw["version"]), str(raw["compiler"])
    if not version.strip() or not compiler.strip():
        raise ValueError("goal-compiler prompt bundle is incomplete")
    return version, compiler


GOAL_COMPILER_PROMPT_VERSION, GOAL_COMPILER_INSTRUCTIONS = _load_prompt()


class GoalItemModel(BaseModel):
    """Five-field model-facing item; bounded unknown descriptive fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    objective: str = Field(min_length=1, max_length=MAX_GOAL_PLAN_TEXT_LENGTH)
    done_when: str = Field(min_length=1, max_length=MAX_GOAL_PLAN_TEXT_LENGTH)
    depends_on: tuple[str, ...] = Field(default=(), max_length=MAX_GOAL_PLAN_ITEMS)
    final: bool = False


class GoalCompilerModelResponse(BaseModel):
    """Simple non-recursive provider envelope for static semantic planning."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    disposition: Literal["ready", "not_required", "needs_input", "unsupported", "failed"]
    items: tuple[GoalItemModel, ...] = Field(default=(), max_length=MAX_GOAL_PLAN_ITEMS)
    reason: str = Field(default="", max_length=160)
    question: str = Field(default="", max_length=1000)
    missing_fields: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def _shape(self) -> GoalCompilerModelResponse:
        if self.disposition == "ready":
            if not self.items or self.reason or self.question or self.missing_fields:
                raise ValueError("ready goal plan has contradictory fields")
            ids = tuple(item.id for item in self.items)
            if len(ids) != len(set(ids)):
                raise ValueError("goal plan item ids must be unique")
            known = set(ids)
            if any(dependency not in known for item in self.items for dependency in item.depends_on):
                raise ValueError("goal plan dependency is dangling")
            if any(item.id in item.depends_on for item in self.items):
                raise ValueError("goal plan item cannot depend on itself")
            if sum(item.final for item in self.items) > 1:
                raise ValueError("goal plan supports at most one final item")
            outgoing = {item_id: [] for item_id in ids}
            indegree = {item_id: 0 for item_id in ids}
            for item in self.items:
                for prerequisite in item.depends_on:
                    outgoing[prerequisite].append(item.id)
                    indegree[item.id] += 1
            pending = [item_id for item_id, count in indegree.items() if count == 0]
            visited = 0
            while pending:
                current = pending.pop()
                visited += 1
                for dependent in outgoing[current]:
                    indegree[dependent] -= 1
                    if indegree[dependent] == 0:
                        pending.append(dependent)
            if visited != len(ids):
                raise ValueError("goal plan dependencies must form a DAG")
        elif self.disposition == "needs_input":
            if self.items or self.reason or not self.question.strip() or not self.missing_fields:
                raise ValueError("needs_input goal plan has contradictory fields")
        elif self.items or self.question or self.missing_fields or not self.reason.strip():
            raise ValueError("non-ready goal plan has contradictory fields")
        return self


@dataclass(frozen=True)
class ModelBackedGoalCompiler:
    port: ModelPort
    config: ModelConfig = field(default_factory=lambda: ModelConfig(
        temperature=0.0,
        max_tokens=2048,
        timeout_s=45.0,
        rate_limit_retries=0,
        transient_retries=0,
        provider_circuit_break_s=0.0,
        prompt_version=GOAL_COMPILER_PROMPT_VERSION,
    ))
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(default=(), init=False, compare=False)
    last_schema_repair_count: int = field(default=0, init=False, compare=False)

    async def _generate_structured(
        self,
        messages: tuple[ModelMessage, ...],
        phase: str,
    ) -> GoalCompilerModelResponse:
        number = len(self.last_generation_attempts) + 1
        try:
            response = await self.port.generate_structured(messages, GoalCompilerModelResponse, self.config)
        except StructuredOutputError as error:
            self._append_attempt(number, phase, "schema_error", error)
            raise
        except Exception as error:
            self._append_attempt(number, phase, "failed", error)
            raise
        self._append_attempt(number, phase, "accepted")
        return response

    async def _generate_with_provider_retry(
        self,
        messages: tuple[ModelMessage, ...],
        phase: str,
    ) -> GoalCompilerModelResponse:
        try:
            return await self._generate_structured(messages, phase)
        except ProviderModelError as error:
            if error.kind is not ProviderFailureKind.RATE_LIMIT_TRANSIENT:
                raise
            retry_after = error.retry_after_s
            delay_s = (
                min(
                    retry_after,
                    self.config.max_provider_retry_delay_s,
                    _MAX_PROVIDER_RETRY_DELAY_S,
                )
                if retry_after is not None
                else self.config.rate_limit_backoff_s
            )
            if delay_s:
                await asyncio.sleep(delay_s)
            return await self._generate_structured(messages, f"{phase}_provider_retry")

    def _append_attempt(
        self,
        number: int,
        phase: str,
        status: str,
        error: Exception | None = None,
    ) -> None:
        record = getattr(self.port, "last_call", None)
        attempt = ModelGenerationAttempt(
            attempt=number,
            phase=phase,
            schema_name=GoalCompilerModelResponse.__name__,
            status=status,
            violations=tuple(getattr(error, "violations", ())),
            response_id=str(getattr(record, "response_id", "")),
            latency_ms=float(getattr(record, "latency_ms", 0.0)),
            prompt_tokens=int(getattr(record, "prompt_tokens", 0)),
            completion_tokens=int(getattr(record, "completion_tokens", 0)),
            total_tokens=int(getattr(record, "total_tokens", 0)),
            exception_class=type(error).__name__ if error else "",
            transcript=getattr(self.port, "last_transcript", None),
        )
        object.__setattr__(self, "last_generation_attempts", (*self.last_generation_attempts, attempt))
        object.__setattr__(self, "last_model_call_count", len(self.last_generation_attempts))

    async def compile(self, request: GoalCompilerRequest) -> GoalCompilerOutcome:
        if request.attempt == 0:
            object.__setattr__(self, "last_generation_attempts", ())
            object.__setattr__(self, "last_schema_repair_count", 0)
            object.__setattr__(self, "last_model_call_count", 0)
        messages = _compiler_messages(request)
        phase = "goal_compile_initial" if request.attempt == 0 else "goal_compile_contract_repair"
        try:
            response = await self._generate_with_provider_retry(messages, phase)
        except StructuredOutputError as error:
            if request.attempt != 0:
                return Failed(request.task.revision, "goal_compiler_model_failed")
            object.__setattr__(self, "last_schema_repair_count", 1)
            try:
                response = await self._generate_with_provider_retry(
                    _schema_repair_messages(messages, request, error),
                    "goal_compile_schema_repair",
                )
            except StructuredModelError:
                return Failed(request.task.revision, "goal_compiler_model_failed")
            except Exception:
                return Failed(request.task.revision, "goal_compiler_call_failed")
        except StructuredModelError:
            return Failed(request.task.revision, "goal_compiler_model_failed")
        except Exception:
            return Failed(request.task.revision, "goal_compiler_call_failed")
        if response.disposition == "ready":
            return GoalPlanProposal(
                request.task.revision,
                tuple(item.model_dump() for item in response.items),
            )
        if response.disposition == "not_required":
            return NotRequired(request.task.revision, response.reason)
        if response.disposition == "needs_input":
            return NeedsInput(request.task.revision, response.question, response.missing_fields)
        if response.disposition == "unsupported":
            return Unsupported(request.task.revision, response.reason)
        return Failed(request.task.revision, response.reason)


def model_goal_compiler_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    port: ModelPort | None = None,
    call_timeout_s: float = 90.0,
) -> ModelBackedGoalCompiler:
    if not 1 < call_timeout_s <= 300:
        raise ValueError("goal compiler timeout must be in (1, 300]")
    selected_port = port or model_port_from_environment(environment)
    output_mode = (
        "json_object_prompt_schema"
        if selected_port.provider.casefold() == "zhipu"
        and selected_port.model.casefold() == "glm-4.1v-thinking-flashx"
        else None
    )
    return ModelBackedGoalCompiler(
        selected_port,
        ModelConfig(
            temperature=0.0,
            max_tokens=2048,
            timeout_s=min(45.0, call_timeout_s - 0.5),
            rate_limit_retries=0,
            transient_retries=0,
            provider_circuit_break_s=0.0,
            prompt_version=GOAL_COMPILER_PROMPT_VERSION,
            structured_output_mode=output_mode,
        ),
    )


def _compiler_messages(request: GoalCompilerRequest) -> tuple[ModelMessage, ...]:
    task = request.task
    payload = {
        "request": {
            "trigger": request.trigger.value,
            "attempt": request.attempt,
            "repair_errors": request.repair_errors,
        },
        "task": {
            "instruction": task.instruction,
            "constraints": task.constraints,
            "allowed_effects": task.allowed_effects,
            "forbidden_effects": task.forbidden_effects,
            "public_inputs": _project_public_task_value(task.inputs),
            "success_criteria": _project_public_task_value(task.success_criteria),
            "requested_outputs": task.requested_outputs,
            "risk_profile": task.risk_profile.value,
        },
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > _MAX_COMPILER_TEXT_BYTES:
        raise ValueError("goal compiler public input exceeds its bounded workspace")
    return (
        ModelMessage(role="system", content=GOAL_COMPILER_INSTRUCTIONS),
        ModelMessage(role="user", content=encoded),
    )


def _schema_repair_messages(
    messages: tuple[ModelMessage, ...],
    request: GoalCompilerRequest,
    error: StructuredOutputError,
) -> tuple[ModelMessage, ...]:
    repair = {
        "repair": structured_output_repair_contract(error),
        "instruction": (
            "Return one complete GoalCompilerModelResponse replacement. "
            "Unknown descriptive fields are unnecessary; preserve only declared fields."
        ),
    }
    return (*messages, ModelMessage(role="user", content=json.dumps(repair, separators=(",", ":"), ensure_ascii=False)))


def _project_public_task_value(value: object) -> object:
    compatible = to_json_compatible(value)
    if isinstance(compatible, Mapping):
        return {
            str(key): _project_public_task_value(item)
            for key, item in compatible.items()
            if str(key).casefold() not in _PRIVATE_TASK_KEYS
        }
    if isinstance(compatible, list):
        return tuple(_project_public_task_value(item) for item in compatible)
    return compatible


__all__ = [
    "GOAL_COMPILER_INSTRUCTIONS",
    "GOAL_COMPILER_PROMPT_VERSION",
    "GoalCompilerModelResponse",
    "GoalItemModel",
    "ModelBackedGoalCompiler",
    "model_goal_compiler_from_environment",
]
