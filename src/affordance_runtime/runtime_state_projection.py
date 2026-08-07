"""Detached read projections for pure Runtime stages."""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Protocol

from affordance_runtime.failure_envelope import RemainingRecoveryBudgets
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.perception_phase import PerceptionStateView
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import semantic_progress_fingerprint
from affordance_runtime.stage_protocol import (
    PerceptionDelta,
    PhaseDelta,
    ProgressDelta,
    ResultDelta,
    RuntimeDeltaUnion,
    RuntimeStateSnapshot,
    StepProgressDelta,
    VerificationDelta,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle


class RuntimeBudgetView(Protocol):
    @property
    def max_steps(self) -> int: ...
    @property
    def max_observations(self) -> int: ...
    @property
    def max_recoveries(self) -> int: ...
    @property
    def max_replans(self) -> int: ...
    @property
    def max_effectful_actions(self) -> int: ...
    @property
    def max_active_perception_observations(self) -> int: ...


def progress_delta_from_projection(state: object) -> tuple[RuntimeDeltaUnion, ...]:
    """Convert the legacy detached calculator result into a closed delta."""

    values = state.delta_values()  # type: ignore[attr-defined]
    deltas: list[RuntimeDeltaUnion] = []
    if values.get("phase") is not None:
        deltas.append(PhaseDelta(RuntimeStep(values["phase"])))
    if "latest_verification" in values and values["latest_verification"] is not None:
        deltas.append(VerificationDelta(values["latest_verification"]))
    if any(key in values for key in ("task_progress", "recent_action_outcomes", "latest_effect_settlement", "replan_count")):
        deltas.append(
            StepProgressDelta(
                task_progress=values.get("task_progress"),
                recent_action_outcomes=values.get("recent_action_outcomes"),
                latest_effect_settlement=values.get("latest_effect_settlement"),
                replan_count=values.get("replan_count"),
            )
        )
    if "latest_progress_guard" in values and values["latest_progress_guard"] is not None:
        guard = values["latest_progress_guard"]
        deltas.append(ProgressDelta(progress_guard=(str(guard["reason"]), str(guard["signature"]))))
    if "final_result" in values:
        deltas.append(ResultDelta(values["final_result"]))
    if "latest_probe_receipt" in values and values["latest_probe_receipt"] is not None:
        deltas.append(PerceptionDelta(probe_receipts=(values["latest_probe_receipt"],)))
    return tuple(deltas)


def perception_state_view(
    envelope: RunRequest,
    state: StateKernel,
    budget: RuntimeBudgetView,
) -> PerceptionStateView:
    task_plan = state.task_plan
    failed_sources: set[GroundingSource] = set()
    for lineage in state.current_grounding_fallback.values():
        try:
            failed_sources.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            continue
    return PerceptionStateView(
        phase=RuntimeStep(state.phase),
        state_version=state.version,
        observation_count=state.observation_count,
        active_perception_count=state.active_perception_count,
        task_revision=(
            task_plan.task_revision
            if task_plan is not None
            else envelope.task_spec.revision
            if envelope.task_spec is not None
            else 1
        ),
        plan_version=task_plan.plan_version if task_plan is not None else 0,
        active_step_id=(
            state.task_progress.active_step_id
            if state.task_progress is not None
            else ""
        ),
        active_subgoal=TaskPlanLifecycle.active_step_for_perception(state) or "",
        attempted_probe_fingerprints=frozenset(state.attempted_probe_fingerprints),
        failed_sources=frozenset(failed_sources),
        effectful_action=(
            envelope.task_spec is not None
            and envelope.task_spec.operation_class
            not in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
        ),
        has_receipts=state.last_receipt is not None,
        max_active_perception_observations=budget.max_active_perception_observations,
        max_observations=budget.max_observations,
        remaining_budgets=RemainingRecoveryBudgets(
            recoveries=max(0, budget.max_recoveries - state.recovery_count),
            observations=max(0, budget.max_observations - state.observation_count),
            replans=max(0, budget.max_replans - state.replan_count),
            provider_switches=1,
            user_escalations=1,
            timeout_ms=120_000,
            model_calls=max(0, budget.max_replans - state.replan_count),
            estimated_cost=10.0,
        ),
        progress_fingerprint=semantic_progress_fingerprint(state),
    )


def runtime_state_snapshot(state: StateKernel) -> RuntimeStateSnapshot:
    """Build an explicit detached read set; do not expose the aggregate internals."""
    return RuntimeStateSnapshot(
        MappingProxyType(
            deepcopy(
                {
                    "task_id": state.task_id,
                    "goal": state.goal,
                    "constraints": dict(state.constraints),
                    "task_plan": state.task_plan,
                    "task_progress": state.task_progress,
                    "phase": state.phase,
                    "version": state.version,
                    "current_observation_ref": state.current_observation_ref,
                    "current_observation_environment_revision": state.current_observation_environment_revision,
                    "current_observation_page_revision": state.current_observation_page_revision,
                    "current_snapshot_id": state.current_snapshot_id,
                    "last_receipt": state.last_receipt,
                    "step_count": state.step_count,
                    "effectful_action_count": state.effectful_action_count,
                    "observation_count": state.observation_count,
                    "active_perception_count": state.active_perception_count,
                    "recovery_count": state.recovery_count,
                    "replan_count": state.replan_count,
                    "current_failure": state.current_failure,
                    "current_disproved_assumption": state.current_disproved_assumption,
                    "current_contract": state.current_contract,
                    "current_execution_attempt": state.current_execution_attempt,
                    "current_recovery_decision": state.current_recovery_decision,
                    "current_recovery_outcome": state.current_recovery_outcome,
                    "attempted_recovery_strategy_ids": frozenset(state.attempted_recovery_strategy_ids),
                    "current_excluded_candidates": {
                        key: frozenset(values) for key, values in state.current_excluded_candidates.items()
                    },
                    "current_grounding_fallback": {
                        key: dict(value) for key, value in state.current_grounding_fallback.items()
                    },
                    "uncertain_external_effects": tuple(state.uncertain_external_effects),
                    "evidence_gaps": tuple(state.evidence_gaps),
                    "recent_action_outcomes": state.recent_action_outcomes,
                    "latest_verification": state.latest_verification,
                    "latest_effect_settlement": state.latest_effect_settlement,
                    "latest_probe_receipt": state.latest_probe_receipt,
                    "active_probe_plan": state.active_probe_plan,
                    "perception_resolution": state.perception_resolution,
                    "final_result": dict(state.final_result),
                }
            )
        ),
    )


def project_working_phase(state: StateKernel, phase: RuntimeStep) -> None:
    state.transition(phase.value)
