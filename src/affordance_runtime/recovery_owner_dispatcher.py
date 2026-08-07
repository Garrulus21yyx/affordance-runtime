"""Canonical SAR-8 recovery owner dispatcher."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_protocol import (
    RecoveryDecision,
    RecoveryDimension,
    RecoveryKind,
    RecoveryOutcome,
)

OWNER_DISPATCH_RECOVERY_KINDS = frozenset(
    {
        RecoveryKind.COMPACT_CONTEXT,
        RecoveryKind.REPAIR_MODEL_SCHEMA,
        RecoveryKind.SWITCH_PROVIDER,
    }
)


@dataclass(frozen=True)
class RecoveryOwnerResult:
    owner_id: str
    kind: RecoveryKind
    success: bool
    state_before_ref: str
    state_after_ref: str
    changed_dimensions: tuple[RecoveryDimension, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    error_code: str = ""
    latency_ms: float = 0.0
    estimated_cost: float = 0.0

    def __post_init__(self) -> None:
        if not self.owner_id.strip():
            raise ValueError("recovery owner result owner_id is required")
        if not self.state_before_ref.strip():
            raise ValueError("recovery owner result state_before_ref is required")
        if not self.state_after_ref.strip():
            raise ValueError("recovery owner result state_after_ref is required")
        if self.latency_ms < 0:
            raise ValueError("recovery owner result latency_ms must be non-negative")
        if self.estimated_cost < 0:
            raise ValueError("recovery owner result estimated_cost must be non-negative")
        object.__setattr__(self, "changed_dimensions", tuple(self.changed_dimensions))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


class RecoveryOwningPort(Protocol):
    owner_id: str
    target_ref: str

    def execute(self, decision: RecoveryDecision) -> RecoveryOwnerResult: ...


@dataclass(frozen=True)
class RecoveryOwnerDispatchResult:
    outcome: RecoveryOutcome
    state_before_ref: str
    state_after_ref: str
    next_attempt_fingerprint: str = ""


@dataclass(frozen=True)
class RecoveryOwnerDispatcher:
    handlers: Mapping[RecoveryKind, RecoveryOwningPort] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unsupported = set(self.handlers) - OWNER_DISPATCH_RECOVERY_KINDS
        if unsupported:
            raise ValueError(f"recovery dispatcher received non-owning-port kinds: {unsupported}")

    @property
    def available_kinds(self) -> frozenset[RecoveryKind]:
        return frozenset(self.handlers)

    def target_ref(self, kind: RecoveryKind) -> str:
        handler = self.handlers.get(kind)
        return handler.target_ref if handler is not None else ""

    def dispatch(
        self,
        decision: RecoveryDecision,
        *,
        failure: FailureEnvelope,
        previous_attempt_fingerprint: str,
    ) -> RecoveryOwnerDispatchResult:
        handler = self.handlers.get(decision.kind)
        if handler is None:
            return _failed(decision, failure, "owning_port_unavailable", "unavailable", "unavailable")
        try:
            result = handler.execute(decision)
        except Exception as exc:
            return _failed(
                decision,
                failure,
                f"owning_port_exception:{type(exc).__name__}",
                handler.owner_id,
                handler.owner_id,
            )
        error = _owner_result_error(decision, handler, result)
        if error:
            return _failed(
                decision,
                failure,
                error,
                result.state_before_ref,
                result.state_after_ref,
            )
        next_fingerprint = _result_fingerprint(decision, result, previous_attempt_fingerprint)
        return RecoveryOwnerDispatchResult(
            outcome=RecoveryOutcome(
                decision_id=decision.decision_id,
                failure_id=failure.failure_id,
                success=True,
                changed_dimensions=result.changed_dimensions,
                next_phase=decision.reentry_phase,
                artifact_refs=result.evidence_refs,
                observation_refs=(),
            ),
            state_before_ref=result.state_before_ref,
            state_after_ref=result.state_after_ref,
            next_attempt_fingerprint=next_fingerprint,
        )


def _owner_result_error(
    decision: RecoveryDecision,
    handler: RecoveryOwningPort,
    result: RecoveryOwnerResult,
) -> str:
    if not result.success:
        return result.error_code or "owning_port_failed"
    if result.kind != decision.kind or result.owner_id != handler.owner_id:
        return "owning_port_identity_mismatch"
    if result.state_before_ref == result.state_after_ref:
        return "owning_port_no_op"
    if set(result.changed_dimensions) != set(decision.changed_dimensions):
        return "owning_port_dimension_mismatch"
    if not result.evidence_refs:
        return "owning_port_evidence_missing"
    if result.error_code:
        return "owning_port_success_with_error"
    return ""


def _failed(
    decision: RecoveryDecision,
    failure: FailureEnvelope,
    error_code: str,
    state_before: str,
    state_after: str,
) -> RecoveryOwnerDispatchResult:
    return RecoveryOwnerDispatchResult(
        outcome=RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=False,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            error_code=error_code,
        ),
        state_before_ref=state_before,
        state_after_ref=state_after,
    )


def _result_fingerprint(
    decision: RecoveryDecision,
    result: RecoveryOwnerResult,
    previous_attempt_fingerprint: str,
) -> str:
    payload = {
        "decision_id": decision.decision_id,
        "kind": decision.kind.value,
        "owner_id": result.owner_id,
        "previous_attempt_fingerprint": previous_attempt_fingerprint,
        "state_before_ref": result.state_before_ref,
        "state_after_ref": result.state_after_ref,
        "changed_dimensions": [item.value for item in result.changed_dimensions],
        "evidence_refs": list(result.evidence_refs),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
