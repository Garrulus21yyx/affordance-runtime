"""Model-backed adapter for one bounded complete TaskGoal revision proposal."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import (
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
)
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
from affordance_runtime.task.contracts import (
    EvaluationSpec,
    LoopBudget,
    MaterialBinding,
    RiskProfile,
)
from affordance_runtime.task.intake import TaskBoundary
from affordance_runtime.task.revision import (
    RevisionFailed,
    RevisionNeedsInput,
    RevisionNewTaskSuggested,
    RevisionNoChange,
    RevisionReady,
    RevisionUnsupported,
    TaskRevisionCompilerOutcome,
    TaskRevisionProposal,
    TaskRevisionRequest,
)

_MAX_COMPILER_TEXT_BYTES = 48 * 1024
_MAX_PROVIDER_RETRY_DELAY_S = 5.0


def _load_prompt() -> tuple[str, str]:
    resource = files("affordance_runtime.model").joinpath("policy/prompts/task_revision_compiler.yaml")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", "compiler"}:
        raise ValueError("task-revision compiler prompt bundle has an invalid shape")
    version, compiler = str(raw["version"]), str(raw["compiler"])
    if not version.strip() or not compiler.strip():
        raise ValueError("task-revision compiler prompt bundle is incomplete")
    return version, compiler


TASK_REVISION_COMPILER_PROMPT_VERSION, TASK_REVISION_COMPILER_INSTRUCTIONS = _load_prompt()


class RevisionMaterialBindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1, max_length=256)
    digest: str = Field(min_length=1, max_length=512)
    media_type: str = Field(min_length=1, max_length=256)
    public_reference: str = Field(max_length=2_000)


class RevisionLoopBudgetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_turns: int = Field(ge=1, le=100)
    max_observations: int = Field(ge=1, le=400)

    @model_validator(mode="after")
    def _observations_cover_turns(self) -> RevisionLoopBudgetModel:
        if self.max_observations < self.max_turns:
            raise ValueError("revision observation budget must cover turns")
        return self


class RevisionEvaluationSpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    success_expression: dict[str, object]
    required_output_integrity: dict[str, object]
    authoritative_checks: tuple[str, ...]
    strict_source_lineage: bool


class RevisedTaskGoalModel(BaseModel):
    """Complete model-facing TaskGoal meaning without Runtime identity/revision."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    instruction: str = Field(min_length=1, max_length=16_384)
    constraints: tuple[str, ...]
    allowed_effects: tuple[str, ...]
    forbidden_effects: tuple[str, ...]
    inputs: dict[str, object]
    success_criteria: tuple[dict[str, object], ...]
    requested_outputs: tuple[str, ...]
    risk_profile: Literal["read_only", "low", "medium", "high"]
    material_bindings: tuple[RevisionMaterialBindingModel, ...]
    loop_budget: RevisionLoopBudgetModel
    evaluation_spec: RevisionEvaluationSpecModel | None

    def proposal(self) -> TaskRevisionProposal:
        evaluation = (
            EvaluationSpec(
                dict(self.evaluation_spec.success_expression),
                dict(self.evaluation_spec.required_output_integrity),
                self.evaluation_spec.authoritative_checks,
                self.evaluation_spec.strict_source_lineage,
            )
            if self.evaluation_spec is not None
            else None
        )
        return TaskRevisionProposal(
            self.instruction,
            TaskBoundary(
                constraints=self.constraints,
                allowed_effects=self.allowed_effects,
                forbidden_effects=self.forbidden_effects,
                inputs=dict(self.inputs),
                success_criteria=tuple(dict(item) for item in self.success_criteria),
                requested_outputs=self.requested_outputs,
                risk_profile=RiskProfile(self.risk_profile),
                material_bindings=tuple(
                    MaterialBinding(
                        item.name,
                        item.digest,
                        item.media_type,
                        item.public_reference,
                    )
                    for item in self.material_bindings
                ),
                loop_budget=LoopBudget(
                    self.loop_budget.max_turns,
                    self.loop_budget.max_observations,
                ),
                evaluation_spec=evaluation,
            ),
        )


class TaskRevisionCompilerModelResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    disposition: Literal[
        "ready",
        "needs_input",
        "no_change",
        "new_task_suggested",
        "unsupported",
        "failed",
    ]
    goal: RevisedTaskGoalModel | None = None
    reason: str = Field(default="", max_length=500)
    question: str = Field(default="", max_length=2_000)
    missing_fields: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def _shape(self) -> TaskRevisionCompilerModelResponse:
        if self.disposition == "ready":
            if self.goal is None or self.reason or self.question or self.missing_fields:
                raise ValueError("ready revision has contradictory fields")
        elif self.disposition == "needs_input":
            if self.goal is not None or self.reason or not self.question.strip() or not self.missing_fields:
                raise ValueError("needs-input revision has contradictory fields")
        elif self.goal is not None or self.question or self.missing_fields or not self.reason.strip():
            raise ValueError("non-ready revision has contradictory fields")
        return self


