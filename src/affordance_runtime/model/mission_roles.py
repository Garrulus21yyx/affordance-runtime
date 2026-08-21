"""Model-backed Manager and Auditor role adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from affordance_runtime.actions import INTERACTION_CAPABILITY_REGISTRY, ActionSpaceBuilder
from affordance_runtime.actions.paging import delivery_descriptor_matches
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.contracts import AgentSubtaskContractView, sanitize_history_value
from affordance_runtime.agent.context.episode_history import (
    EpisodeHistoryCapacityError,
    render_episode_history,
)
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    AuditorDecision,
    AuditorRoleRequest,
    EvidenceRequirement,
    ManagerAssessment,
    ManagerDecision,
    ManagerRequestMode,
    ManagerRoleRequest,
    ManagerRoute,
    RecoveryKind,
    SubtaskContract,
    SubtaskOutcomeKind,
    WorkingFactProposal,
    WorkingOutcomeProposal,
)
from affordance_runtime.model.policy.contracts import (
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
)
from affordance_runtime.model.policy.grounded_tool_catalog import GroundedLocalToolName
from affordance_runtime.model.policy.pydantic_ai_bridge import (
    pydantic_ai_model_from_environment,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBreakdown,
    ModelRequestBudget,
    ModelRequestCapacityError,
    admit_model_request,
    request_breakdown_diagnostics,
)
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ModelMessage,
)
from affordance_runtime.model.pydantic_ai_role_invoker import PydanticAIRoleInvoker
from affordance_runtime.task.contracts import TaskGoal

_AUDIT_HISTORY_BYTES = 16 * 1024
_AUDIT_RENDERED_WORLD_BYTES = 128 * 1024
_MANAGER_MODEL_REASON_MAX = 4_000
_MANAGER_RUNTIME_REASON_MAX = 500
_ACTION_POLICY_IDENTIFIERS = frozenset({
    *(item.semantic_action for item in INTERACTION_CAPABILITY_REGISTRY.definitions),
    *(item.value for item in GroundedLocalToolName),
})
_ACTION_POLICY_IDENTIFIER_PATTERN = (
    r"(?:"
    + "|".join(re.escape(item) for item in sorted(_ACTION_POLICY_IDENTIFIERS))
    + r")"
)
_CODE_STYLE_IDENTIFIER_PATTERN = (
    r"(?:"
    + "|".join(
        re.escape(item) for item in sorted(_ACTION_POLICY_IDENTIFIERS) if "_" in item
    )
    + r")"
)
_PRESCRIBED_IDENTIFIER = re.compile(
    r"(?:\b(?:use|call|invoke|run)\s+(?:"
    + _CODE_STYLE_IDENTIFIER_PATTERN
    + r"\b|the\s+"
    + _ACTION_POLICY_IDENTIFIER_PATTERN
    + r"\s+(?:tool|command|operation)\b)|\b(?:tool|command|operation)\s+"
    + _ACTION_POLICY_IDENTIFIER_PATTERN
    + r"\b|`"
    + _ACTION_POLICY_IDENTIFIER_PATTERN
    + r"`)",
    re.IGNORECASE,
)
_TOOL_CALL_SYNTAX = re.compile(
    r"\b" + _ACTION_POLICY_IDENTIFIER_PATTERN + r"\s*\(",
    re.IGNORECASE,
)
_GUI_IMPLEMENTATION_REF = re.compile(
    r"(?:\b[ENFR][1-9][0-9]{0,3}\b|(?:css|xpath)\s*(?:selector|=)|querySelector)",
    re.IGNORECASE,
)


def _manager_semantic_text(value: str) -> str:
    if (
        _PRESCRIBED_IDENTIFIER.search(value)
        or _TOOL_CALL_SYNTAX.search(value)
        or _GUI_IMPLEMENTATION_REF.search(value)
    ):
        raise ValueError("subtask contract must describe business outcomes, not implementation steps")
    return value


def _load_prompt(name: str, key: str) -> tuple[str, str]:
    resource = files("affordance_runtime.model").joinpath(f"policy/prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", key}:
        raise ValueError(f"{name} has an invalid shape")
    version, prompt = str(raw["version"]), str(raw[key])
    if not version.strip() or not prompt.strip():
        raise ValueError(f"{name} is incomplete")
    return version, prompt


MISSION_MANAGER_PROMPT_VERSION, MISSION_MANAGER_INSTRUCTIONS = _load_prompt(
    "mission_manager.yaml", "manager"
)
MISSION_AUDITOR_PROMPT_VERSION, MISSION_AUDITOR_INSTRUCTIONS = _load_prompt(
    "mission_auditor.yaml", "auditor"
)
INITIAL_MANAGER_SCHEMA_VERSION = "initial-manager-decision.v2"
REVIEW_MANAGER_SCHEMA_VERSION = "review-manager-decision.v2"


class EvidenceRequirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=500)

    @field_validator("description")
    @classmethod
    def _business_evidence_only(cls, value: str) -> str:
        return _manager_semantic_text(value)


class SubtaskContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    objective: str = Field(min_length=1, max_length=500)
    done_when: str = Field(min_length=1, max_length=500)
    task_link: str = Field(min_length=1, max_length=500)
    outcome_kind: Literal["state_change", "evidence_packet"] = "state_change"
    constraints: tuple[str, ...] = Field(default=(), max_length=32)
    relevant_fact_keys: tuple[str, ...] = Field(default=(), max_length=32)
    required_evidence: tuple[EvidenceRequirementModel, ...] = Field(default=(), max_length=32)
    episode_turn_budget: int = Field(default=15, ge=1, le=15)
    related_audit_ids: tuple[str, ...] = Field(default=(), max_length=32)

    @field_validator("objective", "done_when", "task_link")
    @classmethod
    def _semantic_text_not_tool_identifier(cls, value: str) -> str:
        return _manager_semantic_text(value)

    @field_validator("constraints")
    @classmethod
    def _semantic_constraints(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_manager_semantic_text(value) for value in values)

    @model_validator(mode="after")
    def _outcome_shape(self) -> SubtaskContractModel:
        if self.outcome_kind == "evidence_packet" and not self.required_evidence:
            raise ValueError("evidence_packet requires at least one EvidenceRequirement")
        return self


class InitialManagerDecisionModel(BaseModel):
    """Initial-only model output; Runtime owns mode and assessment lowering."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    route: Literal["execute_subtask", "ask_user", "blocked"]
    subtask: SubtaskContractModel | None = None
    question: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=_MANAGER_MODEL_REASON_MAX)

    @model_validator(mode="after")
    def _shape(self) -> InitialManagerDecisionModel:
        if self.route == "execute_subtask":
            if self.subtask is None or self.question:
                raise ValueError("execute_subtask requires exactly one subtask")
        elif self.subtask is not None:
            raise ValueError("only execute_subtask can carry subtask")
        if self.route == "ask_user":
            if not self.question.strip():
                raise ValueError("ask_user requires a question")
        elif self.question:
            raise ValueError("only ask_user can carry a question")
        return self


