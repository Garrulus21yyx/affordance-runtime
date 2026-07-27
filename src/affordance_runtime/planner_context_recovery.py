"""Evidence-backed context compaction ownership for planner-facing context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

from affordance_runtime.recovery_command_dispatcher import RecoveryOwnerResult, RecoveryOwningPort
from affordance_runtime.recovery_commands import (
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
)


@runtime_checkable
class PlannerContextCompactionPort(Protocol):
    """The only surface a context-recovery owner may mutate."""

    def compact_planner_context(self) -> tuple[str, str] | None: ...

    def planner_context_ref(self) -> str: ...


@dataclass(frozen=True)
class PlannerContextCompactionOwner:
    """Compact configured planner context without changing task authority."""

    planner: PlannerContextCompactionPort
    owner_id: str = "planner-context-compaction"

    @property
    def target_ref(self) -> str:
        return self.planner.planner_context_ref()

    def execute(self, command: RecoveryCommand) -> RecoveryOwnerResult:
        before = self.planner.planner_context_ref()
        if command.kind != RecoveryCommandKind.COMPACT_CONTEXT:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=command.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="unsupported_recovery_command",
            )
        compacted = self.planner.compact_planner_context()
        if compacted is None:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=command.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="planner_context_already_minimal",
            )
        before, after = compacted
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=command.kind,
            success=True,
            state_before_ref=before,
            state_after_ref=after,
            changed_dimensions=(RecoveryChangeDimension.CONTEXT,),
            evidence_refs=(f"planner-context-compacted:{before}->{after}",),
        )


def context_compaction_owner_for_planner(
    planner: object | None,
) -> RecoveryOwningPort | None:
    """Expose an owner only for a planner with an actual compaction surface."""

    if not isinstance(planner, PlannerContextCompactionPort):
        return None
    return cast(RecoveryOwningPort, PlannerContextCompactionOwner(planner))
