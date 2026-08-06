from dataclasses import dataclass, field, replace

from affordance_runtime.action_contract_builder import ActionContractMaterializer as ContractBuilder
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RiskLevel,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.coordinator import RunBudget
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    EvidenceKind,
    GroundingSource,
    PerceptionRequirements,
    SourceAssertion,
    SourceObservation,
    UnifiedAffordance,
)
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerDoneResponse,
    PlannerProposalResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.source_assertions import SourceAssertionArbiter
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.unified_grounding import candidate_from_affordance
from affordance_runtime.verification.contracts import SuccessExpression


def _snapshot(sequence: int, *, conflict: bool = False) -> BrowserSnapshot:
    snapshot_id = f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        '<button id="save">Save</button>',
        environment_revision="revision-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "revision-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    candidate = replace(
        candidate_from_affordance(
            model.affordances[0],
            observation,
            semantic_target_id=model.affordances[0].id,
        ),
        verifier_strength=1,
    )
    target = UnifiedAffordance(
        model.affordances[0].id,
        model.affordances[0].role,
        model.affordances[0].label,
        frozenset({model.affordances[0].action}),
        grounding_candidates=(candidate,),
    )
    source_observations = (
        SourceObservation(
            GroundingSource.DOM,
            "dom-test",
            snapshot_id,
            "revision-1",
            "page-1",
        ),
    )
    if not conflict:
        return BrowserSnapshot(
            observation,
            model,
            source_observations=source_observations,
            grounding_candidates=(candidate,),
            unified_affordances=(target,),
        )
    assertions = (
        SourceAssertion(
            f"dom:{sequence}:visible:true",
            "semantic:save",
            "visible",
            True,
            "boolean",
            GroundingSource.DOM,
            snapshot_id,
            "revision-1",
            "page-1",
            "dom-test",
        ),
        SourceAssertion(
            f"dom:{sequence}:visible:false",
            "semantic:save",
            "visible",
            False,
            "boolean",
            GroundingSource.DOM,
            snapshot_id,
            "revision-1",
            "page-1",
            "dom-test",
        ),
    )
    arbitration = SourceAssertionArbiter().arbitrate(
        assertions,
        observation,
        available_sources=frozenset({GroundingSource.DOM}),
        observation_budget=1,
    )
    return BrowserSnapshot(
        observation,
        model,
        source_observations=source_observations,
        grounding_candidates=(candidate,),
        unified_affordances=(target,),
        source_assertions=assertions,
        assertion_decisions=arbitration.decisions,
        active_perception_requests=arbitration.active_perception_requests,
    )


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="active-perception-run",
        revision=1,
        objective="Save the requested setting",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(("Save",), OperationClass.REVERSIBLE_WRITE, "request-1", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("Save",)),
        success=SuccessExpression(
            expression_id="success:effect-present",
            operator="criterion",
            criterion_id="criterion:effect-present",
        ),
        evidence_requirements=("fresh saved-state evidence",),
        source_request_ref="request-1",
    )


def _contract_builder(*, verify_effect: bool = False) -> ContractBuilder:
    verifier_plan = (
        (
            VerifierSpec(
                "observation_metadata",
                "effect_present",
                True,
                criterion_ids=("criterion:effect-present",),
            ),
        )
        if verify_effect
        else ()
    )
    return ContractBuilder(
        requirements={
            "dom_button_1": ContractRequirements(
                verifier_plan=verifier_plan,
                risk=RiskLevel.MEDIUM,
            )
        }
    )


class OneContractPlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse:
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id="active-perception-save",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="save the requested setting",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=request.observation.affordances[0].target_id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="active-perception-test",
            ),
        )


@dataclass
class RecordingExecutor:
    backend: str = "dom"
    contracts: list[ActionContract] = field(default_factory=list)

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        self.contracts.append(contract)
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
        )


class PreflightConflictObserver:
    def __init__(self) -> None:
        self.captures = 0
        self.targeted_captures = 0

    def capture(self) -> BrowserSnapshot:
        self.captures += 1
        return _snapshot(self.captures, conflict=self.captures >= 2)

    def capture_targeted(self, requests: object) -> BrowserSnapshot:
        assert isinstance(requests, tuple) and len(requests) == 1
        self.targeted_captures += 1
        return _snapshot(100 + self.targeted_captures, conflict=True)


