"""Typed recovery protocol trace projections without Runtime mutation."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.immutable import freeze_json
from affordance_runtime.recovery_commands import RecoveryCommand
from affordance_runtime.recovery_protocol import RecoveryDecision


@dataclass(frozen=True)
class RecoveryTraceProjection:
    kind: str
    payload: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_json(self.payload))


def recovery_protocol_projections(
    *,
    state_phase: str,
    failure: FailureEnvelope,
    decision: RecoveryDecision,
    command: RecoveryCommand,
) -> tuple[RecoveryTraceProjection, ...]:
    """Project selected recovery facts; Coordinator remains the trace writer."""

    return (
        RecoveryTraceProjection(
            "FailureDetected",
            {"state": state_phase, "failure": failure.model_dump(mode="json")},
        ),
        RecoveryTraceProjection(
            "RecoveryStrategySelected",
            {
                "state": state_phase,
                "decision": {
                    "decision_id": decision.decision_id,
                    "failure_id": decision.failure_id,
                    "based_on_state_version": decision.based_on_state_version,
                    "strategy_key": decision.strategy_key,
                    "kind": decision.kind.value,
                    "reason_code": decision.reason_code,
                    "reentry_phase": decision.reentry_phase.value,
                    "changed_dimensions": [item.value for item in decision.changed_dimensions],
                },
                "strategy_id": command.strategy_id,
                "changed_dimensions": [item.value for item in command.changed_dimensions],
            },
        ),
        RecoveryTraceProjection(
            "RecoveryCommandStarted",
            {"state": state_phase, "command": command.model_dump(mode="json")},
        ),
    )
