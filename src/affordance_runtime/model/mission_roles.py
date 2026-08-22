"""Model-backed MilestonePlanner and semantic Auditor adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    AuditorDecision,
    AuditorRoleRequest,
    EvidenceAssessment,
    EvidenceRequirement,
    Milestone,
    MilestoneRoadmap,
    PlannerDecision,
    PlannerRoleRequest,
    PlannerRoute,
)
from affordance_runtime.model.policy.contracts import ModelGenerationAttempt, ModelInvocationResult, ModelMetadata
from affordance_runtime.model.policy.pydantic_ai_bridge import pydantic_ai_model_from_environment
from affordance_runtime.model.providers.port import ModelConfig, ModelMessage
from affordance_runtime.model.pydantic_ai_role_invoker import PydanticAIRoleInvoker

_PLANNER_MODEL_REASON_MAX = 4_000
_PLANNER_RUNTIME_REASON_MAX = 500
_GUI_IMPLEMENTATION_REF = re.compile(
    r"(?:\b[ENFR][1-9][0-9]{0,3}\b|\bselector\b|(?:css|xpath)\s*(?:selector|=)|querySelector|\bBID\b|coordinates?)",
    re.IGNORECASE,
)
_PRESCRIBED_OPERATION = re.compile(
    r"(?:\b(?:find_controls|search_page_content|read_region|pin_fact|set_form_fields)\b|"
    r"^\s*(?:click|type|fill|press|scroll|hover|select|navigate)\b)",
    re.IGNORECASE,
)


def _load_prompt(name: str, key: str) -> tuple[str, str]:
    resource = files("affordance_runtime.model").joinpath(f"policy/prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", key}:
        raise ValueError(f"{name} has an invalid shape")
    version, prompt = str(raw["version"]), str(raw[key])
    if not version.strip() or not prompt.strip():
        raise ValueError(f"{name} is incomplete")
    return version, prompt


MILESTONE_PLANNER_PROMPT_VERSION, MILESTONE_PLANNER_INSTRUCTIONS = _load_prompt(
    "milestone_planner.yaml", "planner"
)
MISSION_AUDITOR_PROMPT_VERSION, MISSION_AUDITOR_INSTRUCTIONS = _load_prompt(
    "mission_auditor.yaml", "auditor"
)
MILESTONE_ROADMAP_SCHEMA_VERSION = "milestone-roadmap.v1"
AUDITOR_SCHEMA_VERSION = "milestone-auditor.v1"


def _business_text(value: str) -> str:
    if _GUI_IMPLEMENTATION_REF.search(value) or _PRESCRIBED_OPERATION.search(value):
        raise ValueError("roadmap fields must describe business outcomes, not GUI operations")
    return value


class EvidenceRequirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=500)

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        return _business_text(value)


class MilestoneModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_:-]{0,95}$")
    outcome: str = Field(min_length=1, max_length=500)
    done_when: str = Field(min_length=1, max_length=500)
    required_evidence: list[EvidenceRequirementModel] = Field(default_factory=list, max_length=16)
    depends_on: list[str] = Field(default_factory=list, max_length=5)
    final: bool = False

    @field_validator("outcome", "done_when")
    @classmethod
    def _validate_business_text(cls, value: str) -> str:
        return _business_text(value)


class MilestoneRoadmapModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    version: int = Field(ge=1)
    milestones: list[MilestoneModel] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def _closed_graph(self) -> MilestoneRoadmapModel:
        _lower_roadmap(self)
        return self


class PlannerDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    route: Literal["roadmap", "ask_user", "blocked"]
    roadmap: MilestoneRoadmapModel | None = None
    question: str = Field(default="", max_length=1_000)
    reason: str = Field(default="", max_length=_PLANNER_MODEL_REASON_MAX)

    @model_validator(mode="after")
    def _shape(self) -> PlannerDecisionModel:
        if self.route == "roadmap":
            if self.roadmap is None or self.question:
                raise ValueError("roadmap route requires exactly one roadmap")
        elif self.roadmap is not None:
            raise ValueError("only roadmap route can carry a roadmap")
        if self.route == "ask_user":
            if not self.question.strip():
                raise ValueError("ask_user requires a question")
        elif self.question:
            raise ValueError("only ask_user can carry a question")
        return self


class AuditorDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    assessment: Literal["satisfied", "unsatisfied", "unknown", "blocked"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _evidence_required_for_satisfaction(self) -> AuditorDecisionModel:
        if self.assessment == "satisfied" and not self.evidence_refs:
            raise ValueError("satisfied Auditor decision requires evidence refs")
        return self


def _lower_roadmap(model: MilestoneRoadmapModel) -> MilestoneRoadmap:
    return MilestoneRoadmap(
        model.version,
        tuple(
            Milestone(
                item.id,
                item.outcome,
                item.done_when,
                tuple(EvidenceRequirement(req.key, req.description) for req in item.required_evidence),
                tuple(item.depends_on),
                item.final,
            )
            for item in model.milestones
        ),
    )


@dataclass(frozen=True)
class _Invocation:
    output: BaseModel | None
    failure: ModelFailure | None
    attempts: tuple[ModelGenerationAttempt, ...] = ()


async def _invoke(
    invoker: PydanticAIRoleInvoker,
    config: ModelConfig,
    messages: tuple[ModelMessage, ...],
    schema: type[BaseModel],
    *,
    role: str,
    mode: str,
    schema_version: str,
    trigger: str,
) -> _Invocation:
    try:
        result = await invoker.invoke(
            messages=messages,
            schema=schema,
            output_tool_name=f"{role}_{mode}_output",
            config=config,
            role=role,
            mode=mode,
            schema_version=schema_version,
            trigger=trigger,
        )
    except Exception:
        return _Invocation(None, ModelFailure(ModelFailureKind.INTERNAL_ERROR, "role invocation failed", False))
    return _Invocation(result.output, result.failure, result.attempts)


def _messages(instructions: str, payload: Mapping[str, object]) -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(role="system", content=instructions),
        ModelMessage(
            role="user",
            content=json.dumps(to_json_compatible(payload), ensure_ascii=False, separators=(",", ":")),
        ),
    )


@dataclass(frozen=True)
class ModelBackedMilestonePlanner:
    invoker: PydanticAIRoleInvoker
    config: ModelConfig = field(
        default_factory=lambda: ModelConfig(
            temperature=0.0,
            max_tokens=2_048,
            timeout_s=45.0,
            prompt_version=MILESTONE_PLANNER_PROMPT_VERSION,
        )
    )
    last_invocation_result: ModelInvocationResult[PlannerDecision] | None = field(
        default=None, init=False, compare=False
    )

    def bind_attempt_sink(self, sink) -> None:
        object.__setattr__(self, "invoker", replace(self.invoker, attempt_sink=sink))

    async def plan(self, request: PlannerRoleRequest) -> ModelInvocationResult[PlannerDecision]:
        config = self.config.model_copy(
            update={
                "temperature": 0.0,
                "max_tokens": 2_048,
                "thinking_mode": "enabled" if self.invoker.supports_thinking_control else None,
            }
        )
        invocation = await _invoke(
            self.invoker,
            config,
            _planner_messages(request),
            PlannerDecisionModel,
            role="planner",
            mode=request.mode.value,
            schema_version=MILESTONE_ROADMAP_SCHEMA_VERSION,
            trigger=request.mode.value,
        )
        if invocation.failure is not None:
            return self._finish(failure=invocation.failure, attempts=invocation.attempts, config=config)
        if not isinstance(invocation.output, PlannerDecisionModel):
            return self._finish(
                failure=ModelFailure(ModelFailureKind.SCHEMA_ERROR, "planner contract invalid", False),
                attempts=invocation.attempts,
                config=config,
            )
        try:
            output = PlannerDecision(
                PlannerRoute(invocation.output.route),
                _lower_roadmap(invocation.output.roadmap) if invocation.output.roadmap is not None else None,
                invocation.output.question,
                invocation.output.reason.strip()[:_PLANNER_RUNTIME_REASON_MAX],
            )
        except (TypeError, ValueError):
            return self._finish(
                failure=ModelFailure(ModelFailureKind.SCHEMA_ERROR, "planner contract invalid", False),
                attempts=invocation.attempts,
                config=config,
            )
        return self._finish(output=output, attempts=invocation.attempts, config=config)

    def _finish(
        self,
        *,
        output: PlannerDecision | None = None,
        failure: ModelFailure | None = None,
        attempts: tuple[ModelGenerationAttempt, ...],
        config: ModelConfig,
    ) -> ModelInvocationResult[PlannerDecision]:
        result = ModelInvocationResult(
            output=output,
            failure=failure,
            metadata=_metadata(self.invoker, config, attempts, MILESTONE_ROADMAP_SCHEMA_VERSION),
            attempts=attempts,
            repair_diagnostics=_repair_diagnostics(attempts),
            diagnostics={"role": "planner", "provider_attempts": len(attempts)},
            lineage={"role": "MilestonePlanner"},
        )
        object.__setattr__(self, "last_invocation_result", result)
        return result


@dataclass(frozen=True)
class ModelBackedMissionAuditor:
    invoker: PydanticAIRoleInvoker
    config: ModelConfig = field(
        default_factory=lambda: ModelConfig(
            temperature=0.0,
            max_tokens=1_024,
            timeout_s=45.0,
            prompt_version=MISSION_AUDITOR_PROMPT_VERSION,
        )
    )
    last_invocation_result: ModelInvocationResult[AuditorDecision] | None = field(
        default=None, init=False, compare=False
    )

    def bind_attempt_sink(self, sink) -> None:
        object.__setattr__(self, "invoker", replace(self.invoker, attempt_sink=sink))

    async def audit(self, request: AuditorRoleRequest) -> ModelInvocationResult[AuditorDecision]:
        invocation = await _invoke(
            self.invoker,
            self.config,
            _auditor_messages(request),
            AuditorDecisionModel,
            role="auditor",
            mode="semantic_unknown",
            schema_version=AUDITOR_SCHEMA_VERSION,
            trigger="deterministic_admission_unknown",
        )
        failure = invocation.failure
        output = None
        if failure is None and isinstance(invocation.output, AuditorDecisionModel):
            try:
                output = AuditorDecision(
                    EvidenceAssessment(invocation.output.assessment),
                    invocation.output.evidence_refs,
                    invocation.output.reason,
                )
            except (TypeError, ValueError):
                failure = ModelFailure(ModelFailureKind.SCHEMA_ERROR, "auditor contract invalid", False)
        elif failure is None:
            failure = ModelFailure(ModelFailureKind.SCHEMA_ERROR, "auditor contract invalid", False)
        result = ModelInvocationResult(
            output=output,
            failure=failure,
            metadata=_metadata(self.invoker, self.config, invocation.attempts, AUDITOR_SCHEMA_VERSION),
            attempts=invocation.attempts,
            repair_diagnostics=_repair_diagnostics(invocation.attempts),
            diagnostics={"role": "auditor", "provider_attempts": len(invocation.attempts)},
            lineage={"role": "Auditor"},
        )
        object.__setattr__(self, "last_invocation_result", result)
        return result


def _planner_messages(request: PlannerRoleRequest) -> tuple[ModelMessage, ...]:
    payload = {
        "trigger": request.mode.value,
        "task": to_json_compatible(request.original_task),
        "mission_state": to_json_compatible(request.mission_state),
        "current_roadmap": to_json_compatible(request.current_roadmap),
        "last_typed_milestone_result_or_failure": request.last_typed_exit,
        "last_milestone_id": request.last_milestone_id,
        "remaining_mission_budget": request.remaining_mission_budget,
        "functional_regions": to_json_compatible(request.environment.functional_regions),
        "recovery": to_json_compatible(request.recovery),
    }
    return _messages(MILESTONE_PLANNER_INSTRUCTIONS, payload)


def _auditor_messages(request: AuditorRoleRequest) -> tuple[ModelMessage, ...]:
    records = tuple(
        {
            "evidence_ref": item.evidence_ref,
            "kind": item.kind,
            "value": item.value,
            "source": item.source_observation_id,
        }
        for item in request.audit_bundle.evidence_records[:128]
    )
    payload = {
        "task": to_json_compatible(request.task),
        "milestone": to_json_compatible(request.milestone),
        "mission_state": to_json_compatible(request.pre_mission_state),
        "working_facts": to_json_compatible(request.working_facts),
        "yield_reason": request.yield_reason,
        "evidence": records,
    }
    return _messages(MISSION_AUDITOR_INSTRUCTIONS, payload)


def mission_roles_from_environment(environment: Mapping[str, str] | None = None):
    configured = pydantic_ai_model_from_environment(environment)
    invoker = PydanticAIRoleInvoker(
        configured.model,
        configured.provider_id,
        configured.model_id,
        configured.endpoint_host,
        configured.provider_id == "zhipu",
    )
    return ModelBackedMilestonePlanner(invoker), ModelBackedMissionAuditor(invoker)


def mission_planner_from_environment(environment: Mapping[str, str] | None = None):
    configured = pydantic_ai_model_from_environment(environment)
    return ModelBackedMilestonePlanner(
        PydanticAIRoleInvoker(
            configured.model,
            configured.provider_id,
            configured.model_id,
            configured.endpoint_host,
            configured.provider_id == "zhipu",
        )
    )


def _metadata(port, config, attempts, schema_name: str) -> ModelMetadata:
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model_name,
        response_id=attempts[-1].response_id if attempts else "",
        endpoint_class=port.endpoint_class,
        prompt_version=config.prompt_version,
        schema_version=schema_name,
        latency_ms=sum(item.latency_ms for item in attempts),
        prompt_tokens=sum(item.prompt_tokens for item in attempts),
        completion_tokens=sum(item.completion_tokens for item in attempts),
        total_tokens=sum(item.total_tokens for item in attempts),
        rate_limit_retry_count=sum(_attempt_http_status(item) == 429 for item in attempts[1:]),
        transient_retry_count=sum(
            (status := _attempt_http_status(item)) is not None and 500 <= status < 600 for item in attempts[1:]
        ),
    )


def _attempt_http_status(attempt: ModelGenerationAttempt) -> int | None:
    value = attempt.transcript.get("error.http_status") if isinstance(attempt.transcript, Mapping) else None
    return value if isinstance(value, int) else None


def _repair_diagnostics(attempts) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "kind": "structured_output_repair",
            "phase": item.phase,
            "repair_of_attempt": item.attempt - 1,
            "attempt": item.attempt,
            "role": item.role,
            "mode": item.mode,
            "schema_version": item.schema_version,
        }
        for item in attempts
        if item.phase.endswith("output_retry")
    )
