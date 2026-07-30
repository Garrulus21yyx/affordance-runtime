"""Coordinator-facing post-action verification seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace

from affordance_runtime.action_outcome_flow import record_contract_action_outcome_trace
from affordance_runtime.active_perception import ActivePerceptionRequest
from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.perception_session import PerceptionSession
from affordance_runtime.route_calibration import (
    RouteCalibrator,
    RouteOutcome,
    RouteOutcomeStatus,
    RouteScope,
)
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.runtime_evidence import verification_satisfies_effect
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport, VerificationStatus

WriteObservation = Callable[[str, int, BrowserSnapshot], ArtifactRef | None]
WriteVerification = Callable[[str, int, VerificationReport], ArtifactRef | None]
IndexArtifact = Callable[[TraceDag, ArtifactRef | None], None]
IndexPaths = Callable[[TraceDag, list[str]], None]
TraceSourceArbitration = Callable[[TraceDag, TraceNode, BrowserSnapshot, str], TraceNode]
FulfillTargetedPerception = Callable[
    [TaskEnvelope, StateKernel, TraceDag, TraceNode, BrowserSnapshot],
    tuple[BrowserSnapshot, TraceNode],
]
@dataclass(frozen=True)
class VerificationPhaseResult:
    parent: TraceNode
    post_snapshot: BrowserSnapshot
    verification: VerificationReport
    verification_ref: ArtifactRef | None


class VerificationPhase:
    """Observe after execution, verify the contract, and record outcome traces."""

    def run(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        receipt: ExecutionReceipt,
        execution_observation: Observation,
        action_signature: str,
        skill_step_id: str,
        contract_execution_loop: ContractExecutionLoop,
        perception_session: PerceptionSession,
        structural_verification_enabled: bool,
        write_observation: WriteObservation,
        write_verification: WriteVerification,
        index_artifact: IndexArtifact,
        index_paths: IndexPaths,
        trace_source_arbitration: TraceSourceArbitration,
        fulfill_targeted_perception: FulfillTargetedPerception,
        route_calibrator: RouteCalibrator,
        decision_has_proposal: bool,
    ) -> VerificationPhaseResult:
        post_snapshot, parent, post_ref = _capture_post_action_observation(
            envelope,
            state,
            perception_session,
            write_observation,
            index_artifact,
            index_paths,
            trace,
            parent,
        )
        parent = trace_source_arbitration(trace, parent, post_snapshot, state.phase)
        latest_verification = contract_execution_loop.verify(
            contract,
            receipt,
            post_snapshot.observation,
            structural_verification_enabled=structural_verification_enabled,
            disabled_reason="structural verification disabled by benchmark ablation",
        )
        if (
            latest_verification.status == VerificationStatus.INCONCLUSIVE
            and structural_verification_enabled
        ):
            requested_sources = tuple(
                dict.fromkeys(
                    item.source
                    for item in post_snapshot.source_observations
                    if item.source
                    in {
                        GroundingSource.DOM,
                        GroundingSource.ACCESSIBILITY,
                        GroundingSource.API,
                    }
                )
            ) or (GroundingSource.DOM, GroundingSource.ACCESSIBILITY)
            repair_request = ActivePerceptionRequest(
                entity_key=contract.affordance_id,
                property_key="verification",
                requested_sources=requested_sources,
                reason="verifier is inconclusive and requires fresh independent structural evidence",
                max_observations=1,
            )
            repair_snapshot = replace(
                post_snapshot,
                active_perception_requests=(repair_request,),
            )
            parent = trace.add(
                "VerificationEvidenceRepairRequested",
                {
                    "state": state.phase,
                    "contract_id": contract.id,
                    "verification_status": latest_verification.status.value,
                },
                parents=[parent.id],
            )
            repair_snapshot, parent = fulfill_targeted_perception(
                envelope,
                state,
                trace,
                parent,
                repair_snapshot,
            )
            if repair_snapshot.observation.snapshot_id != post_snapshot.observation.snapshot_id:
                post_snapshot = repair_snapshot
                latest_verification = contract_execution_loop.verify(
                    contract,
                    receipt,
                    post_snapshot.observation,
                    structural_verification_enabled=True,
                    disabled_reason="",
                )
                parent = trace.add(
                    "VerificationEvidenceReevaluated",
                    {
                        "state": state.phase,
                        "contract_id": contract.id,
                        "verification_status": latest_verification.status.value,
                        "snapshot_id": post_snapshot.observation.snapshot_id,
                    },
                    parents=[parent.id],
                )
        state.latest_verification = latest_verification
        parent = record_contract_action_outcome_trace(
            contract_execution_loop,
            trace,
            parent,
            contract,
            execution_observation,
            state.version,
            receipt,
            latest_verification,
            post_snapshot.observation,
            skill_step_id or contract.affordance_id,
            state.phase,
        ).parent
        if decision_has_proposal:
            state.record_action_progress(
                action_signature,
                post_snapshot.observation.environment_revision,
                verification_passed=latest_verification.passed,
                effect_satisfied=verification_satisfies_effect(latest_verification),
                post_page_revision=post_snapshot.observation.page_revision,
            )
        verification_ref = write_verification(
            envelope.task_id,
            state.step_count,
            latest_verification,
        )
        index_artifact(trace, verification_ref)
        parent = trace.add(
            "PostconditionPassed" if latest_verification.passed else "PostconditionFailed",
            {
                "state": state.phase,
                "contract_id": contract.id,
                "status": latest_verification.status.value,
                "reason": latest_verification.reason,
                "artifact_refs": [verification_ref.path] if verification_ref else [],
                "evidence": [asdict(item) for item in latest_verification.evidence],
            },
            parents=[parent.id],
        )
        parent = self.record_route_outcome(
            trace,
            parent,
            contract,
            receipt,
            latest_verification,
            post_snapshot,
            state.phase,
            route_calibrator,
        )
        return VerificationPhaseResult(
            parent=parent,
            post_snapshot=post_snapshot,
            verification=latest_verification,
            verification_ref=verification_ref,
        )

    @staticmethod
    def record_route_outcome(
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        receipt: ExecutionReceipt,
        report: VerificationReport,
        snapshot: BrowserSnapshot,
        state_phase: str,
        route_calibrator: RouteCalibrator,
    ) -> TraceNode:
        candidate = contract.grounding_candidate
        route_plan = contract.route_plan
        if candidate is None or route_plan is None or not route_plan.verifier_kinds:
            return parent
        scope = RouteScope(
            environment_family=route_plan.environment_scope,
            action_kind=route_plan.action_kind or contract.action,
            source=candidate.source,
            executor=candidate.compatible_executor,
            verifier_kinds=route_plan.verifier_kinds,
        )
        outcome = RouteOutcome.from_verification(
            outcome_id=f"route-outcome:{contract.id}:{snapshot.observation.snapshot_id}",
            scope=scope,
            semantic_target_id=candidate.semantic_target_id,
            candidate_id=candidate.candidate_id,
            contract_id=contract.id,
            report=report,
            post_snapshot_id=snapshot.observation.snapshot_id,
            latency_ms=receipt.latency_ms,
            expected_cost=candidate.expected_cost,
        )
        route_calibrator.record(outcome)
        return trace.add(
            "RouteOutcomeRecorded",
            {
                "state": state_phase,
                "outcome_id": outcome.outcome_id,
                "status": outcome.status.value,
                "verification_status": outcome.verification_status.value,
                "trainable": outcome.status != RouteOutcomeStatus.INCONCLUSIVE,
                "semantic_target_id": outcome.semantic_target_id,
                "candidate_id": outcome.candidate_id,
                "contract_id": outcome.contract_id,
                "post_snapshot_id": outcome.post_snapshot_id,
                "evidence_ids": list(outcome.evidence_ids),
                "scope": {
                    "environment_family": scope.environment_family,
                    "action_kind": scope.action_kind,
                    "source": scope.source.value,
                    "executor": scope.executor,
                    "verifier_kinds": list(scope.verifier_kinds),
                },
                "latency_ms": outcome.latency_ms,
                "expected_cost": outcome.expected_cost,
            },
            parents=[parent.id],
        )


def _capture_post_action_observation(
    envelope: TaskEnvelope,
    state: StateKernel,
    perception_session: PerceptionSession,
    write_observation: WriteObservation,
    index_artifact: IndexArtifact,
    index_paths: IndexPaths,
    trace: TraceDag,
    parent: TraceNode,
) -> tuple[BrowserSnapshot, TraceNode, ArtifactRef | None]:
    post_snapshot = perception_session.capture(
        envelope,
        state,
        state.observation_count + 1,
    )
    state.remember_observation(post_snapshot.observation)
    post_ref = write_observation(envelope.task_id, state.observation_count, post_snapshot)
    index_artifact(trace, post_ref)
    index_paths(trace, post_snapshot.observation.artifact_refs)
    parent = trace.add(
        "PostActionObservationCaptured",
        {
            "state": state.phase,
            "snapshot_id": post_snapshot.observation.snapshot_id,
            "page_revision": post_snapshot.observation.page_revision,
            "artifact_refs": ([post_ref.path] if post_ref else [])
            + list(post_snapshot.observation.artifact_refs),
        },
        parents=[parent.id],
    )
    return post_snapshot, parent, post_ref
