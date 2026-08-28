"""Read-only benchmark projection of the thin Runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.world.contracts import CoverageState


@dataclass(frozen=True)
class EpisodeSnapshot:
    observation_count: int
    execution_count: int
    currentness_probe_count: int
    completed_turn_count: int
    latest_task_status: str
    latest_action_observed_change: str
    latest_action_local_postcondition: str
    latest_action_evidence_method: str
    latest_semantic_attempt_key_digest: str
    same_attempt_streak: int
    no_progress_count: int
    sent_unknown_count: int
    last_decision_kind: str
    last_action_space_option_count: int
    last_world_target_count: int
    last_world_coverage: str
    pending_kind: str
    decision_kind_counts: tuple[tuple[str, int], ...] = ()
    latest_control_status: str = ""
    latest_control_reason_code: str = ""
    latest_control_owner: str = ""
    latest_acquisition_request_kind: str = ""
    latest_attempt_operation: str = ""
    latest_attempt_reason_code: str = ""
    task_outcome_kind: str = ""
    task_outcome_code: str = ""
    agent_failure_code: str = ""
    policy_failure_code: str = ""
    runtime_failure: RuntimeFailure | None = None
    user_question: str = ""


def snapshot_episode(
    state: RunState | None,
    *,
    episode_monitor: EpisodeMonitor | None = None,
    control_status: RunStatus | None = None,
    user_question: str = "",
    terminal_evaluation: TaskEvaluation | None = None,
) -> EpisodeSnapshot:
    """Project benchmark-safe facts without adding state to the product loop."""

    if state is None:
        if control_status is None:
            raise ValueError("a state-free terminal snapshot requires control status")
        return EpisodeSnapshot(
            observation_count=0,
            execution_count=0,
            currentness_probe_count=0,
            completed_turn_count=0,
            latest_task_status="",
            latest_action_observed_change="",
            latest_action_local_postcondition="",
            latest_action_evidence_method="",
            latest_semantic_attempt_key_digest="",
            same_attempt_streak=0,
            no_progress_count=0,
            sent_unknown_count=0,
            last_decision_kind="",
            last_action_space_option_count=0,
            last_world_target_count=0,
            last_world_coverage="",
            pending_kind="",
            latest_control_status=str(control_status),
            user_question=user_question,
        )

    latest = state.last_step
    latest_action = state.latest_action_outcome
    task_evaluation = terminal_evaluation or state.current_task_evaluation
    task_outcome = task_evaluation.outcome if task_evaluation is not None else None
    latest_attempt = episode_monitor.latest_attempt_signature if episode_monitor is not None else None
    return EpisodeSnapshot(
        observation_count=state.observation_count,
        execution_count=state.execution_count,
        currentness_probe_count=state.currentness_probe_count,
        completed_turn_count=state.step_count,
        latest_task_status=str(task_evaluation.status) if task_evaluation is not None else "",
        latest_action_observed_change=str(latest_action.observed_change) if latest_action is not None else "",
        latest_action_local_postcondition=str(latest_action.local_postcondition) if latest_action is not None else "",
        latest_action_evidence_method=str(latest_action.evidence_method) if latest_action is not None else "",
        latest_semantic_attempt_key_digest=latest_attempt.digest if latest_attempt is not None else "",
        same_attempt_streak=episode_monitor.same_attempt_streak if episode_monitor is not None else 0,
        no_progress_count=episode_monitor.no_progress_count if episode_monitor is not None else 0,
        sent_unknown_count=state.sent_unknown_count,
        last_decision_kind=(
            latest.decision.kind.value
            if latest is not None and not isinstance(latest.decision, PolicyFailure)
            else ""
        ),
        last_action_space_option_count=len(state.action_page.visible_action_ids) if state.action_page is not None else 0,
        last_world_target_count=len(state.current_world.targets),
        last_world_coverage=_coverage_summary(
            {item.source_observation_id: item.coverage for item in state.current_world.source_manifest}
        ),
        pending_kind=_pending_kind(state),
        decision_kind_counts=tuple(
            (kind.value, count) for kind, count in sorted(state.decision_counts.items(), key=lambda item: item[0].value)
        ),
        latest_control_status=str(control_status or state.status),
        latest_control_reason_code=(
            state.control_termination.kind.value if state.control_termination is not None else ""
        ),
        latest_control_owner=(
            state.control_termination.owner if state.control_termination is not None else ""
        ),
        task_outcome_kind=str(task_outcome.kind) if task_outcome is not None else "",
        task_outcome_code=task_outcome.code if task_outcome is not None else "",
        agent_failure_code=state.failure_code.value if state.failure_code is not None else "",
        policy_failure_code=state.policy_failure.kind.value if state.policy_failure is not None else "",
        runtime_failure=state.runtime_failure,
        user_question=user_question,
    )


def _pending_kind(state: RunState) -> str:
    if state.status is RunStatus.WAITING_USER:
        return "user_question"
    if state.status is RunStatus.WAITING_CONFIRMATION:
        return "confirmation"
    return ""


def _coverage_summary(coverage: dict[str, CoverageState]) -> str:
    values = set(coverage.values())
    for status in (
        CoverageState.FAILED,
        CoverageState.TRUNCATED,
        CoverageState.STALE,
        CoverageState.NOT_ACQUIRED,
    ):
        if status in values:
            return str(status)
    return str(CoverageState.COMPLETE)
