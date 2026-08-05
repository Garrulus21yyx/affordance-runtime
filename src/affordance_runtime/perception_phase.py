"""Pure observation and active-perception stage."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.active_perception import (
    EvidenceGap,
    PerceptionResolution,
    PerceptionResolutionStatus,
    ProbePlan,
    ProbeReceipt,
)
from affordance_runtime.active_perception_flow import (
    ActivePerceptionFlow,
    ActivePerceptionFlowContext,
)
from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.immutable import to_json_compatible
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
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.stage_protocol import RuntimeEvent, RuntimeTransition, StageResult
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import SubgoalSpec
from affordance_runtime.unified_observation import UnifiedObservation


@dataclass(frozen=True)
class PerceptionStateView:
    phase: RuntimeStep
    state_version: int
    observation_count: int
    active_perception_count: int
    task_revision: int
    plan_version: int
    active_subgoal_id: str
    remaining_budgets: RemainingRecoveryBudgets
    active_subgoal: SubgoalSpec | str = ""
    attempted_probe_fingerprints: frozenset[str] = frozenset()
    failed_sources: frozenset[GroundingSource] = frozenset()
    effectful_action: bool = False
    has_receipts: bool = False
    max_active_perception_observations: int = 0
    max_observations: int = 0
    progress_fingerprint: str = ""


@dataclass(frozen=True)
class PerceptionStageInput:
    envelope: RunRequest
    state_view: PerceptionStateView
    initial_snapshot: BrowserSnapshot | PerceptionCapture | None = None


@dataclass(frozen=True)
class ObservationOutput:
    capture: PerceptionCapture
    observation: UnifiedObservation
    observation_ref: ObservationRef
    captured_captures: tuple[PerceptionCapture, ...]
    captured_observation_refs: tuple[ObservationRef, ...]
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    active_probe_plan: ProbePlan | None = None
    probe_receipts: tuple[ProbeReceipt, ...] = ()
    perception_resolution: PerceptionResolution | None = None
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PerceptionStage:
    session: PerceptionSession
    active_perception_flow: ActivePerceptionFlow
    artifacts: ArtifactStore | None = None
    budget: object | None = None
    observation_builder: CanonicalObservationBuilder = CanonicalObservationBuilder()
    observation_store: InMemoryObservationStore = field(default_factory=InMemoryObservationStore)

    def run(self, stage_input: PerceptionStageInput) -> StageResult[ObservationOutput]:
        view = stage_input.state_view
        phase = (
            RuntimeStep.OBSERVING
            if view.phase in {RuntimeStep.CREATED, RuntimeStep.RECOVERING}
            else None
        )
        state_label = (phase or view.phase).value
        events: list[RuntimeEvent] = []
        captured: list[PerceptionCapture] = []
        canonical_observations: list[UnifiedObservation] = []
        observation_refs: list[ObservationRef] = []
        artifact_refs: list[str] = []
        sequence = view.observation_count

        if stage_input.initial_snapshot is None:
            try:
                snapshot = self.session.capture(
                    PerceptionCaptureRequest(
                        envelope=stage_input.envelope,
                        sequence=sequence + 1,
                        active_subgoal=view.active_subgoal,
                        failed_sources=view.failed_sources,
                    )
                )
            except Exception as exc:
                failure = make_failure_envelope(
                    run_id=stage_input.envelope.task_id,
                    phase=FailurePhase.OBSERVATION,
                    failure_class=FailureClass.INTERNAL,
                    error_code=RuntimeErrorCode.PRECONDITION_FAILED,
                    message=f"{type(exc).__name__}: {exc}"[:500],
                    state_version=view.state_version,
                    task_revision=view.task_revision,
                    plan_version=view.plan_version,
                    active_subgoal_id=view.active_subgoal_id,
                    expected_effect=stage_input.envelope.goal,
                    remaining_budgets=view.remaining_budgets,
                    recoverable=True,
                    progress_fingerprint=view.progress_fingerprint,
                )
                return StageResult(
                    transition=RuntimeTransition(phase=phase),
                    events=(
                        _event(
                            "ObservationFailed",
                            state_label,
                            error_code=RuntimeErrorCode.PRECONDITION_FAILED.value,
                            reason=failure.message,
                        ),
                    ),
                    failure=failure,
                )
            captured.append(snapshot)
            canonical, canonical_ref = self._canonicalize(snapshot)
            canonical_observations.append(canonical)
            observation_refs.append(canonical_ref)
            sequence += 1
            observation_ref = self._write_observation(
                stage_input.envelope.task_id,
                sequence,
                snapshot,
            )
            artifact_refs.extend(_snapshot_artifact_refs(snapshot, observation_ref))
            events.append(_observation_event(snapshot, observation_ref, state_label))
            events.extend(_source_arbitration_events(snapshot, state_label))
        else:
            snapshot = (
                stage_input.initial_snapshot
                if isinstance(stage_input.initial_snapshot, PerceptionCapture)
                else PerceptionCapture.from_browser_snapshot(stage_input.initial_snapshot)
            )
            canonical, canonical_ref = self._canonicalize(snapshot)
            canonical_observations.append(canonical)
            observation_refs.append(canonical_ref)

        (
            snapshot,
            targeted_snapshots,
            targeted_events,
            targeted_artifacts,
            gaps,
            probe_plan,
            receipts,
            resolution,
        ) = self._fulfill_targeted_perception(
            stage_input,
            snapshot,
            sequence=sequence,
            state_label=state_label,
        )
        captured.extend(targeted_snapshots)
        for targeted in targeted_snapshots:
            canonical, canonical_ref = self._canonicalize(targeted)
            canonical_observations.append(canonical)
            observation_refs.append(canonical_ref)
        events.extend(targeted_events)
        artifact_refs.extend(targeted_artifacts)
        effective_snapshot = captured[-1] if captured else snapshot
        output = ObservationOutput(
            capture=effective_snapshot,
            observation=canonical_observations[-1],
            observation_ref=observation_refs[-1],
            captured_captures=tuple(captured),
            captured_observation_refs=tuple(observation_refs),
            evidence_gaps=gaps,
            active_probe_plan=probe_plan,
            probe_receipts=receipts,
            perception_resolution=resolution,
            artifact_refs=tuple(dict.fromkeys(artifact_refs)),
        )
        transition = RuntimeTransition(
            phase=phase,
            perception_update=True,
            observation_commits=tuple(
                ObservationCommit(
                    ref,
                    canonical.environment_revision,
                    canonical.page_revision,
                )
                for canonical, ref in zip(canonical_observations, observation_refs, strict=True)
            ),
            evidence_gaps=gaps,
            active_probe_plan=probe_plan,
            probe_receipts=receipts,
            perception_resolution=resolution,
            active_perception_count_delta=len(receipts),
            artifact_refs=output.artifact_refs,
        )
        effectful_task = (
            stage_input.envelope.task_spec is not None
            and stage_input.envelope.task_spec.operation_class
            != OperationClass.READ_ONLY
        )
        if (
            resolution is not None
            and resolution.blocks_effectful_action
            and effectful_task
        ):
            failure = make_failure_envelope(
                run_id=stage_input.envelope.task_id,
                phase=FailurePhase.FUSION,
                failure_class=FailureClass.SOURCE_CONFLICT,
                error_code=RuntimeErrorCode.PRECONDITION_FAILED,
                message=resolution.reason,
                state_version=view.state_version + len(captured),
                task_revision=view.task_revision,
                plan_version=view.plan_version,
                active_subgoal_id=view.active_subgoal_id,
                observation_epoch_id=snapshot.observation.snapshot_id,
                snapshot_id=snapshot.observation.snapshot_id,
                expected_effect=stage_input.envelope.goal,
                remaining_budgets=view.remaining_budgets,
                recoverable=False,
                progress_fingerprint=view.progress_fingerprint,
            )
            events.append(
                _event(
                    (
                        "PerceptionBlockedEffectfulRepeat"
                        if view.has_receipts
                        else "PerceptionBlockedEffectfulAction"
                    ),
                    state_label,
                    resolution=resolution.model_dump(mode="json"),
                )
            )
            return StageResult(
                output=output,
                transition=transition,
                events=tuple(events),
                failure=failure,
            )
        return StageResult(
            output=output,
            transition=transition,
            events=tuple(events),
        )

    def _fulfill_targeted_perception(
        self,
        stage_input: PerceptionStageInput,
        snapshot: PerceptionCapture,
        *,
        sequence: int,
        state_label: str,
    ) -> tuple[
        PerceptionCapture,
        tuple[PerceptionCapture, ...],
        tuple[RuntimeEvent, ...],
        tuple[str, ...],
        tuple[EvidenceGap, ...],
        ProbePlan | None,
        tuple[ProbeReceipt, ...],
        PerceptionResolution | None,
    ]:
        view = stage_input.state_view
        events: list[RuntimeEvent] = []
        captured: list[PerceptionCapture] = []
        artifacts: list[str] = []
        receipts: list[ProbeReceipt] = []
        attempted = set(view.attempted_probe_fingerprints)
        resolution: PerceptionResolution | None = None
        active_plan: ProbePlan | None = None
        gaps: tuple[EvidenceGap, ...] = ()
        while True:
            remaining = min(
                view.max_active_perception_observations
                - view.active_perception_count
                - len(receipts),
                view.max_observations
                - view.observation_count
                - len(captured),
            )
            preparation = self.active_perception_flow.prepare(
                ActivePerceptionFlowContext(
                    snapshot=snapshot,
                    run_id=stage_input.envelope.task_id,
                    task_revision=view.task_revision,
                    plan_version=view.plan_version,
                    active_subgoal_id=view.active_subgoal_id,
                    state_version=view.state_version + len(captured),
                    remaining_observations=max(0, remaining),
                    attempted_probe_fingerprints=frozenset(attempted),
                    effectful_action=view.effectful_action,
                )
            )
            gaps = preparation.gaps
            if not gaps:
                break
            events.append(
                _event(
                    "EvidenceGapDetected",
                    state_label,
                    snapshot_id=snapshot.observation.snapshot_id,
                    gaps=[item.model_dump(mode="json") for item in gaps],
                )
            )
            decision = preparation.decision
            if decision is None:
                raise RuntimeError("active perception flow omitted a decision")
            resolution = decision.resolution
            if not preparation.targeted_capture_available:
                events.append(
                    _event(
                        "TargetedPerceptionUnavailable",
                        state_label,
                        reason="observation source has no capture_targeted port",
                    )
                )
                events.extend(_resolution_events(resolution, state_label))
                break
            if decision.plan is None:
                events.append(
                    _event(
                        "TargetedPerceptionBudgetExhausted",
                        state_label,
                        active_perception_count=view.active_perception_count + len(receipts),
                        max_active_perception_observations=view.max_active_perception_observations,
                        reason=resolution.reason if resolution is not None else "",
                    )
                )
                events.extend(_resolution_events(resolution, state_label))
                break
            active_plan = decision.plan
            if preparation.selected_probe_fingerprint:
                attempted.add(preparation.selected_probe_fingerprint)
            command = active_plan.commands[0]
            events.extend(
                (
                    _event(
                        "ActivePerceptionPlanned",
                        state_label,
                        plan=active_plan.model_dump(mode="json"),
                        remaining_budget=preparation.budget.model_dump(mode="json"),
                    ),
                    _event(
                        "ProbeStarted",
                        state_label,
                        command=command.model_dump(mode="json"),
                    ),
                )
            )
            probe_result = self.active_perception_flow.execute(preparation)
            receipts.append(probe_result.receipt)
            resolution = probe_result.resolution
            targeted = probe_result.targeted_snapshot
            if targeted is None:
                events.append(
                    _event(
                        "ProbeCompleted",
                        state_label,
                        receipt=probe_result.receipt.model_dump(mode="json"),
                    )
                )
                events.extend(_resolution_events(resolution, state_label))
                break
            captured.append(targeted)
            sequence += 1
            targeted_ref = self._write_observation(
                stage_input.envelope.task_id,
                sequence,
                targeted,
            )
            artifacts.extend(_snapshot_artifact_refs(targeted, targeted_ref))
            events.extend(
                (
                    _event(
                        "TargetedPerceptionCaptured",
                        state_label,
                        snapshot_id=targeted.observation.snapshot_id,
                        page_revision=targeted.observation.page_revision,
                        environment_revision=targeted.observation.environment_revision,
                        artifact_refs=_snapshot_artifact_refs(targeted, targeted_ref),
                        source_observations=to_json_compatible(targeted.source_observations),
                    ),
                    _event(
                        "ProbeCompleted",
                        state_label,
                        receipt=probe_result.receipt.model_dump(mode="json"),
                    ),
                )
            )
            events.extend(_source_arbitration_events(targeted, state_label))
            events.extend(_resolution_events(resolution, state_label))
            snapshot = targeted
        return (
            snapshot,
            tuple(captured),
            tuple(events),
            tuple(artifacts),
            gaps,
            active_plan,
            tuple(receipts),
            resolution,
        )

    def _write_observation(
        self,
        run_id: str,
        sequence: int,
        snapshot: PerceptionCapture,
    ) -> ArtifactRef | None:
        return (
            self.artifacts.write_observation(run_id, sequence, snapshot.observation)
            if self.artifacts is not None
            else None
        )

    def _canonicalize(
        self, capture: PerceptionCapture
    ) -> tuple[UnifiedObservation, ObservationRef]:
        observation = self.observation_builder.build(capture)
        return observation, self.observation_store.put(observation)


def _snapshot_artifact_refs(
    snapshot: PerceptionCapture,
    observation_ref: ArtifactRef | None,
) -> list[str]:
    refs = list(snapshot.observation.artifact_refs)
    return ([observation_ref.path] if observation_ref is not None else []) + refs


def _observation_event(
    snapshot: PerceptionCapture,
    observation_ref: ArtifactRef | None,
    state_label: str,
) -> RuntimeEvent:
    return _event(
        "ObservationCaptured",
        state_label,
        snapshot_id=snapshot.observation.snapshot_id,
        page_revision=snapshot.observation.page_revision,
        environment_revision=snapshot.observation.environment_revision,
        url=snapshot.observation.url,
        artifact_refs=_snapshot_artifact_refs(snapshot, observation_ref),
        perception_requirements=snapshot.observation.metadata.get("perception_requirements"),
        source_observations=to_json_compatible(snapshot.source_observations),
    )


def _source_arbitration_events(
    snapshot: PerceptionCapture,
    state_label: str,
) -> tuple[RuntimeEvent, ...]:
    events: list[RuntimeEvent] = []
    if snapshot.source_assertions:
        events.append(
            _event(
                "SourceAssertionsCollected",
                state_label,
                assertions=_redacted_json(snapshot.source_assertions),
            )
        )
    if snapshot.assertion_decisions:
        events.append(
            _event(
                "SourceAssertionsArbitrated",
                state_label,
                decisions=_redacted_json(snapshot.assertion_decisions),
            )
        )
    if snapshot.active_perception_requests:
        events.append(
            _event(
                "TargetedPerceptionRequested",
                state_label,
                requests=to_json_compatible(snapshot.active_perception_requests),
            )
        )
    return tuple(events)


def _redacted_json(value: object) -> object:
    projected = to_json_compatible(value)
    if isinstance(projected, dict):
        return {
            key: _redacted_json(item)
            for key, item in projected.items()
            if key != "value"
        }
    if isinstance(projected, list):
        return [_redacted_json(item) for item in projected]
    return projected


def _event(kind: str, state: str, **payload: object) -> RuntimeEvent:
    return RuntimeEvent(kind, {"state": state, **payload})


def _resolution_events(
    resolution: PerceptionResolution | None,
    state_label: str,
) -> tuple[RuntimeEvent, ...]:
    if resolution is None:
        return ()
    return (
        _event(
            (
                "EvidenceGapResolved"
                if resolution.status == PerceptionResolutionStatus.RESOLVED
                else "EvidenceGapUnresolved"
            ),
            state_label,
            resolution=resolution.model_dump(mode="json"),
        ),
    )
