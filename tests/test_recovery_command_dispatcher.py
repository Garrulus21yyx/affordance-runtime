from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import EffectStatus
from affordance_runtime.recovery_command_dispatcher import (
    RecoveryCommandDispatcher,
    RecoveryOwnerResult,
)
from affordance_runtime.recovery_commands import (
    RecoveryBudgetCost,
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
    RecoveryReentryPhase,
)


def _command(kind: RecoveryCommandKind) -> RecoveryCommand:
    dimension = {
        RecoveryCommandKind.COMPACT_CONTEXT: RecoveryChangeDimension.CONTEXT,
        RecoveryCommandKind.REPAIR_MODEL_SCHEMA: RecoveryChangeDimension.CONTEXT,
        RecoveryCommandKind.SWITCH_PROVIDER: RecoveryChangeDimension.PROVIDER,
    }[kind]
    return RecoveryCommand(
        command_id=f"command:{kind.value}",
        failure_id="failure-1",
        based_on_state_version=2,
        strategy_id=f"strategy:{kind.value}",
        kind=kind,
        expected_change=f"apply {kind.value} through its owning port",
        changed_dimensions=(dimension,),
        preconditions=("owning port is configured",),
        budget_cost=RecoveryBudgetCost(
            recoveries=1,
            replans=1,
            provider_switches=int(kind == RecoveryCommandKind.SWITCH_PROVIDER),
            timeout_ms=500,
        ),
        timeout_ms=500,
        reentry_phase=RecoveryReentryPhase.PLANNING,
        effect_status=EffectStatus.NOT_DISPATCHED,
        provider_id="provider-b" if kind == RecoveryCommandKind.SWITCH_PROVIDER else "",
    )


@dataclass
class RecordingOwner:
    kind: RecoveryCommandKind
    no_op: bool = False
    fail: bool = False
    owner_id: str = "context-owner"
    target_ref: str = "provider-b"
    calls: int = 0

    def execute(self, command: RecoveryCommand) -> RecoveryOwnerResult:
        self.calls += 1
        assert command.kind == self.kind
        dimension = command.changed_dimensions
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=self.kind,
            success=not self.fail,
            state_before_ref="context:before",
            state_after_ref="context:before" if self.no_op else "context:after",
            changed_dimensions=dimension if not self.fail else (),
            evidence_refs=("artifact:owner-result",) if not self.fail else (),
            error_code="owner_failed" if self.fail else "",
        )


def test_dispatcher_credits_only_real_evidence_backed_owner_change() -> None:
    owner = RecordingOwner(RecoveryCommandKind.COMPACT_CONTEXT)
    dispatcher = RecoveryCommandDispatcher(
        {RecoveryCommandKind.COMPACT_CONTEXT: owner}
    )

    result = dispatcher.dispatch(
        _command(RecoveryCommandKind.COMPACT_CONTEXT),
        previous_attempt_fingerprint="sha256:" + "1" * 64,
    )

    assert owner.calls == 1
    assert result.receipt.success
    assert result.delta is not None
    assert result.receipt.artifact_refs == ("artifact:owner-result",)
    assert result.delta.new_evidence_refs == ("artifact:owner-result",)
    assert result.delta.previous_attempt_fingerprint != result.delta.next_attempt_fingerprint


def test_dispatcher_rejects_no_op_owner_result_without_delta() -> None:
    owner = RecordingOwner(RecoveryCommandKind.REPAIR_MODEL_SCHEMA, no_op=True)
    dispatcher = RecoveryCommandDispatcher(
        {RecoveryCommandKind.REPAIR_MODEL_SCHEMA: owner}
    )

    result = dispatcher.dispatch(
        _command(RecoveryCommandKind.REPAIR_MODEL_SCHEMA),
        previous_attempt_fingerprint="sha256:" + "2" * 64,
    )

    assert owner.calls == 1
    assert not result.receipt.success
    assert result.receipt.error_code == "owning_port_no_op"
    assert result.delta is None
    assert result.receipt.delta is None


def test_dispatcher_rejects_failed_or_unavailable_owner_without_progress() -> None:
    owner = RecordingOwner(RecoveryCommandKind.SWITCH_PROVIDER, fail=True)
    dispatcher = RecoveryCommandDispatcher(
        {RecoveryCommandKind.SWITCH_PROVIDER: owner}
    )

    failed = dispatcher.dispatch(
        _command(RecoveryCommandKind.SWITCH_PROVIDER),
        previous_attempt_fingerprint="sha256:" + "3" * 64,
    )
    unavailable = RecoveryCommandDispatcher().dispatch(
        _command(RecoveryCommandKind.COMPACT_CONTEXT),
        previous_attempt_fingerprint="sha256:" + "4" * 64,
    )

    assert dispatcher.available_commands == frozenset(
        {RecoveryCommandKind.SWITCH_PROVIDER}
    )
    assert dispatcher.target_ref(RecoveryCommandKind.SWITCH_PROVIDER) == "provider-b"
    assert not failed.receipt.success and failed.delta is None
    assert failed.receipt.error_code == "owner_failed"
    assert not unavailable.receipt.success and unavailable.delta is None
    assert unavailable.receipt.error_code == "owning_port_unavailable"
