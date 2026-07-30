"""Generic recovery failure envelope seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.failure_owner_flow import commit_non_runtime_failure_owner_handoff
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import (
    FailureOwner,
    RecoveryKind,
    RuntimePhase,
    classify_failure,
)
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.runtime_evidence import semantic_progress_fingerprint
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


class RecoveryBudgetView(Protocol):
    @property
    def max_observations(self) -> int: ...

    @property
    def max_recoveries(self) -> int: ...

    @property
    def max_replans(self) -> int: ...



@dataclass(frozen=True)
class RecoveryFailurePhase:
    """Build failure envelopes and delegate runtime-owned recovery decisions."""

    recovery_phase: RecoveryPhase
    budget: RecoveryBudgetView
    runtime_profile_digest: str = ""
    loaded_profile_artifact_ids: tuple[str, ...] = ()

    def recover_execution_failure(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        error: RuntimeErrorCode | None,
        *,
        failure_context: dict[str, object] | None = None,
        verification: VerificationReport | None = None,
        verification_ref: str = "",
    ) -> tuple[RecoveryKind, TraceNode]:
        task_plan = state.task_plan
        if verification is not None or error == RuntimeErrorCode.VERIFICATION_FAILED:
            phase = FailurePhase.VERIFICATION
            failure_class = FailureClass.VERIFICATION
        elif state.phase == "preflight":
            phase = FailurePhase.PREFLIGHT
            failure_class = (
                FailureClass.AUTHORITY
                if error
                in {
                    RuntimeErrorCode.CAPABILITY_DENIED,
                    RuntimeErrorCode.UNSAFE_ACTION,
                    RuntimeErrorCode.APPROVAL_REQUIRED,
                }
                else FailureClass.VALIDATION
            )
        elif (
            receipt is not None
            and receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT
            and receipt.evidence.get("dispatched") is not False
        ):
            phase = FailurePhase.EXECUTION_UNCERTAIN
            failure_class = FailureClass.EXECUTION
        else:
            phase = FailurePhase.EXECUTION_NOT_DISPATCHED
            failure_class = FailureClass.EXECUTION
        failure_message = (
            verification.reason
            if verification is not None and verification.reason
            else error.value
            if isinstance(error, RuntimeErrorCode)
            else str(error or "execution failed")
        )
        failure = make_failure_envelope(
            run_id=envelope.task_id,
            phase=phase,
            failure_class=failure_class,
            error_code=error or RuntimeErrorCode.EXECUTION_FAILED,
            message=failure_message,
            state_version=state.version,
            task_revision=(
                task_plan.task_revision
                if task_plan is not None
                else envelope.task_spec.revision
                if envelope.task_spec is not None
                else 1
            ),
            plan_version=task_plan.plan_version if task_plan is not None else 0,
            active_subgoal_id=(
                state.plan_progress.active_subgoal_id
                if state.plan_progress is not None
                else ""
            ),
            observation_epoch_id=state.current_snapshot_id,
            snapshot_id=state.current_snapshot_id,
            contract=contract,
            receipt=receipt,
            expected_effect=contract.intent,
            evidence_refs=(verification_ref,) if verification_ref else (),
            verification_ref=verification_ref,
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=tuple(state.disproved_assumptions),
            remaining_budgets=self._remaining_recovery_budgets(state),
            progress_fingerprint=semantic_progress_fingerprint(state),
            debug_context=failure_context or {},
        )
        available: set[RecoveryKind] = {RecoveryKind.ABORT}
        if phase == FailurePhase.PREFLIGHT:
            available.add(RecoveryKind.REOBSERVE)
        if phase in {
            FailurePhase.EXECUTION_UNCERTAIN,
            FailurePhase.VERIFICATION,
        }:
            available.update(
                {
                    RecoveryKind.REOBSERVE,
                    RecoveryKind.INSPECT_POST_STATE,
                }
            )
        fresh_candidate_id = ""
        fresh_route_ref = ""
        route_plan = contract.route_plan
        if route_plan is not None:
            for candidate in route_plan.viable_alternatives:
                if candidate.candidate_id != route_plan.selected_candidate.candidate_id:
                    fresh_candidate_id = candidate.candidate_id
                    available.add(RecoveryKind.REROUTE)
                    break
        if not fresh_candidate_id:
            tried_backends = {item.backend for item in state.receipts}
            for backend in contract.fallback_backends:
                if backend not in tried_backends:
                    fresh_route_ref = backend
                    available.add(RecoveryKind.REROUTE)
                    break
        if contract.idempotency_key:
            available.add(RecoveryKind.RETRY_IDEMPOTENT)
        if contract.compensation:
            available.add(RecoveryKind.COMPENSATE)
        classification = classify_failure(failure)
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            return commit_non_runtime_failure_owner_handoff(
                state,
                trace,
                parent,
                failure=failure,
                classification=classification,
            )
        recovery_result = self.recovery_phase.handle_phase_failure(
            failure=failure,
            state=state,
            trace=trace,
            parent=parent,
            available_commands=frozenset(available),
            runtime_profile_digest=self.runtime_profile_digest,
            loaded_profile_artifact_ids=self.loaded_profile_artifact_ids,
            fresh_candidate_id=fresh_candidate_id,
            fresh_route_ref=fresh_route_ref,
            idempotency_key=contract.idempotency_key,
            compensation_contract_id=(
                f"compensation:{contract.id}" if contract.compensation else ""
            ),
        )
        parent = recovery_result.parent
        recovery_kind = recovery_result.recovery_kind
        if contract.grounding_candidate is not None:
            if recovery_kind == RecoveryKind.REROUTE:
                state.record_grounding_reroute(
                    contract,
                    "recovery reroute",
                    exclude_candidate=True,
                )
            elif recovery_kind in {
                RecoveryKind.REOBSERVE,
                RecoveryKind.RETRY_IDEMPOTENT,
            }:
                state.record_grounding_reroute(
                    contract,
                    "recovery requires fresh observation",
                    exclude_candidate=False,
                )
        return recovery_kind, parent

    def recover_phase_failure(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        phase: FailurePhase,
        failure_class: FailureClass,
        error_code: RuntimeErrorCode | str,
        message: str,
        available_commands: frozenset[RecoveryKind],
        snapshot: BrowserSnapshot | None = None,
        proposal_id: str = "",
        proposal_rejection: ProposalRejectionContext | None = None,
        expected_effect: str = "",
        recoverable: bool = True,
        abort_reentry_phase: RuntimePhase = RuntimePhase.ABORTED,
    ) -> tuple[RecoveryKind, TraceNode]:
        task_plan = state.task_plan
        failure = make_failure_envelope(
            run_id=envelope.task_id,
            phase=phase,
            failure_class=failure_class,
            error_code=error_code,
            message=message,
            state_version=state.version,
            task_revision=(
                task_plan.task_revision
                if task_plan is not None
                else envelope.task_spec.revision
                if envelope.task_spec is not None
                else 1
            ),
            plan_version=task_plan.plan_version if task_plan is not None else 0,
            active_subgoal_id=(
                state.plan_progress.active_subgoal_id
                if state.plan_progress is not None
                else ""
            ),
            observation_epoch_id=(
                snapshot.observation.snapshot_id
                if snapshot is not None
                else state.current_snapshot_id
            ),
            snapshot_id=(
                snapshot.observation.snapshot_id
                if snapshot is not None
                else state.current_snapshot_id
            ),
            proposal_id=proposal_id,
            proposal_rejection=proposal_rejection,
            expected_effect=expected_effect or envelope.goal,
            effect_status=EffectStatus.NOT_DISPATCHED,
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=tuple(state.disproved_assumptions),
            remaining_budgets=self._remaining_recovery_budgets(state),
            recoverable=recoverable,
            progress_fingerprint=semantic_progress_fingerprint(state),
        )
        classification = classify_failure(failure)
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            return commit_non_runtime_failure_owner_handoff(
                state,
                trace,
                parent,
                failure=failure,
                classification=classification,
            )
        recovery_result = self.recovery_phase.handle_phase_failure(
            failure=failure,
            state=state,
            trace=trace,
            parent=parent,
            available_commands=available_commands,
            runtime_profile_digest=self.runtime_profile_digest,
            loaded_profile_artifact_ids=self.loaded_profile_artifact_ids,
            abort_reentry_phase=abort_reentry_phase,
        )
        return recovery_result.recovery_kind, recovery_result.parent

    def _remaining_recovery_budgets(
        self,
        state: StateKernel,
    ) -> RemainingRecoveryBudgets:
        return RemainingRecoveryBudgets(
            recoveries=max(0, self.budget.max_recoveries - state.recovery_count),
            observations=max(0, self.budget.max_observations - state.observation_count),
            replans=max(0, self.budget.max_replans - state.replan_count),
            provider_switches=1,
            user_escalations=1,
            timeout_ms=120_000,
            model_calls=max(0, self.budget.max_replans - state.replan_count),
            estimated_cost=10.0,
        )
