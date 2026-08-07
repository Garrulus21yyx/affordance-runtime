"""Pure ActionStage: bind, preflight, approve, route, execute, and return a receipt."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.active_perception import PerceptionResolution, ProbeReceipt
from affordance_runtime.active_perception_flow import ActivePerceptionFlow
from affordance_runtime.approval_contracts import ApprovalProvider, present_approval
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.choice_contracts import ActionSelection
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    ProviderAck,
    RiskLevel,
    RuntimeErrorCode,
    TransportState,
)
from affordance_runtime.dispatch_lifecycle import (
    DispatchAdmissionRejected,
    DispatchCommitter,
    FinalDispatchAdmission,
    PreparedDispatch,
)
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.high_risk_effect_policy import policy_for_effect
from affordance_runtime.observation_store import (
    InMemoryObservationStore,
    ObservationCommit,
)
from affordance_runtime.perception_session import (
    PerceptionCapture,
    PerceptionCaptureRequest,
    PerceptionSession,
)
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import (
    semantic_progress_fingerprint,
    semantic_target_descriptor,
)
from affordance_runtime.safety import CapabilityGate
from affordance_runtime.simplified_runtime_contracts import (
    ExecutionAttempt,
)
from affordance_runtime.stage_protocol import (
    ArtifactIndexDelta,
    CounterDelta,
    LoopDirective,
    PerceptionDelta,
    PhaseDelta,
    PlanningDelta,
    ProgressDelta,
    ReceiptDelta,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
    UncertainEffectDelta,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer
from affordance_runtime.unified_observation import UnifiedObservation


@dataclass(frozen=True)
class ActionStageInput:
    envelope: RunRequest
    capture: PerceptionCapture
    observation: UnifiedObservation
    state_view: RuntimeStateSnapshot
    remaining_budgets: RemainingRecoveryBudgets
    skill_step_id: str = ""
    catalog: ActionChoiceCatalog | None = None
    selection: ActionSelection | None = None
    dispatch_committer: DispatchCommitter | None = None


@dataclass(frozen=True)
class ActionOutput:
    contract: ActionContract
    receipt: ExecutionReceipt
    execution_capture: PerceptionCapture
    action_signature: str
    execution_attempt: ExecutionAttempt

    @property
    def execution_snapshot(self) -> PerceptionCapture:
        return self.execution_capture


@dataclass(frozen=True)
class _PerceptionDelta:
    captures: tuple[PerceptionCapture, ...] = ()
    observation_commits: tuple[ObservationCommit, ...] = ()
    probe_receipts: tuple[ProbeReceipt, ...] = ()
    resolution: PerceptionResolution | None = None
    active_count_delta: int = 0


@dataclass(frozen=True)
class ActionStage:
    contract_builder: ActionTransactionMaterializer | None
    contract_execution_loop: ContractExecutionLoop
    perception_session: PerceptionSession
    observation_builder: CanonicalObservationBuilder = CanonicalObservationBuilder()
    observation_store: InMemoryObservationStore = field(default_factory=InMemoryObservationStore)
    active_perception_flow: ActivePerceptionFlow | None = None
    approval_provider: ApprovalProvider | None = None
    artifacts: ArtifactStore | None = None
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None
    runtime_gate: CapabilityGate = field(default_factory=CapabilityGate)
    preflight_enabled: bool = True
    capability_gate_enabled: bool = True
    recovery_enabled: bool = True
    approval_required_risks: frozenset[RiskLevel] = frozenset()
    approval_required_capabilities: frozenset[str] = frozenset()

    def run(self, stage_input: ActionStageInput) -> StageResult[ActionOutput]:
        bound = self._bind(stage_input)
        if isinstance(bound, StageResult):
            return bound
        contract, signature, events, proposal_payload = bound

        checked = self._preflight(stage_input, contract, events)
        if isinstance(checked, StageResult):
            return checked
        contract, execution_snapshot, events, artifact_refs, perception_delta, gate = checked
        approval_decision_id = ""

        attempt = self.contract_execution_loop.build_execution_attempt(
            contract,
            execution_snapshot.observation,
            issued_at_state_version=stage_input.state_view.version,
            active_step_id=stage_input.skill_step_id,
        )
        events.append(
            _event(
                "ExecutionAttemptIssued",
                RuntimeStep.ACTING,
                contract_id=contract.id,
                contract_hash=contract.contract_hash,
                attempt_id=attempt.attempt_id,
                transaction_identity=attempt.transaction_identity,
                idempotency_identity=attempt.idempotency_identity,
            )
        )
        if stage_input.dispatch_committer is None:
            return self._failure(
                stage_input,
                FailurePhase.PREFLIGHT,
                FailureClass.AUTHORITY,
                RuntimeErrorCode.CAPABILITY_DENIED,
                "canonical dispatch requires the RuntimeCommitter linearization boundary",
                contract=contract,
                events=tuple(events),
                recoverable=False,
            )
        try:
            admission = FinalDispatchAdmission.issue(
                contract=contract,
                observation=execution_snapshot.observation,
                expected_state_version=stage_input.state_view.version,
                gate=gate,
                policy_check=lambda: self.contract_execution_loop.task_policy.check(
                    contract,
                    stage_input.envelope.constraints,
                    stage_input.envelope.task_spec,
                    stage_input.observation,
                ),
                surface_check=lambda: self.perception_session.surface_is_current(
                    contract.live_surface_binding
                ) if contract.live_surface_binding is not None else False,
                coordinate_check=lambda binding: self.perception_session.coordinate_is_current(
                    binding,
                    require_live_probe=contract.backend == "visual",
                ),
                fence_lock=self.perception_session.surface_lock,
            )
            prepared = PreparedDispatch(
                contract=contract,
                observation=execution_snapshot.observation,
                attempt=attempt,
                admission=admission,
                expected_state_version=admission.expected_state_version,
                selection_id=stage_input.selection.choice_id if stage_input.selection is not None else "",
                catalog_id=stage_input.catalog.catalog_id if stage_input.catalog is not None else "",
                action_signature=attempt.transaction_identity,
                approval_decision_id=next(
                    (
                        str(event.payload.get("token_id", ""))
                        for event in events
                        if event.kind == "HumanApprovalGranted"
                    ),
                    approval_decision_id,
                ),
                preflight_passed=True,
                artifact_refs=tuple(artifact_refs),
                semantic_target=next(
                    (
                        dict(event.payload["semantic_action"]["target"])
                        for event in events
                        if event.kind == "ContractBuilt"
                        and isinstance(event.payload.get("semantic_action"), Mapping)
                    ),
                    {},
                ),
                semantic_destination=next(
                    (
                        dict(event.payload["semantic_action"].get("destination") or {})
                        for event in events
                        if event.kind == "ContractBuilt"
                        and isinstance(event.payload.get("semantic_action"), Mapping)
                    ),
                    {},
                ),
            )
            permit = stage_input.dispatch_committer(prepared)
            events = []
        except DispatchAdmissionRejected as exc:
            drift = exc.code in _DRIFT_ERRORS
            events.append(
                _event(
                    "EnvironmentDriftDetected" if drift else "PreflightBlocked",
                    stage_input.state_view.phase,
                    error_code=exc.code.value,
                )
            )
            return self._failure(
                stage_input,
                FailurePhase.PREFLIGHT,
                FailureClass.STALE_STATE if drift else FailureClass.AUTHORITY,
                exc.code,
                f"final dispatch admission rejected: {exc.code.value}",
                contract=contract,
                events=tuple(events),
                recoverable=self.recovery_enabled if drift else False,
            )
        receipt = self.contract_execution_loop.dispatch(permit)
        if receipt.backend != contract.backend:
            # A provider receipt from a different backend is not evidence of a
            # successful execution of this contract. Preserve the conservative
            # transport truth and route it through the uncertain-effect path.
            receipt = replace(
                receipt,
                backend=contract.backend,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message="executor receipt backend does not match the admitted contract",
                transport_state=TransportState.SENT_UNKNOWN,
                provider_ack=ProviderAck.UNKNOWN,
            )

        receipt_ref = self._write_receipt(stage_input, receipt)
        if receipt_ref:
            artifact_refs.append(receipt_ref)
        uncertain_updates = (
            _uncertain_effect_updates(stage_input, contract, attempt)
            if not receipt.success
            and receipt.transport_state == TransportState.SENT_UNKNOWN
            and contract.effectful
            else None
        )
        if uncertain_updates is not None:
            events.append(
                _event(
                    "UncertainExternalEffectRecorded",
                    RuntimeStep.ACTING,
                    attempt_id=attempt.attempt_id,
                    contract_hash=attempt.contract_hash,
                )
            )
        transition = RuntimeTransition(
            # Final admission commits the attempt and advances the aggregate
            # version exactly once before the provider call.
            # The current phase bridge performs PLANNING -> PREFLIGHT -> ACTING
            # plus the admission commit's version increment.
            expected_state_version=attempt.issued_at_state_version + 3,
            deltas=(
                PhaseDelta(RuntimeStep.VERIFYING if receipt.success else RuntimeStep.ACTING),
                PerceptionDelta(
                    commits=perception_delta.observation_commits,
                    probe_receipts=perception_delta.probe_receipts,
                    perception_resolution=perception_delta.resolution,
                    active_perception_count_delta=perception_delta.active_count_delta,
                ),
                PlanningDelta(
                    planner_proposal=(
                        {
                            "selection_id": stage_input.selection.choice_id,
                            "catalog_id": stage_input.catalog.catalog_id if stage_input.catalog is not None else "",
                        }
                        if stage_input.selection is not None
                        else None
                    )
                ),
                ReceiptDelta(attempt.attempt_id, contract.id, contract.contract_hash, receipt),
                CounterDelta(subgoal_action_count=1),
                ArtifactIndexDelta(tuple(artifact_refs)),
                *( (UncertainEffectDelta(attempt),) if uncertain_updates is not None else () ),
            ),
        )
        if not receipt.success:
            execution_uncertain = receipt.transport_state == TransportState.SENT_UNKNOWN and contract.effectful
            failure = self._failure(
                stage_input,
                FailurePhase.EXECUTION_UNCERTAIN
                if execution_uncertain
                else FailurePhase.EXECUTION_NOT_DISPATCHED,
                FailureClass.EXECUTION,
                receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
                receipt.message or "action execution failed",
                contract=contract,
                receipt=receipt,
                events=tuple(events),
                transition=transition,
                recoverable=self.recovery_enabled,
                effect_status=(EffectStatus.MAY_HAVE_OCCURRED if execution_uncertain else EffectStatus.NOT_DISPATCHED),
            )
            return replace(
                failure,
                output=ActionOutput(contract, receipt, execution_snapshot, signature, attempt),
            )
        return StageResult(
            output=ActionOutput(contract, receipt, execution_snapshot, signature, attempt),
            transition=transition,
            events=tuple(events),
        )

    def _bind(
        self, stage_input: ActionStageInput
    ) -> tuple[ActionContract, str, list[RuntimeEvent], dict[str, Any]] | StageResult[ActionOutput]:
        task_spec = stage_input.envelope.task_spec
        if self.contract_builder is None or task_spec is None:
            return self._failure(
                stage_input,
                FailurePhase.GROUNDING_BINDING,
                FailureClass.GROUNDING,
                RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                "semantic selection requires TaskSpec and the canonical transaction materializer",
                recoverable=False,
            )
        if stage_input.catalog is None or stage_input.selection is None:
            return self._failure(
                stage_input,
                FailurePhase.GROUNDING_BINDING,
                FailureClass.GROUNDING,
                RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                "action stage requires a canonical selection",
                recoverable=False,
            )
        choice = stage_input.catalog.get(stage_input.selection.choice_id)
        if choice is None:
            return self._failure(
                stage_input,
                FailurePhase.GROUNDING_BINDING,
                FailureClass.GROUNDING,
                RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                "selected choice is not in the current Catalog",
                recoverable=True,
            )
        try:
            contract = self.contract_builder.build(
                stage_input.selection,
                stage_input.catalog,
                task_spec,
                cast(Any, stage_input.state_view),
                stage_input.capture,
                stage_input.observation,
            )
        except ValueError as exc:
            return self._failure(
                stage_input,
                FailurePhase.GROUNDING_BINDING,
                FailureClass.GROUNDING,
                RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                str(exc),
                recoverable=True,
            )
        proposal_payload = {
            "selection_id": stage_input.selection.choice_id,
            "catalog_id": stage_input.catalog.catalog_id,
            "catalog_digest": stage_input.catalog.catalog_digest,
            "observation_ref": stage_input.selection.observation_ref,
        }
        signature = json.dumps(
            {
                "action_kind": choice.action_kind.value,
                "target": choice.target_id,
                "destination": choice.destination_id,
                "parameters": dict(choice.parameters),
                "subgoal": stage_input.selection.active_step_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        progress_target = None
        if stage_input.skill_step_id and self.task_skill_runtime is not None:
            requirement_error = self.task_skill_runtime.contract_requirement_error(
                cast(Any, stage_input.state_view),
                contract,
                approval_required_risks=self.approval_required_risks,
                approval_required_capabilities=self.approval_required_capabilities,
            )
            if requirement_error:
                self.task_skill_runtime.fallthrough(cast(Any, stage_input.state_view), requirement_error)
                return StageResult(
                    transition=RuntimeTransition(
                        expected_state_version=stage_input.state_view.version,
                        deltas=(PhaseDelta(RuntimeStep.OBSERVING), CounterDelta(replan_count=1)),
                    ),
                    events=(
                        _event(
                            "TaskSkillFellThrough",
                            stage_input.state_view.phase,
                            step_id=stage_input.skill_step_id,
                            reason=requirement_error,
                            fallback="system_2",
                        ),
                    ),
                    directive=LoopDirective.REPEAT_OBSERVATION,
                )

        progress_block = stage_input.state_view.check_progress_guard(signature)
        if progress_block is not None:
            if progress_block == RuntimeErrorCode.EFFECT_ALREADY_SATISFIED.value and progress_target is not None:
                return self._failure(
                    stage_input,
                    FailurePhase.PROGRESS,
                    FailureClass.MISSING_EVIDENCE,
                    RuntimeErrorCode.PROGRESS_CREDIT_INVARIANT,
                    "verified effect cannot be credited to the unchanged active step",
                    contract=contract,
                    events=(
                        _event(
                            "PlannerProgressBlocked",
                            stage_input.state_view.phase,
                            error_code=RuntimeErrorCode.PROGRESS_CREDIT_INVARIANT.value,
                            action_signature=signature,
                            environment_revision=stage_input.state_view.current_revision(),
                        ),
                    ),
                    effect_status=EffectStatus.CONFIRMED_OCCURRED,
                )
            return StageResult(
                transition=RuntimeTransition(
                    expected_state_version=stage_input.state_view.version,
                    deltas=(
                        PhaseDelta(RuntimeStep.OBSERVING),
                        CounterDelta(replan_count=1),
                        ProgressDelta(progress_guard=(progress_block, signature)),
                    ),
                ),
                events=(
                    _event(
                        "PlannerProgressBlocked",
                        stage_input.state_view.phase,
                        error_code=progress_block,
                        action_signature=signature,
                        environment_revision=stage_input.state_view.current_revision(),
                    ),
                ),
                directive=LoopDirective.REPEAT_OBSERVATION,
            )

        events = [_contract_built_event(stage_input, contract), *_route_events(stage_input, contract)]
        return contract, signature, events, proposal_payload

    def _preflight(
        self,
        stage_input: ActionStageInput,
        contract: ActionContract,
        events: list[RuntimeEvent],
    ) -> (
        tuple[
            ActionContract,
            PerceptionCapture,
            list[RuntimeEvent],
            list[str],
            _PerceptionDelta,
            CapabilityGate,
        ]
        | StageResult[ActionOutput]
    ):
        checked = self.contract_execution_loop.initial_check(
            contract,
            stage_input.envelope,
            stage_input.capture.observation,
            capability_gate_enabled=self.capability_gate_enabled,
            preflight_enabled=self.preflight_enabled,
            canonical_observation=stage_input.observation,
        )
        gate = checked.gate
        error = checked.error
        current = stage_input.capture
        admission_observation = stage_input.observation
        artifact_refs: list[str] = []
        perception_delta = _PerceptionDelta()
        if error is None:
            surface = contract.live_surface_binding
            coordinate = contract.coordinate_binding
            if (
                surface is None
                or coordinate is None
                or not surface.lease.current(surface)
                or not coordinate.current_for(surface)
                or contract.snapshot_id != stage_input.observation.epoch_id
                or contract.route_binding is None
                or contract.route_binding.observation_digest != stage_input.observation.digest
            ):
                error = RuntimeErrorCode.STALE_OBSERVATION
            events.append(
                _event(
                    "CommittedObservationPreflightChecked",
                    stage_input.state_view.phase,
                    snapshot_id=stage_input.observation.epoch_id,
                    contract_hash=contract.contract_hash,
                )
            )

        if error == RuntimeErrorCode.APPROVAL_REQUIRED:
            committed_ref = getattr(stage_input.state_view, "current_observation_ref", None)
            if (
                committed_ref is None
                or committed_ref.epoch_id != contract.snapshot_id
                or committed_ref.digest != admission_observation.digest
            ):
                return self._failure(
                    stage_input,
                    FailurePhase.PREFLIGHT,
                    FailureClass.AUTHORITY,
                    RuntimeErrorCode.APPROVAL_INVALID,
                    "approval requires an exact sealed contract over a committed fresh observation",
                    contract=contract,
                    events=tuple(events),
                    transition=RuntimeTransition(
                        expected_state_version=stage_input.state_view.version,
                        deltas=(
                            PerceptionDelta(
                                commits=perception_delta.observation_commits,
                                probe_receipts=perception_delta.probe_receipts,
                                perception_resolution=perception_delta.resolution,
                                active_perception_count_delta=perception_delta.active_count_delta,
                            ),
                            ArtifactIndexDelta(tuple(artifact_refs)),
                        ),
                    ),
                    recoverable=self.recovery_enabled,
                )
            approval_presentation = present_approval(contract)
            events.append(
                _event(
                    "HumanApprovalRequested",
                    RuntimeStep.WAITING_APPROVAL,
                    contract_hash=contract.contract_hash,
                    snapshot_id=contract.snapshot_id,
                    page_revision=contract.page_revision,
                    environment_revision=contract.environment_revision,
                    required_capabilities=tuple(contract.required_capabilities),
                    approval_presentation=asdict(approval_presentation),
                )
            )
            token = self.approval_provider.approve(contract) if self.approval_provider else None
            if token is None:
                return StageResult(
                    transition=RuntimeTransition(
                        expected_state_version=stage_input.state_view.version,
                        deltas=(PhaseDelta(RuntimeStep.WAITING_APPROVAL),),
                    ),
                    events=tuple(events),
                    terminal=TerminalResult("", "approval_required", RuntimeStep.WAITING_APPROVAL, error),
                    directive=LoopDirective.WAIT_USER,
                )
            # The run-scoped gate references the single registry owned by the
            # root gate; do not maintain a second shadow token store.
            gate.approval_tokens[token.token_id] = token
            events.append(
                _event(
                    "HumanApprovalGranted",
                    stage_input.state_view.phase,
                    token_id=token.token_id,
                    approver=token.approver,
                    capability=token.capability,
                    expires_at_s=token.expires_at_s,
                    snapshot_id=token.snapshot_id,
                    page_revision=token.page_revision,
                    environment_revision=token.environment_revision,
                )
            )
            events.append(
                _event(
                    "ApprovalStateRevalidated",
                    stage_input.state_view.phase,
                    snapshot_id=current.observation.snapshot_id,
                    page_revision=current.observation.page_revision,
                    environment_revision=current.observation.environment_revision,
                )
            )
            error = self.contract_execution_loop.revalidate(
                contract,
                stage_input.envelope,
                current.observation,
                gate,
                capability_gate_enabled=True,
                include_policy=True,
                canonical_observation=self.observation_builder.build(current),
            )

        if error is not None:
            events.append(
                _event(
                    "EnvironmentDriftDetected" if error in _DRIFT_ERRORS else "PreflightBlocked",
                    stage_input.state_view.phase,
                    error_code=error.value,
                )
            )
            return self._failure(
                stage_input,
                FailurePhase.PREFLIGHT,
                FailureClass.STALE_STATE
                if error in _DRIFT_ERRORS
                else FailureClass.AUTHORITY
                if error in {RuntimeErrorCode.CAPABILITY_DENIED, RuntimeErrorCode.UNSAFE_ACTION}
                else FailureClass.VALIDATION,
                error,
                f"preflight rejected contract: {error.value}",
                contract=contract,
                events=tuple(events),
                transition=RuntimeTransition(
                    expected_state_version=stage_input.state_view.version,
                    deltas=(
                        PerceptionDelta(
                            commits=perception_delta.observation_commits,
                            probe_receipts=perception_delta.probe_receipts,
                            perception_resolution=perception_delta.resolution,
                            active_perception_count_delta=perception_delta.active_count_delta,
                        ),
                        ArtifactIndexDelta(tuple(artifact_refs)),
                    ),
                ),
                recoverable=error in _DRIFT_ERRORS and self.recovery_enabled,
            )
        authorization_error = gate.check(contract) if self.capability_gate_enabled else None
        if authorization_error is not None:
            return self._failure(
                stage_input,
                FailurePhase.PREFLIGHT,
                FailureClass.AUTHORITY,
                authorization_error,
                f"contract authorization rejected: {authorization_error.value}",
                contract=contract,
                events=tuple(events),
                recoverable=False,
            )
        retry_error = _pending_retry_contract_error(stage_input.state_view, contract)
        if retry_error is not None:
            return self._failure(
                stage_input,
                FailurePhase.PREFLIGHT,
                FailureClass.AUTHORITY,
                retry_error,
                "retry contract did not retain validated idempotency and effect scope",
                contract=contract,
                events=tuple(events),
                recoverable=False,
            )
        events.append(_event("PreflightPassed", stage_input.state_view.phase))
        return contract, current, events, artifact_refs, perception_delta, gate

    def _failure(
        self,
        stage_input: ActionStageInput,
        phase: FailurePhase,
        failure_class: FailureClass,
        error_code: RuntimeErrorCode,
        message: str,
        *,
        contract: ActionContract | None = None,
        receipt: ExecutionReceipt | None = None,
        events: tuple[RuntimeEvent, ...] = (),
        transition: RuntimeTransition | None = None,
        recoverable: bool = True,
        effect_status: EffectStatus | None = None,
    ) -> StageResult[ActionOutput]:
        view = stage_input.state_view
        plan = view.task_plan
        failure = make_failure_envelope(
            run_id=stage_input.envelope.task_id,
            phase=phase,
            failure_class=failure_class,
            error_code=error_code,
            message=message,
            state_version=view.version,
            task_revision=plan.task_revision
            if plan is not None
            else stage_input.envelope.task_spec.revision
            if stage_input.envelope.task_spec is not None
            else 1,
            plan_version=plan.plan_version if plan is not None else 0,
            active_step_id=view.task_progress.active_step_id if view.task_progress is not None else "",
            observation_epoch_id=stage_input.capture.observation.snapshot_id,
            snapshot_id=stage_input.capture.observation.snapshot_id,
            proposal_id=(stage_input.selection.choice_id if stage_input.selection is not None else ""),
            proposal_rejection=None,
            contract=contract,
            expected_effect="; ".join(
                (
                    cast(Any, stage_input.catalog.get(stage_input.selection.choice_id)).effect_refs
                    if stage_input.catalog is not None
                    and stage_input.selection is not None
                    and stage_input.catalog.get(stage_input.selection.choice_id) is not None
                    else ()
                )
            ),
            receipt=receipt,
            receipt_ref=receipt.contract_id if receipt is not None else "",
            effect_status=effect_status
            or (
                EffectStatus.CONFIRMED_OCCURRED
                if receipt is not None and receipt.success
                else EffectStatus.MAY_HAVE_OCCURRED
                if receipt is not None and receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT
                else EffectStatus.NOT_DISPATCHED
            ),
            remaining_budgets=stage_input.remaining_budgets,
            recoverable=recoverable,
            progress_fingerprint=semantic_progress_fingerprint(cast(Any, view)),
        )
        return StageResult(
            transition=transition,
            events=events
            + (
                _event(
                    "PlannerProposalRejected" if phase == FailurePhase.GROUNDING_BINDING else "FailureDetected",
                    view.phase,
                    error_code=error_code.value,
                    rejection_code="",
                    rejection_reason_code="",
                    reason=message,
                ),
            ),
            failure=failure,
        )

    def _write_observation(
        self,
        stage_input: ActionStageInput,
        snapshot: PerceptionCapture,
        *,
        sequence_offset: int = 0,
    ) -> str:
        if self.artifacts is None:
            return ""
        ref = self.artifacts.write_observation(
            stage_input.envelope.task_id,
            stage_input.state_view.observation_count + 1 + sequence_offset,
            snapshot.observation,
        )
        return ref.path

    def _write_receipt(self, stage_input: ActionStageInput, receipt: ExecutionReceipt) -> str:
        if self.artifacts is None:
            return ""
        download_path = receipt.evidence.get("path")
        if isinstance(download_path, str) and download_path:
            path = self.artifacts.run_dir(stage_input.envelope.task_id) / "downloads" / Path(download_path).name
            if path.exists():
                self.artifacts.register_file(stage_input.envelope.task_id, path, "application/octet-stream")
        return self.artifacts.write_receipt(
            stage_input.envelope.task_id,
            stage_input.state_view.step_count + 1,
            receipt,
        ).path


_DRIFT_ERRORS = frozenset(
    {
        RuntimeErrorCode.STALE_OBSERVATION,
        RuntimeErrorCode.STALE_PAGE_REVISION,
        RuntimeErrorCode.SNAPSHOT_MISMATCH,
        RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
        RuntimeErrorCode.LEASE_EXPIRED,
    }
)


def _capture_request(stage_input: ActionStageInput, *, sequence_offset: int = 0) -> PerceptionCaptureRequest:
    failed_sources: set[GroundingSource] = set()
    for lineage in stage_input.state_view.current_grounding_fallback.values():
        try:
            failed_sources.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            continue
    return PerceptionCaptureRequest(
        envelope=stage_input.envelope,
        sequence=stage_input.state_view.observation_count + 1 + sequence_offset,
        active_subgoal=TaskPlanLifecycle.active_step_for_perception(cast(Any, stage_input.state_view)) or "",
        failed_sources=frozenset(failed_sources),
    )


def _pending_retry_contract_error(
    state_view: RuntimeStateSnapshot, contract: ActionContract
) -> RuntimeErrorCode | None:
    decision = state_view.current_recovery_decision
    if decision is None or decision.kind != RecoveryKind.RETRY_IDEMPOTENT:
        return None
    effect_status = (
        state_view.current_failure.effect_status
        if state_view.current_failure is not None
        else EffectStatus.NOT_DISPATCHED
    )
    if (
        not contract.idempotency_key
        or contract.idempotency_key != decision.idempotency_key
        or effect_status not in {EffectStatus.NOT_DISPATCHED, EffectStatus.CONFIRMED_NOT_OCCURRED}
    ):
        return RuntimeErrorCode.UNSAFE_ACTION
    return None


def _uncertain_effect_updates(
    stage_input: ActionStageInput,
    contract: ActionContract,
    attempt: ExecutionAttempt,
) -> bool | None:
    signature = contract.runtime_effect_signature
    if not contract.effectful or signature is None or signature.externality is None:
        return None
    if signature.externality.value in {"local", "same_origin"}:
        return None
    existing = tuple(stage_input.state_view.uncertain_external_effects)
    if any(item.attempt.attempt_id == attempt.attempt_id for item in existing):
        return None
    return True


def _fresh_route_candidate(
    observation: UnifiedObservation,
    target_id: str,
    action: str,
    previous: Any | None,
):
    candidates = tuple(
        item
        for item in observation.bindings
        if item.semantic_target_id == target_id
        and action in item.supported_actions
        and (previous is None or item.compatible_executor == previous.compatible_executor)
    )
    if previous is not None:
        same_source = tuple(item for item in candidates if item.source == previous.source)
        if same_source:
            candidates = same_source
    return min(candidates, key=lambda item: item.candidate_id, default=None)


def _contract_built_event(stage_input: ActionStageInput, contract: ActionContract) -> RuntimeEvent:
    choice = (
        stage_input.catalog.get(stage_input.selection.choice_id)
        if stage_input.catalog is not None and stage_input.selection is not None
        else None
    )
    if choice is None:
        raise RuntimeError("contract event requires a canonical choice")
    resolved_choice = cast(Any, choice)
    action_kind = resolved_choice.action_kind.value
    target_id = resolved_choice.target_id
    destination_id = resolved_choice.destination_id
    parameters = dict(resolved_choice.parameters)
    return _event(
        "ContractBuilt",
        RuntimeStep.PREFLIGHT,
        contract_id=contract.id,
        contract_hash=contract.contract_hash,
        schema_version=contract.schema_version,
        snapshot_id=contract.snapshot_id,
        page_revision=contract.page_revision,
        target_fingerprint=contract.target_fingerprint,
        backend=contract.backend,
        choice_id=stage_input.selection.choice_id if stage_input.selection is not None else "",
        catalog_id=stage_input.catalog.catalog_id if stage_input.catalog is not None else "",
        semantic_action={
            "action_kind": action_kind,
            "target": semantic_target_descriptor(stage_input.observation, target_id),
            "destination": semantic_target_descriptor(stage_input.observation, destination_id),
            "parameters": parameters,
            "expected_effects": [asdict(item) for item in contract.expected_effects],
            "verifier_plan": [asdict(item) for item in contract.verifier_plan],
            "required_capabilities": list(contract.required_capabilities),
            "risk": contract.risk.value,
        },
    )


def _route_events(stage_input: ActionStageInput, contract: ActionContract) -> list[RuntimeEvent]:
    candidate = contract.grounding_candidate
    if candidate is None:
        return []
    route_plan = contract.route_plan
    return [
        _event(
            "RouteSelected",
            RuntimeStep.PREFLIGHT,
            semantic_target_id=candidate.semantic_target_id,
            candidate_id=candidate.candidate_id,
            source=candidate.source.value,
            executor=candidate.compatible_executor,
            observation_epoch_id=candidate.observation_epoch_id,
            page_revision=candidate.page_revision,
            fingerprint_key=candidate.fingerprint_key or candidate.candidate_id,
            evidence_refs=list(candidate.evidence_refs),
            decision_reason=route_plan.decision_reason if route_plan is not None else "",
            viable_alternative_ids=(
                [item.candidate_id for item in route_plan.viable_alternatives] if route_plan is not None else []
            ),
            hard_gates=(
                [
                    {
                        "candidate_id": item.candidate_id,
                        "passed": item.passed,
                        "reasons": list(item.reasons),
                    }
                    for item in route_plan.hard_gate_results
                ]
                if route_plan is not None
                else []
            ),
            scores=(
                [
                    {
                        "candidate_id": item.candidate_id,
                        "score": item.score,
                        "confidence_component": item.confidence_component,
                        "latency_component": item.latency_component,
                        "cost_component": item.cost_component,
                        "verification_component": item.verification_component,
                    }
                    for item in route_plan.scores
                ]
                if route_plan is not None
                else []
            ),
            contract_id=contract.id,
            contract_hash=contract.contract_hash,
        )
    ]


def _policy_preflight_required(contract: ActionContract) -> bool:
    signature = contract.runtime_effect_signature
    if signature is None:
        return False
    policy = policy_for_effect(signature.effect_class, signature.operation_ref)
    return bool(policy and policy.preflight_required)


def _event(kind: str, state: RuntimeStep | str, **payload: object) -> RuntimeEvent:
    return RuntimeEvent(
        kind,
        {"state": state.value if isinstance(state, RuntimeStep) else state, **payload},
    )
