"""Evidence-backed recovery owner for configured model-provider fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from affordance_runtime.model_port import FallbackModelPort, ModelPort
from affordance_runtime.planner_context_recovery import context_compaction_owner_for_planner
from affordance_runtime.planner_schema_recovery import schema_repair_owner_for_planner
from affordance_runtime.recovery_owner_dispatcher import (
    RecoveryOwnerDispatcher,
    RecoveryOwnerResult,
    RecoveryOwningPort,
)
from affordance_runtime.recovery_protocol import RecoveryDecision, RecoveryDimension, RecoveryKind


@dataclass(frozen=True)
class FallbackProviderSwitchOwner:
    """Switch only between configured fallback profiles; never invent one."""

    model: FallbackModelPort
    owner_id: str = "fallback-model-provider-switch"

    @property
    def target_ref(self) -> str:
        return self.model.next_profile_ref

    def execute(self, decision: RecoveryDecision) -> RecoveryOwnerResult:
        before = self.model.active_profile_ref
        if decision.kind != RecoveryKind.SWITCH_PROVIDER:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=decision.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="unsupported_recovery_decision",
            )
        switched = self.model.switch_to_next_profile()
        if switched is None:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=decision.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="configured_fallback_unavailable",
            )
        before, after = switched
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=decision.kind,
            success=True,
            state_before_ref=before,
            state_after_ref=after,
            changed_dimensions=(RecoveryDimension.PROVIDER,),
            evidence_refs=(f"model-profile-switch:{before}->{after}",),
        )


def recovery_dispatcher_for_model(
    model: ModelPort,
    *,
    planner: object | None = None,
) -> RecoveryOwnerDispatcher:
    """Expose only configured provider/context owners with real state changes."""

    handlers: dict[RecoveryKind, RecoveryOwningPort] = {}
    context_owner = context_compaction_owner_for_planner(planner)
    if context_owner is not None:
        handlers[RecoveryKind.COMPACT_CONTEXT] = context_owner
    schema_owner = schema_repair_owner_for_planner(planner)
    if schema_owner is not None:
        handlers[RecoveryKind.REPAIR_MODEL_SCHEMA] = schema_owner
    if isinstance(model, FallbackModelPort) and model.next_profile_ref:
        handlers[RecoveryKind.SWITCH_PROVIDER] = cast(
            "RecoveryOwningPort",
            FallbackProviderSwitchOwner(model),
        )
    return RecoveryOwnerDispatcher(handlers)
