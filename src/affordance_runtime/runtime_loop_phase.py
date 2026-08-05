"""Runtime loop lifecycle seam for Coordinator phase extraction.

This module owns loop-start and phase-entry lifecycle commits that are not
domain planning, execution, verification, progress, or recovery decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.stage_protocol import (
    ProgressHandoff,
    RuntimeEvent,
    RuntimeTransition,
    StageResult,
    TerminalResult,
    UserInputRequest,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class RuntimeLoopEvent:
    kind: str
    payload: dict[str, object]
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeLoopTransition:
    phase: RuntimeStep
    activate_next_step: bool = False


@dataclass(frozen=True)
class RuntimeLoopStartResult:
    state: StateKernel
    trace: TraceDag
    event: RuntimeLoopEvent


@dataclass(frozen=True)
class RuntimeLoopTerminalResult:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None
    transition: RuntimeLoopTransition
    event: RuntimeLoopEvent


class RuntimeBudgetView(Protocol):
    @property
    def max_steps(self) -> int: ...

    @property
    def max_observations(self) -> int: ...

    @property
    def max_replans(self) -> int: ...

    @property
    def max_recoveries(self) -> int: ...

    @property
    def max_effectful_actions(self) -> int: ...


class RuntimeLoopPhase:
    """Prepare loop lifecycle transitions and events without committing them."""

    def start(
        self,
        *,
        envelope: RunRequest,
        upstream_trace: TraceDag | None,
        runtime_profile_digest: str,
        loaded_profile_artifact_ids: tuple[str, ...],
    ) -> RuntimeLoopStartResult:
        state = StateKernel(
            task_id=envelope.task_id,
            goal=envelope.goal,
            constraints=dict(envelope.constraints),
        )
        if upstream_trace is not None and upstream_trace.run_id != envelope.task_id:
            raise ValueError("upstream trace run_id does not match task")
        trace = upstream_trace or TraceDag(run_id=envelope.task_id)
        upstream_parent = trace.nodes[-1] if trace.nodes else None
        event = RuntimeLoopEvent(
            kind="TaskCreated",
            payload={
                "state": RuntimeStep.CREATED.value,
                "goal": envelope.goal,
                "constraints": envelope.constraints,
                "task_spec_identity": (
                    envelope.task_spec.identity if envelope.task_spec is not None else ""
                ),
                "runtime_profile_digest": runtime_profile_digest,
                "loaded_profile_artifact_ids": list(loaded_profile_artifact_ids),
            },
            parent_ids=(upstream_parent.id,) if upstream_parent else (),
        )
        return RuntimeLoopStartResult(state=state, trace=trace, event=event)

    def check_budget(
        self,
        *,
        state: StateKernel,
        budget: RuntimeBudgetView,
    ) -> RuntimeLoopTerminalResult | None:
        budget_error = _budget_error(state, budget)
        if budget_error is None:
            return None
        return RuntimeLoopTerminalResult(
            status=RuntimeStep.FAILED,
            error_code=budget_error,
            transition=RuntimeLoopTransition(RuntimeStep.FAILED),
            event=RuntimeLoopEvent(
                kind="TaskFailed",
                payload={
                    "state": RuntimeStep.FAILED.value,
                    "error_code": budget_error.value,
                    "reason": "runtime budget exhausted",
                },
            ),
        )

    def enter_planning(self, *, has_task_plan: bool) -> RuntimeLoopTransition:
        return RuntimeLoopTransition(
            RuntimeStep.PLANNING,
            activate_next_step=has_task_plan,
        )

    def enter_verifying(self) -> RuntimeLoopTransition:
        return RuntimeLoopTransition(RuntimeStep.VERIFYING)


@dataclass
class RuntimeCommitSession:
    """Run lifecycle orchestration around the typed RuntimeCommitter boundary."""

    committer: Any
    result_builder: Any
    recovery_stage: Any
    envelope: RunRequest
    budget: RuntimeBudgetView
    state: StateKernel
    trace: TraceDag
    parent: TraceNode
    latest_verification: VerificationReport | None = None

    @classmethod
    def start(
        cls,
        committer: Any,
        result_builder: Any,
        recovery_stage: Any,
        envelope: RunRequest,
        budget: RuntimeBudgetView,
        upstream_trace: TraceDag | None,
    ) -> RuntimeCommitSession:
        started = RuntimeLoopPhase().start(
            envelope=envelope,
            upstream_trace=upstream_trace,
            runtime_profile_digest=recovery_stage.runtime_profile_digest,
            loaded_profile_artifact_ids=recovery_stage.loaded_profile_artifact_ids,
        )
        return cls(
            committer,
            result_builder,
            recovery_stage,
            envelope,
            budget,
            started.state,
            started.trace,
            committer.commit_loop_event(started.trace, started.event),
        )

    @property
    def remaining_budgets(self) -> Any:
        from affordance_runtime.runtime_state_projection import perception_state_view

        return perception_state_view(
            self.envelope, self.state, self.budget
        ).remaining_budgets

    def finish(self, terminal: TerminalResult) -> Any:
        from affordance_runtime.runtime_result_phase import finish_phase_terminal

        return finish_phase_terminal(
            self.result_builder,
            self.envelope,
            self.state,
            self.trace,
            terminal,
            self.parent,
            self.latest_verification,
        )

    def check_budget(self) -> Any | None:
        result = RuntimeLoopPhase().check_budget(state=self.state, budget=self.budget)
        if result is None:
            return None
        self.committer.commit_loop_transition(self.state, result.transition)
        self.parent = self.committer.commit_loop_event(
            self.trace, result.event, self.parent
        )
        return self.result_builder.finish(
            self.envelope,
            self.state,
            self.trace,
            result.status,
            self.parent,
            result.error_code,
            self.latest_verification,
        )

    def commit(self, result: StageResult[Any]) -> None:
        self.parent = self.committer.commit(
            self.state, self.trace, self.parent, result
        )

    def enter_planning(self) -> None:
        self.committer.commit_loop_transition(
            self.state,
            RuntimeLoopPhase().enter_planning(
                has_task_plan=self.state.task_plan is not None
            ),
        )

    def fail_observation(self, failure: FailureEnvelope) -> Any:
        self.commit(
            StageResult(transition=RuntimeTransition(phase=RuntimeStep.FAILED))
        )
        return self.finish(
            TerminalResult(
                failure.failure_id,
                "observation_failed",
                RuntimeStep.FAILED,
                RuntimeErrorCode.PRECONDITION_FAILED,
            )
        )

    def recover(
        self,
        failure: FailureEnvelope,
        commands: frozenset[Any],
        *,
        preserve_terminal: bool = False,
        terminate_all_handoffs: bool = False,
    ) -> Any | None:
        from affordance_runtime.recovery_phase import RecoveryStageInput
        from affordance_runtime.recovery_protocol import (
            FailureOwner,
            RecoveryKind,
            classify_failure,
        )
        from affordance_runtime.runtime_state_projection import runtime_state_snapshot

        classification = classify_failure(failure)
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            handoff, self.parent = self.committer.commit_failure_owner(
                self.state, self.trace, self.parent, failure, classification
            )
        else:
            result = self.recovery_stage.run(
                RecoveryStageInput(
                    failure=failure,
                    state_view=runtime_state_snapshot(self.state),
                    available_commands=commands,
                    runtime_profile_digest=self.recovery_stage.runtime_profile_digest,
                    loaded_profile_artifact_ids=(
                        self.recovery_stage.loaded_profile_artifact_ids
                    ),
                )
            )
            self.commit(result)
            if result.terminal is not None:
                handoff = result.terminal
            elif result.output is not None:
                handoff = result.output.recovery_kind
            else:
                raise RuntimeError("recovery stage returned neither output nor terminal")
        if isinstance(handoff, RecoveryKind):
            return None
        if (
            isinstance(handoff, ProgressHandoff)
            and handoff.reason_code == "progress_credit_invariant"
        ):
            return self.finish(
                TerminalResult(
                    handoff.failure_id,
                    handoff.reason_code,
                    RuntimeStep.FAILED,
                    RuntimeErrorCode.PROGRESS_CREDIT_INVARIANT,
                )
            )
        if not terminate_all_handoffs and not isinstance(
            handoff, (TerminalResult, UserInputRequest)
        ):
            return None
        if preserve_terminal and isinstance(handoff, TerminalResult):
            return self.finish(handoff)
        try:
            error = RuntimeErrorCode(failure.error_code)
        except ValueError:
            error = {
                "perception": RuntimeErrorCode.PRECONDITION_FAILED,
                "planning": RuntimeErrorCode.PLANNER_FAILED,
                "verification": RuntimeErrorCode.VERIFICATION_FAILED,
            }.get(failure.phase.value, RuntimeErrorCode.EXECUTION_FAILED)
        return self.finish(
            TerminalResult(
                handoff.failure_id,
                handoff.reason_code,
                RuntimeStep(self.state.phase),
                error,
            )
        )

    def abort_pending_recovery(self, failure: FailureEnvelope) -> Any:
        self.commit(
            StageResult(
                transition=RuntimeTransition(
                    phase=RuntimeStep.ABORTED,
                    clear_recovery_decision=True,
                ),
                events=(
                    RuntimeEvent(
                        "FailureOwnerRouted",
                        {
                            "state": RuntimeStep.RECOVERING.value,
                            "failure_id": failure.failure_id,
                            "owner": "terminal",
                            "handoff_type": "TerminalResult",
                            "reason_code": "runtime_recovery_failed",
                        },
                    ),
                ),
            )
        )
        return self.finish(
            TerminalResult(
                failure.failure_id,
                failure.error_code,
                RuntimeStep.ABORTED,
                RuntimeErrorCode(failure.error_code),
            )
        )

    def commit_recovery_observation(
        self,
        snapshot: Any,
        execution_loop: Any,
        *,
        task_skill_progress: object | None = None,
    ) -> tuple[VerificationReport | None, TerminalResult | None]:
        """Evaluate a recovery observation, then commit only its typed result."""

        from affordance_runtime.recovery_protocol import (
            RecoveryKind,
            RecoveryOutcome,
            RuntimePhase,
        )
        from affordance_runtime.runtime_evidence import verification_confirms_effect_absent

        decision = self.state.current_recovery_decision
        failure = self.state.current_failure
        if decision is None or failure is None or self.state.current_recovery_outcome is not None:
            return None, None
        verification = None
        failed = False
        events: list[RuntimeEvent] = []
        updates: dict[str, object] = {}
        if decision.kind == RecoveryKind.INSPECT_POST_STATE:
            contract = self.state.current_contract
            receipt = self.state.last_receipt
            if contract is None or receipt is None:
                raise ValueError("post-state recovery inspection requires contract and receipt lineage")
            verification = execution_loop.verify(
                contract,
                receipt,
                snapshot.observation,
                structural_verification_enabled=True,
                disabled_reason="",
            )
            updates["latest_verification"] = verification
            events.append(
                RuntimeEvent(
                    "RecoveryStateInspected",
                    {
                        "state": self.state.phase,
                        "verification": verification.status.value,
                        "snapshot_id": snapshot.observation.snapshot_id,
                        "artifact_refs": snapshot.observation.artifact_refs,
                    },
                )
            )
            skill_fallthrough = bool(
                verification_confirms_effect_absent(verification)
                and task_skill_progress is not None
                and not getattr(task_skill_progress, "active", True)
            )
            failed = not verification.passed and not skill_fallthrough
        if decision.kind not in {RecoveryKind.REOBSERVE, RecoveryKind.INSPECT_POST_STATE}:
            return verification, None
        outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=not failed,
            changed_dimensions=decision.changed_dimensions,
            next_phase=RuntimePhase.ABORTED if failed else decision.reentry_phase,
            artifact_refs=() if failed else tuple(snapshot.observation.artifact_refs),
            observation_refs=() if failed else (snapshot.observation.snapshot_id,),
            error_code="verification_failed" if failed else "",
        )
        updates["current_recovery_outcome"] = outcome
        events.append(RuntimeEvent("RecoveryOutcomeRecorded", _recovery_outcome_payload(self.state.phase, outcome)))
        terminal = None
        phase = None
        if failed:
            phase = RuntimeStep.ABORTED
            events.append(
                RuntimeEvent(
                    "RecoveryAborted",
                    {
                        "state": self.state.phase,
                        "reason": "post-state inspection did not establish a safe changed effect status",
                    },
                )
            )
            terminal = TerminalResult(
                failure.failure_id,
                "post_state_inspection_failed",
                RuntimeStep.ABORTED,
                RuntimeErrorCode.PRECONDITION_FAILED,
            )
        else:
            events.append(
                RuntimeEvent(
                    "RecoveryReenteredPhase",
                    {
                        "state": self.state.phase,
                        "reentry_phase": decision.reentry_phase.value,
                    },
                )
            )
        self.commit(
            StageResult(
                transition=RuntimeTransition(phase=phase, state_updates=updates),
                events=tuple(events),
                terminal=terminal,
            )
        )
        return verification, terminal


def _recovery_outcome_payload(state_phase: str, outcome: Any) -> dict[str, object]:
    return {
        "state": state_phase,
        "outcome": {
            "decision_id": outcome.decision_id,
            "failure_id": outcome.failure_id,
            "success": outcome.success,
            "changed_dimensions": [item.value for item in outcome.changed_dimensions],
            "next_phase": outcome.next_phase.value,
            "artifact_refs": list(outcome.artifact_refs),
            "observation_refs": list(outcome.observation_refs),
            "error_code": outcome.error_code,
        },
    }


def _budget_error(
    state: StateKernel,
    budget: RuntimeBudgetView,
) -> RuntimeErrorCode | None:
    if state.step_count >= budget.max_steps:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.observation_count >= budget.max_observations:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.replan_count >= budget.max_replans:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.recovery_count >= budget.max_recoveries:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.effectful_action_count >= budget.max_effectful_actions:
        return RuntimeErrorCode.UNSAFE_ACTION
    return None