def _resolved_snapshot(sequence: int) -> BrowserSnapshot:
    snapshot = _snapshot(sequence)
    assertion = SourceAssertion(
        f"dom:{sequence}:visible:true",
        "semantic:save",
        "visible",
        True,
        "boolean",
        GroundingSource.DOM,
        snapshot.observation.snapshot_id,
        snapshot.observation.environment_revision,
        snapshot.observation.page_revision,
        "dom-test",
    )
    arbitration = SourceAssertionArbiter().arbitrate(
        (assertion,),
        snapshot.observation,
        available_sources=frozenset({GroundingSource.DOM}),
        observation_budget=0,
    )
    return replace(
        snapshot,
        observation=replace(
            snapshot.observation,
            metadata={
                "criterion_evaluations": {
                    "criterion:effect-present": "satisfied",
                }
            },
        ),
        source_assertions=(assertion,),
        assertion_decisions=arbitration.decisions,
    )


class ResolvingConflictObserver:
    targeted_captures = 0

    def capture(self) -> BrowserSnapshot:
        return _snapshot(1, conflict=True)

    def capture_targeted(self, requests: object) -> BrowserSnapshot:
        assert isinstance(requests, tuple) and len(requests) == 1
        self.targeted_captures += 1
        return _resolved_snapshot(100 + self.targeted_captures)


class FinishAfterObservationPlanner:
    def propose(self, request: PlanningRequest) -> PlannerDoneResponse:
        del request
        return PlannerDoneResponse(result={"observed": True})


class ZeroBudgetVisualObserver:
    targeted_captures = 0

    def capture(self) -> BrowserSnapshot:
        snapshot_id = "zero-budget-snapshot"
        model = DomAdapter().transduce(
            "<main></main>",
            environment_revision="revision-1",
            snapshot_id=snapshot_id,
            page_revision="page-1",
        )
        return BrowserSnapshot(
            Observation(
                "revision-1",
                screenshot_ref="transport-only.png",
                snapshot_id=snapshot_id,
                page_revision="page-1",
            ),
            model,
            source_observations=(
                SourceObservation(
                    GroundingSource.VISUAL,
                    "playwright-screenshot",
                    snapshot_id,
                    "revision-1",
                    "page-1",
                    artifact_refs=("transport-only.png",),
                ),
            ),
            active_perception_requests=(
                ActivePerceptionRequest(
                    "task:unresolved-target",
                    "appearance",
                    (GroundingSource.VISUAL,),
                    "visual evidence is required",
                ),
            ),
            perception_requirements=PerceptionRequirements(
                required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
                acceptable_evidence=frozenset({GroundingSource.VISUAL}),
                preferred_sources=(GroundingSource.VISUAL,),
                observation_budget=1,
                model_call_budget=0,
                latency_budget_ms=500,
                cost_budget=0.0,
            ),
        )

    def capture_targeted(self, requests: object) -> BrowserSnapshot:
        del requests
        self.targeted_captures += 1
        raise AssertionError("zero-budget visual probe must not execute")


def test_coordinator_rejects_visual_probe_without_model_or_cost_authority() -> None:
    observer = ZeroBudgetVisualObserver()

    result = compose_run_coordinator(
        observer=observer,
        executor=RecordingExecutor(),
    ).run_sync(
        RunRequest(
            task_spec=_task().model_copy(
                update={
                    "task_id": "zero-budget",
                    "operation_class": OperationClass.READ_ONLY,
                }
            )
        )
    )

    events = [node.kind for node in result.trace.nodes]
    assert result.status == RuntimeStep.ABORTED
    assert observer.targeted_captures == 0
    assert "EvidenceGapDetected" in events
    assert "TargetedPerceptionBudgetExhausted" in events
    assert "ActivePerceptionPlanned" not in events
    assert "ProbeStarted" not in events
    assert result.state.perception_resolution is not None
    assert result.state.perception_resolution.status.value == "inconclusive"


def test_targeted_probe_resolves_injected_conflict_in_a_new_epoch() -> None:
    observer = ResolvingConflictObserver()
    result = compose_run_coordinator(
        observer=observer,
        executor=RecordingExecutor(),
    ).run_sync(
        RunRequest(
            task_spec=_task().model_copy(
                update={
                    "task_id": "resolve-conflict",
                    "operation_class": OperationClass.READ_ONLY,
                }
            )
        )
    )

    events = [node.kind for node in result.trace.nodes]
    assert result.status == RuntimeStep.DONE
    assert observer.targeted_captures == 1
    assert "EvidenceGapDetected" in events
    assert "ActivePerceptionPlanned" in events
    assert "EvidenceGapResolved" in events
    assert result.state.perception_resolution is not None
    assert result.state.perception_resolution.status.value == "resolved"
    assert result.state.perception_resolution.based_on_snapshot_id != (
        result.state.perception_resolution.observation_epoch_id
    )


