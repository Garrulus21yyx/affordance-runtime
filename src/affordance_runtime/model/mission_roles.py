"""Model-backed Manager and Auditor role adapters."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.episode_history import (
    EpisodeHistoryCapacityError,
    render_episode_history,
)
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.context.world_projection import project_model_world
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    AuditDelta,
    AuditDeltaStatus,
    AuditorRoleRequest,
    ManagerDecision,
    ManagerRoleRequest,
    ManagerRoute,
    OutcomeProposal,
    PromoteFactProposal,
    SubtaskContract,
)
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
    StructuredOutputError,
    model_port_from_environment,
    structured_output_repair_contract,
)

_MAX_ROLE_INPUT_BYTES = 24 * 1024
_AUDIT_WORLD_BYTES = 12 * 1024
_AUDIT_HISTORY_BYTES = 8 * 1024


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


class SubtaskContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    objective: str = Field(min_length=1, max_length=500)
    done_when: str = Field(min_length=1, max_length=500)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)
    relevant_fact_keys: tuple[str, ...] = Field(default=(), max_length=32)
    candidate_output_keys: tuple[str, ...] = Field(default=(), max_length=32)
    episode_turn_budget: int = Field(default=10, ge=1, le=100)
    related_audit_ids: tuple[str, ...] = Field(default=(), max_length=32)


class ManagerDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    route: Literal["execute_subtask", "ask_user", "blocked", "request_final_audit"]
    subtask: SubtaskContractModel | None = None
    question: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _shape(self) -> ManagerDecisionModel:
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


class OutcomeProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    audit_id: str = Field(min_length=1, max_length=96)
    status: Literal["audited_satisfied", "audited_unsatisfied"]
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=32)
    summary: str = Field(min_length=1, max_length=500)


class PromoteFactProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    evidence_ref: str = Field(min_length=1, max_length=512)
    value: object
    purpose: str = Field(min_length=1, max_length=500)


class AuditDeltaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    status: Literal["audited_satisfied", "audited_unsatisfied", "unknown", "blocked"]
    base_mission_version: int = Field(ge=0)
    completed_outcomes: tuple[OutcomeProposalModel, ...] = Field(default=(), max_length=32)
    promote_facts: tuple[PromoteFactProposalModel, ...] = Field(default=(), max_length=32)
    invalidate_fact_keys: tuple[str, ...] = Field(default=(), max_length=32)
    missing_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    recovery_hint: str = Field(default="", max_length=500)


class RoleInputCapacityError(ValueError):
    """A role input cannot fit the declared bounded model context."""


@dataclass(frozen=True)
class _StructuredRoleInvocation:
    output: BaseModel | None
    failure: ModelFailure | None
    attempts: tuple[ModelGenerationAttempt, ...] = ()


async def _invoke_structured_role(
    port: ModelPort,
    config: ModelConfig,
    message_factory: Callable[[], tuple[ModelMessage, ...]],
    schema: type[BaseModel],
    initial_phase: str,
    repair_phase: str,
) -> _StructuredRoleInvocation:
    attempts: tuple[ModelGenerationAttempt, ...] = ()
    try:
        messages = message_factory()
    except RoleInputCapacityError:
        return _StructuredRoleInvocation(None, ModelFailure(ModelFailureKind.INTERNAL_ERROR, "context_capacity", False))
    except Exception:
        return _StructuredRoleInvocation(None, ModelFailure(ModelFailureKind.INTERNAL_ERROR, "role input construction failed", False))
    try:
        response, attempts = await _generate_structured_role(port, config, messages, schema, initial_phase, attempts)
    except StructuredOutputError as exc:
        attempts = getattr(exc, "_mission_role_attempts", attempts)
        try:
            response, attempts = await _generate_structured_role(
                port,
                config,
                _repair_messages(messages, exc),
                schema,
                repair_phase,
                attempts,
            )
        except StructuredOutputError as repair_exc:
            attempts = getattr(repair_exc, "_mission_role_attempts", attempts)
            return _StructuredRoleInvocation(
                None,
                ModelFailure(ModelFailureKind.SCHEMA_ERROR, "role output invalid", False),
                attempts,
            )
        except Exception as repair_exc:
            attempts = getattr(repair_exc, "_mission_role_attempts", attempts)
            return _StructuredRoleInvocation(None, _provider_failure(repair_exc), attempts)
    except Exception as exc:
        attempts = getattr(exc, "_mission_role_attempts", attempts)
        return _StructuredRoleInvocation(None, _provider_failure(exc), attempts)
    return _StructuredRoleInvocation(response, None, attempts)


async def _generate_structured_role(
    port: ModelPort,
    config: ModelConfig,
    messages: tuple[ModelMessage, ...],
    schema: type[BaseModel],
    phase: str,
    attempts: tuple[ModelGenerationAttempt, ...],
) -> tuple[BaseModel, tuple[ModelGenerationAttempt, ...]]:
    number = len(attempts) + 1
    try:
        result = await port.generate_structured(messages, schema, config)
    except Exception as exc:
        status = "schema_error" if isinstance(exc, StructuredOutputError) else "failed"
        return _raise_with_attempt(exc, (*attempts, _attempt(number, phase, schema.__name__, status, exc)))
    return result, (*attempts, _attempt(number, phase, schema.__name__, "accepted"))


def _raise_with_attempt(exc: Exception, attempts: tuple[ModelGenerationAttempt, ...]):
    exc.__dict__["_mission_role_attempts"] = attempts
    raise exc


def _attempt(
    number: int,
    phase: str,
    schema_name: str,
    status: str,
    exc: Exception | None = None,
) -> ModelGenerationAttempt:
    return ModelGenerationAttempt(
        number,
        phase,
        schema_name,
        status,
        tuple(getattr(exc, "violations", ())),
        exception_class=type(exc).__name__ if exc else "",
    )


def _provider_failure(exc: Exception) -> ModelFailure:
    if isinstance(exc, ProviderModelError) and exc.kind is ProviderFailureKind.QUOTA_EXHAUSTED:
        return ModelFailure(ModelFailureKind.PROVIDER_EXHAUSTED, "mission role provider exhausted", False)
    return ModelFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "mission role provider failed", True)


@dataclass(frozen=True)
class ModelBackedMissionManager:
    port: ModelPort
    config: ModelConfig = field(default_factory=lambda: ModelConfig(
        temperature=0.0,
        max_tokens=2048,
        timeout_s=45.0,
        prompt_version=MISSION_MANAGER_PROMPT_VERSION,
    ))
    last_invocation_result: ModelInvocationResult[ManagerDecision] | None = field(
        default=None, init=False, compare=False
    )
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(
        default=(), init=False, compare=False
    )

    async def decide(self, request: ManagerRoleRequest) -> ModelInvocationResult[ManagerDecision]:
        object.__setattr__(self, "last_generation_attempts", ())
        invocation = await _invoke_structured_role(
            self.port,
            self.config,
            lambda: _manager_messages(request),
            ManagerDecisionModel,
            "manager_initial",
            "manager_schema_repair",
        )
        object.__setattr__(self, "last_generation_attempts", invocation.attempts)
        if invocation.failure is not None:
            return self._finish_failure(invocation.failure)
        response = invocation.output
        assert isinstance(response, ManagerDecisionModel)
        try:
            subtask = (
                SubtaskContract(**response.subtask.model_dump())
                if response.subtask is not None
                else None
            )
            output = ManagerDecision(
                ManagerRoute(response.route),
                subtask,
                response.question,
                response.reason,
            )
        except (TypeError, ValueError):
            return self._finish_failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "manager contract invalid", False))
        return self._finish_output(output, "Manager")

    def _finish_output(self, output: ManagerDecision, role: str) -> ModelInvocationResult[ManagerDecision]:
        invocation = ModelInvocationResult(
            output=output,
            metadata=_metadata(self.port, self.config, self.last_generation_attempts, ManagerDecisionModel.__name__),
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            lineage={"role": role},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _finish_failure(self, failure: ModelFailure) -> ModelInvocationResult[ManagerDecision]:
        invocation = ModelInvocationResult(
            failure=failure,
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            lineage={"role": "Manager"},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation


@dataclass(frozen=True)
class ModelBackedMissionAuditor:
    port: ModelPort
    config: ModelConfig = field(default_factory=lambda: ModelConfig(
        temperature=0.0,
        max_tokens=2048,
        timeout_s=45.0,
        prompt_version=MISSION_AUDITOR_PROMPT_VERSION,
    ))
    last_invocation_result: ModelInvocationResult[AuditDelta] | None = field(
        default=None, init=False, compare=False
    )
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(
        default=(), init=False, compare=False
    )

    async def audit(self, request: AuditorRoleRequest) -> ModelInvocationResult[AuditDelta]:
        object.__setattr__(self, "last_generation_attempts", ())
        invocation = await _invoke_structured_role(
            self.port,
            self.config,
            lambda: _auditor_messages(request),
            AuditDeltaModel,
            "auditor_initial",
            "auditor_schema_repair",
        )
        object.__setattr__(self, "last_generation_attempts", invocation.attempts)
        if invocation.failure is not None:
            return self._finish_failure(invocation.failure)
        response = invocation.output
        assert isinstance(response, AuditDeltaModel)
        try:
            output = AuditDelta(
                AuditDeltaStatus(response.status),
                response.base_mission_version,
                tuple(
                    OutcomeProposal(
                        item.audit_id,
                        AuditDeltaStatus(item.status),
                        item.evidence_refs,
                        item.summary,
                    )
                    for item in response.completed_outcomes
                ),
                tuple(
                    PromoteFactProposal(
                        item.key,
                        item.evidence_ref,
                        item.value,
                        item.purpose,
                    )
                    for item in response.promote_facts
                ),
                response.invalidate_fact_keys,
                response.missing_evidence,
                response.recovery_hint,
            )
        except (TypeError, ValueError):
            return self._finish_failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "auditor contract invalid", False))
        return self._finish_output(output, "Auditor")

    def _finish_output(self, output: AuditDelta, role: str) -> ModelInvocationResult[AuditDelta]:
        invocation = ModelInvocationResult(
            output=output,
            metadata=_metadata(self.port, self.config, self.last_generation_attempts, AuditDeltaModel.__name__),
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            lineage={"role": role},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _finish_failure(self, failure: ModelFailure) -> ModelInvocationResult[AuditDelta]:
        invocation = ModelInvocationResult(
            failure=failure,
            attempts=self.last_generation_attempts,
            repair_diagnostics=_repair_diagnostics(self.last_generation_attempts),
            lineage={"role": "Auditor"},
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation


def mission_roles_from_environment(environment: Mapping[str, str] | None = None):
    port = model_port_from_environment(environment)
    return ModelBackedMissionManager(port), ModelBackedMissionAuditor(port)


def _manager_messages(request: ManagerRoleRequest) -> tuple[ModelMessage, ...]:
    payload = {
        "task": _task_payload(request.original_task),
        "mission_state": _mission_payload(request.mission_state),
        "last_typed_exit": request.last_typed_exit,
        "last_audit_or_failure_ref": request.last_audit_or_failure_ref,
        "remaining_rounds": request.remaining_rounds,
    }
    return _messages(MISSION_MANAGER_INSTRUCTIONS, payload)


def _auditor_messages(request: AuditorRoleRequest) -> tuple[ModelMessage, ...]:
    audit_world = _audit_world_payload(request)
    visible_refs = _visible_audit_refs(audit_world)
    try:
        episode_history = render_episode_history(request.episode_history, _AUDIT_HISTORY_BYTES)
    except EpisodeHistoryCapacityError as exc:
        raise RoleInputCapacityError("audit history exceeds bounded context") from exc
    payload = {
        "task": _task_payload(request.original_task),
        "subtask": to_json_compatible(request.subtask),
        "pre_mission_state": _mission_payload(request.pre_mission_state),
        "audit_world": audit_world,
        "working_facts": tuple(
            {
                "key": item.key,
                "value": item.record.value,
                "evidence_ref": item.record.evidence_ref,
                "purpose": item.purpose,
            }
            for item in request.working_facts
        ),
        "yield_reason": request.yield_reason,
        "episode_history": episode_history,
        "audit_bundle": {
            "observation_id": request.audit_bundle.observation_id,
            "total_evidence_count": request.audit_bundle.total_evidence_count or len(request.audit_bundle.evidence_records),
            "truncated": request.audit_bundle.truncated,
            "evidence": tuple(
                _evidence_payload(item)
                for item in request.audit_bundle.evidence_records
                if item.evidence_ref in visible_refs
            ),
        },
        "related_audit_ids": request.related_audit_ids,
    }
    return _messages(MISSION_AUDITOR_INSTRUCTIONS, payload)


def _messages(instructions: str, payload: Mapping[str, object]) -> tuple[ModelMessage, ...]:
    encoded = json.dumps(to_json_compatible(payload), separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > _MAX_ROLE_INPUT_BYTES:
        raise RoleInputCapacityError("mission role input exceeds bounded workspace")
    return (
        ModelMessage(role="system", content=instructions),
        ModelMessage(role="user", content=encoded),
    )


def _repair_messages(messages: tuple[ModelMessage, ...], error: StructuredOutputError) -> tuple[ModelMessage, ...]:
    repair = {
        "repair": structured_output_repair_contract(error),
        "instruction": "Return one complete replacement object using only the declared schema.",
    }
    return (*messages, ModelMessage(role="user", content=json.dumps(repair, separators=(",", ":"))))


def _task_payload(task) -> Mapping[str, object]:
    return {
        "instruction": task.instruction,
        "constraints": task.constraints,
        "allowed_effects": task.allowed_effects,
        "forbidden_effects": task.forbidden_effects,
        "public_inputs": task.inputs,
        "success_criteria": task.success_criteria,
        "requested_outputs": task.requested_outputs,
        "risk_profile": task.risk_profile.value,
    }


def _audit_world_payload(request: AuditorRoleRequest) -> Mapping[str, object]:
    try:
        view = project_model_world(
            request.after_world,
            ContextProjectionBudget(
                max_facts=64,
                max_artifact_summaries=8,
                max_history_serialized_bytes=_AUDIT_HISTORY_BYTES,
                max_total_serialized_bytes=_AUDIT_WORLD_BYTES * 2,
            ),
        )
    except ValueError as exc:
        raise RoleInputCapacityError("audit world exceeds bounded context") from exc
    target_labels = {item.target_id: item.label for item in view.targets.items}
    retained_refs = {item.evidence_ref for item in request.audit_bundle.evidence_records}
    facts = tuple(item for item in view.facts.items if item.fact_ref in retained_refs)
    artifacts = tuple(item for item in view.artifact_summaries.items if item.evidence_ref in retained_refs)
    return {
        "observation_id": request.after_world.observation_id,
        "targets": tuple(to_json_compatible(item) for item in view.targets.items),
        "facts": tuple(
            {
                "evidence_ref": item.fact_ref,
                "subject_id": item.subject_id,
                "subject_label": target_labels.get(item.subject_id, ""),
                "predicate": item.predicate,
                "value": item.value,
            }
            for item in facts
        ),
        "artifacts": tuple(to_json_compatible(item) for item in artifacts),
        "sources": tuple(to_json_compatible(item) for item in view.sources),
        "target_total_count": view.targets.total_count,
        "fact_total_count": view.facts.total_count,
        "artifact_total_count": view.artifact_summaries.total_count,
        "truncated": (
            view.targets.truncated
            or view.facts.truncated
            or view.artifact_summaries.truncated
            or len(facts) < len(view.facts.items)
            or len(artifacts) < len(view.artifact_summaries.items)
        ),
    }


def _visible_audit_refs(audit_world: Mapping[str, object]) -> frozenset[str]:
    refs: set[str] = set()
    for section in ("facts", "artifacts"):
        value = audit_world.get(section)
        if not isinstance(value, tuple):
            continue
        for item in value:
            if isinstance(item, Mapping):
                ref = item.get("evidence_ref")
                if isinstance(ref, str) and ref:
                    refs.add(ref)
    return frozenset(refs)


def _mission_payload(mission) -> Mapping[str, object]:
    return {
        "version": mission.version,
        "audited_outcomes": to_json_compatible(mission.audited_outcomes),
        "accepted_facts": tuple(
            {
                "key": item.key,
                "value": item.record.value,
                "evidence_ref": item.record.evidence_ref,
                "accepted_at_version": item.accepted_at_version,
            }
            for item in mission.accepted_facts
        ),
        "audit_lineage": mission.audit_lineage,
    }


def _evidence_payload(record) -> Mapping[str, object]:
    return {
        "evidence_ref": record.evidence_ref,
        "kind": record.kind,
        "source_observation_id": record.source_observation_id,
        "source_modality": record.source_modality,
        "source_assurance": record.source_assurance,
        "subject_id": record.subject_id,
        "predicate": record.predicate,
        "value": record.value,
        "artifact_kind": record.artifact_kind,
        "output_id": record.output_id,
        "public_summary": record.public_summary,
    }


def _metadata(port, config, attempts, schema_name: str) -> ModelMetadata:
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model,
        response_id=attempts[-1].response_id if attempts else "",
        endpoint_class=port.endpoint_class,
        prompt_version=config.prompt_version,
        schema_version=schema_name,
        latency_ms=sum(item.latency_ms for item in attempts),
        prompt_tokens=sum(item.prompt_tokens for item in attempts),
        completion_tokens=sum(item.completion_tokens for item in attempts),
        total_tokens=sum(item.total_tokens for item in attempts),
    )


def _repair_diagnostics(attempts) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {"kind": "structured_output_repair", "phase": item.phase}
        for item in attempts
        if item.phase.endswith("schema_repair")
    )
