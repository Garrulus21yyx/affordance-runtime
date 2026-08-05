"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from affordance_runtime.execution_phase import ActionStage, ActionStageInput
from affordance_runtime.perception_phase import PerceptionStage, PerceptionStageInput
from affordance_runtime.planning_contracts import PlannerProposalResponse
from affordance_runtime.planning_phase import (
    PlanningStage,
    PlanningStageInput,
    task_skill_progress,
)
from affordance_runtime.progress_phase import (
    ProgressActionInput,
    ProgressStage,
    ProgressStageInput,
)
from affordance_runtime.recovery_phase import RecoveryStage
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.recovery_state_projection import (
    available_owner_recovery_kinds,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.runtime_committer import (
    RuntimeCommitSession,
    RuntimeCommitter,
    perception_state_view,
    runtime_state_snapshot,
)
from affordance_runtime.runtime_result_phase import (
    RunResult,
    RuntimeResultPhase,
)
from affordance_runtime.stage_protocol import LoopDirective
from affordance_runtime.trace import TraceDag


def _available_action_recovery_kinds(
    failure_phase: str,
    contract: Any,
    state: Any,
) -> frozenset[RecoveryKind]:
    available: set[RecoveryKind] = set()
    if failure_phase == "grounding_binding":
        available.add(RecoveryKind.REGROUND)
    if failure_phase == "preflight":
        available.add(RecoveryKind.REOBSERVE)
    if failure_phase in {"execution_uncertain", "verification"}:
        available.update({RecoveryKind.REOBSERVE, RecoveryKind.INSPECT_POST_STATE})
    if contract is None:
        return frozenset(available)
    if contract.idempotency_key:
        available.add(RecoveryKind.RETRY_IDEMPOTENT)
    if contract.compensation:
        available.add(RecoveryKind.COMPENSATE)
    route_plan = contract.route_plan
    if route_plan is not None and any(
        item.candidate_id != route_plan.selected_candidate.candidate_id
        for item in route_plan.viable_alternatives
    ):
        available.add(RecoveryKind.REROUTE)
    tried_backends = {state.last_receipt.backend} if state.last_receipt is not None else set()
    if any(item not in tried_backends for item in contract.fallback_backends):
        available.add(RecoveryKind.REROUTE)
    return frozenset(available)


@dataclass(frozen=True)
class RunBudget:
    max_steps: int = 20
    max_observations: int = 30
    max_replans: int = 10
    max_recoveries: int = 3
    max_effectful_actions: int = 5
    max_active_perception_observations: int = 3


@dataclass(frozen=True)
class RuntimeFeatures:
    preflight: bool = True
    structural_verification: bool = True
    capability_gate: bool = True
    recovery: bool = True


@dataclass(frozen=True)
class RunCoordinator:
    perception_stage: PerceptionStage
    planning_stage: PlanningStage
    action_stage: ActionStage
    progress_stage: ProgressStage
    recovery_stage: RecoveryStage
    committer: RuntimeCommitter
    result_builder: RuntimeResultPhase

    async def run(self, envelope: RunRequest, upstream_trace: TraceDag | None = None) -> RunResult:
        """Async-compatible entry point for framework and service adapters."""

        return await asyncio.to_thread(self.run_sync, envelope, upstream_trace)

    def run_sync(self, envelope: RunRequest, upstream_trace: TraceDag | None = None) -> RunResult:
        """Execute one task with serial state mutation and action semantics."""
        budget = self.perception_stage.budget
        if not isinstance(budget, RunBudget):
            raise TypeError("PerceptionStage requires the composed RunBudget")
        loop = RuntimeCommitSession.start(
            self.committer,
            self.result_builder,
            self.recovery_stage,
            envelope,
            budget,
            upstream_trace,
        )
        while True:
            if (terminal := loop.check_budget()) is not None:
                return terminal
            perception = self.perception_stage.run(
                PerceptionStageInput(
                    envelope=envelope,
                    state_view=perception_state_view(envelope, loop.state, loop.budget),
                )
            )
            loop.commit(perception)
            if perception.failure is not None:
                if not self.action_stage.recovery_enabled:
                    return loop.fail_observation(perception.failure)
                terminal = loop.recover(
                    perception.failure,
                    frozenset({RecoveryKind.REOBSERVE}),
                    preserve_terminal=True,
                )
                if terminal is not None:
                    return terminal
                continue
            assert perception.output is not None
            capture = perception.output.capture
            observation = perception.output.observation
            observation_ref = perception.output.observation_ref
            recovery_skill_progress = (
                task_skill_progress(self.progress_stage.task_skill_runtime, loop.state)
                if self.progress_stage.task_skill_runtime is not None
                else None
            )
            recovered_verification, recovery_terminal, loop.parent = (
                self.committer.commit_recovery_observation(
                    loop.state,
                    loop.trace,
                    loop.parent,
                    capture,
                    self.progress_stage.execution_loop,
                    task_skill_progress=recovery_skill_progress,
                )
            )
            if recovered_verification is not None:
                loop.latest_verification = recovered_verification
            if recovery_terminal is not None:
                return loop.finish(recovery_terminal)
            progress = self.progress_stage.run(
                ProgressStageInput(
                    envelope=envelope,
                    capture=capture,
                    observation=observation,
                    state_view=runtime_state_snapshot(loop.state),
                    budget=loop.budget,
                    remaining_budgets=loop.remaining_budgets,
                )
            )
            loop.commit(progress)
            if progress.terminal is not None:
                return loop.finish(progress.terminal)
            if progress.directive == LoopDirective.REPEAT_OBSERVATION:
                continue
            loop.enter_planning()
            planning = self.planning_stage.run(
                PlanningStageInput(
                    envelope=envelope,
                    capture=capture,
                    observation=observation,
                    observation_ref=observation_ref,
                    state_view=runtime_state_snapshot(loop.state),
                    budget=loop.budget,
                    latest_verification=loop.latest_verification,
                    remaining_budgets=loop.remaining_budgets,
                )
            )
            loop.commit(planning)
            if planning.terminal is not None:
                return loop.finish(planning.terminal)
            if planning.directive == LoopDirective.REPEAT_OBSERVATION:
                continue
            if planning.failure is not None:
                terminal = loop.recover(
                    planning.failure,
                    available_owner_recovery_kinds(
                        self.recovery_stage.owner_dispatcher
                    ),
                )
                if terminal is not None:
                    return terminal
                continue
            assert planning.output is not None
            if planning.output.task_plan_changed:
                continue
            decision = planning.output.response
            skill_step_id = planning.output.skill_step_id
            if (
                not isinstance(decision, PlannerProposalResponse)
                and (planning.output.selection is None or planning.output.catalog is None)
            ):
                raise RuntimeError("planning stage returned no actionable proposal")
            action = self.action_stage.run(
                ActionStageInput(
                    envelope=envelope,
                    decision=decision,
                    capture=capture,
                    observation=observation,
                    state_view=runtime_state_snapshot(loop.state),
                    remaining_budgets=loop.remaining_budgets,
                    skill_step_id=skill_step_id,
                    catalog=planning.output.catalog,
                    selection=planning.output.selection,
                )
            )
            loop.parent, pending_recovery_failed = self.committer.commit_action(
                loop.state, loop.trace, loop.parent, action
            )
            if pending_recovery_failed and action.failure is not None:
                return loop.abort_pending_recovery(action.failure)
            if action.terminal is not None:
                return loop.finish(action.terminal)
            if action.directive == LoopDirective.REPEAT_OBSERVATION:
                continue
            if action.failure is not None:
                terminal = loop.recover(
                    action.failure,
                    available_owner_recovery_kinds(self.recovery_stage.owner_dispatcher)
                    | _available_action_recovery_kinds(
                        action.failure.phase.value,
                        loop.state.current_contract,
                        loop.state,
                    ),
                )
                if terminal is not None:
                    return terminal
                continue
            assert action.output is not None
            progress = self.progress_stage.run(
                ProgressStageInput(
                    envelope=envelope,
                    capture=capture,
                    observation=observation,
                    state_view=runtime_state_snapshot(loop.state),
                    budget=loop.budget,
                    remaining_budgets=loop.remaining_budgets,
                    action=ProgressActionInput(
                        contract=action.output.contract,
                        receipt=action.output.receipt,
                        execution_observation=action.output.execution_snapshot.observation,
                        action_signature=action.output.action_signature,
                        skill_step_id=skill_step_id,
                    ),
                )
            )
            loop.commit(progress)
            if progress.output is not None and progress.output.verification is not None:
                loop.latest_verification = progress.output.verification
            if progress.terminal is not None:
                return loop.finish(progress.terminal)
            if progress.directive == LoopDirective.REPEAT_OBSERVATION:
                continue
            if progress.failure is not None:
                terminal = loop.recover(
                    progress.failure,
                    available_owner_recovery_kinds(self.recovery_stage.owner_dispatcher)
                    | _available_action_recovery_kinds(
                        progress.failure.phase.value,
                        loop.state.current_contract,
                        loop.state,
                    ),
                    terminate_all_handoffs=True,
                )
                if terminal is not None:
                    return terminal
                continue
