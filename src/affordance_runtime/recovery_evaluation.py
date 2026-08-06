"""Pure recovery outcome evaluation for observations and action attempts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import EffectStatus
from affordance_runtime.recovery_protocol import RecoveryKind, RecoveryOutcome, RuntimePhase
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.runtime_evidence import effect_settlement_status
from affordance_runtime.simplified_runtime_contracts import EffectSettlementStatus
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class RecoveryObservationEvaluation:
    verification: VerificationReport | None
    outcome: RecoveryOutcome


@dataclass(frozen=True)
class RecoveryActionSettlement:
    outcome: RecoveryOutcome


@dataclass(frozen=True)
class RecoveryObservationEvaluator:
    """Evaluate a recovery observation without mutating Runtime state."""

    def evaluate(
        self,
        *,
        state: RuntimeStateSnapshot,
        snapshot: Any,
        execution_loop: Any,
        task_skill_progress: object | None = None,
    ) -> StageResult[RecoveryObservationEvaluation] | None:
        decision = state.current_recovery_decision
        failure = state.current_failure
        if (
            decision is None
            or failure is None
            or state.current_recovery_outcome is not None
            or decision.kind not in {RecoveryKind.REOBSERVE, RecoveryKind.INSPECT_POST_STATE}
        ):
            return None
        verification = None
        failed = False
        events: list[RuntimeEvent] = []
        updates: dict[str, object] = {}
        if decision.kind == RecoveryKind.INSPECT_POST_STATE:
            contract = state.current_contract
            receipt = state.last_receipt
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
                        "state": state.phase,
                        "verification": verification.status.value,
                        "snapshot_id": snapshot.observation.snapshot_id,
                        "artifact_refs": snapshot.observation.artifact_refs,
                    },
                )
            )
            current_attempt = state.current_execution_attempt
            unresolved_attempt_ids = {item.attempt.attempt_id for item in state.uncertain_external_effects}
            settlement = (
                effect_settlement_status(verification, contract, current_attempt)
                if current_attempt is not None and current_attempt.attempt_id in unresolved_attempt_ids
                else EffectSettlementStatus.STILL_UNCERTAIN
            )
            absence_confirmed = settlement == EffectSettlementStatus.CONFIRMED_NOT_OCCURRED
            effect_settled = bool(
                settlement
                in {
                    EffectSettlementStatus.CONFIRMED_OCCURRED,
                    EffectSettlementStatus.CONFIRMED_NOT_OCCURRED,
                }
            )
            skill_fallthrough = bool(
                absence_confirmed
                and task_skill_progress is not None
                and not getattr(task_skill_progress, "active", True)
            )
            failed = not verification.passed and not absence_confirmed and not skill_fallthrough
            if effect_settled:
                updates["uncertain_external_effects"] = tuple(
                    item
                    for item in state.uncertain_external_effects
                    if current_attempt is None or item.attempt.attempt_id != current_attempt.attempt_id
                )
            if absence_confirmed:
                updates["current_failure"] = failure.model_copy(
                    update={"effect_status": EffectStatus.CONFIRMED_NOT_OCCURRED},
                )
        outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=not failed,
            changed_dimensions=decision.changed_dimensions,
            next_phase=RuntimePhase.ABORTED if failed else decision.reentry_phase,
            artifact_refs=() if failed else tuple(snapshot.observation.artifact_refs),
            observation_refs=(() if failed else (snapshot.observation.snapshot_id,)),
            error_code="verification_failed" if failed else "",
        )
        updates["current_recovery_outcome"] = outcome
        events.append(_outcome_event(state.phase, outcome))
        terminal = None
        phase = None
        if failed:
            phase = RuntimeStep.ABORTED
            events.append(
                RuntimeEvent(
                    "RecoveryAborted",
                    {
                        "state": state.phase,
                        "reason": ("post-state inspection did not establish a safe changed effect status"),
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
            events.append(_reentry_event(state.phase, decision.reentry_phase.value))
        return StageResult(
            output=RecoveryObservationEvaluation(verification, outcome),
            transition=RuntimeTransition(phase=phase, state_updates=updates),
            events=tuple(events),
            terminal=terminal,
            directive=(LoopDirective.TERMINAL if terminal is not None else LoopDirective.NEXT_STAGE),
        )


@dataclass(frozen=True)
class RecoveryActionEvaluator:
    """Settle reground, reroute, or idempotent retry from a typed Action result."""

    def evaluate(
        self,
        *,
        state: RuntimeStateSnapshot,
        action_result: StageResult[Any],
    ) -> StageResult[RecoveryActionSettlement] | None:
        decision = state.current_recovery_decision
        failure = state.current_failure
        if decision is None or failure is None or state.current_recovery_outcome is not None:
            return None
        output = action_result.output
        outcome: RecoveryOutcome | None = None
        if (
            action_result.failure is not None
            and action_result.failure.phase.value == "grounding_binding"
            and decision.kind in {RecoveryKind.REGROUND, RecoveryKind.REROUTE}
        ):
            outcome = _failed_outcome(decision, failure, action_result.failure.error_code)
        elif output is not None and decision.kind in {
            RecoveryKind.REGROUND,
            RecoveryKind.REROUTE,
        }:
            outcome = _binding_outcome(decision, failure, output.contract)
        elif (
            output is not None and decision.kind == RecoveryKind.RETRY_IDEMPOTENT and action_result.failure is not None
        ):
            outcome = _execution_outcome(
                decision,
                failure,
                output.receipt,
                output.execution_snapshot.observation,
            )
        if outcome is None:
            return None
        events = [_outcome_event(state.phase, outcome)]
        terminal = None
        phase = None
        clear_decision = False
        if outcome.success:
            if decision.kind in {RecoveryKind.REGROUND, RecoveryKind.REROUTE}:
                events.append(_reentry_event(state.phase, decision.reentry_phase.value))
        elif action_result.failure is not None:
            phase = RuntimeStep.ABORTED
            clear_decision = True
            events.append(
                RuntimeEvent(
                    "FailureOwnerRouted",
                    {
                        "state": RuntimeStep.RECOVERING.value,
                        "failure_id": action_result.failure.failure_id,
                        "owner": "terminal",
                        "handoff_type": "TerminalResult",
                        "reason_code": "runtime_recovery_failed",
                    },
                )
            )
            terminal = TerminalResult(
                action_result.failure.failure_id,
                action_result.failure.error_code,
                RuntimeStep.ABORTED,
                _runtime_error(action_result.failure.error_code),
            )
        return StageResult(
            output=RecoveryActionSettlement(outcome),
            transition=RuntimeTransition(
                phase=phase,
                intermediate_phases=((RuntimeStep.RECOVERING,) if phase == RuntimeStep.ABORTED else ()),
                state_updates={"current_recovery_outcome": outcome},
                clear_recovery_decision=clear_decision,
            ),
            events=tuple(events),
            terminal=terminal,
            directive=(LoopDirective.TERMINAL if terminal is not None else LoopDirective.NEXT_STAGE),
        )


def _binding_outcome(decision: Any, failure: Any, contract: Any) -> RecoveryOutcome:
    candidate_id = contract.grounding_candidate.candidate_id if contract.grounding_candidate is not None else ""
    route_matches = bool(
        decision.kind == RecoveryKind.REGROUND
        or (decision.candidate_id and candidate_id == decision.candidate_id)
        or (decision.route_ref and contract.backend == decision.route_ref)
    )
    if not contract.snapshot_id or contract.snapshot_id == failure.snapshot_id or not route_matches:
        return _failed_outcome(decision, failure, "planner_proposal_rejected")
    return RecoveryOutcome(
        decision_id=decision.decision_id,
        failure_id=failure.failure_id,
        success=True,
        changed_dimensions=decision.changed_dimensions,
        next_phase=decision.reentry_phase,
        artifact_refs=tuple(item for item in (candidate_id, contract.id) if item),
    )


def _execution_outcome(
    decision: Any,
    failure: Any,
    receipt: Any,
    observation: Any,
) -> RecoveryOutcome:
    return RecoveryOutcome(
        decision_id=decision.decision_id,
        failure_id=failure.failure_id,
        success=receipt.success,
        changed_dimensions=decision.changed_dimensions,
        next_phase=decision.reentry_phase,
        artifact_refs=tuple(item for item in receipt.evidence.values() if isinstance(item, str)),
        observation_refs=(observation.snapshot_id,) if observation.snapshot_id else (),
        error_code=(
            ""
            if receipt.success
            else receipt.error_code.value
            if receipt.error_code is not None
            else "execution_failed"
        ),
    )


def _failed_outcome(decision: Any, failure: Any, error_code: str) -> RecoveryOutcome:
    return RecoveryOutcome(
        decision_id=decision.decision_id,
        failure_id=failure.failure_id,
        success=False,
        changed_dimensions=decision.changed_dimensions,
        next_phase=RuntimePhase.ABORTED,
        error_code=error_code,
    )


def _outcome_event(state_phase: str, outcome: RecoveryOutcome) -> RuntimeEvent:
    return RuntimeEvent(
        "RecoveryOutcomeRecorded",
        {
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
        },
    )


def _reentry_event(state_phase: str, reentry_phase: str) -> RuntimeEvent:
    return RuntimeEvent(
        "RecoveryReenteredPhase",
        {"state": state_phase, "reentry_phase": reentry_phase},
    )


def _runtime_error(error_code: str) -> RuntimeErrorCode:
    try:
        return RuntimeErrorCode(error_code)
    except ValueError:
        return RuntimeErrorCode.EXECUTION_FAILED