@dataclass(frozen=True)
class ModelBackedTaskRevisionCompiler:
    port: ModelPort
    config: ModelConfig = field(
        default_factory=lambda: ModelConfig(
            temperature=0.0,
            max_tokens=4096,
            timeout_s=45.0,
            rate_limit_retries=0,
            transient_retries=0,
            provider_circuit_break_s=0.0,
            prompt_version=TASK_REVISION_COMPILER_PROMPT_VERSION,
        )
    )
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(default=(), init=False, compare=False)
    last_invocation_result: ModelInvocationResult[TaskRevisionCompilerOutcome] | None = field(
        default=None, init=False, compare=False
    )
    last_schema_repair_count: int = field(default=0, init=False, compare=False)

    async def compile(self, request: TaskRevisionRequest) -> TaskRevisionCompilerOutcome:
        object.__setattr__(self, "last_generation_attempts", ())
        object.__setattr__(self, "last_invocation_result", None)
        object.__setattr__(self, "last_schema_repair_count", 0)
        object.__setattr__(self, "last_model_call_count", 0)
        messages = _compiler_messages(request)
        try:
            response = await self._generate_with_provider_retry(
                messages,
                "task_revision_compile_initial",
            )
        except StructuredOutputError as error:
            object.__setattr__(self, "last_schema_repair_count", 1)
            try:
                response = await self._generate_with_provider_retry(
                    _schema_repair_messages(messages, error),
                    "task_revision_compile_schema_repair",
                )
            except StructuredModelError:
                return self._finish(
                    RevisionFailed(
                        request.current_task.revision,
                        "task_revision_compiler_model_failed",
                    ),
                    request,
                )
            except Exception:
                return self._finish(
                    RevisionFailed(
                        request.current_task.revision,
                        "task_revision_compiler_call_failed",
                    ),
                    request,
                )
        except StructuredModelError:
            return self._finish(
                RevisionFailed(
                    request.current_task.revision,
                    "task_revision_compiler_model_failed",
                ),
                request,
            )
        except Exception:
            return self._finish(
                RevisionFailed(
                    request.current_task.revision,
                    "task_revision_compiler_call_failed",
                ),
                request,
            )
        try:
            outcome = _model_outcome(response, request)
        except (TypeError, ValueError):
            outcome = RevisionFailed(
                request.current_task.revision,
                "task_revision_proposal_invalid",
            )
        return self._finish(outcome, request)

    async def _generate_structured(
        self,
        messages: tuple[ModelMessage, ...],
        phase: str,
    ) -> TaskRevisionCompilerModelResponse:
        number = len(self.last_generation_attempts) + 1
        try:
            response = await self.port.generate_structured(
                messages,
                TaskRevisionCompilerModelResponse,
                self.config,
            )
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
    ) -> TaskRevisionCompilerModelResponse:
        try:
            return await self._generate_structured(messages, phase)
        except ProviderModelError as error:
            if error.kind is not ProviderFailureKind.RATE_LIMIT_TRANSIENT:
                raise
            delay_s = (
                min(
                    error.retry_after_s,
                    self.config.max_provider_retry_delay_s,
                    _MAX_PROVIDER_RETRY_DELAY_S,
                )
                if error.retry_after_s is not None
                else self.config.rate_limit_backoff_s
            )
            if delay_s:
                await asyncio.sleep(delay_s)
            return await self._generate_structured(
                messages,
                f"{phase}_provider_retry",
            )

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
            schema_name=TaskRevisionCompilerModelResponse.__name__,
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
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )
        object.__setattr__(self, "last_model_call_count", len(self.last_generation_attempts))

    def _finish(
        self,
        outcome: TaskRevisionCompilerOutcome,
        request: TaskRevisionRequest,
    ) -> TaskRevisionCompilerOutcome:
        attempts = self.last_generation_attempts
        result = ModelInvocationResult(
            output=outcome,
            metadata=_metadata(self.port, self.config, attempts),
            attempts=attempts,
            repair_diagnostics=(
                ({"kind": "structured_output_repair", "count": 1},) if self.last_schema_repair_count else ()
            ),
            lineage={
                "role": "TaskRevisionCompiler",
                "task_revision": request.current_task.revision,
            },
        )
        object.__setattr__(self, "last_invocation_result", result)
        return outcome


