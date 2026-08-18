"""Model-backed Manager and Auditor role adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
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
    StructuredOutputError,
    model_port_from_environment,
    structured_output_repair_contract,
)

_MAX_ROLE_INPUT_BYTES = 24 * 1024


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


@dataclass(frozen=True)
class ModelBackedMissionManager:
    port: ModelPort
    config: ModelConfig = field(default_factory=lambda: ModelConfig(
        temperature=0.0,
        max_tokens=2048,
        timeout_s=45.0,
        rate_limit_retries=0,
        transient_retries=0,
        provider_circuit_break_s=0.0,
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
        messages = _manager_messages(request)
        try:
            response = await self._generate(messages, ManagerDecisionModel, "manager_initial")
        except StructuredOutputError as exc:
            try:
                response = await self._generate(
                    _repair_messages(messages, exc),
                    ManagerDecisionModel,
                    "manager_schema_repair",
                )
            except Exception:
                return self._finish_failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "manager output invalid", False))
        except Exception:
            return self._finish_failure(ModelFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "manager provider failed", True))
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

    async def _generate(self, messages, schema, phase: str):
        attempt_no = len(self.last_generation_attempts) + 1
        try:
            result = await self.port.generate_structured(messages, schema, self.config)
        except Exception as exc:
            self._append_attempt(attempt_no, phase, schema.__name__, "schema_error" if isinstance(exc, StructuredOutputError) else "failed", exc)
            raise
        self._append_attempt(attempt_no, phase, schema.__name__, "accepted")
        return result

    def _append_attempt(self, number: int, phase: str, schema_name: str, status: str, exc: Exception | None = None) -> None:
        record = getattr(self.port, "last_call", None)
        object.__setattr__(self, "last_generation_attempts", (*self.last_generation_attempts, ModelGenerationAttempt(
            number,
            phase,
            schema_name,
            status,
            tuple(getattr(exc, "violations", ())),
            response_id=str(getattr(record, "response_id", "")),
            latency_ms=float(getattr(record, "latency_ms", 0.0)),
            prompt_tokens=int(getattr(record, "prompt_tokens", 0)),
            completion_tokens=int(getattr(record, "completion_tokens", 0)),
            total_tokens=int(getattr(record, "total_tokens", 0)),
            exception_class=type(exc).__name__ if exc else "",
            transcript=getattr(self.port, "last_transcript", None),
        )))

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
        rate_limit_retries=0,
        transient_retries=0,
        provider_circuit_break_s=0.0,
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
        messages = _auditor_messages(request)
        try:
            response = await self._generate(messages, AuditDeltaModel, "auditor_initial")
        except StructuredOutputError as exc:
            try:
                response = await self._generate(
                    _repair_messages(messages, exc),
                    AuditDeltaModel,
                    "auditor_schema_repair",
                )
            except Exception:
                return self._finish_failure(ModelFailure(ModelFailureKind.SCHEMA_ERROR, "auditor output invalid", False))
        except Exception:
            return self._finish_failure(ModelFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "auditor provider failed", True))
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

    async def _generate(self, messages, schema, phase: str):
        attempt_no = len(self.last_generation_attempts) + 1
        try:
            result = await self.port.generate_structured(messages, schema, self.config)
        except Exception as exc:
            self._append_attempt(attempt_no, phase, schema.__name__, "schema_error" if isinstance(exc, StructuredOutputError) else "failed", exc)
            raise
        self._append_attempt(attempt_no, phase, schema.__name__, "accepted")
        return result

    def _append_attempt(self, number: int, phase: str, schema_name: str, status: str, exc: Exception | None = None) -> None:
        record = getattr(self.port, "last_call", None)
        object.__setattr__(self, "last_generation_attempts", (*self.last_generation_attempts, ModelGenerationAttempt(
            number,
            phase,
            schema_name,
            status,
            tuple(getattr(exc, "violations", ())),
            response_id=str(getattr(record, "response_id", "")),
            latency_ms=float(getattr(record, "latency_ms", 0.0)),
            prompt_tokens=int(getattr(record, "prompt_tokens", 0)),
            completion_tokens=int(getattr(record, "completion_tokens", 0)),
            total_tokens=int(getattr(record, "total_tokens", 0)),
            exception_class=type(exc).__name__ if exc else "",
            transcript=getattr(self.port, "last_transcript", None),
        )))

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
    payload = {
        "task": _task_payload(request.original_task),
        "subtask": to_json_compatible(request.subtask),
        "pre_mission_state": _mission_payload(request.pre_mission_state),
        "after_world": {
            "observation_id": request.after_world.observation_id,
            "target_count": len(request.after_world.targets),
            "fact_count": len(request.after_world.facts),
        },
        "working_facts": to_json_compatible(request.working_facts),
        "yield_reason": request.yield_reason,
        "episode_history": to_json_compatible(request.episode_history),
        "audit_bundle": {
            "observation_id": request.audit_bundle.observation_id,
            "evidence": tuple(_evidence_payload(item) for item in request.audit_bundle.evidence_records),
        },
        "related_audit_ids": request.related_audit_ids,
    }
    return _messages(MISSION_AUDITOR_INSTRUCTIONS, payload)


def _messages(instructions: str, payload: Mapping[str, object]) -> tuple[ModelMessage, ...]:
    encoded = json.dumps(to_json_compatible(payload), separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > _MAX_ROLE_INPUT_BYTES:
        raise ValueError("mission role input exceeds bounded workspace")
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
        "task_id": task.task_id,
        "instruction": task.instruction,
        "constraints": task.constraints,
        "allowed_effects": task.allowed_effects,
        "forbidden_effects": task.forbidden_effects,
        "public_inputs": task.inputs,
        "success_criteria": task.success_criteria,
        "requested_outputs": task.requested_outputs,
        "risk_profile": task.risk_profile.value,
    }


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
