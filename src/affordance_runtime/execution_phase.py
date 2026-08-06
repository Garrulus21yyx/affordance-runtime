"""Pure ActionStage: bind, preflight, approve, route, execute, and return a receipt."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.action_contract_builder import ActionContractBuilder, ActionContractMaterializer
from affordance_runtime.active_perception import PerceptionResolution, ProbeReceipt
from affordance_runtime.active_perception_flow import (
    ActivePerceptionFlow,
    ActivePerceptionFlowContext,
)
from affordance_runtime.approval_contracts import ApprovalProvider, present_approval
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.choice_contracts import ActionSelection
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    RiskLevel,
    RuntimeErrorCode,
)
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    ProposalRejectionContext,
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
from affordance_runtime.planning import (
    PlannerActionKind,
    ProposalRejected,
    bind_active_step_verifiers,
    proposal_error_code,
    proposal_record,
    resolve_task_plan_progress_target,
)
from affordance_runtime.planning_contracts import PlannerProposalResponse
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import (
    action_progress_signature,
    semantic_progress_fingerprint,
    semantic_target_descriptor,
)
from affordance_runtime.safety import CapabilityGate
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.unified_observation import UnifiedObservation


@dataclass(frozen=True)
class ActionStageInput:
    envelope: RunRequest
    decision: PlannerProposalResponse | None
    capture: PerceptionCapture
    observation: UnifiedObservation
    state_view: RuntimeStateSnapshot
    remaining_budgets: RemainingRecoveryBudgets
    skill_step_id: str = ""
    catalog: ActionChoiceCatalog | None = None
    selection: ActionSelection | None = None


@dataclass(frozen=True)
class ActionOutput:
    contract: ActionContract
    receipt: ExecutionReceipt
    execution_capture: PerceptionCapture
    action_signature: str

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
    contract_builder: ActionContractBuilder | ActionContractMaterializer | None
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
        contract, execution_snapshot, events, artifact_refs, perception_delta = checked

        events.append(_event("ActionStarted", RuntimeStep.ACTING, contract_id=contract.id))
        try:
            receipt = self.contract_execution_loop.execute(
                contract, execution_snapshot.observation
            )
        except Exception as exc:
            return self._failure(
                stage_input,
                FailurePhase.EXECUTION_NOT_DISPATCHED,
                FailureClass.EXECUTION,
                RuntimeErrorCode.EXECUTION_FAILED,
                f"{type(exc).__name__}: {exc}"[:500],
                contract=contract,
                events=tuple(events),
            )

        receipt_ref = self._write_receipt(stage_input, receipt)
        if receipt_ref:
            artifact_refs.append(receipt_ref)
        transition = RuntimeTransition(
            phase=RuntimeStep.VERIFYING if receipt.success else RuntimeStep.ACTING,
            observation_commits=perception_delta.observation_commits,
            perception_update=perception_delta.resolution is not None,
            probe_receipts=perception_delta.probe_receipts,
            perception_resolution=perception_delta.resolution,
            active_perception_count_delta=perception_delta.active_count_delta,
            artifact_refs=tuple(artifact_refs),
            planner_proposal=proposal_payload,
            current_contract=contract,
            receipt=receipt,
            step_count_delta=1,
            subgoal_action_count_delta=1,
            effectful_action_count_delta=1 if contract.required_capabilities else 0,
        )
        if not receipt.success:
            failure = self._failure(
                stage_input,
                FailurePhase.EXECUTION_UNCERTAIN
                if receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT
                else FailurePhase.EXECUTION_NOT_DISPATCHED,
                FailureClass.EXECUTION,
                receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
                receipt.message or "action execution failed",
                contract=contract,
                receipt=receipt,
                events=tuple(events),
                transition=transition,
                recoverable=self.recovery_enabled,
            )
            return replace(
                failure,
                output=ActionOutput(contract, receipt, execution_snapshot, signature),
            )
        return StageResult(
            output=ActionOutput(contract, receipt, execution_snapshot, signature),
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
                "semantic proposal requires TaskSpec and ActionContractMaterializer",
                recoverable=False,
            )
        canonical = (
            stage_input.catalog is not None
            and stage_input.selection is not None
            and isinstance(self.contract_builder, ActionContractBuilder)
        )
        if canonical:
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
            except (ProposalRejected, ValueError) as exc:
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
            proposal = None
        else:
            if stage_input.decision is None:
                return self._failure(
                    stage_input,
                    FailurePhase.GROUNDING_BINDING,
                    FailureClass.GROUNDING,
                    RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                    "action stage requires a canonical selection",
                    recoverable=False,
                )
            proposal = stage_input.decision.proposal
            try:
                legacy_builder = (
                    self.contract_builder.materializer
                    if isinstance(self.contract_builder, ActionContractBuilder)
                    else self.contract_builder
                )
                contract = legacy_builder.build(
                    proposal,
                    task_spec,
                    cast(Any, stage_input.state_view),
                    stage_input.capture,
                    stage_input.observation,
                )
            except ProposalRejected as exc:
                return self._contract_rejected(stage_input, exc)
            if stage_input.decision.proposal_provenance is None:
                raise RuntimeError("validated proposal is missing provenance")
            proposal_payload = proposal_record(
                proposal, stage_input.decision.proposal_provenance
            )
            signature = action_progress_signature(proposal, contract)

        contract = self.contract_execution_loop.bind_contract(
            contract, stage_input.envelope, stage_input.capture.observation
        )
        progress_target = (
            None
            if proposal is None
            else resolve_task_plan_progress_target(
                proposal,
                cast(Any, stage_input.state_view),
                stage_input.capture,
            )
        )
        contract = replace(
            contract,
            verifier_plan=list(
                bind_active_step_verifiers(
                    tuple(contract.verifier_plan),
                    cast(Any, stage_input.state_view),
                    progress_target=progress_target,
                )
            ),
            contract_hash="",
        )
        if stage_input.skill_step_id and self.task_skill_runtime is not None:
            requirement_error = self.task_skill_runtime.contract_requirement_error(
                cast(Any, stage_input.state_view),
                contract,
                approval_required_risks=self.approval_required_risks,
                approval_required_capabilities=self.approval_required_capabilities,
            )
            if requirement_error:
                self.task_skill_runtime.fallthrough(
                    cast(Any, stage_input.state_view), requirement_error
                )
                return StageResult(
                    transition=RuntimeTransition(
                        phase=RuntimeStep.OBSERVING, replan_count_delta=1
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
            if (
                progress_block == RuntimeErrorCode.EFFECT_ALREADY_SATISFIED.value
                and progress_target is not None
            ):
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
                    phase=RuntimeStep.OBSERVING,
                    replan_count_delta=1,
                    progress_guard=(progress_block, signature),
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
    ) -> tuple[
        ActionContract,
        PerceptionCapture,
        list[RuntimeEvent],
        list[str],
        _PerceptionDelta,
    ] | StageResult[ActionOutput]:
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
        artifact_refs: list[str] = []
        perception_delta = _PerceptionDelta()
        policy_preflight_required = _policy_preflight_required(contract)
        if error is None and (self.preflight_enabled or policy_preflight_required):
            current = self.perception_session.capture(_capture_request(stage_input))
            ref = self._write_observation(stage_input, current)
            if ref:
                artifact_refs.append(ref)
            artifact_refs.extend(current.observation.artifact_refs)
            events.append(
                _event(
                    "PreflightObservationCaptured",
                    stage_input.state_view.phase,
                    snapshot_id=current.observation.snapshot_id,
                    page_revision=current.observation.page_revision,
                    artifact_refs=artifact_refs,
                )
            )
            current, perception_delta = self._probe_preflight(
                stage_input, current, events, artifact_refs
            )
            perception_error = (
                RuntimeErrorCode.PRECONDITION_FAILED
                if perception_delta.resolution is not None
                and perception_delta.resolution.blocks_effectful_action
                else None
            )
            error = self.contract_execution_loop.revalidate(
                contract,
                stage_input.envelope,
                current.observation,
                gate,
                capability_gate_enabled=False,
                include_policy=False,
                require_snapshot_identity=False,
                require_environment_revision=False,
            )
            error = perception_error or error
            source_contract = contract
            rebound = self._rebind_point_target(stage_input, contract, current, gate, error)
            if rebound is not None:
                contract, error = rebound
                events.append(
                    _event(
                        "ContractReboundAtPreflight",
                        stage_input.state_view.phase,
                        source_contract_id=source_contract.id,
                        source_contract_hash=source_contract.contract_hash,
                        contract_id=contract.id,
                        contract_hash=contract.contract_hash,
                        snapshot_id=contract.snapshot_id,
                    )
                )
        elif not self.preflight_enabled and not policy_preflight_required:
            events.append(_event("AblationApplied", stage_input.state_view.phase, disabled_layer="preflight"))

        if error == RuntimeErrorCode.APPROVAL_REQUIRED:
            approval_presentation = present_approval(contract)
            events.append(
                _event(
                    "HumanApprovalRequested",
                    RuntimeStep.WAITING_APPROVAL,
                    contract_hash=contract.contract_hash,
                    snapshot_id=contract.snapshot_id,
                    page_revision=contract.page_revision,
                    environment_revision=contract.environment_revision,
                    approval_presentation=asdict(approval_presentation),
                )
            )
            token = self.approval_provider.approve(contract) if self.approval_provider else None
            if token is None:
                return StageResult(
                    transition=RuntimeTransition(
                        phase=RuntimeStep.WAITING_APPROVAL, current_contract=contract
                    ),
                    events=tuple(events),
                    terminal=TerminalResult(
                        "", "approval_required", RuntimeStep.WAITING_APPROVAL, error
                    ),
                    directive=LoopDirective.WAIT_USER,
                )
            gate.approval_tokens[token.token_id] = token
            self.runtime_gate.approval_tokens[token.token_id] = token
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
                canonical_observation=stage_input.observation,
            )

        if error is not None:
            events.append(
                _event(
                    "EnvironmentDriftDetected"
                    if error in _DRIFT_ERRORS
                    else "PreflightBlocked",
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
                    observation_commits=perception_delta.observation_commits,
                    perception_update=perception_delta.resolution is not None,
                    probe_receipts=perception_delta.probe_receipts,
                    perception_resolution=perception_delta.resolution,
                    active_perception_count_delta=perception_delta.active_count_delta,
                    artifact_refs=tuple(artifact_refs),
                    current_contract=contract,
                ),
                recoverable=error in _DRIFT_ERRORS and self.recovery_enabled,
            )
        authorization_error = gate.authorize(contract) if self.capability_gate_enabled else None
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
        return contract, current, events, artifact_refs, perception_delta

    def _probe_preflight(
        self,
        stage_input: ActionStageInput,
        snapshot: PerceptionCapture,
        events: list[RuntimeEvent],
        artifact_refs: list[str],
    ) -> tuple[PerceptionCapture, _PerceptionDelta]:
        flow = self.active_perception_flow
        if flow is None:
            return snapshot, self._perception_delta((snapshot,))
        task_spec = stage_input.envelope.task_spec
        effectful = bool(
            task_spec is not None
            and task_spec.operation_class
            not in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
        )
        plan = stage_input.state_view.task_plan
        progress = stage_input.state_view.task_progress
        preparation = flow.prepare(
            ActivePerceptionFlowContext(
                snapshot=snapshot,
                run_id=stage_input.envelope.task_id,
                task_revision=(
                    plan.task_revision
                    if plan is not None
                    else task_spec.revision
                    if task_spec is not None
                    else 1
                ),
                plan_version=plan.plan_version if plan is not None else 0,
                active_step_id=(
                    progress.active_step_id if progress is not None else ""
                ),
                state_version=stage_input.state_view.version,
                remaining_observations=stage_input.remaining_budgets.observations,
                attempted_probe_fingerprints=frozenset(
                    stage_input.state_view.attempted_probe_fingerprints
                ),
                effectful_action=effectful,
            )
        )
        if not preparation.gaps or preparation.decision is None:
            return snapshot, self._perception_delta((snapshot,))
        events.append(
            _event(
                "EvidenceGapDetected",
                stage_input.state_view.phase,
                gap_ids=[item.gap_id for item in preparation.gaps],
            )
        )
        decision = preparation.decision
        if decision.plan is None:
            resolution = decision.resolution
            if resolution is not None:
                events.append(
                    _event(
                        "EvidenceGapUnresolved",
                        stage_input.state_view.phase,
                        reason=resolution.reason,
                    )
                )
            return snapshot, self._perception_delta((snapshot,), resolution=resolution)
        command = decision.plan.commands[0]
        events.extend(
            (
                _event(
                    "ActivePerceptionPlanned",
                    stage_input.state_view.phase,
                    plan_id=decision.plan.plan_id,
                ),
                _event(
                    "ProbeStarted",
                    stage_input.state_view.phase,
                    command_id=command.command_id,
                ),
            )
        )
        result = flow.execute(preparation)
        events.append(
            _event(
                "ProbeCompleted",
                stage_input.state_view.phase,
                command_id=result.receipt.command_id,
                success=result.receipt.success,
            )
        )
        current = result.targeted_snapshot or snapshot
        if result.targeted_snapshot is not None:
            ref = self._write_observation(stage_input, result.targeted_snapshot)
            if ref:
                artifact_refs.append(ref)
            artifact_refs.extend(result.targeted_snapshot.observation.artifact_refs)
        events.append(
            _event(
                "EvidenceGapResolved"
                if not result.resolution.blocks_effectful_action
                else "EvidenceGapUnresolved",
                stage_input.state_view.phase,
                reason=result.resolution.reason,
            )
        )
        snapshots = (
            (snapshot, result.targeted_snapshot)
            if result.targeted_snapshot is not None
            else (snapshot,)
        )
        return current, self._perception_delta(
            cast(tuple[PerceptionCapture, ...], snapshots),
            probe_receipts=(result.receipt,),
            resolution=result.resolution,
            active_count_delta=1,
        )

    def _perception_delta(
        self,
        captures: tuple[PerceptionCapture, ...],
        *,
        probe_receipts: tuple[ProbeReceipt, ...] = (),
        resolution: PerceptionResolution | None = None,
        active_count_delta: int = 0,
    ) -> _PerceptionDelta:
        commits: list[ObservationCommit] = []
        for capture in captures:
            canonical = self.observation_builder.build(capture)
            ref = self.observation_store.put(canonical)
            commits.append(
                ObservationCommit(
                    ref,
                    canonical.environment_revision,
                    canonical.page_revision,
                )
            )
        return _PerceptionDelta(
            captures,
            tuple(commits),
            probe_receipts,
            resolution,
            active_count_delta,
        )

    def _rebind_point_target(
        self,
        stage_input: ActionStageInput,
        contract: ActionContract,
        snapshot: PerceptionCapture,
        gate: CapabilityGate,
        error: RuntimeErrorCode | None,
    ) -> tuple[ActionContract, RuntimeErrorCode | None] | None:
        if stage_input.decision is None:
            # A new route requires a fresh Catalog/selection/contract epoch.
            return None
        proposal = stage_input.decision.proposal
        candidate = contract.grounding_candidate
        if (
            error != RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH
            or proposal.action_kind != PlannerActionKind.POINT_ACTIVATE
            or candidate is None
            or candidate.source not in {GroundingSource.SVG, GroundingSource.VISUAL}
            or self.contract_builder is None
            or stage_input.envelope.task_spec is None
        ):
            return None
        rebound_proposal = proposal.model_copy(
            update={
                "proposal_id": f"{proposal.proposal_id}-preflight-{stage_input.state_view.version}",
                "based_on_state_version": stage_input.state_view.version,
                "snapshot_id": snapshot.observation.snapshot_id,
            }
        )
        try:
            legacy_builder = (
                self.contract_builder.materializer
                if isinstance(self.contract_builder, ActionContractBuilder)
                else self.contract_builder
            )
            rebound = legacy_builder.build(
                rebound_proposal,
                stage_input.envelope.task_spec,
                cast(Any, stage_input.state_view),
                snapshot,
                self.observation_builder.build(snapshot),
            )
        except ProposalRejected:
            return None
        rebound = self.contract_execution_loop.bind_contract(
            rebound, stage_input.envelope, snapshot.observation
        )
        progress_target = resolve_task_plan_progress_target(
            rebound_proposal,
            cast(Any, stage_input.state_view),
            snapshot,
        )
        rebound = replace(
            rebound,
            verifier_plan=list(
                bind_active_step_verifiers(
                    tuple(rebound.verifier_plan),
                    cast(Any, stage_input.state_view),
                    progress_target=progress_target,
                )
            ),
            contract_hash="",
        )
        rebound_error = self.contract_execution_loop.revalidate(
            rebound,
            stage_input.envelope,
            snapshot.observation,
            gate,
            capability_gate_enabled=self.capability_gate_enabled,
            include_policy=True,
            canonical_observation=self.observation_builder.build(snapshot),
        )
        return (rebound, None) if rebound_error is None else None

    def _contract_rejected(
        self,
        stage_input: ActionStageInput,
        rejection: ProposalRejected,
    ) -> StageResult[ActionOutput]:
        if stage_input.decision is None:
            return self._failure(
                stage_input,
                FailurePhase.GROUNDING_BINDING,
                FailureClass.GROUNDING,
                RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                rejection.detail or rejection.code.value,
                recoverable=True,
            )
        error_code = proposal_error_code(rejection.code)
        message = rejection.detail or rejection.code.value
        if stage_input.skill_step_id and self.task_skill_runtime is not None:
            reason = f"TaskSkill contract binding rejected: {message}"
            self.task_skill_runtime.fallthrough(cast(Any, stage_input.state_view), reason)
            return StageResult(
                transition=RuntimeTransition(
                    phase=RuntimeStep.OBSERVING, replan_count_delta=1
                ),
                events=(
                    _event(
                        "TaskSkillFellThrough",
                        stage_input.state_view.phase,
                        step_id=stage_input.skill_step_id,
                        reason=reason,
                        fallback="system_2",
                    ),
                ),
                directive=LoopDirective.REPEAT_OBSERVATION,
            )
        return self._failure(
            stage_input,
            FailurePhase.GROUNDING_BINDING,
            FailureClass.GROUNDING,
            error_code,
            message,
            recoverable=True,
            proposal_rejection=ProposalRejectionContext(
                code=rejection.code.value,
                reason_code=rejection.reason_code,
                semantic_target_id=stage_input.decision.proposal.target_affordance_id,
            ),
        )

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
        proposal_rejection: ProposalRejectionContext | None = None,
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
            task_revision=plan.task_revision if plan is not None else stage_input.envelope.task_spec.revision if stage_input.envelope.task_spec is not None else 1,
            plan_version=plan.plan_version if plan is not None else 0,
            active_step_id=view.task_progress.active_step_id if view.task_progress is not None else "",
            observation_epoch_id=stage_input.capture.observation.snapshot_id,
            snapshot_id=stage_input.capture.observation.snapshot_id,
            proposal_id=(
                stage_input.decision.proposal.proposal_id
                if stage_input.decision is not None
                else stage_input.selection.choice_id
                if stage_input.selection is not None
                else ""
            ),
            proposal_rejection=proposal_rejection,
            contract=contract,
            expected_effect=(
                "; ".join(stage_input.decision.proposal.expected_effects)
                if stage_input.decision is not None
                else "; ".join(
                    (
                        stage_input.catalog.get(stage_input.selection.choice_id).effect_refs
                        if stage_input.catalog is not None
                        and stage_input.selection is not None
                        and stage_input.catalog.get(stage_input.selection.choice_id) is not None
                        else ()
                    )
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
                    "PlannerProposalRejected"
                    if phase == FailurePhase.GROUNDING_BINDING
                    else "FailureDetected",
                    view.phase,
                    error_code=error_code.value,
                    rejection_code=(
                        proposal_rejection.code if proposal_rejection is not None else ""
                    ),
                    rejection_reason_code=(
                        proposal_rejection.reason_code
                        if proposal_rejection is not None
                        else ""
                    ),
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

    def _write_receipt(
        self, stage_input: ActionStageInput, receipt: ExecutionReceipt
    ) -> str:
        if self.artifacts is None:
            return ""
        download_path = receipt.evidence.get("path")
        if isinstance(download_path, str) and download_path:
            path = self.artifacts.run_dir(stage_input.envelope.task_id) / "downloads" / Path(download_path).name
            if path.exists():
                self.artifacts.register_file(
                    stage_input.envelope.task_id, path, "application/octet-stream"
                )
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


def _capture_request(
    stage_input: ActionStageInput, *, sequence_offset: int = 0
) -> PerceptionCaptureRequest:
    failed_sources: set[GroundingSource] = set()
    for lineage in stage_input.state_view.current_grounding_fallback.values():
        try:
            failed_sources.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            continue
    return PerceptionCaptureRequest(
        envelope=stage_input.envelope,
        sequence=stage_input.state_view.observation_count + 1 + sequence_offset,
        active_subgoal=TaskPlanLifecycle.active_step_for_perception(
            cast(Any, stage_input.state_view)
        )
        or "",
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
        or effect_status
        not in {EffectStatus.NOT_DISPATCHED, EffectStatus.CONFIRMED_NOT_OCCURRED}
    ):
        return RuntimeErrorCode.UNSAFE_ACTION
    return None


def _contract_built_event(
    stage_input: ActionStageInput, contract: ActionContract
) -> RuntimeEvent:
    proposal = stage_input.decision.proposal if stage_input.decision is not None else None
    choice = (
        stage_input.catalog.get(stage_input.selection.choice_id)
        if stage_input.catalog is not None and stage_input.selection is not None
        else None
    )
    action_kind = proposal.action_kind.value if proposal is not None else choice.action_kind.value
    target_id = proposal.target_affordance_id if proposal is not None else choice.target_id
    destination_id = (
        proposal.destination_affordance_id if proposal is not None else choice.destination_id
    )
    parameters = dict(proposal.parameters if proposal is not None else choice.parameters)
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
        proposal_id=proposal.proposal_id if proposal is not None else "",
        choice_id=stage_input.selection.choice_id if stage_input.selection is not None else "",
        catalog_id=stage_input.catalog.catalog_id if stage_input.catalog is not None else "",
        supersedes_contract_id=contract.supersedes_contract_id,
        source_contract_id=contract.source_contract_id,
        fallback_reason=contract.fallback_reason,
        semantic_action={
            "action_kind": action_kind,
            "target": semantic_target_descriptor(
                stage_input.observation, target_id
            ),
            "destination": semantic_target_descriptor(
                stage_input.observation, destination_id
            ),
            "parameters": parameters,
            "expected_effects": [asdict(item) for item in contract.expected_effects],
            "verifier_plan": [asdict(item) for item in contract.verifier_plan],
            "required_capabilities": list(contract.required_capabilities),
            "risk": contract.risk.value,
        },
    )


def _route_events(
    stage_input: ActionStageInput, contract: ActionContract
) -> list[RuntimeEvent]:
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
                [item.candidate_id for item in route_plan.viable_alternatives]
                if route_plan is not None
                else []
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
