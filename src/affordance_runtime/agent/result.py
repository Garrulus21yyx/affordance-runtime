"""Result contract and count composition for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from affordance_runtime.agent.control_transition import ControlTransition, Turn
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation

if TYPE_CHECKING:
    from affordance_runtime.agent.control_outcome import Pause, Terminate
    from affordance_runtime.agent.session import AgentRunSession


@dataclass(frozen=True)
class AgentResult:
    status: AgentLoopStatus
    task: TaskGoal
    final_observation: WorldObservation
    turns: tuple[Turn, ...]
    observation_count: int
    execution_count: int
    currentness_probe_count: int = 0
    message: str = ""
    confirmation_request: ConfirmationRequest | None = None
    policy_failure: PolicyFailure | None = None
    failure_code: AgentFailureCode | None = None
    control_transitions: tuple[ControlTransition, ...] = ()
    control_transition_total_count: int = 0
    reason_code: str = ""
    control_transition_kind_counts: tuple[tuple[str, int], ...] = ()
    sent_unknown_count: int = 0


def project_result(session: AgentRunSession, outcome: Pause | Terminate) -> AgentResult:
    """Project one public result from authoritative absolute session state."""

    state = session.state
    return AgentResult(
        outcome.status,
        session.task,
        state.current_observation,
        state.recent_turns,
        session.accounting.observation_attempts,
        session.accounting.execution_attempts,
        session.accounting.currentness_probes,
        outcome.message,
        state.pending_confirmation
        if outcome.status == AgentLoopStatus.WAITING_CONFIRMATION else None,
        outcome.policy_failure,
        outcome.failure_code,
        state.recent_control_transitions,
        state.control_transition_total_count,
        outcome.reason_code,
        tuple(sorted(state.control_transition_kind_counts.items())),
        state.sent_unknown_total_count,
    )
