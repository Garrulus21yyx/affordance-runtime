"""Post-action observation capture and bounded verification-evidence repair."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

from affordance_runtime.active_perception import ActivePerceptionRequest, ProbeReceipt
from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.observation_store import (
    InMemoryObservationStore,
    ObservationCommit,
    ObservationRef,
)
from affordance_runtime.perception_session import (
    PerceptionCapture,
    PerceptionCaptureRequest,
    PerceptionSession,
)
from affordance_runtime.stage_protocol import RuntimeEventBuffer, RuntimeStateSnapshot
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class PostActionObservation:
    capture: PerceptionCapture
    observation: UnifiedObservation
    observation_ref: ObservationRef
    observation_commits: tuple[ObservationCommit, ...]


@dataclass(frozen=True)
class PostActionObservationService:
    perception_session: PerceptionSession
    execution_loop: ContractExecutionLoop
    observation_builder: CanonicalObservationBuilder = CanonicalObservationBuilder()
    observation_store: InMemoryObservationStore = field(default_factory=InMemoryObservationStore)
    artifacts: ArtifactStore | None = None

    def capture(
        self,
        *,
        envelope: Any,
        state: Any,
        state_view: RuntimeStateSnapshot,
        events: RuntimeEventBuffer,
    ) -> PostActionObservation:
        capture = self.perception_session.capture(
            PerceptionCaptureRequest(
                envelope=envelope,
                sequence=state.observation_count + 1,
                active_subgoal="",
                failed_sources=_failed_sources(state_view),
            )
        )
        canonical, ref, commit = self.canonicalize(capture)
        artifact = self.write_observation(
            envelope.task_id,
            state.observation_count,
            capture,
        )
        refs = tuple(
            dict.fromkeys(
                (*((artifact.path,) if artifact else ()), *capture.observation.artifact_refs)
            )
        )
        events.artifact_index.extend(refs)
        events.add(
            "PostActionObservationCaptured",
            {
                "state": state.phase,
                "snapshot_id": capture.observation.snapshot_id,
                "page_revision": capture.observation.page_revision,
                "artifact_refs": list(refs),
            },
        )
        return PostActionObservation(capture, canonical, ref, (commit,))

    def repair_verification(
        self,
        *,
        action: Any,
        state: Any,
        events: RuntimeEventBuffer,
        capture: PerceptionCapture,
        report: VerificationReport,
    ) -> tuple[PostActionObservation, VerificationReport]:
        sources = tuple(
            dict.fromkeys(
                item.source
                for item in capture.source_observations
                if item.source
                in {
                    GroundingSource.DOM,
                    GroundingSource.ACCESSIBILITY,
                    GroundingSource.API,
                }
            )
        ) or (GroundingSource.DOM, GroundingSource.ACCESSIBILITY)
        request = ActivePerceptionRequest(
            entity_key=action.contract.affordance_id,
            property_key="verification",
            requested_sources=sources,
            reason=(
                "verifier is inconclusive and requires fresh independent "
                "structural evidence"
            ),
            max_observations=1,
        )
        events.add(
            "VerificationEvidenceRepairRequested",
            {
                "state": state.phase,
                "contract_id": action.contract.id,
                "verification_status": report.status.value,
            },
        )
        events.add(
            "ActivePerceptionPlanned",
            {
                "state": state.phase,
                "reason": request.reason,
                "requested_sources": [item.value for item in request.requested_sources],
            },
        )
        events.add(
            "ProbeStarted",
            {
                "state": state.phase,
                "entity_key": request.entity_key,
                "property_key": request.property_key,
            },
        )
        try:
            repaired = self.perception_session.capture_targeted((request,))
        except Exception:
            events.add("ProbeCompleted", {"state": state.phase, "success": False})
            canonical, ref, _commit = self.canonicalize(capture)
            return PostActionObservation(capture, canonical, ref, ()), report
        if repaired.observation.snapshot_id == capture.observation.snapshot_id:
            canonical, ref, _commit = self.canonicalize(capture)
            return PostActionObservation(capture, canonical, ref, ()), report
        canonical, ref, commit = self.canonicalize(repaired)
        now = time()
        state.latest_probe_receipt = ProbeReceipt(
            command_id=f"verification-probe:{action.contract.id}",
            started_at_s=now,
            completed_at_s=now,
            observation_epoch_id=repaired.observation.snapshot_id,
            source=request.requested_sources[0],
            success=True,
            artifact_refs=tuple(repaired.observation.artifact_refs),
        )
        state.active_perception_count += 1
        events.add(
            "TargetedPerceptionCaptured",
            {"state": state.phase, "snapshot_id": repaired.observation.snapshot_id},
        )
        events.add("ProbeCompleted", {"state": state.phase, "success": True})
        repaired_report = self.execution_loop.verify(
            action.contract,
            action.receipt,
            repaired.observation,
            structural_verification_enabled=True,
            disabled_reason="",
        )
        events.add(
            "VerificationEvidenceReevaluated",
            {
                "state": state.phase,
                "contract_id": action.contract.id,
                "verification_status": repaired_report.status.value,
                "snapshot_id": repaired.observation.snapshot_id,
            },
        )
        return PostActionObservation(repaired, canonical, ref, (commit,)), repaired_report

    def canonicalize(
        self,
        capture: PerceptionCapture,
    ) -> tuple[UnifiedObservation, ObservationRef, ObservationCommit]:
        canonical = self.observation_builder.build(capture)
        ref = self.observation_store.put(canonical)
        return (
            canonical,
            ref,
            ObservationCommit(
                ref,
                canonical.environment_revision,
                canonical.page_revision,
            ),
        )

    def write_observation(
        self,
        run_id: str,
        sequence: int,
        capture: PerceptionCapture,
    ) -> ArtifactRef | None:
        if self.artifacts is None:
            return None
        return self.artifacts.write_observation(run_id, sequence, capture.observation)


def _failed_sources(view: RuntimeStateSnapshot) -> frozenset[GroundingSource]:
    result: set[GroundingSource] = set()
    for lineage in view.current_grounding_fallback.values():
        try:
            result.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            pass
    return frozenset(result)
