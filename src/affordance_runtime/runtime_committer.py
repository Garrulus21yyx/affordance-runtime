"""Single commit boundary for immutable stage results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from threading import RLock
from time import time
from typing import Any, TypeVar, cast

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.dispatch_lifecycle import (
    DispatchAdmissionRejected,
    DispatchPermit,
    PreparedDispatch,
)
from affordance_runtime.execution_context import digest_payload
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.stage_protocol import (
    ArtifactIndexDelta,
    CompletionDelta,
    CounterDelta,
    EffectSettlementDelta,
    GroundingRecoveryDelta,
    ObservationDelta,
    PerceptionDelta,
    PhaseDelta,
    PlanningDelta,
    ProgressDelta,
    ReceiptDelta,
    RecoveryDelta,
    ResultDelta,
    RuntimeEvent,
    StageResult,
    StepProgressDelta,
    UncertainEffectDelta,
    VerificationDelta,
    VersionDelta,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.contracts import TaskCompletionEvaluation

T = TypeVar("T")
_DISPATCH_LINEARIZATION_LOCK = RLock()


@dataclass(frozen=True)
class RuntimeCommitter:
    def admit_dispatch(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        prepared: PreparedDispatch,
    ) -> tuple[DispatchPermit, TraceNode]:
        """Commit a complete prepared dispatch at one linearization point."""

        admission = prepared.admission
        attempt = prepared.attempt
        if state.version != prepared.expected_state_version:
            raise DispatchAdmissionRejected(RuntimeErrorCode.STALE_OBSERVATION)
        if parent.id not in {node.id for node in trace.nodes}:
            raise DispatchAdmissionRejected(RuntimeErrorCode.STALE_OBSERVATION)
        if state.phase not in {RuntimeStep.PLANNING.value, RuntimeStep.PREFLIGHT.value}:
            raise DispatchAdmissionRejected(RuntimeErrorCode.PRECONDITION_FAILED)
        if admission.contract_hash != prepared.contract.contract_hash:
            raise DispatchAdmissionRejected(RuntimeErrorCode.STALE_OBSERVATION)
        surface = admission.contract.live_surface_binding
        if surface is None:
            raise DispatchAdmissionRejected(RuntimeErrorCode.STALE_OBSERVATION)
        pre_events = self._prepared_events(prepared)
        # Validate the complete trace shape before consuming any authority.
        shadow_trace = deepcopy(trace)
        shadow_parent = self.commit_events(shadow_trace, parent, pre_events)
        del shadow_parent

        with _DISPATCH_LINEARIZATION_LOCK, admission.gate.linearized_authority():
            if (
                state.task_id != admission.run_id
                or attempt.contract_id != prepared.contract.id
                or attempt.contract_hash != admission.contract_hash
                or attempt.issued_at_state_version != admission.expected_state_version
                or prepared.observation.snapshot_id != admission.observation.snapshot_id
                or prepared.observation.page_revision != admission.observation.page_revision
                or prepared.observation.environment_revision != admission.observation.environment_revision
            ):
                raise DispatchAdmissionRejected(
                    RuntimeErrorCode.STALE_OBSERVATION
                )
            error = admission.consume_if_current(state_version=state.version)
            if error is not None:
                raise DispatchAdmissionRejected(error)
            state.current_contract = admission.contract
            state.current_execution_attempt = attempt
            self._commit_phase(state, RuntimeStep.ACTING)
            state.step_count += 1
            if admission.contract.effectful:
                state.effectful_action_count += 1
            state.version += 1
            committed_version = state.version
            parent = self.commit_events(trace, parent, pre_events)
            attempt_node = trace.add(
                "ExecutionAttemptCommitted",
                {
                    "admission_id": admission.admission_id,
                    "attempt_id": attempt.attempt_id,
                    "contract_hash": admission.contract.contract_hash,
                    "state_version": committed_version,
                },
                parents=[parent.id],
            )
            node = trace.add(
                "DispatchIntentCommitted",
                {
                    "admission_id": admission.admission_id,
                    "attempt_id": attempt.attempt_id,
                    "contract_hash": admission.contract.contract_hash,
                    "state_version": committed_version,
                },
                parents=[attempt_node.id],
            )
            issued = time()
            permit = DispatchPermit(
                permit_id="dispatch-permit:"
                + digest_payload((admission.admission_id, attempt.attempt_id, committed_version, issued)).split(":", 1)[1],
                admission_id=admission.admission_id,
                contract=admission.contract,
                observation=admission.observation,
                attempt=attempt,
                committed_state_version=committed_version,
                issued_at_s=issued,
                expires_at_s=min(admission.expires_at_s, surface.lease.expires_at_s),
                contract_hash=admission.contract_hash,
                run_id=admission.run_id,
                session_generation=admission.session_generation,
                surface_id=admission.surface_id,
                surface_check=admission.surface_check,
                coordinate_check=admission.coordinate_check,
                fence_lock=admission.fence_lock,
            )
            return permit, node

    @staticmethod
    def _prepared_events(prepared: PreparedDispatch) -> tuple[RuntimeEvent, ...]:
        """Construct the only authoritative pre-dispatch event sequence."""

        contract = prepared.contract
        route = contract.route_binding
        if route is None:
            raise DispatchAdmissionRejected(RuntimeErrorCode.STALE_OBSERVATION)
        events = [
            RuntimeEvent(
                "ContractBuilt",
                {
                    "contract_hash": contract.contract_hash,
                    "contract_id": contract.id,
                    "schema_version": contract.schema_version,
                    "snapshot_id": contract.snapshot_id,
                    "page_revision": contract.page_revision,
                    "backend": contract.backend,
                    "target_fingerprint": contract.target_fingerprint,
                    "semantic_action": {
                        "action_kind": {
                            "type": "type_text",
                            "fill": "type_text",
                            "select": "select_option",
                            "press": "press_key",
                        }.get(contract.action, contract.action),
                        "target": dict(prepared.semantic_target)
                        or {"role": contract.affordance_id, "label": contract.affordance_id},
                        "destination": dict(prepared.semantic_destination),
                        "parameters": (
                            {"text": route.named_parameters.get("value", "")}
                            if contract.action in {"type", "fill"}
                            else dict(route.named_parameters)
                        ),
                        "expected_effects": [asdict(item) for item in contract.expected_effects],
                        "verifier_plan": [asdict(item) for item in contract.verifier_plan],
                        "required_capabilities": list(contract.required_capabilities),
                        "risk": contract.risk.value,
                    },
                    "choice_id": prepared.selection_id,
                    "catalog_id": prepared.catalog_id,
                },
            ),
            RuntimeEvent(
                "RouteSelected",
                {
                    "contract_hash": contract.contract_hash,
                    "candidate_id": route.target_id,
                    "backend": contract.backend,
                    "source": (
                        contract.grounding_candidate.source.value
                        if contract.grounding_candidate is not None
                        else ""
                    ),
                    "semantic_target_id": (
                        contract.grounding_candidate.semantic_target_id
                        if contract.grounding_candidate is not None
                        else ""
                    ),
                    "executor": route.adapter_id,
                    "hard_gates": [
                        {
                            "candidate_id": item.candidate_id,
                            "passed": item.passed,
                            "reasons": list(item.reasons),
                        }
                        for item in (contract.route_plan.hard_gate_results if contract.route_plan is not None else ())
                    ],
                    "decision_reason": contract.route_plan.decision_reason if contract.route_plan is not None else "",
                    "viable_alternative_ids": [
                        item.candidate_id
                        for item in (contract.route_plan.viable_alternatives if contract.route_plan is not None else ())
                    ],
                    "scores": [
                        {
                            "candidate_id": item.candidate_id,
                            "score": item.score,
                            "confidence_component": item.confidence_component,
                            "latency_component": item.latency_component,
                            "cost_component": item.cost_component,
                            "verification_component": item.verification_component,
                        }
                        for item in (contract.route_plan.scores if contract.route_plan is not None else ())
                    ],
                },
            ),
            RuntimeEvent(
                "CommittedObservationPreflightChecked",
                {
                    "contract_hash": contract.contract_hash,
                    "snapshot_id": prepared.observation.snapshot_id,
                    "page_revision": prepared.observation.page_revision,
                },
            ),
        ]
        if prepared.approval_decision_id:
            events.append(
                RuntimeEvent(
                    "HumanApprovalRequested",
                    {
                        "contract_hash": contract.contract_hash,
                        "snapshot_id": contract.snapshot_id,
                        "page_revision": contract.page_revision,
                        "environment_revision": contract.environment_revision,
                    },
                )
            )
            events.append(
                RuntimeEvent(
                    "HumanApprovalGranted",
                    {
                        "contract_hash": contract.contract_hash,
                        "decision_id": prepared.approval_decision_id,
                        "snapshot_id": contract.snapshot_id,
                        "page_revision": contract.page_revision,
                        "environment_revision": contract.environment_revision,
                    },
                )
            )
            events.append(
                RuntimeEvent(
                    "ApprovalStateRevalidated",
                    {
                        "contract_hash": contract.contract_hash,
                        "snapshot_id": contract.snapshot_id,
                        "page_revision": contract.page_revision,
                        "environment_revision": contract.environment_revision,
                    },
                )
            )
        events.extend(
            (
                RuntimeEvent("PreflightPassed", {"contract_hash": contract.contract_hash}),
                RuntimeEvent(
                    "ExecutionAttemptIssued",
                    {"attempt_id": prepared.attempt.attempt_id, "contract_hash": contract.contract_hash},
                ),
            )
        )
        return tuple(events)

    def commit_loop_transition(self, state: StateKernel, transition: Any) -> None:
        state.transition(transition.phase.value)
        if transition.activate_next_step:
            state.activate_next_step()

    def commit_loop_event(
        self,
        trace: TraceDag,
        event: Any,
        parent: TraceNode | None = None,
    ) -> TraceNode:
        parent_ids = event.parent_ids
        if not parent_ids and parent is not None:
            parent_ids = (parent.id,)
        return trace.add(
            event.kind,
            event.payload,
            parents=list(parent_ids) if parent_ids else None,
        )

    def commit(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        result: StageResult[T],
    ) -> TraceNode:
        transition = result.transition
        if transition is None:
            if result.failure is not None:
                state.current_failure = result.failure
            return self.commit_events(trace, parent, result.events)
        if state.version != transition.expected_state_version:
            raise ValueError(
                f"stale runtime transition expected state version "
                f"(actual={state.version}, expected={transition.expected_state_version})"
            )

        # Validate the complete batch against detached state/trace first. No
        # live state, trace, artifact index, or failure owner is touched until
        # every delta and event has succeeded.
        shadow_state = deepcopy(state)
        shadow_trace = deepcopy(trace)
        shadow_parent = self._apply_commit_batch(shadow_state, shadow_trace, parent, result)
        del shadow_parent

        return self._apply_commit_batch(state, trace, parent, result)

    def _apply_commit_batch(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        result: StageResult[T],
    ) -> TraceNode:
        transition = result.transition
        if transition is None:
            return self.commit_events(trace, parent, result.events)
        if result.failure is not None:
            state.current_failure = result.failure
        for delta in transition.deltas:
            self._apply_delta(state, delta)
            if isinstance(delta, ArtifactIndexDelta):
                trace.artifact_index.extend(delta.refs)
        parent = self.commit_events(trace, parent, result.events)
        completion = next((delta.evaluation for delta in transition.deltas if isinstance(delta, CompletionDelta)), None)
        if completion is not None:
            parent = self.commit_task_completion(state, trace, parent, completion)
        return parent

    @staticmethod
    def _apply_delta(state: StateKernel, delta: object) -> None:
        """Apply only the closed state-delta union; unknown values fail closed."""

        if isinstance(delta, PhaseDelta):
            RuntimeCommitter._commit_phase(state, delta.phase)
        elif isinstance(delta, ObservationDelta):
            for observation in delta.commits:
                state.remember_observation_commit(observation)
        elif isinstance(delta, PerceptionDelta):
            for observation in delta.commits:
                state.remember_observation_commit(observation)
            state.evidence_gaps = delta.evidence_gaps
            state.active_probe_plan = delta.active_probe_plan
            if delta.probe_receipts:
                state.latest_probe_receipt = delta.probe_receipts[-1]
            state.perception_resolution = delta.perception_resolution
            state.active_perception_count += delta.active_perception_count_delta
        elif isinstance(delta, PlanningDelta):
            if delta.task_plan_transition is not None:
                transition = delta.task_plan_transition
                if transition.previous_plan is None:
                    state.install_task_plan(transition.plan)
                else:
                    state.replace_task_plan(transition.plan)
                state.activate_next_step()
            if delta.planner_proposal is not None:
                state.record_planner_proposal(dict(delta.planner_proposal))
        elif isinstance(delta, VerificationDelta):
            state.latest_verification = delta.report
        elif isinstance(delta, StepProgressDelta):
            if delta.task_progress is not None:
                state.task_progress = deepcopy(delta.task_progress)
            if delta.recent_action_outcomes is not None:
                from affordance_runtime.state_kernel import RecentActionOutcomeIndex

                state.recent_action_outcomes = cast(
                    RecentActionOutcomeIndex, deepcopy(delta.recent_action_outcomes)
                )
            if delta.latest_effect_settlement is not None:
                state.latest_effect_settlement = delta.latest_effect_settlement
            if delta.latest_progress_guard is not None:
                state.latest_progress_guard = dict(delta.latest_progress_guard)
            if delta.replan_count is not None:
                if delta.replan_count < state.replan_count:
                    raise ValueError("progress replan count cannot decrease")
                state.replan_count = delta.replan_count
        elif isinstance(delta, CounterDelta):
            if min(delta.step_count, delta.subgoal_action_count, delta.effectful_action_count, delta.replan_count) < 0:
                raise ValueError("counter delta must be non-negative")
            state.step_count += delta.step_count
            for _ in range(delta.subgoal_action_count):
                state.record_step_action()
            state.effectful_action_count += delta.effectful_action_count
            state.replan_count += delta.replan_count
        elif isinstance(delta, VersionDelta):
            if delta.delta <= 0:
                raise ValueError("version delta must be positive")
            state.version += delta.delta
        elif isinstance(delta, ResultDelta):
            state.final_result = dict(delta.result_payload)
        elif isinstance(delta, UncertainEffectDelta):
            if any(item.attempt.attempt_id == delta.attempt.attempt_id for item in state.uncertain_external_effects):
                raise ValueError("duplicate uncertain effect attempt")
            from affordance_runtime.simplified_runtime_contracts import UncertainExternalEffect

            state.uncertain_external_effects = (
                *state.uncertain_external_effects,
                UncertainExternalEffect(delta.attempt),
            )
        elif isinstance(delta, ReceiptDelta):
            attempt = state.current_execution_attempt
            contract = state.current_contract
            if (
                attempt is None
                or contract is None
                or delta.attempt_id != attempt.attempt_id
                or delta.contract_id != attempt.contract_id
                or delta.contract_hash != attempt.contract_hash
                or delta.receipt.contract_id != contract.id
                or delta.receipt.backend != contract.backend
            ):
                raise ValueError(
                    "receipt is not bound to current execution attempt "
                    f"(attempt={getattr(attempt, 'attempt_id', None)!r}, "
                    f"delta_attempt={delta.attempt_id!r}, contract={getattr(contract, 'id', None)!r}, "
                    f"delta_contract={delta.contract_id!r}, "
                    f"hash_match={getattr(attempt, 'contract_hash', None) == delta.contract_hash}, "
                    f"receipt_contract={delta.receipt.contract_id!r}, "
                    f"receipt_backend={delta.receipt.backend!r}, "
                    f"contract_backend={getattr(contract, 'backend', None)!r})"
                )
            if state.last_receipt_attempt_id == delta.attempt_id:
                raise ValueError("duplicate receipt")
            state.record_receipt(delta.receipt, attempt_id=delta.attempt_id)
        elif isinstance(delta, EffectSettlementDelta):
            attempt = state.current_execution_attempt
            if attempt is None or attempt.attempt_id != delta.attempt_id or attempt.contract_hash != delta.contract_hash:
                raise ValueError("effect settlement is not bound to current attempt")
            if not delta.evidence_refs:
                raise ValueError("effect settlement requires identity-bound evidence")
            state.latest_effect_settlement = delta.settlement
            status = getattr(delta.settlement.status, "value", str(delta.settlement.status))
            if status in {"occurred", "not_occurred"}:
                state.uncertain_external_effects = tuple(
                    item for item in state.uncertain_external_effects
                    if item.attempt.attempt_id != delta.attempt_id
                )
        elif isinstance(delta, ProgressDelta):
            if delta.latest_verification is not None:
                state.latest_verification = delta.latest_verification
            if delta.progress_guard is not None:
                from affordance_runtime.state_kernel import ProgressGuardReason

                reason, signature = delta.progress_guard
                state.record_progress_guard(ProgressGuardReason(reason), signature)
        elif isinstance(delta, RecoveryDelta):
            if delta.failure is not None and state.current_failure is None:
                state.current_failure = delta.failure
            if delta.decision is not None:
                state.current_recovery_decision = delta.decision
            if delta.outcome is not None:
                state.current_recovery_outcome = delta.outcome
            if delta.attempted_strategy_ids is not None:
                state.attempted_recovery_strategy_ids = set(delta.attempted_strategy_ids)
            if delta.recovery_count is not None:
                state.recovery_count = delta.recovery_count
            if delta.disproved_assumption is not None:
                state.record_disproved_assumption(delta.disproved_assumption)
            if delta.excluded_candidates is not None:
                state.current_excluded_candidates = {
                    key: set(values) for key, values in delta.excluded_candidates.items()
                }
            if delta.grounding_fallback is not None:
                state.current_grounding_fallback = {
                    key: dict(value) for key, value in delta.grounding_fallback.items()
                }
            if delta.clear_decision:
                state.current_recovery_decision = None
            if delta.clear_outcome:
                state.current_recovery_outcome = None
        elif isinstance(delta, GroundingRecoveryDelta):
            if delta.excluded_candidates is not None:
                state.current_excluded_candidates = {
                    key: set(values) for key, values in delta.excluded_candidates.items()
                }
            if delta.grounding_fallback is not None:
                state.current_grounding_fallback = {
                    key: dict(value) for key, value in delta.grounding_fallback.items()
                }
        elif isinstance(delta, CompletionDelta):
            if not delta.evaluation.completed:
                raise ValueError("completion delta must be completed")
            state.final_result = dict(delta.evaluation.result_payload)
        elif isinstance(delta, ArtifactIndexDelta):
            if any(not ref for ref in delta.refs):
                raise ValueError("artifact index delta contains empty ref")
        else:
            raise TypeError(f"unknown runtime delta: {type(delta).__name__}")

    @staticmethod
    def commit_task_completion(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        completion: TaskCompletionEvaluation,
    ) -> TraceNode:
        """Commit one already-evaluated typed completion transition/event."""

        if not completion.completed:
            raise ValueError("task completion evaluation is not satisfied")
        state.final_result = dict(completion.result_payload)
        if state.phase != RuntimeStep.DONE.value:
            state.transition(RuntimeStep.DONE.value)
        return trace.add(
            "TaskCompleted",
            {
                "state": state.phase,
                "result": {
                    "content_digest": digest_payload(state.final_result),
                    "keys": tuple(sorted(state.final_result)),
                    "redacted": True,
                    "access_policy_ref": "task-owner@v1",
                    "retention_policy_ref": "run-scoped@v1",
                },
            },
            parents=[parent.id],
        )

    @staticmethod
    def _commit_phase(state: StateKernel, target: RuntimeStep) -> None:
        """Commit the canonical in-stage action path through valid Runtime states."""

        if state.phase == RuntimeStep.PLANNING.value and target in {
            RuntimeStep.ACTING,
            RuntimeStep.VERIFYING,
        }:
            state.transition(RuntimeStep.PREFLIGHT.value)
        if state.phase == RuntimeStep.PREFLIGHT.value and target == RuntimeStep.VERIFYING:
            state.transition(RuntimeStep.ACTING.value)
        if (
            state.phase
            in {
                RuntimeStep.ACTING.value,
                RuntimeStep.VERIFYING.value,
            }
            and target == RuntimeStep.ABORTED
        ):
            state.transition(RuntimeStep.RECOVERING.value)
        if state.phase != target.value:
            state.transition(target.value)

    @staticmethod
    def commit_events(
        trace: TraceDag,
        parent: TraceNode,
        events: tuple[RuntimeEvent, ...],
    ) -> TraceNode:
        for event in events:
            if event.kind == "TaskCompleted":
                raise ValueError("TaskCompleted may only be emitted from typed completion commit")
            parent = trace.add(event.kind, dict(event.payload), parents=[parent.id])
        return parent
