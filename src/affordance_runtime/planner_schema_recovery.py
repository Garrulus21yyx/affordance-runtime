"""Evidence-backed schema recovery for planner model orchestration."""

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
class PlannerSchemaRepairPort(Protocol):
    """A planner-owned, one-way schema-narrowing state transition."""

    def repair_planner_schema(self) -> tuple[str, str] | None: ...

    def planner_schema_ref(self) -> str: ...


@dataclass(frozen=True)
class PlannerSchemaRepairOwner:
    """Switch subsequent model generation to the target-bound repair schema."""

    planner: PlannerSchemaRepairPort
    owner_id: str = "planner-model-schema-repair"

    @property
    def target_ref(self) -> str:
        return self.planner.planner_schema_ref()

    def execute(self, command: RecoveryCommand) -> RecoveryOwnerResult:
        before = self.planner.planner_schema_ref()
        if command.kind != RecoveryCommandKind.REPAIR_MODEL_SCHEMA:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=command.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="unsupported_recovery_command",
            )
        repaired = self.planner.repair_planner_schema()
        if repaired is None:
            return RecoveryOwnerResult(
                owner_id=self.owner_id,
                kind=command.kind,
                success=False,
                state_before_ref=before,
                state_after_ref=before,
                error_code="planner_schema_already_repaired",
            )
        before, after = repaired
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=command.kind,
            success=True,
            state_before_ref=before,
            state_after_ref=after,
            changed_dimensions=(RecoveryChangeDimension.CONTEXT,),
            evidence_refs=(f"planner-schema-repaired:{before}->{after}",),
        )


def schema_repair_owner_for_planner(planner: object | None) -> RecoveryOwningPort | None:
    """Expose schema repair only for a planner with owned schema state."""

    if not isinstance(planner, PlannerSchemaRepairPort):
        return None
    return cast(RecoveryOwningPort, PlannerSchemaRepairOwner(planner))
