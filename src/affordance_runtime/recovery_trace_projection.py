"""Typed recovery protocol trace projections without Runtime mutation."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_commands import RecoveryPlan


@dataclass(frozen=True)
class RecoveryTraceProjection:
    kind: str
    payload: dict[str, object]


def recovery_protocol_projections(
    *,
    state_phase: str,
    failure: FailureEnvelope,
    plan: RecoveryPlan,
) -> tuple[RecoveryTraceProjection, ...]:
    """Project selected recovery facts; Coordinator remains the trace writer."""

    command = plan.commands[0]
    return (
        RecoveryTraceProjection(
            "FailureDetected",
            {"state": state_phase, "failure": failure.model_dump(mode="json")},
        ),
        RecoveryTraceProjection(
            "RecoveryStrategySelected",
            {
                "state": state_phase,
                "plan": plan.model_dump(mode="json"),
                "strategy_id": command.strategy_id,
                "changed_dimensions": [item.value for item in command.changed_dimensions],
            },
        ),
        RecoveryTraceProjection(
            "RecoveryCommandStarted",
            {"state": state_phase, "command": command.model_dump(mode="json")},
        ),
    )
