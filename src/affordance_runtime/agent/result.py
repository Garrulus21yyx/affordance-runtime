"""Result contract and count composition for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus, Turn
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


class AgentFailureCode(StrEnum):
    NO_PROGRESS_REPETITION = "no_progress_repetition"
    OBSERVATION_CAPABILITY_UNAVAILABLE = "observation_capability_unavailable"
    OBSERVATION_ACQUISITION_FAILED = "observation_acquisition_failed"
    OBSERVATION_FRESHNESS_INVALID = "observation_freshness_invalid"
    OBSERVATION_ORIGIN_INVALID = "observation_origin_invalid"
    POST_ACTION_CAPABILITY_UNAVAILABLE = "post_action_capability_unavailable"
    POST_ACTION_ACQUISITION_FAILED = "post_action_acquisition_failed"
    POST_ACTION_FRESHNESS_INVALID = "post_action_freshness_invalid"
    POST_ACTION_ORIGIN_INVALID = "post_action_origin_invalid"


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


def build_result(
    status: AgentLoopStatus,
    task: TaskGoal,
    state: AgentLoopState,
    observation_count: int,
    execution_count: int,
    message: str,
    currentness_probe_count: int = 0,
    policy_failure: PolicyFailure | None = None,
    failure_code: AgentFailureCode | None = None,
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
        failure_code,
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
        result_value.failure_code,
    )
