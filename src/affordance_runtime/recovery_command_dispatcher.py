"""Invoke recovery owning ports and reject synthetic or no-op completion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from pydantic import Field

from affordance_runtime.recovery_commands import (
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
    RecoveryDelta,
    RecoveryReceipt,
)
from affordance_runtime.task_intake import StrictModel

OWNER_DISPATCH_COMMANDS = frozenset(
    {
        RecoveryCommandKind.COMPACT_CONTEXT,
        RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
        RecoveryCommandKind.SWITCH_PROVIDER,
    }
)


class RecoveryOwnerResult(StrictModel):
    owner_id: str = Field(min_length=1)
    kind: RecoveryCommandKind
    success: bool
    state_before_ref: str = Field(min_length=1)
    state_after_ref: str = Field(min_length=1)
    changed_dimensions: tuple[RecoveryChangeDimension, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    error_code: str = ""
    latency_ms: float = Field(default=0.0, ge=0.0)
    estimated_cost: float = Field(default=0.0, ge=0.0)


class RecoveryOwningPort(Protocol):
    owner_id: str
    target_ref: str

    def execute(self, command: RecoveryCommand) -> RecoveryOwnerResult: ...


@dataclass(frozen=True)
class RecoveryDispatchResult:
    receipt: RecoveryReceipt
    delta: RecoveryDelta | None = None


@dataclass(frozen=True)
class RecoveryCommandDispatcher:
    handlers: Mapping[RecoveryCommandKind, RecoveryOwningPort] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unsupported = set(self.handlers) - OWNER_DISPATCH_COMMANDS
        if unsupported:
            raise ValueError(f"recovery dispatcher received non-owning-port commands: {unsupported}")

    @property
    def available_commands(self) -> frozenset[RecoveryCommandKind]:
        return frozenset(self.handlers)

    def target_ref(self, kind: RecoveryCommandKind) -> str:
        handler = self.handlers.get(kind)
        return handler.target_ref if handler is not None else ""

    def dispatch(
        self,
        command: RecoveryCommand,
        *,
        previous_attempt_fingerprint: str,
    ) -> RecoveryDispatchResult:
        handler = self.handlers.get(command.kind)
        if handler is None:
            return _failed(command, "owning_port_unavailable", "unavailable", "unavailable")
        try:
            result = handler.execute(command)
        except Exception as exc:
            return _failed(
                command,
                f"owning_port_exception:{type(exc).__name__}",
                handler.owner_id,
                handler.owner_id,
            )
        error = _owner_result_error(command, handler, result)
        if error:
            return _failed(
                command,
                error,
                result.state_before_ref,
                result.state_after_ref,
                latency_ms=result.latency_ms,
                estimated_cost=result.estimated_cost,
            )
        next_fingerprint = _result_fingerprint(command, result)
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_attempt_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=result.changed_dimensions,
            new_evidence_refs=result.evidence_refs,
            new_plan_or_route_ref=result.state_after_ref,
            explanation=command.expected_change,
        )
        return RecoveryDispatchResult(
            RecoveryReceipt(
                command_id=command.command_id,
                success=True,
                state_before=result.state_before_ref,
                state_after=result.state_after_ref,
                changed_dimensions=result.changed_dimensions,
                artifact_refs=result.evidence_refs,
                plan_refs=(result.state_after_ref,),
                latency_ms=result.latency_ms,
                estimated_cost=result.estimated_cost,
                delta=delta,
            ),
            delta,
        )


def _owner_result_error(
    command: RecoveryCommand,
    handler: RecoveryOwningPort,
    result: RecoveryOwnerResult,
) -> str:
    if not result.success:
        return result.error_code or "owning_port_failed"
    if result.kind != command.kind or result.owner_id != handler.owner_id:
        return "owning_port_identity_mismatch"
    if result.state_before_ref == result.state_after_ref:
        return "owning_port_no_op"
    if set(result.changed_dimensions) != set(command.changed_dimensions):
        return "owning_port_dimension_mismatch"
    if not result.evidence_refs:
        return "owning_port_evidence_missing"
    if result.error_code:
        return "owning_port_success_with_error"
    return ""


def _failed(
    command: RecoveryCommand,
    error_code: str,
    state_before: str,
    state_after: str,
    *,
    latency_ms: float = 0.0,
    estimated_cost: float = 0.0,
) -> RecoveryDispatchResult:
    return RecoveryDispatchResult(
        RecoveryReceipt(
            command_id=command.command_id,
            success=False,
            state_before=state_before,
            state_after=state_after,
            error_code=error_code,
            latency_ms=latency_ms,
            estimated_cost=estimated_cost,
        )
    )


def _result_fingerprint(command: RecoveryCommand, result: RecoveryOwnerResult) -> str:
    payload = {
        "command_id": command.command_id,
        "kind": command.kind.value,
        "owner_id": result.owner_id,
        "state_before_ref": result.state_before_ref,
        "state_after_ref": result.state_after_ref,
        "changed_dimensions": [item.value for item in result.changed_dimensions],
        "evidence_refs": list(result.evidence_refs),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
