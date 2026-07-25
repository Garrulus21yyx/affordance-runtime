"""Evidence-backed recovery owner for configured model-provider fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from affordance_runtime.model_port import FallbackModelPort, ModelPort
from affordance_runtime.recovery_command_dispatcher import (
    RecoveryCommandDispatcher,
    RecoveryOwnerResult,
    RecoveryOwningPort,
)
from affordance_runtime.recovery_commands import (
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
)


@dataclass(frozen=True)
class FallbackProviderSwitchOwner:
    """Switch only between configured fallback profiles; never invent one."""

    model: FallbackModelPort
    owner_id: str = "fallback-model-provider-switch"

    @property
    def target_ref(self) -> str:
        return self.model.next_profile_ref

    def execute(self, command: RecoveryCommand) -> RecoveryOwnerResult:
        before = self.model.active_profile_ref
        if command.kind != RecoveryCommandKind.SWITCH_PROVIDER:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=command.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="unsupported_recovery_command",
            )
        switched = self.model.switch_to_next_profile()
        if switched is None:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=command.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="configured_fallback_unavailable",
            )
        before, after = switched
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=command.kind,
            success=True,
            state_before_ref=before,
            state_after_ref=after,
            changed_dimensions=(RecoveryChangeDimension.PROVIDER,),
            evidence_refs=(f"model-profile-switch:{before}->{after}",),
        )


def recovery_dispatcher_for_model(model: ModelPort) -> RecoveryCommandDispatcher:
    """Expose provider recovery only when the model has a real alternate profile."""

    if not isinstance(model, FallbackModelPort) or not model.next_profile_ref:
        return RecoveryCommandDispatcher()
    return RecoveryCommandDispatcher(
        {
            RecoveryCommandKind.SWITCH_PROVIDER: cast(
                "RecoveryOwningPort",
                FallbackProviderSwitchOwner(model),
            )
        }
    )
