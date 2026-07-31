"""Phase-general, environment-neutral Runtime failure contracts."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import Field, model_validator

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.task_intake import StrictModel


class FailurePhase(StrEnum):
    INTAKE = "intake"
    OBSERVATION = "observation"
    FUSION = "fusion"
    TASK_PLANNING = "task_planning"
    STEP_PLANNING = "step_planning"
    PROPOSAL_VALIDATION = "proposal_validation"
    GROUNDING_BINDING = "grounding_binding"
    PREFLIGHT = "preflight"
    EXECUTION_NOT_DISPATCHED = "execution_not_dispatched"
    EXECUTION_UNCERTAIN = "execution_uncertain"
    VERIFICATION = "verification"
    PROGRESS = "progress"
    PROVIDER_CONTEXT = "provider_context"
    SKILL_ACTIVATION = "skill_activation"


class FailureClass(StrEnum):
    INVALID_INPUT = "invalid_input"
    MISSING_EVIDENCE = "missing_evidence"
    SOURCE_CONFLICT = "source_conflict"
    STALE_STATE = "stale_state"
    PLANNING = "planning"
    VALIDATION = "validation"
    GROUNDING = "grounding"
    AUTHORITY = "authority"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    PROVIDER = "provider"
    CONTEXT = "context"
    SKILL = "skill"
    BUDGET = "budget"
    INTERNAL = "internal"


class EffectStatus(StrEnum):
    NOT_DISPATCHED = "not_dispatched"
    MAY_HAVE_OCCURRED = "may_have_occurred"
    CONFIRMED_OCCURRED = "confirmed_occurred"
    CONFIRMED_NOT_OCCURRED = "confirmed_not_occurred"
    IRREVERSIBLE_OR_UNKNOWN = "irreversible_or_unknown"


class RemainingRecoveryBudgets(StrictModel):
    recoveries: int = Field(default=0, ge=0, le=64)
    observations: int = Field(default=0, ge=0, le=1_000)
    replans: int = Field(default=0, ge=0, le=1_000)
    provider_switches: int = Field(default=0, ge=0, le=16)
    user_escalations: int = Field(default=0, ge=0, le=16)
    timeout_ms: int = Field(default=0, ge=0, le=3_600_000)
    model_calls: int = Field(default=0, ge=0, le=1_000)
    estimated_cost: float = Field(default=0.0, ge=0.0)


class ProposalRejectionContext(StrictModel):
    """Bounded validator-owned facts for one rejected semantic proposal."""

    code: str = Field(min_length=1, max_length=80)
    reason_code: str = Field(default="", max_length=80)
    semantic_target_id: str = Field(default="", max_length=320)


class FailureEnvelope(StrictModel):
    """One failure representation valid before or after contract creation."""

    failure_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_revision: int = Field(default=1, ge=1)
    plan_version: int = Field(default=0, ge=0)
    active_subgoal_id: str = ""
    phase: FailurePhase
    failure_class: FailureClass
    semantic_family_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    exact_debug_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    state_version: int = Field(default=0, ge=0)
    observation_epoch_id: str = ""
    snapshot_id: str = ""
    proposal_id: str = ""
    proposal_rejection: ProposalRejectionContext | None = None
    contract_id: str = ""
    expected_effect: str = ""
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=500)
    evidence_refs: tuple[str, ...] = ()
    receipt_ref: str = ""
    verification_ref: str = ""
    effect_status: EffectStatus = EffectStatus.NOT_DISPATCHED
    attempted_strategy_ids: tuple[str, ...] = ()
    rejected_assumptions: tuple[str, ...] = ()
    remaining_budgets: RemainingRecoveryBudgets = Field(
        default_factory=RemainingRecoveryBudgets
    )
    recoverable: bool = True
    progress_fingerprint: str = ""

    @model_validator(mode="after")
    def validate_effect_and_lineage(self) -> "FailureEnvelope":
        execution_phases = {
            FailurePhase.EXECUTION_NOT_DISPATCHED,
            FailurePhase.EXECUTION_UNCERTAIN,
            FailurePhase.VERIFICATION,
            FailurePhase.PROGRESS,
        }
        if self.effect_status != EffectStatus.NOT_DISPATCHED and self.phase not in execution_phases:
            raise ValueError("pre-execution failures cannot claim an external effect")
        if self.phase == FailurePhase.EXECUTION_NOT_DISPATCHED and self.effect_status not in {
            EffectStatus.NOT_DISPATCHED,
            EffectStatus.CONFIRMED_NOT_OCCURRED,
        }:
            raise ValueError("not-dispatched execution cannot claim a possible effect")
        if self.phase == FailurePhase.EXECUTION_UNCERTAIN and self.effect_status not in {
            EffectStatus.MAY_HAVE_OCCURRED,
            EffectStatus.IRREVERSIBLE_OR_UNKNOWN,
        }:
            raise ValueError("uncertain execution requires an uncertain effect status")
        if self.contract_id == "" and self.receipt_ref:
            raise ValueError("a receipt reference requires contract lineage")
        if len(self.attempted_strategy_ids) != len(set(self.attempted_strategy_ids)):
            raise ValueError("attempted recovery strategy ids must be unique")
        if (
            self.proposal_rejection is not None
            and self.phase
            not in {
                FailurePhase.PROPOSAL_VALIDATION,
                FailurePhase.GROUNDING_BINDING,
            }
        ):
            raise ValueError(
                "proposal rejection context requires proposal validation or grounding binding phase"
            )
        return self


def make_failure_envelope(
    *,
    run_id: str,
    phase: FailurePhase,
    failure_class: FailureClass,
    error_code: RuntimeErrorCode | str,
    message: str,
    state_version: int,
    task_revision: int = 1,
    plan_version: int = 0,
    active_subgoal_id: str = "",
    observation_epoch_id: str = "",
    snapshot_id: str = "",
    proposal_id: str = "",
    proposal_rejection: ProposalRejectionContext | None = None,
    contract: ActionContract | None = None,
    receipt: ExecutionReceipt | None = None,
    expected_effect: str = "",
    evidence_refs: tuple[str, ...] = (),
    receipt_ref: str = "",
    verification_ref: str = "",
    effect_status: EffectStatus | None = None,
    attempted_strategy_ids: tuple[str, ...] = (),
    rejected_assumptions: tuple[str, ...] = (),
    remaining_budgets: RemainingRecoveryBudgets | None = None,
    recoverable: bool = True,
    progress_fingerprint: str = "",
    debug_context: Mapping[str, Any] | None = None,
) -> FailureEnvelope:
    """Build stable semantic and exact keys from redacted Runtime facts."""

    code = error_code.value if isinstance(error_code, RuntimeErrorCode) else str(error_code)
    resolved_effect_status = effect_status or infer_effect_status(phase, receipt)
    semantic_value = {
        "phase": phase.value,
        "failure_class": failure_class.value,
        "active_subgoal_id": active_subgoal_id,
        "expected_effect": _normalize_semantic_text(expected_effect),
        "effect_status": resolved_effect_status.value,
        "progress_fingerprint": progress_fingerprint,
        "proposal_rejection_code": (
            proposal_rejection.code if proposal_rejection is not None else ""
        ),
        "proposal_rejection_reason_code": (
            proposal_rejection.reason_code if proposal_rejection is not None else ""
        ),
    }
    exact_value = {
        **semantic_value,
        "error_code": code,
        "message": _normalize_debug_text(message),
        "observation_epoch_id": observation_epoch_id,
        "snapshot_id": snapshot_id,
        "proposal_id": proposal_id,
        "rejected_semantic_target_id": (
            proposal_rejection.semantic_target_id
            if proposal_rejection is not None
            else ""
        ),
        "contract_id": contract.id if contract is not None else "",
        "receipt_contract_id": receipt.contract_id if receipt is not None else "",
        "debug_context": _safe_debug_mapping(debug_context or {}),
    }
    return FailureEnvelope(
        failure_id=f"failure-{uuid4().hex}",
        run_id=run_id,
        task_revision=task_revision,
        plan_version=plan_version,
        active_subgoal_id=active_subgoal_id,
        phase=phase,
        failure_class=failure_class,
        semantic_family_key=_digest(semantic_value),
        exact_debug_key=_digest(exact_value),
        state_version=state_version,
        observation_epoch_id=observation_epoch_id,
        snapshot_id=snapshot_id,
        proposal_id=proposal_id,
        proposal_rejection=proposal_rejection,
        contract_id=contract.id if contract is not None else "",
        expected_effect=expected_effect,
        error_code=code,
        message=_normalize_debug_text(message),
        evidence_refs=evidence_refs,
        receipt_ref=receipt_ref,
        verification_ref=verification_ref,
        effect_status=resolved_effect_status,
        attempted_strategy_ids=attempted_strategy_ids,
        rejected_assumptions=rejected_assumptions,
        remaining_budgets=remaining_budgets or RemainingRecoveryBudgets(),
        recoverable=recoverable,
        progress_fingerprint=progress_fingerprint,
    )


def infer_effect_status(
    phase: FailurePhase,
    receipt: ExecutionReceipt | None,
) -> EffectStatus:
    if phase not in {
        FailurePhase.EXECUTION_NOT_DISPATCHED,
        FailurePhase.EXECUTION_UNCERTAIN,
        FailurePhase.VERIFICATION,
    }:
        return EffectStatus.NOT_DISPATCHED
    if receipt is None or receipt.evidence.get("dispatched") is False:
        return EffectStatus.NOT_DISPATCHED
    if receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT:
        return EffectStatus.MAY_HAVE_OCCURRED
    if phase == FailurePhase.EXECUTION_UNCERTAIN:
        return EffectStatus.MAY_HAVE_OCCURRED
    if phase == FailurePhase.VERIFICATION:
        return EffectStatus.MAY_HAVE_OCCURRED
    return EffectStatus.CONFIRMED_NOT_OCCURRED


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _normalize_semantic_text(value: str) -> str:
    normalized = value.casefold().strip()
    normalized = re.sub(r"https?://\S+", "<url>", normalized)
    normalized = re.sub(r"\b(?:selector|target|backend|mark|coordinate)s?\s*[:=]\s*\S+", "", normalized)
    normalized = re.sub(r"\b[0-9a-f]{12,}\b", "<id>", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", normalized)
    return re.sub(r"\s+", " ", normalized)[:240]


def _normalize_debug_text(value: str) -> str:
    normalized = value.strip()
    normalized = re.sub(r"(?i)(api[_-]?key|authorization|token)\s*[:=]\s*\S+", r"\1=<redacted>", normalized)
    return re.sub(r"\s+", " ", normalized)[:500] or "unknown failure"


def _safe_debug_mapping(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(key): _normalize_debug_text(str(item))
        for key, item in value.items()
        if str(key).casefold() not in {"api_key", "authorization", "token", "secret", "password"}
    }
