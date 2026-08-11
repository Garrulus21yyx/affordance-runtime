"""Runtime-owned synchronization and verification of the rolling task frontier."""

from __future__ import annotations

from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.task.frontier import (
    ObjectiveVerificationDisposition,
    apply_objective_verification,
    synchronize_verified_task_state,
    verify_active_objective,
)
from affordance_runtime.task.frontier_contracts import ActiveObjective


def audit_task_frontier(
    session,
    evaluation: TaskEvaluation,
    *,
    evidence_refs: tuple[str, ...] = (),
) -> None:
    """Refresh verifier truth, then close an objective only by its predicate."""

    state = session.state
    verified = synchronize_verified_task_state(
        session.task,
        evaluation,
        state.current_observation,
        state.verified_task_state,
    )
    active = state.active_objective
    if isinstance(active, ActiveObjective):
        outcome = verify_active_objective(
            active,
            verified,
            state.current_observation,
            evaluation,
            evidence_refs=evidence_refs,
        )
        if outcome.disposition is not ObjectiveVerificationDisposition.ACTIVE:
            verified = apply_objective_verification(
                active,
                outcome,
                verified,
                state.current_observation.observation_id,
            )
            state.install_verified_task_state(verified)
            state.clear_active_objective()
            return
    state.install_verified_task_state(verified)