def test_material_conflict_surviving_probe_blocks_effectful_execution() -> None:
    observer = PreflightConflictObserver()
    executor = RecordingExecutor()

    result = compose_run_coordinator(
        observer=observer,
        executor=executor,
        contract_builder=_contract_builder(verify_effect=True),
        budget=RunBudget(max_active_perception_observations=1),
    ).run_sync(RunRequest(task_spec=_task()))

    events = [node.kind for node in result.trace.nodes]
    assert result.status == RuntimeStep.ABORTED
    assert result.error_code is None
    assert executor.contracts == []
    assert observer.targeted_captures == 1
    assert "ActivePerceptionPlanned" in events
    assert "ProbeStarted" in events
    assert "ProbeCompleted" in events
    assert "EvidenceGapUnresolved" in events
    assert "PerceptionBlockedEffectfulAction" in events
    assert result.state.perception_resolution is not None
    assert result.state.perception_resolution.blocks_effectful_action
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase.value == "fusion"
    assert "FailureDetected" in events


class VerificationRepairObserver:
    def __init__(self) -> None:
        self.captures = 0
        self.targeted_captures = 0

    def capture(self) -> BrowserSnapshot:
        self.captures += 1
        return _snapshot(self.captures)

    def capture_targeted(self, requests: object) -> BrowserSnapshot:
        assert isinstance(requests, tuple) and len(requests) == 1
        assert requests[0].property_key == "verification"
        self.targeted_captures += 1
        return _snapshot(200 + self.targeted_captures)


def test_inconclusive_verification_probes_fresh_evidence_without_repeating_effect() -> None:
    observer = VerificationRepairObserver()
    executor = RecordingExecutor()

    result = compose_run_coordinator(
        observer=observer,
        executor=executor,
        contract_builder=_contract_builder(),
        budget=RunBudget(max_active_perception_observations=1),
    ).run_sync(RunRequest(task_spec=_task()))

    events = [node.kind for node in result.trace.nodes]
    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PRECONDITION_FAILED
    assert len(executor.contracts) == 1
    assert observer.targeted_captures == 1
    assert "VerificationEvidenceRepairRequested" in events
    assert "VerificationEvidenceReevaluated" in events
    assert "ActivePerceptionPlanned" in events
    assert result.state.latest_probe_receipt is not None
    assert result.state.latest_probe_receipt.observation_epoch_id != "snapshot-3"


class RecoveryInspectionObserver:
    def __init__(self) -> None:
        self.captures = 0
        self.targeted_captures = 0

    def capture(self) -> BrowserSnapshot:
        self.captures += 1
        snapshot = _snapshot(self.captures, conflict=self.captures == 3)
        if self.targeted_captures:
            snapshot = replace(
                snapshot,
                observation=replace(
                    snapshot.observation,
                    metadata={
                        "effect_present": True,
                        "criterion_evaluations": {
                            "criterion:effect-present": "satisfied",
                        },
                    },
                ),
            )
        return snapshot

    def capture_targeted(self, requests: object) -> BrowserSnapshot:
        assert isinstance(requests, tuple) and len(requests) == 1
        self.targeted_captures += 1
        snapshot = _resolved_snapshot(300 + self.targeted_captures)
        return replace(
            snapshot,
            observation=replace(
                snapshot.observation,
                metadata={"effect_present": True},
            ),
        )


class RecoveryAwarePlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse | PlannerDoneResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"effect_confirmed": True})
        return OneContractPlanner().propose(request)


@dataclass
class UncertainExecutor:
    backend: str = "dom"
    calls: int = 0

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        self.calls += 1
        return ExecutionReceipt(
            contract.id,
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": True},
            error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
        )


def test_recovery_post_state_inspection_uses_same_probe_controller_before_any_repeat() -> None:
    observer = RecoveryInspectionObserver()
    executor = UncertainExecutor()

    result = compose_run_coordinator(
        observer=observer,
        executor=executor,
        contract_builder=_contract_builder(verify_effect=True),
        budget=RunBudget(max_active_perception_observations=1),
    ).run_sync(RunRequest(task_spec=_task()))

    events = [node.kind for node in result.trace.nodes]
    assert result.status == RuntimeStep.DONE
    assert executor.calls == 1
    assert observer.targeted_captures == 1
    assert "EvidenceGapResolved" in events
    assert "RecoveryStateInspected" in events
    assert "FailureDetected" in events
    assert "RecoveryOutcomeRecorded" in events
    recovery_outcome = next(
        node.payload["outcome"] for node in reversed(result.trace.nodes) if node.kind == "RecoveryOutcomeRecorded"
    )
    assert recovery_outcome["success"]
    assert recovery_outcome["changed_dimensions"][0] == "effect_status"
