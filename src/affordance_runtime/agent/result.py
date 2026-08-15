"""Result contract and count composition for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from affordance_runtime.agent.control_transition import ControlTransition
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.runtime_failure import RuntimeFailure, runtime_failure_from_outcome
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.agent.user_input import UserInputRequest
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
    user_input_request: UserInputRequest | None = None


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
        status=outcome.status,
        task=session.task,
        final_observation=state.current_observation,
        observation_count=session.accounting.observation_attempts,
        execution_count=session.accounting.execution_attempts,
        currentness_probe_count=session.accounting.currentness_probes,
        message=outcome.message,
        confirmation_request=(
            state.pending_confirmation
            if outcome.status == AgentLoopStatus.WAITING_CONFIRMATION
            else None
        ),
        policy_failure=outcome.policy_failure,
        failure_code=outcome.failure_code,
        control_transitions=state.recent_control_transitions,
        control_transition_total_count=state.control_transition_total_count,
        reason_code=outcome.reason_code,
        control_transition_kind_counts=tuple(sorted(state.control_transition_kind_counts.items())),
        sent_unknown_count=state.sent_unknown_total_count,
        runtime_failure=(
            runtime_failure
            or runtime_failure_from_outcome(outcome, root_id=root_id, attempt_id=attempt_id)
        ),
        task_outcome=current_outcome,
        control_feedback_count=state.control_feedback_total_count,
        control_feedback_delivery_count=state.control_feedback_delivery_total_count,
        control_issue_consumption_count=state.control_issue_consumption_total_count,
        control_repetition_count=state.control_repetition_total_count,
        user_input_request=(
            state.pending_user_request if outcome.status == AgentLoopStatus.WAITING_USER else None
        ),
    )
