"""Bounded recovery decisions for contract execution failures.

This keeps the earlier retry/reroute/rollback cascade, but removes smart-room
skill coupling and makes uncertain side effects inspect-before-retry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode


class RecoveryAction(StrEnum):
    REOBSERVE = "reobserve"
    VERIFY_STATE = "verify_state"
    RETRY = "retry"
    REROUTE = "reroute"
    COMPENSATE = "compensate"
    REQUEST_APPROVAL = "request_approval"
    ABORT = "abort"


class RecoveryAttemptOutcome(StrEnum):
    PENDING = "pending"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    LOOP_ABORTED = "loop_aborted"


class RecoveryLoopKind(StrEnum):
    REPEATED_SIGNATURE = "repeated_signature"
    NO_PROGRESS = "no_progress"
    AB_OSCILLATION = "a_b_oscillation"
    REPEATED_STALE_CONTRACT = "repeated_stale_contract"
    REPEATED_VERIFIER_FAILURE = "repeated_verifier_failure"
    FALLBACK_EXHAUSTION = "fallback_exhaustion"
    DUPLICATE_EFFECT_RISK = "duplicate_effect_risk"


@dataclass(frozen=True)
class FailureSignature:
    phase: str
    normalized_error: str
    error_code: str
    action: str
    backend: str
    target_fingerprint: str
    verifier_kind: str
    state_revision: str

    @classmethod
    def from_failure(
        cls,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        *,
        phase: str,
        error_code: RuntimeErrorCode | None,
        state_revision: str,
    ) -> "FailureSignature":
        code = error_code or (receipt.error_code if receipt else None)
        message = receipt.message if receipt else (code.value if code else "unknown")
        return cls(
            phase=phase,
            normalized_error=_normalize_error(message),
            error_code=code.value if code else "unknown",
            action=contract.action,
            backend=contract.backend,
            target_fingerprint=contract.target_fingerprint,
            verifier_kind=contract.verifier_plan[0].kind if contract.verifier_plan else "",
            state_revision=state_revision,
        )

    def key(self, *, include_revision: bool = False) -> str:
        value = {
            "phase": self.phase,
            "normalized_error": self.normalized_error,
            "error_code": self.error_code,
            "action": self.action,
            "backend": self.backend,
            "target_fingerprint": self.target_fingerprint,
            "verifier_kind": self.verifier_kind,
        }
        if include_revision:
            value["state_revision"] = self.state_revision
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass
class RecoveryAttempt:
    index: int
    signature: FailureSignature
    recovery_action: RecoveryAction
    state_before: str
    state_after: str = ""
    outcome: RecoveryAttemptOutcome = RecoveryAttemptOutcome.PENDING
    effect_may_have_occurred: bool = False
    idempotency_key: str = ""


@dataclass
class RecoveryIncident:
    incident_id: str
    source_contract_id: str
    source_snapshot_id: str
    root_failure: FailureSignature
    attempts: list[RecoveryAttempt] = field(default_factory=list)
    symptom_chain: list[FailureSignature] = field(default_factory=list)
    findings: list[RecoveryLoopKind] = field(default_factory=list)
    terminal_outcome: str = "open"
    context: dict[str, Any] = field(default_factory=dict)

    def complete_pending(self, state_after: str, outcome: RecoveryAttemptOutcome) -> None:
        pending = next((item for item in reversed(self.attempts) if item.outcome == RecoveryAttemptOutcome.PENDING), None)
        if pending is not None:
            pending.state_after = state_after
            pending.outcome = outcome

    def diagnostics(self) -> dict[str, Any]:
        repeated = max(0, len(self.attempts) - len({item.signature.key() for item in self.attempts}))
        completed = [item for item in self.attempts if item.outcome != RecoveryAttemptOutcome.PENDING]
        effective = sum(item.outcome == RecoveryAttemptOutcome.SUCCEEDED for item in completed)
        duplicate_risks = sum(
            item.recovery_action == RecoveryAction.RETRY
            and item.effect_may_have_occurred
            and not item.idempotency_key
            for item in self.attempts
        )
        return {
            "incident_id": self.incident_id,
            "cascade_depth": len(self.attempts),
            "repeated_failures": repeated,
            "repeated_failure_rate": repeated / len(self.attempts) if self.attempts else 0.0,
            "loop_aborts": int(self.terminal_outcome == RecoveryAttemptOutcome.LOOP_ABORTED.value),
            "effective_recovery_actions": effective,
            "recovery_action_effectiveness": effective / len(completed) if completed else 0.0,
            "duplicate_effect_risk_count": duplicate_risks,
            "findings": [item.value for item in self.findings],
            "terminal_outcome": self.terminal_outcome,
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class RecoveryCascadeAssessment:
    findings: tuple[RecoveryLoopKind, ...]
    should_abort: bool


@dataclass(frozen=True)
class RecoveryCascadeDetector:
    """Detect deterministic repeated cascades before another action is issued."""

    def assess(
        self,
        incident: RecoveryIncident,
        current: FailureSignature,
        *,
        fallbacks_remaining: bool,
        effect_may_have_occurred: bool,
        idempotency_key: str,
    ) -> RecoveryCascadeAssessment:
        previous_signatures = [item.signature for item in incident.attempts]
        keys = [item.key() for item in previous_signatures] + [current.key()]
        findings: list[RecoveryLoopKind] = []
        if current.key() in keys[:-1]:
            findings.append(RecoveryLoopKind.REPEATED_SIGNATURE)
        completed = [item for item in incident.attempts if item.outcome != RecoveryAttemptOutcome.PENDING]
        if completed and completed[-1].state_before == completed[-1].state_after:
            findings.append(RecoveryLoopKind.NO_PROGRESS)
        if len(keys) >= 3 and keys[-1] == keys[-3] and keys[-1] != keys[-2]:
            findings.append(RecoveryLoopKind.AB_OSCILLATION)
        stale_codes = {
            RuntimeErrorCode.STALE_OBSERVATION.value,
            RuntimeErrorCode.STALE_PAGE_REVISION.value,
            RuntimeErrorCode.SNAPSHOT_MISMATCH.value,
            RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH.value,
        }
        if current.error_code in stale_codes and sum(item.error_code in stale_codes for item in previous_signatures) >= 1:
            findings.append(RecoveryLoopKind.REPEATED_STALE_CONTRACT)
        if current.error_code == RuntimeErrorCode.VERIFICATION_FAILED.value and sum(
            item.error_code == RuntimeErrorCode.VERIFICATION_FAILED.value for item in previous_signatures
        ) >= 1:
            findings.append(RecoveryLoopKind.REPEATED_VERIFIER_FAILURE)
        if previous_signatures and not fallbacks_remaining and any(
            item.recovery_action == RecoveryAction.REROUTE for item in incident.attempts
        ):
            findings.append(RecoveryLoopKind.FALLBACK_EXHAUSTION)
        if incident.attempts and any(
            item.recovery_action == RecoveryAction.RETRY
            and item.effect_may_have_occurred
            and not item.idempotency_key
            for item in incident.attempts
        ):
            findings.append(RecoveryLoopKind.DUPLICATE_EFFECT_RISK)
        abort_kinds = {
            RecoveryLoopKind.REPEATED_SIGNATURE,
            RecoveryLoopKind.NO_PROGRESS,
            RecoveryLoopKind.AB_OSCILLATION,
            RecoveryLoopKind.REPEATED_STALE_CONTRACT,
            RecoveryLoopKind.REPEATED_VERIFIER_FAILURE,
            RecoveryLoopKind.FALLBACK_EXHAUSTION,
            RecoveryLoopKind.DUPLICATE_EFFECT_RISK,
        }
        unique = tuple(dict.fromkeys(findings))
        return RecoveryCascadeAssessment(unique, bool(abort_kinds.intersection(unique)))


@dataclass(frozen=True)
class RecoveryContext:
    attempt: int = 0
    recovery_count: int = 0
    tried_backends: list[str] = field(default_factory=list)
    backend_fallback_count: int = 0
    effect_may_have_occurred: bool = False
    approval_available: bool = False
    failure_signature: FailureSignature | None = None
    task_id: str = ""


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    backend: str | None = None


@dataclass
class BoundedRecoveryPolicy:
    max_recoveries: int = 3
    max_retries: int = 1
    max_backend_fallbacks: int = 1
    decision_override: Callable[
        [ActionContract, ExecutionReceipt | None, RecoveryContext, RuntimeErrorCode | None],
        RecoveryDecision | None,
    ] | None = None

    def decide(
        self,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        context: RecoveryContext,
        *,
        error_code: RuntimeErrorCode | None = None,
    ) -> RecoveryDecision:
        if context.recovery_count >= self.max_recoveries:
            return RecoveryDecision(RecoveryAction.ABORT, "recovery budget exhausted")

        if self.decision_override is not None:
            override = self.decision_override(contract, receipt, context, error_code)
            if override is not None:
                return override

        code = error_code or (receipt.error_code if receipt else None)
        if code in {
            RuntimeErrorCode.STALE_OBSERVATION,
            RuntimeErrorCode.STALE_PAGE_REVISION,
            RuntimeErrorCode.SNAPSHOT_MISMATCH,
            RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
            RuntimeErrorCode.LEASE_EXPIRED,
        }:
            return RecoveryDecision(RecoveryAction.REOBSERVE, "contract state is stale")
        if code in {RuntimeErrorCode.CAPABILITY_DENIED, RuntimeErrorCode.UNSAFE_ACTION}:
            if context.approval_available:
                return RecoveryDecision(RecoveryAction.REQUEST_APPROVAL, "capability or approval is required")
            return RecoveryDecision(RecoveryAction.ABORT, "action is not authorized")

        if context.effect_may_have_occurred:
            return RecoveryDecision(
                RecoveryAction.VERIFY_STATE,
                "execution outcome is uncertain; inspect post-state before retry",
            )

        if receipt is not None and receipt.success:
            return RecoveryDecision(RecoveryAction.VERIFY_STATE, "execution succeeded; verify expected effects")

        if (
            receipt is not None
            and receipt.evidence.get("dispatched") is False
            and contract.grounding_candidate is not None
            and code == RuntimeErrorCode.EXECUTION_FAILED
        ):
            # A deterministic failure before dispatch disproves the selected
            # grounding route, not the semantic intent.  Exclude it and let
            # the next coherent observation acquire another typed source.
            return RecoveryDecision(
                RecoveryAction.REROUTE,
                "selected grounding route failed before dispatch",
            )

        route_alternatives = contract.route_plan.viable_alternatives if contract.route_plan else ()
        if route_alternatives:
            alternative = route_alternatives[0]
            return RecoveryDecision(
                RecoveryAction.REROUTE,
                "exclude failed grounding candidate and bind a fresh route",
                alternative.compatible_executor,
            )

        can_retry = (
            context.attempt < self.max_retries
            and bool(contract.idempotency_key)
            and contract.risk != RiskLevel.IRREVERSIBLE
        )
        if can_retry:
            return RecoveryDecision(RecoveryAction.RETRY, "idempotent action may be retried once", contract.backend)

        tried = set(context.tried_backends)
        fallbacks = [backend for backend in contract.fallback_backends if backend not in tried]
        if fallbacks and context.backend_fallback_count < self.max_backend_fallbacks:
            return RecoveryDecision(RecoveryAction.REROUTE, "use next untried contract fallback", fallbacks[0])

        if contract.compensation:
            return RecoveryDecision(RecoveryAction.COMPENSATE, "contract declares a compensation action")

        return RecoveryDecision(RecoveryAction.ABORT, "no safe recovery remains")


def _normalize_error(message: str) -> str:
    value = message.lower().strip()
    value = re.sub(r"https?://\S+", "<url>", value)
    value = re.sub(r"\b[0-9a-f]{16,}\b", "<id>", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", value)
    return re.sub(r"\s+", " ", value)[:240]
