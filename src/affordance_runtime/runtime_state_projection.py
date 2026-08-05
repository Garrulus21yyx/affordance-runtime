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
from affordance_runtime.stage_protocol import RuntimeStateSnapshot
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle


class RuntimeBudgetView(Protocol):
    max_steps: int
    max_observations: int
    max_recoveries: int
    max_replans: int
    max_effectful_actions: int
    max_active_perception_observations: int


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
    return RuntimeStateSnapshot(
        MappingProxyType(deepcopy(vars(state))),
        deepcopy(state),
    )


def project_working_phase(state: StateKernel, phase: RuntimeStep) -> None:
    state.transition(phase.value)
