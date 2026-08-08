"""Result contract and count composition for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus, Turn
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


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


def build_result(
    status: AgentLoopStatus,
    task: TaskGoal,
    state: AgentLoopState,
    observation_count: int,
    execution_count: int,
    message: str,
    currentness_probe_count: int = 0,
    policy_failure: PolicyFailure | None = None,
) -> AgentResult:
    return AgentResult(
        status,
        task,
        state.current_observation,
        state.recent_turns,
        observation_count,
        execution_count,
        currentness_probe_count,
        message,
        state.pending_confirmation if status == AgentLoopStatus.WAITING_CONFIRMATION else None,
        policy_failure,
    )


def observation_budget_result(
    task: TaskGoal,
    state: AgentLoopState,
    observation_count: int,
    execution_count: int,
) -> AgentResult:
    return build_result(
        AgentLoopStatus.FAILED,
        task,
        state,
        observation_count,
        execution_count,
        "agent loop observation budget exhausted",
    )


def add_counts(result_value: AgentResult, observations: int, executions: int, probes: int) -> AgentResult:
    return AgentResult(
        result_value.status,
        result_value.task,
        result_value.final_observation,
        result_value.turns,
        observations,
        executions,
        probes,
        result_value.message,
        result_value.confirmation_request,
        result_value.policy_failure,
    )
