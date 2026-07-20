"""Bounded recovery decisions for contract execution failures.

This keeps the earlier retry/reroute/rollback cascade, but removes smart-room
skill coupling and makes uncertain side effects inspect-before-retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode


class RecoveryAction(StrEnum):
    REOBSERVE = "reobserve"
    VERIFY_STATE = "verify_state"
    RETRY = "retry"
    REROUTE = "reroute"
    COMPENSATE = "compensate"
    REQUEST_APPROVAL = "request_approval"
    ABORT = "abort"


@dataclass(frozen=True)
class RecoveryContext:
    attempt: int = 0
    recovery_count: int = 0
    tried_backends: list[str] = field(default_factory=list)
    backend_fallback_count: int = 0
    effect_may_have_occurred: bool = False
    approval_available: bool = False


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

        code = error_code or (receipt.error_code if receipt else None)
        if code == RuntimeErrorCode.STALE_OBSERVATION:
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
