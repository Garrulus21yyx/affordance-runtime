"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.execution_context import RunProvenanceManifest
from affordance_runtime.execution_phase import ActionStage, ActionStageInput
from affordance_runtime.perception_phase import PerceptionStage, PerceptionStageInput
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
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.runtime_loop_phase import RuntimeCommitSession
from affordance_runtime.runtime_result_phase import (
    RunResult,
    RuntimeResultPhase,
)
from affordance_runtime.runtime_state_projection import (
    perception_state_view,
    runtime_state_snapshot,
)
from affordance_runtime.stage_protocol import LoopDirective
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification.contracts import ObservationDisposition


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
    provenance_manifest: RunProvenanceManifest

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
            self.provenance_manifest,
        )
        reusable_capture = None
        while True:
            if (terminal := loop.check_budget()) is not None:
                return terminal
            perception = self.perception_stage.run(
                PerceptionStageInput(
                    envelope=envelope,
                    state_view=perception_state_view(envelope, loop.state, loop.budget),
                    initial_snapshot=reusable_capture,
                )
            )
            reusable_capture = None
            loop.commit(perception)
            if perception.failure is not None:
                if not self.action_stage.recovery_enabled:
                    terminal_failure = self.recovery_stage.terminal_failure(
                        perception.failure,
                        reason_code="observation_failed",
                        status=RuntimeStep.FAILED,
                        error_code=RuntimeErrorCode.PRECONDITION_FAILED,
                    )
                    loop.commit(terminal_failure)
                    assert terminal_failure.terminal is not None
                    return loop.finish(terminal_failure.terminal)
                terminal = loop.recover(
                    perception.failure,
                    self.recovery_stage.available_commands(perception.failure, runtime_state_snapshot(loop.state)),
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
            recovery_observation = self.recovery_stage.evaluate_observation(
                state=runtime_state_snapshot(loop.state),
                snapshot=capture,
                execution_loop=self.progress_stage.execution_loop,
                task_skill_progress=recovery_skill_progress,
            )
            if recovery_observation is not None:
                loop.commit(recovery_observation)
                if recovery_observation.output is not None and recovery_observation.output.verification is not None:
                    loop.latest_verification = recovery_observation.output.verification
                if recovery_observation.terminal is not None:
                    return loop.finish(recovery_observation.terminal)
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
                    self.recovery_stage.available_commands(planning.failure, runtime_state_snapshot(loop.state)),
                )
                if terminal is not None:
                    return terminal
                continue
            assert planning.output is not None
            if planning.output.task_plan_changed:
                continue
            skill_step_id = planning.output.skill_step_id
            if planning.output.selection is None or planning.output.catalog is None:
                raise RuntimeError("planning stage returned no actionable proposal")
            action = self.action_stage.run(
                ActionStageInput(
                    envelope=envelope,
                    capture=capture,
                    observation=observation,
                    state_view=runtime_state_snapshot(loop.state),
                    remaining_budgets=loop.remaining_budgets,
                    skill_step_id=skill_step_id,
                    catalog=planning.output.catalog,
                    selection=planning.output.selection,
                    dispatch_committer=loop.admit_dispatch,
                )
            )
            action_recovery = self.recovery_stage.evaluate_action(
                state=runtime_state_snapshot(loop.state),
                action_result=action,
            )
            loop.commit(action)
            if action_recovery is not None:
                loop.commit(action_recovery)
                if action_recovery.terminal is not None:
                    return loop.finish(action_recovery.terminal)
            if action.terminal is not None:
                return loop.finish(action.terminal)
            if action.directive == LoopDirective.REPEAT_OBSERVATION:
                continue
            if action.failure is not None:
                terminal = loop.recover(
                    action.failure,
                    self.recovery_stage.available_commands(action.failure, runtime_state_snapshot(loop.state)),
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
                        execution_attempt=action.output.execution_attempt,
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
                    self.recovery_stage.available_commands(progress.failure, runtime_state_snapshot(loop.state)),
                    terminate_all_handoffs=True,
                )
                if terminal is not None:
                    return terminal
                continue
            continuation = (
                progress.output.loop_evaluation.observation_continuation
                if progress.output is not None and progress.output.loop_evaluation is not None
                else None
            )
            if continuation is not None and continuation.disposition in {
                ObservationDisposition.REUSE,
                ObservationDisposition.AUGMENT_TARGETED,
            }:
                assert progress.output is not None
                reusable_capture = progress.output.capture