def model_task_revision_compiler_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    port: ModelPort | None = None,
    call_timeout_s: float = 90.0,
) -> ModelBackedTaskRevisionCompiler:
    if not 1 < call_timeout_s <= 300:
        raise ValueError("task revision compiler timeout must be in (1, 300]")
    selected_port = port or model_port_from_environment(environment)
    output_mode: Literal["json_object_prompt_schema"] | None = (
        "json_object_prompt_schema"
        if selected_port.provider.casefold() == "zhipu" and selected_port.model.casefold() == "glm-4.1v-thinking-flashx"
        else None
    )
    return ModelBackedTaskRevisionCompiler(
        selected_port,
        ModelConfig(
            temperature=0.0,
            max_tokens=4096,
            timeout_s=min(45.0, call_timeout_s - 0.5),
            rate_limit_retries=0,
            transient_retries=0,
            provider_circuit_break_s=0.0,
            prompt_version=TASK_REVISION_COMPILER_PROMPT_VERSION,
            structured_output_mode=output_mode,
        ),
    )


def _model_outcome(
    response: TaskRevisionCompilerModelResponse,
    request: TaskRevisionRequest,
) -> TaskRevisionCompilerOutcome:
    revision = request.current_task.revision
    if response.disposition == "ready":
        assert response.goal is not None
        return RevisionReady(revision, response.goal.proposal())
    if response.disposition == "needs_input":
        return RevisionNeedsInput(revision, response.question, response.missing_fields)
    if response.disposition == "no_change":
        return RevisionNoChange(revision, response.reason)
    if response.disposition == "new_task_suggested":
        return RevisionNewTaskSuggested(revision, response.reason)
    if response.disposition == "unsupported":
        return RevisionUnsupported(revision, response.reason)
    return RevisionFailed(revision, response.reason)


def _compiler_messages(request: TaskRevisionRequest) -> tuple[ModelMessage, ...]:
    task = request.current_task
    context = request.runtime_context
    payload = {
        "current_task": {
            "instruction": task.instruction,
            "constraints": task.constraints,
            "allowed_effects": task.allowed_effects,
            "forbidden_effects": task.forbidden_effects,
            "inputs": to_json_compatible(task.inputs),
            "success_criteria": to_json_compatible(task.success_criteria),
            "requested_outputs": task.requested_outputs,
            "risk_profile": task.risk_profile.value,
            "material_bindings": to_json_compatible(task.material_bindings),
            "loop_budget": to_json_compatible(task.loop_budget),
            "evaluation_spec": to_json_compatible(task.evaluation_spec),
            "revision": task.revision,
        },
        "conversation": {
            "turns": [
                {
                    "turn_id": turn.turn_id,
                    "role": turn.role,
                    "text": turn.text,
                }
                for turn in request.conversation.turns
            ],
            "latest_turn_id": request.conversation.latest_turn_id,
        },
        "runtime_context": {
            "pending_question": (
                {
                    "request_id": context.pending_question_id,
                    "prompt": context.pending_question,
                    "requested_fields": context.pending_question_fields,
                }
                if context.pending_question_id
                else None
            ),
            "pending_confirmation": (
                {
                    "request_id": context.pending_confirmation_id,
                    "summary": context.pending_confirmation_summary,
                    "risk": context.pending_confirmation_risk,
                }
                if context.pending_confirmation_id
                else None
            ),
        },
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > _MAX_COMPILER_TEXT_BYTES:
        raise ValueError("task revision compiler public input exceeds its bounded workspace")
    return (
        ModelMessage(role="system", content=TASK_REVISION_COMPILER_INSTRUCTIONS),
        ModelMessage(role="user", content=encoded),
    )


def _schema_repair_messages(
    messages: tuple[ModelMessage, ...],
    error: StructuredOutputError,
) -> tuple[ModelMessage, ...]:
    repair = {
        "repair": structured_output_repair_contract(error),
        "instruction": (
            "Return one complete TaskRevisionCompilerModelResponse replacement using only the declared fields."
        ),
    }
    return (
        *messages,
        ModelMessage(
            role="user",
            content=json.dumps(repair, separators=(",", ":"), ensure_ascii=False),
        ),
    )


def _metadata(
    port: ModelPort,
    config: ModelConfig,
    attempts: tuple[ModelGenerationAttempt, ...],
) -> ModelMetadata:
    last = attempts[-1] if attempts else None
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model,
        response_id=last.response_id if last is not None else "",
        endpoint_class=port.endpoint_class,
        prompt_version=config.prompt_version,
        schema_version=TaskRevisionCompilerModelResponse.__name__,
        latency_ms=sum(item.latency_ms for item in attempts),
        prompt_tokens=sum(item.prompt_tokens for item in attempts),
        completion_tokens=sum(item.completion_tokens for item in attempts),
        total_tokens=sum(item.total_tokens for item in attempts),
        rate_limit_retry_count=sum("provider_retry" in item.phase for item in attempts),
    )


__all__ = [
    "ModelBackedTaskRevisionCompiler",
    "RevisedTaskGoalModel",
    "TASK_REVISION_COMPILER_INSTRUCTIONS",
    "TASK_REVISION_COMPILER_PROMPT_VERSION",
    "TaskRevisionCompilerModelResponse",
    "model_task_revision_compiler_from_environment",
]