class ReviewManagerDecisionModel(BaseModel):
    """Episode-review output with cited working proposals and one next route."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    assessment: Literal["satisfied", "unsatisfied", "unknown", "blocked"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    working_outcomes: tuple["WorkingOutcomeProposalModel", ...] = Field(default=(), max_length=32)
    working_facts: tuple["WorkingFactProposalModel", ...] = Field(default=(), max_length=32)
    invalidate_fact_keys: tuple[str, ...] = Field(default=(), max_length=32)
    route: Literal["execute_subtask", "ask_user", "blocked", "request_finalization"]
    subtask: SubtaskContractModel | None = None
    question: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=_MANAGER_MODEL_REASON_MAX)
    final_response: object | None = None
    final_response_evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def _shape(self) -> ReviewManagerDecisionModel:
        if self.route == "execute_subtask":
            if self.subtask is None or self.question:
                raise ValueError("execute_subtask requires exactly one subtask")
        elif self.subtask is not None:
            raise ValueError("only execute_subtask can carry subtask")
        if self.route == "ask_user":
            if not self.question.strip():
                raise ValueError("ask_user requires a question")
        elif self.question:
            raise ValueError("only ask_user can carry a question")
        if self.route == "request_finalization":
            if (
                self.assessment != "satisfied"
                or self.final_response is None
                or not self.final_response_evidence_refs
            ):
                raise ValueError(
                    "request_finalization requires satisfied assessment, direct final_response, and evidence"
                )
        elif self.final_response is not None or self.final_response_evidence_refs:
            raise ValueError("only request_finalization can carry final response fields")
        if self.assessment == "blocked" and self.route != "blocked":
            raise ValueError("blocked assessment requires blocked route")
        return self


class WorkingOutcomeProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    outcome_id: str = Field(min_length=1, max_length=96)
    assessment: Literal["satisfied", "unsatisfied"]
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=32)
    summary: str = Field(min_length=1, max_length=500)


class WorkingFactProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    evidence_ref: str = Field(min_length=1, max_length=512)
    purpose: str = Field(min_length=1, max_length=500)


class AuditorDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    assessment: Literal["satisfied", "unsatisfied", "unknown", "blocked"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    reason: str = Field(default="", max_length=500)


class RoleInputCapacityError(ValueError):
    """A role input cannot fit the declared bounded model context."""


@dataclass(frozen=True)
class _StructuredRoleInvocation:
    output: BaseModel | None
    failure: ModelFailure | None
    attempts: tuple[ModelGenerationAttempt, ...] = ()
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    public_evidence_refs: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _RolePrompt:
    messages: tuple[ModelMessage, ...]
    component_payloads: Mapping[str, object]
    public_evidence_refs: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _AuditWorldProjection:
    payload: Mapping[str, object]
    public_evidence_refs: Mapping[str, str]


async def _invoke_structured_role(
    invoker: PydanticAIRoleInvoker,
    config: ModelConfig,
    message_factory: Callable[[], _RolePrompt],
    schema: type[BaseModel],
    initial_phase: str,
    request_budget: ModelRequestBudget | None = None,
    *,
    role: str = "",
    mode: str = "",
    schema_version: str = "",
    trigger: str = "",
) -> _StructuredRoleInvocation:
    attempts: tuple[ModelGenerationAttempt, ...] = ()
    try:
        prompt = message_factory()
    except RoleInputCapacityError:
        return _StructuredRoleInvocation(None, ModelFailure(ModelFailureKind.INTERNAL_ERROR, "context_capacity", False))
    except Exception:
        return _StructuredRoleInvocation(None, ModelFailure(ModelFailureKind.INTERNAL_ERROR, "role input construction failed", False))
    try:
        admitted = admit_model_request(
            messages=prompt.messages,
            tools=(),
            budget=request_budget or ModelRequestBudget(max_output_tokens=config.max_tokens),
            phase=initial_phase,
            component_payloads=prompt.component_payloads,
        )
        messages = admitted.messages
        breakdowns = (admitted.breakdown,)
        diagnostics = _role_request_diagnostics(breakdowns, provider_attempts=0)
    except ModelRequestCapacityError as exc:
        return _StructuredRoleInvocation(
            None,
            ModelFailure(ModelFailureKind.CONTEXT_CAPACITY, "context_capacity", False),
            diagnostics=_role_request_diagnostics((exc.breakdown,), provider_attempts=0),
            public_evidence_refs=prompt.public_evidence_refs,
        )
    try:
        result = await invoker.invoke(
            messages=messages,
            schema=schema,
            output_tool_name=_role_output_tool_name(role, mode),
            config=config,
            role=role,
            mode=mode,
            schema_version=schema_version,
            trigger=trigger,
        )
    except Exception:
        return _StructuredRoleInvocation(
            None,
            ModelFailure(ModelFailureKind.INTERNAL_ERROR, "role invocation failed", False),
            attempts,
            diagnostics=diagnostics,
            public_evidence_refs=prompt.public_evidence_refs,
        )
    attempts = result.attempts
    diagnostics = _role_request_diagnostics(breakdowns, provider_attempts=len(attempts))
    if result.failure is not None:
        return _StructuredRoleInvocation(
            None,
            result.failure,
            attempts,
            diagnostics=diagnostics,
            public_evidence_refs=prompt.public_evidence_refs,
        )
    return _StructuredRoleInvocation(
        result.output,
        None,
        attempts,
        diagnostics=diagnostics,
        public_evidence_refs=prompt.public_evidence_refs,
    )


def _role_output_tool_name(role: str, mode: str) -> str:
    suffix = mode or "decision"
    return f"{role}_{suffix}_output"


def _role_request_diagnostics(
    breakdowns: tuple[ModelRequestBreakdown, ...],
    *,
    provider_attempts: int,
) -> dict[str, object]:
    diagnostics = request_breakdown_diagnostics(breakdowns)
    diagnostics["role"] = _role_from_phase(breakdowns[-1].phase)
    diagnostics["provider_attempts"] = provider_attempts
    return diagnostics


def _role_from_phase(phase: str) -> str:
    return phase.split("_", 1)[0] if "_" in phase else phase


@dataclass(frozen=True)
class ModelBackedMissionManager:
    invoker: PydanticAIRoleInvoker
    config: ModelConfig = field(default_factory=lambda: ModelConfig(
        temperature=0.0,
        max_tokens=2048,
        timeout_s=45.0,
        prompt_version=MISSION_MANAGER_PROMPT_VERSION,
    ))
    request_budget: ModelRequestBudget | None = None
    last_invocation_result: ModelInvocationResult[ManagerDecision] | None = field(
        default=None, init=False, compare=False
    )
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(
        default=(), init=False, compare=False
    )
    last_role_diagnostics: Mapping[str, object] = field(default_factory=dict, init=False, compare=False)

    async def decide(self, request: ManagerRoleRequest) -> ModelInvocationResult[ManagerDecision]:
        object.__setattr__(self, "last_generation_attempts", ())
        schema, schema_version = _manager_output_contract(request.mode)
        config = _manager_config(self.invoker, self.config)
        invocation = await _invoke_structured_role(
            self.invoker,
            config,
            lambda: _manager_messages(request),
            schema,
            "manager_initial",
            self.request_budget,
            role="manager",
            mode=request.mode.value,
            schema_version=schema_version,
            trigger=_manager_trigger(request),
        )
        object.__setattr__(self, "last_generation_attempts", invocation.attempts)
        object.__setattr__(self, "last_role_diagnostics", invocation.diagnostics)
        if invocation.failure is not None:
            return self._finish_failure(invocation.failure, config, schema_version)
        response = invocation.output
        try:
            output = _lower_manager_decision(
                request.mode,
                response,
                invocation.public_evidence_refs,
            )
        except (TypeError, ValueError):
            return self._finish_failure(
                ModelFailure(ModelFailureKind.SCHEMA_ERROR, "manager contract invalid", False),
                config,
                schema_version,
            )
        return self._finish_output(output, "Manager", config, schema_version)

    def _finish_output(
        self,
        output: ManagerDecision,
        role: str,
        config: ModelConfig,
        schema_version: str,
    ) -> ModelInvocationResult[ManagerDecision]:
        invocation = ModelInvocationResult(
            output=output,
            metadata=_metadata(self.invoker, config, self.last_generation_attempts, schema_version),
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            diagnostics=self.last_role_diagnostics,
            lineage={"role": role},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _finish_failure(
        self,
        failure: ModelFailure,
        config: ModelConfig,
        schema_version: str,
    ) -> ModelInvocationResult[ManagerDecision]:
        invocation = ModelInvocationResult(
            failure=failure,
            metadata=_metadata(
                self.invoker,
                config,
                self.last_generation_attempts,
                schema_version,
            ),
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            diagnostics=self.last_role_diagnostics,
            lineage={"role": "Manager"},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation


@dataclass(frozen=True)
class ModelBackedMissionAuditor:
    invoker: PydanticAIRoleInvoker
    config: ModelConfig = field(default_factory=lambda: ModelConfig(
        temperature=0.0,
        max_tokens=2048,
        timeout_s=45.0,
        prompt_version=MISSION_AUDITOR_PROMPT_VERSION,
    ))
    request_budget: ModelRequestBudget | None = None
    last_invocation_result: ModelInvocationResult[AuditorDecision] | None = field(
        default=None, init=False, compare=False
    )
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(
        default=(), init=False, compare=False
    )
    last_role_diagnostics: Mapping[str, object] = field(default_factory=dict, init=False, compare=False)

    async def audit(self, request: AuditorRoleRequest) -> ModelInvocationResult[AuditorDecision]:
        object.__setattr__(self, "last_generation_attempts", ())
        invocation = await _invoke_structured_role(
            self.invoker,
            self.config,
            lambda: _auditor_messages(request),
            AuditorDecisionModel,
            "auditor_initial",
            self.request_budget,
            role="auditor",
            schema_version=AuditorDecisionModel.__name__,
            trigger="strict_exceptional_claim",
        )
        object.__setattr__(self, "last_generation_attempts", invocation.attempts)
        object.__setattr__(self, "last_role_diagnostics", invocation.diagnostics)
        if invocation.failure is not None:
            return self._finish_failure(invocation.failure)
        response = invocation.output
        assert isinstance(response, AuditorDecisionModel)
        try:
            output = AuditorDecision(
                ManagerAssessment(response.assessment),
                _canonical_evidence_refs(response.evidence_refs, invocation.public_evidence_refs),
                response.reason,
            )
        except (TypeError, ValueError):
            return self._finish_failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "auditor contract invalid", False))
        return self._finish_output(output, "Auditor")

    def _finish_output(self, output: AuditorDecision, role: str) -> ModelInvocationResult[AuditorDecision]:
        invocation = ModelInvocationResult(
            output=output,
            metadata=_metadata(self.invoker, self.config, self.last_generation_attempts, AuditorDecisionModel.__name__),
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            diagnostics=self.last_role_diagnostics,
            lineage={"role": role},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _finish_failure(self, failure: ModelFailure) -> ModelInvocationResult[AuditorDecision]:
        invocation = ModelInvocationResult(
            failure=failure,
            metadata=_metadata(
                self.invoker,
                self.config,
                self.last_generation_attempts,
                AuditorDecisionModel.__name__,
            ),
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            diagnostics=self.last_role_diagnostics,
            lineage={"role": "Auditor"},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation


def mission_roles_from_environment(environment: Mapping[str, str] | None = None):
    configured = pydantic_ai_model_from_environment(environment)
    invoker = PydanticAIRoleInvoker(
        configured.model,
        configured.provider_id,
        configured.model_id,
        configured.endpoint_host,
        configured.provider_id == "zhipu",
    )
    return ModelBackedMissionManager(invoker), ModelBackedMissionAuditor(invoker)


def mission_manager_from_environment(environment: Mapping[str, str] | None = None):
    configured = pydantic_ai_model_from_environment(environment)
    return ModelBackedMissionManager(PydanticAIRoleInvoker(
        configured.model,
        configured.provider_id,
        configured.model_id,
        configured.endpoint_host,
        configured.provider_id == "zhipu",
    ))


def _manager_output_contract(
    mode: ManagerRequestMode,
) -> tuple[type[BaseModel], str]:
    if mode is ManagerRequestMode.INITIAL_PLAN:
        return InitialManagerDecisionModel, INITIAL_MANAGER_SCHEMA_VERSION
    if mode is ManagerRequestMode.REVIEW_AND_ROUTE:
        return ReviewManagerDecisionModel, REVIEW_MANAGER_SCHEMA_VERSION
    raise ValueError("unsupported Manager request mode")


def _manager_config(invoker: PydanticAIRoleInvoker, config: ModelConfig) -> ModelConfig:
    """Request disabled thinking only through a provider-declared capability."""

    thinking_mode = (
        "disabled"
        if invoker.supports_thinking_control
        else None
    )
    return config.model_copy(update={
        "temperature": 0.0,
        "max_tokens": 2048,
        "thinking_mode": thinking_mode,
    })


def _manager_trigger(request: ManagerRoleRequest) -> str:
    if request.mode is ManagerRequestMode.INITIAL_PLAN:
        return "task_start"
    signal = request.recovery.recovery_signal if request.recovery is not None else None
    if (
        signal is not None
        and signal.kind is RecoveryKind.SUBTASK_MISALIGNED
        and signal.recovery_attempt == 2
    ):
        return "subtask_misaligned_deliberate_replan"
    return "meaningful_episode_boundary"


def _lower_manager_decision(
    mode: ManagerRequestMode,
    response: BaseModel | None,
    public_evidence_refs: Mapping[str, str],
) -> ManagerDecision:
    if mode is ManagerRequestMode.INITIAL_PLAN:
        if not isinstance(response, InitialManagerDecisionModel):
            raise TypeError("initial Manager output uses the wrong contract")
        subtask = _lower_subtask(response.subtask)
        return ManagerDecision(
            ManagerAssessment.NOT_APPLICABLE,
            ManagerRoute(response.route),
            subtask=subtask,
            question=response.question,
            reason=_manager_reason(response.reason),
        )
    if mode is not ManagerRequestMode.REVIEW_AND_ROUTE or not isinstance(
        response, ReviewManagerDecisionModel
    ):
        raise TypeError("review Manager output uses the wrong contract")
    subtask = _lower_subtask(response.subtask)
    return ManagerDecision(
        ManagerAssessment(response.assessment),
        ManagerRoute(response.route),
        _canonical_evidence_refs(response.evidence_refs, public_evidence_refs),
        tuple(
            WorkingOutcomeProposal(
                item.outcome_id,
                ManagerAssessment(item.assessment),
                _canonical_evidence_refs(item.evidence_refs, public_evidence_refs),
                item.summary,
            )
            for item in response.working_outcomes
        ),
        tuple(
            WorkingFactProposal(
                item.key,
                _canonical_evidence_ref(item.evidence_ref, public_evidence_refs),
                item.purpose,
            )
            for item in response.working_facts
        ),
        response.invalidate_fact_keys,
        subtask,
        response.question,
        _manager_reason(response.reason),
        response.final_response,
        _canonical_evidence_refs(
            response.final_response_evidence_refs,
            public_evidence_refs,
        ),
    )


def _lower_subtask(model: SubtaskContractModel | None) -> SubtaskContract | None:
    if model is None:
        return None
    return SubtaskContract(
        model.objective,
        model.done_when,
        model.task_link,
        SubtaskOutcomeKind(model.outcome_kind),
        model.constraints,
        model.relevant_fact_keys,
        tuple(EvidenceRequirement(item.key, item.description) for item in model.required_evidence),
        model.episode_turn_budget,
        model.related_audit_ids,
    )


def _manager_reason(value: str) -> str:
    """Mechanically bound non-authoritative explanation text before Runtime lowering."""

    return value.strip()[:_MANAGER_RUNTIME_REASON_MAX]


def _manager_messages(request: ManagerRoleRequest) -> _RolePrompt:
    review_projection = None
    public_evidence_refs: Mapping[str, str] = {}
    if request.mode is ManagerRequestMode.REVIEW_AND_ROUTE:
        assert request.active_subtask is not None
        assert request.review_world is not None
        assert request.evidence_bundle is not None
        review_request = AuditorRoleRequest.from_authorities(
            request.original_task,
            request.active_subtask,
            request.mission_state,
            request.review_world,
            request.episode_working_facts,
            "outcome_proposed",
            (),
            request.evidence_bundle,
            request.active_subtask.related_audit_ids,
        )
        projection = _audit_world_payload(review_request)
        review_projection = projection.payload
        allowed = set(request.allowed_evidence_refs)
        public_evidence_refs = {
            public: canonical
            for public, canonical in projection.public_evidence_refs.items()
            if canonical in allowed
        }
        canonical_to_public = {
            canonical: public for public, canonical in public_evidence_refs.items()
        }
        next_index = max(
            (_public_fact_sort_key(item)[0] for item in public_evidence_refs),
            default=0,
        )
        for fact in request.episode_working_facts:
            canonical = fact.record.evidence_ref
            if canonical not in allowed or canonical in canonical_to_public:
                continue
            next_index += 1
            public = f"F{next_index}"
            public_evidence_refs[public] = canonical
            canonical_to_public[canonical] = public
    required_status = _manager_required_evidence_status(request, review_projection)
    payload = {
        "mode": request.mode.value,
        "task": _manager_task_payload(request.original_task),
        "mission_state": _mission_payload(request.mission_state),
        "last_typed_exit": request.last_typed_exit,
        "last_audit_or_failure_ref": request.last_audit_or_failure_ref,
        "remaining_rounds": request.remaining_rounds,
        "environment": (
            to_json_compatible(request.environment)
            if request.mode is ManagerRequestMode.INITIAL_PLAN
            else None
        ),
        "active_subtask": to_json_compatible(request.active_subtask),
        "mission_review_bundle": (
            {
                "priority_1_admitted_episode_working_facts": tuple(
                    {
                        "key": item.key,
                        "value": item.record.value,
                        "purpose": item.purpose,
                    }
                    for item in request.episode_working_facts
                ),
                "required_evidence_status": required_status,
                "priority_2_fresh_relevant_result_evidence": _changed_review_candidates(
                    review_projection,
                    request,
                    public_evidence_refs,
                ),
                "priority_3_current_page_identity": {
                    "current_route": request.environment.current_route,
                    "visible_primary_heading": request.environment.visible_primary_heading,
                    "document_title": request.environment.document_title,
                    "identity_conflict": request.environment.identity_conflict,
                },
                "priority_4_typed_recovery_or_failure": _manager_recovery_payload(request),
                "priority_5_generic_environment": to_json_compatible(request.environment),
                "bounded_fresh_world": review_projection,
            }
            if request.mode is ManagerRequestMode.REVIEW_AND_ROUTE
            else None
        ),
        "allowed_evidence_refs": tuple(
            sorted(public_evidence_refs, key=_public_fact_sort_key)
        ),
        "episode_working_facts": tuple(
            {
                "key": item.key,
                "evidence_ref": canonical_to_public[item.record.evidence_ref],
                "value": item.record.value,
                "purpose": item.purpose,
                "observation_lineage": {
                    "origin": "pinned_episode_fact",
                },
            }
            for item in request.episode_working_facts
            if item.record.evidence_ref in canonical_to_public
        ),
    }
    if request.mode is ManagerRequestMode.REVIEW_AND_ROUTE:
        payload["public_final_response_schema"] = to_json_compatible(
            request.final_response_schema
        )
    return _RolePrompt(
        _messages(MISSION_MANAGER_INSTRUCTIONS, payload),
        {"task_plan": payload},
        public_evidence_refs,
    )


def _manager_required_evidence_status(
    request: ManagerRoleRequest,
    review_projection: Mapping[str, object] | None,
) -> tuple[Mapping[str, object], ...]:
    subtask = request.active_subtask
    if subtask is None:
        return ()
    retained = {item.key for item in request.episode_working_facts}
    return tuple(
        {
            "key": item.key,
            "description": item.description,
            "status": (
                "retained"
                if item.key in retained
                else "currently_visible"
                if _manager_requirement_currently_visible(item, review_projection)
                else "missing"
            ),
        }
        for item in subtask.required_evidence
    )


def _manager_requirement_currently_visible(
    requirement: EvidenceRequirement,
    review_projection: Mapping[str, object] | None,
) -> bool:
    if review_projection is None:
        return False
    candidates = review_projection.get("evidence_candidates", ())
    if not isinstance(candidates, tuple | list):
        return False
    intent = f"{requirement.key} {requirement.description}"
    return any(
        isinstance(item, Mapping)
        and delivery_descriptor_matches(
            intent,
            f"{item.get('predicate', '')} {item.get('value', '')}",
            (
                str(item.get("source_context", "")),
                str(item.get("region_ref", "")),
            ),
        )
        for item in candidates
    )


def _changed_review_candidates(
    review_projection: Mapping[str, object] | None,
    request: ManagerRoleRequest,
    public_evidence_refs: Mapping[str, str],
) -> tuple[Mapping[str, object], ...]:
    if review_projection is None:
        return ()
    changed = set(request.changed_evidence_refs)
    candidates = review_projection.get("evidence_candidates", ())
    if not isinstance(candidates, tuple | list):
        return ()
    return tuple(
        item
        for item in candidates
        if isinstance(item, Mapping)
        and public_evidence_refs.get(str(item.get("evidence_ref", "")), "") in changed
    )[:5]


def _manager_recovery_payload(request: ManagerRoleRequest) -> Mapping[str, object] | None:
    recovery = request.recovery
    if recovery is None:
        return None
    signal = recovery.recovery_signal
    evidence = dict(signal.observed_evidence) if signal is not None else {}
    repeated_arguments = evidence.pop("arguments", {})
    repeat_count = evidence.pop("same_result_count", 0)
    item_count = evidence.get("item_count")
    result = "empty" if item_count == 0 else "nonempty" if isinstance(item_count, int) else "unknown"
    payload: dict[str, object] = {
        "authority": "temporary_non_authoritative_guidance",
        "scope": "next_manager_decision_only",
        "exit_kind": recovery.exit_kind,
        "world_changed": recovery.world_changed,
        "attempted_modes": recovery.attempted_modes,
        "repeated_arguments": repeated_arguments,
        "result": result,
        "repeat_count": repeat_count,
        "observed_evidence": evidence,
        "outcome_proposal": recovery.outcome_proposal,
        "working_proposal_feedback": recovery.working_proposal_feedback,
        "prohibited_repeat": (
            signal.prohibited_immediate_repeat if signal is not None else ""
        ),
        "prior_subtask": to_json_compatible(recovery.prior_subtask),
    }
    if recovery.audit_guidance is not None:
        payload["audit_guidance"] = {
            "missing_evidence": recovery.audit_guidance.missing_evidence,
            "recovery_hint": recovery.audit_guidance.recovery_hint,
        }
    sanitized = sanitize_history_value(payload)
    if not isinstance(sanitized, Mapping):
        raise TypeError("Manager recovery projection must remain a mapping")
    return sanitized


def _auditor_messages(request: AuditorRoleRequest) -> _RolePrompt:
    audit_projection = _audit_world_payload(request)
    audit_world = audit_projection.payload
    public_evidence_refs = dict(audit_projection.public_evidence_refs)
    canonical_to_public = {
        canonical: public for public, canonical in public_evidence_refs.items()
    }
    next_index = max(
        (_public_fact_sort_key(item)[0] for item in public_evidence_refs),
        default=0,
    )
    for fact in request.working_facts:
        canonical = fact.record.evidence_ref
        if canonical in canonical_to_public:
            continue
        if (
            request.audit_bundle.resolve(canonical) != fact.record
            or canonical not in request.audit_bundle.pinned_evidence_refs
        ):
            continue
        next_index += 1
        public = f"F{next_index}"
        public_evidence_refs[public] = canonical
        canonical_to_public[canonical] = public
    public_refs = tuple(sorted(public_evidence_refs, key=_public_fact_sort_key))
    audit_evidence = {
        "total_evidence_count": request.audit_bundle.total_evidence_count or len(request.audit_bundle.evidence_records),
        "visible_ref_count": len(public_refs),
        "visible_refs": public_refs,
        "truncated": request.audit_bundle.truncated,
    }
    try:
        episode_history = render_episode_history(request.episode_history, _AUDIT_HISTORY_BYTES)
    except EpisodeHistoryCapacityError as exc:
        raise RoleInputCapacityError("audit history exceeds bounded context") from exc
    payload = {
        "task": _auditor_task_payload(request),
        "subtask": _auditor_subtask_payload(request.subtask),
        "pre_mission_state": _auditor_mission_payload(request),
        "audit_world": audit_world,
        "working_facts": tuple(
            _public_working_fact_payload(item, canonical_to_public)
            for item in request.working_facts
        ),
        "yield_reason": request.yield_reason,
        "episode_history": episode_history,
        "audit_evidence": audit_evidence,
        "related_audit_ids": request.related_audit_ids,
    }
    component_payloads = {
        "task_plan": {
            "task": payload["task"],
            "subtask": payload["subtask"],
            "pre_mission_state": payload["pre_mission_state"],
            "yield_reason": request.yield_reason,
            "related_audit_ids": request.related_audit_ids,
        },
        "actor_world": audit_world,
        "working_set": payload["working_facts"],
        "history": episode_history,
        "evidence": audit_evidence,
    }
    return _RolePrompt(
        _messages(MISSION_AUDITOR_INSTRUCTIONS, payload),
        component_payloads,
        public_evidence_refs,
    )


def _messages(instructions: str, payload: Mapping[str, object]) -> tuple[ModelMessage, ...]:
    encoded = json.dumps(to_json_compatible(payload), separators=(",", ":"), ensure_ascii=False)
    return (
        ModelMessage(role="system", content=instructions),
        ModelMessage(role="user", content=encoded),
    )


def _manager_task_payload(task: TaskGoal) -> Mapping[str, object]:
    return {
        "instruction": task.instruction,
        "constraints": task.constraints,
        "allowed_effects": task.allowed_effects,
        "forbidden_effects": task.forbidden_effects,
        "public_inputs": _role_public_inputs(task),
        "success_criteria": task.success_criteria,
        "requested_outputs": task.requested_outputs,
        "risk_profile": task.risk_profile.value,
    }


def _role_public_inputs(task: TaskGoal) -> Mapping[str, object]:
    return {
        key: value
        for key, value in task.inputs.items()
        if key != PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
    }


def _auditor_task_payload(request: AuditorRoleRequest) -> Mapping[str, object]:
    task = request.task
    return {
        "instruction": task.instruction,
        "constraints": task.constraints,
        "related_success_criteria": task.related_success_criteria,
        "related_requested_outputs": task.related_requested_outputs,
    }


def _auditor_subtask_payload(subtask: SubtaskContract) -> Mapping[str, object]:
    return {
        "objective": subtask.objective,
        "done_when": subtask.done_when,
        "task_link": subtask.task_link,
        "outcome_kind": subtask.outcome_kind.value,
        "constraints": subtask.constraints,
        "required_evidence": tuple(
            {"key": item.key, "description": item.description}
            for item in subtask.required_evidence
        ),
    }


def _auditor_mission_payload(request: AuditorRoleRequest) -> Mapping[str, object]:
    mission = request.pre_mission_state
    related_audits = set(request.related_audit_ids)
    relevant_facts = set(request.subtask.relevant_fact_keys)
    return {
        "version": mission.version,
        "working_outcomes": tuple(
            {
                "outcome_id": item.outcome_id,
                "assessment": item.assessment.value,
                "summary": item.summary,
            }
            for item in mission.working_outcomes
            if item.outcome_id in related_audits
        ),
        "accepted_facts": tuple(
            {
                "key": item.key,
                "value": item.record.value,
                "purpose": item.purpose,
                "accepted_at_version": item.accepted_at_version,
            }
            for item in mission.accepted_facts
            if item.key in relevant_facts
        ),
        "evidence_lineage": tuple(
            item for item in mission.evidence_lineage if item in related_audits
        ),
    }


def _audit_world_payload(request: AuditorRoleRequest) -> _AuditWorldProjection:
    try:
        context = _auditor_delivery_context(request)
        delivery = build_model_turn_delivery(
            context,
            include_images=False,
            max_rendered_bytes=_AUDIT_RENDERED_WORLD_BYTES,
        )
        rendered = delivery.view
    except ValueError as exc:
        raise RoleInputCapacityError("audit world exceeds bounded context") from exc
    public_evidence_refs = _visible_delivery_fact_refs(context, request, rendered)
    return _AuditWorldProjection({
        "format": "compact_ax.v2",
        "delivery_projection": rendered.projection,
        "observation": rendered.text,
        "evidence_candidates": tuple(
            {
                "evidence_ref": item.fact_ref,
                "value": item.value,
                "predicate": item.predicate,
                "source_context": item.source_context,
                "region_ref": item.region_ref,
                "coverage": item.coverage,
                "lineage": item.lineage,
            }
            for item in (
                context.evidence_candidates.candidates
                if context.evidence_candidates is not None
                else ()
            )
            if item.fact_ref in rendered.manifest.fact_refs
        ),
        "sources": tuple(
            {
                "source_ref": item.source_ref,
                "modality": item.modality,
                "assurance": item.assurance,
                "freshness": item.freshness,
                "inventory_coverage": item.inventory_coverage,
                "projection_coverage": item.projection_coverage,
                "rendering_coverage": item.rendering_coverage,
            }
            for item in context.actor_world.sources
        ),
        "fact_total_count": len(context.private_fact_bindings),
        "artifact_total_count": sum(1 for record in request.audit_bundle.evidence_records if record.kind == "artifact"),
        "truncated": context.actor_world.documents[0].truncated if context.actor_world.documents else False,
    }, public_evidence_refs)


def _auditor_delivery_context(request: AuditorRoleRequest):
    projected_task = TaskGoal(
        request.task.task_id,
        request.task.instruction,
        constraints=request.task.constraints,
        success_criteria=request.task.related_success_criteria,
        requested_outputs=request.task.related_requested_outputs,
        revision=request.task.revision,
    )
    action_space = ActionSpaceBuilder().build(projected_task, request.after_world)
    evaluation = TaskEvaluation(
        projected_task.task_id,
        request.after_world.observation_id,
        TaskEvaluationStatus.UNKNOWN,
        "auditor read-only delivery",
    )
    return ContextBuilder(
        budget=ContextProjectionBudget(
            max_facts=4096,
            max_facts_per_target=4096,
            max_history_serialized_bytes=_AUDIT_HISTORY_BYTES,
        ),
        include_public_text_evidence=True,
    ).build(
        projected_task,
        request.after_world,
        action_space,
        evaluation,
        working_facts=request.working_facts,
        active_subtask=AgentSubtaskContractView(
            request.subtask.objective,
            request.subtask.done_when,
            request.subtask.task_link,
            request.subtask.outcome_kind.value,
            request.subtask.constraints,
            tuple(
                (item.key, item.description)
                for item in request.subtask.required_evidence
            ),
        ),
    )


def _visible_delivery_fact_refs(context, request: AuditorRoleRequest, rendered) -> dict[str, str]:
    values: dict[str, str] = {}
    for public_ref, canonical_ref in sorted(
        context.private_fact_bindings.items(),
        key=lambda item: _public_fact_sort_key(item[0]),
    ):
        if public_ref not in rendered.manifest.fact_refs:
            continue
        record = request.audit_bundle.resolve(canonical_ref)
        if record is None and context.evidence_index is not None:
            record = context.evidence_index.resolve_record(canonical_ref)
        if record is None:
            continue
        values[public_ref] = record.evidence_ref
    return values


def _public_fact_sort_key(public_ref: str) -> tuple[int, str]:
    suffix = public_ref[1:] if public_ref.startswith("F") else ""
    return (int(suffix) if suffix.isdecimal() else 0, public_ref)


def _canonical_evidence_refs(refs: tuple[str, ...], public_refs: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(_canonical_evidence_ref(ref, public_refs) for ref in refs)


def _canonical_evidence_ref(ref: str, public_refs: Mapping[str, str]) -> str:
    try:
        return public_refs[ref]
    except KeyError as exc:
        raise ValueError("model cited an evidence ref that was not offered") from exc


def _mission_payload(mission) -> Mapping[str, object]:
    return {
        "version": mission.version,
        "working_outcomes": tuple(
            {
                "outcome_id": item.outcome_id,
                "assessment": item.assessment.value,
                "summary": item.summary,
            }
            for item in mission.working_outcomes
        ),
        "accepted_facts": tuple(
            {
                "key": item.key,
                "value": item.record.value,
                "purpose": item.purpose,
                "accepted_at_version": item.accepted_at_version,
            }
            for item in mission.accepted_facts
        ),
        "evidence_lineage": mission.evidence_lineage,
    }


def _public_working_fact_payload(
    item,
    canonical_to_public: Mapping[str, str],
) -> Mapping[str, object]:
    payload = {
        "key": item.key,
        "value": item.record.value,
        "purpose": item.purpose,
    }
    public_ref = canonical_to_public.get(item.record.evidence_ref)
    if public_ref:
        payload["evidence_ref"] = public_ref
    return payload


def _metadata(port, config, attempts, schema_name: str) -> ModelMetadata:
    retry_statuses = tuple(
        _attempt_http_status(attempts[index - 1])
        for index, item in enumerate(attempts)
        if index > 0 and item.phase.endswith("provider_retry")
    )
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
        rate_limit_retry_count=sum(status == 429 for status in retry_statuses),
        transient_retry_count=sum(
            status is not None and 500 <= status < 600
            for status in retry_statuses
        ),
    )


def _attempt_http_status(attempt: ModelGenerationAttempt) -> int | None:
    transcript = attempt.transcript
    if not isinstance(transcript, Mapping):
        return None
    value = transcript.get("error.http_status")
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
