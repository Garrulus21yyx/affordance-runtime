"""Result contract and count composition for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from affordance_runtime.agent.control_transition import ControlTransition, Turn
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.runtime_failure import RuntimeFailure, runtime_failure_from_outcome
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.evaluation.contracts import TaskOutcomeFact
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
    runtime_failure: RuntimeFailure | None = None
    task_outcome: TaskOutcomeFact | None = None
    control_feedback_count: int = 0
    control_feedback_delivery_count: int = 0
    control_issue_consumption_count: int = 0
    control_repetition_count: int = 0
    requirement_hypothesis_accepted_count: int = 0
    requirement_hypothesis_rejected_count: int = 0
    requirement_hypothesis_rejection_code_counts: tuple[tuple[str, int], ...] = ()


def project_result(
    session: AgentRunSession,
    outcome: Pause | Terminate,
    *,
    runtime_failure: RuntimeFailure | None = None,
) -> AgentResult:
    """Project one public result from authoritative absolute session state."""

    state = session.state
    current_evaluation = state.current_task_evaluation
    current_outcome = (
        current_evaluation.outcome
        if current_evaluation is not None
        and current_evaluation.observation_id == state.current_observation.observation_id
        else None
    )
    latest = state.recent_control_transitions[-1] if state.recent_control_transitions else None
    root_id = latest.transition_id if latest is not None else ""
    attempt_id = latest.attempt_receipts[-1].attempt_id if latest is not None and latest.attempt_receipts else ""
    if runtime_failure is not None and root_id:
        runtime_failure = replace(
            runtime_failure,
            root_id=root_id,
            attempt_id=attempt_id,
        )
    return AgentResult(
        outcome.status,
        session.task,
        state.current_observation,
        state.recent_turns,
        session.accounting.observation_attempts,
        session.accounting.execution_attempts,
        session.accounting.currentness_probes,
        outcome.message,
        state.pending_confirmation if outcome.status == AgentLoopStatus.WAITING_CONFIRMATION else None,
        outcome.policy_failure,
        outcome.failure_code,
        state.recent_control_transitions,
        state.control_transition_total_count,
        outcome.reason_code,
        tuple(sorted(state.control_transition_kind_counts.items())),
        state.sent_unknown_total_count,
        runtime_failure or runtime_failure_from_outcome(outcome, root_id=root_id, attempt_id=attempt_id),
        current_outcome,
        state.control_feedback_total_count,
        state.control_feedback_delivery_total_count,
        state.control_issue_consumption_total_count,
        state.control_repetition_total_count,
        state.requirement_hypothesis_accepted_total_count,
        state.requirement_hypothesis_rejected_total_count,
        tuple(sorted(state.requirement_hypothesis_rejection_code_counts.items())),
    )
