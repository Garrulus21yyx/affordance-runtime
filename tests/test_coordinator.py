import asyncio
import json
from dataclasses import dataclass, replace
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.benchmarks.composition import compose_benchmark_run_coordinator
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    ProviderAck,
    RuntimeErrorCode,
    TransportState,
    VerifierSpec,
)
from affordance_runtime.coordinator import RunBudget
from affordance_runtime.criteria import (
    LiteralValue,
    OpenSemanticCriterion,
    PredicateExpr,
    PredicateOperator,
    SubjectExpr,
    evidence_requirement_id,
)
from affordance_runtime.effect_authority_contracts import (
    EffectAuthorizationScope,
    EffectClass,
    ResourceScopeRef,
)
from affordance_runtime.grounding import GroundingSource, SourceAssertion
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ProviderFailureKind,
    ProviderModelError,
)
from affordance_runtime.observation_store import ObservationCommit, ObservationRef
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerClarificationResponse,
    PlannerDecision,
    PlannerDoneResponse,
    PlannerProposalResponse,
    PlannerUnsupportedResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep, legacy_run_request
from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.source_assertions import SourceAssertionArbiter
from affordance_runtime.state_kernel import ProgressGuardReason, StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    UserRequest,
)
from affordance_runtime.task_pipeline import GeneralistTaskPipeline
from affordance_runtime.task_plan_contracts import (
    PlanProposal as PlanCandidate,
)
from affordance_runtime.task_plan_contracts import (
    TaskPlanGeneratorSource,
)
from affordance_runtime.task_planner import TaskPlanningRequest as TaskPlanningContext
from affordance_runtime.trace import TraceDag
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer as ContractBuilder
from affordance_runtime.unified_observation import SourceCoverage
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    EvidenceValidityMode,
    SuccessExpression,
)
from runtime_test_support import legacy_step_spec

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="coordinator-test-planner",
)


def _resolve_planner_decision(value: object) -> PlannerDecision:
    resolved = resolve_awaitable(value) if hasattr(value, "__await__") else value
    assert isinstance(resolved, PlannerDecision)
    return resolved


def _snapshot(
    sequence: int,
    *,
    saved: bool = False,
    snapshot_id: str | None = None,
    operation_ref: str = "resource.update@v1",
    effect_class: str = "update",
    externality: str = "local",
    reversibility: str = "reversible",
) -> BrowserSnapshot:
    environment_revision = f"environment-{sequence}"
    snapshot_id = snapshot_id or f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        (
            f"<main><button id='save' data-runtime-operation='{operation_ref}' "
            f"data-runtime-effect-class='{effect_class}' data-runtime-externality='{externality}' "
            f"data-runtime-reversibility='{reversibility}' "
            "data-runtime-source-assurance='structural' "
            "data-runtime-risk='medium'>Save</button></main>"
        ),
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
    )
    observation = Observation(
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        metadata={
            "saved": saved,
            "criterion_evaluations": {
                "criterion:task-success": {
                    "status": "satisfied" if saved and sequence >= 3 else "unsatisfied",
                    "evidence_refs": [f"observation:{snapshot_id}:task-success"],
                }
            },
        },
    )
    return BrowserSnapshot(
        observation,
        model,
        source_coverage=(
            SourceCoverage.complete(
                GroundingSource.DOM,
                captured_item_count=len(model.affordances),
                capture_policy_id="coordinator-test-dom@v1",
                acquisition_epoch_ref=snapshot_id,
                adapter_version="coordinator-test@v1",
            ),
        ),
    )


class FakeObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1, snapshot_id="snapshot-1-preflight"),
            _snapshot(1, saved=True, snapshot_id="snapshot-1-targeted"),
            _snapshot(2, saved=True),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        if len(self.snapshots) == 1:
            return self.snapshots[0]
        return self.snapshots.pop(0)


class SavePlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse | PlannerDoneResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"saved": True}, reason="persisted state observed")
        return PlannerProposalResponse(
            proposal=_activate_first(request, "save-settings", "save settings"),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            reason="save button available",
        )


@dataclass
class FakeExecutor:
    backend: str = "dom"
    supported_backends = ("dom",)
    supported_actions = ("activate", "click", "type_text", "fill", "select_option", "press_key")
    provider_capabilities = ("settings.write",)
    adapter_capabilities = provider_capabilities

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": True},
        )


def test_coordinator_runs_pre_observe_act_post_observe_verify_loop(tmp_path) -> None:
    coordinator = compose_run_coordinator(
        observer=FakeObserver(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        task_planner=SingleStageTaskPlanner(),
    )
    assert (
        coordinator.perception_stage.observation_store
        is coordinator.action_stage.observation_store
        is coordinator.progress_stage.observation_store
    )
    result = asyncio.run(coordinator.run(_semantic_envelope("run-1")))

    assert result.status == RuntimeStep.DONE
    assert result.state.task_plan is not None
    assert result.state.task_plan.plan_id.startswith("plan:")
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_step_ids == ("subgoal-1",)
    assert result.verification is not None and result.verification.passed
    assert result.state.observation_count == 3
    event_types = [node.kind for node in result.trace.nodes]
    captured_epoch_ids = [
        str(node.payload["snapshot_id"])
        for node in result.trace.nodes
        if node.kind
        in {
            "ObservationCaptured",
            "TargetedPerceptionCaptured",
            "PreflightObservationCaptured",
            "PostActionObservationCaptured",
        }
        and "snapshot_id" in node.payload
    ]
    assert len(captured_epoch_ids) == len(set(captured_epoch_ids))
    assert event_types.count("PlanningTurnEvaluated") == 0
    assert event_types.count("ActionChoiceCatalogBuilt") == 1
    assert "ActionCompleted" not in event_types
    assert event_types.count("ActionOutcomeRecorded") == 1
    assert event_types.count("PostActionEvaluated") == 1
    assert event_types.index("PostActionObservationCaptured") < event_types.index("ActionOutcomeRecorded")
    outcome = next(node for node in result.trace.nodes if node.kind == "ActionOutcomeRecorded")
    assert str(outcome.payload["contract_id"]).startswith("contract_candidate_dom_dom_button_1_")
    assert outcome.payload["status"] == "verified_effect"
    assert outcome.payload["receipt_success"] is True
    assert outcome.payload["verification_status"] == "passed"
    assert outcome.payload["post_snapshot_id"] == "snapshot-1-targeted"
    evaluated = next(node for node in result.trace.nodes if node.kind == "PostActionEvaluated")
    assert evaluated.payload["action_effect_status"] == "passed"
    assert evaluated.payload["active_step_status"] == "completed"
    assert evaluated.payload["task_completion_status"] == "completed"
    assert evaluated.payload["progress_committed"] is True
    assert (tmp_path / "artifacts/run-1/events.jsonl").exists()
    assert (tmp_path / "artifacts/run-1/run.json").exists()


def test_progress_stage_does_not_treat_observation_final_recheck_metadata_as_runtime_authority() -> None:
    result = compose_run_coordinator(
        observer=FinalRecheckObserver(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=FinalRecheckTaskPlanner(),
    ).run_sync(_semantic_envelope("run-final-recheck"))

    assert result.status == RuntimeStep.ABORTED
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_step_ids == ()


def test_open_semantic_without_resolver_routes_to_typed_clarification() -> None:
    result = compose_run_coordinator(
        observer=FakeObserver(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=OpenSemanticTaskPlanner(),
    ).run_sync(_semantic_envelope("run-open-semantic"))

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert "no admitted resolver" in str(result.result["clarification"])
    assert result.result["task_spec_gaps"][0]["missing_field"] == ("open_semantic:sounds_natural")
    assert any(node.kind == "OpenSemanticUnresolved" for node in result.trace.nodes)


def test_coordinator_continues_an_upstream_compiler_trace() -> None:
    trace = TraceDag("run-upstream")
    compiler_node = trace.add("TaskSpecCreated", {"task_revision": 1})

    result = compose_run_coordinator(
        observer=FakeObserver(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
    ).run_sync(_semantic_envelope("run-upstream"), trace)

    assert result.trace is trace
    task_node = next(node for node in trace.nodes if node.kind == "TaskCreated")
    assert task_node.parents == [compiler_node.id]


def test_coordinator_traces_source_assertion_decisions_and_targeted_perception() -> None:
    snapshot = _snapshot(1)
    assertions = (
        SourceAssertion(
            "visible-true",
            "semantic:save",
            "visible",
            True,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
            evidence_refs=("artifact:dom",),
        ),
        SourceAssertion(
            "visible-false",
            "semantic:save",
            "visible",
            False,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
            evidence_refs=("artifact:dom-second",),
        ),
    )
    arbitration = SourceAssertionArbiter().arbitrate(
        assertions,
        snapshot.observation,
        available_sources=frozenset({GroundingSource.DOM, GroundingSource.ACCESSIBILITY}),
        observation_budget=1,
    )

    class AssertionObserver:
        def __init__(self) -> None:
            self.targeted_calls = 0

        def capture(self) -> BrowserSnapshot:
            return replace(
                snapshot,
                source_assertions=assertions,
                assertion_decisions=arbitration.decisions,
                active_perception_requests=arbitration.active_perception_requests,
            )

        def capture_targeted(self, requests: object) -> BrowserSnapshot:
            assert isinstance(requests, tuple) and len(requests) == 1
            assert requests[0].entity_key == "semantic:save"
            assert requests[0].property_key == "visible"
            assert requests[0].requested_sources[0] in {
                GroundingSource.DOM,
                GroundingSource.ACCESSIBILITY,
            }
            self.targeted_calls += 1
            return _snapshot(2)

    class FinishPlanner:
        def propose(self, request: PlanningRequest) -> PlannerUnsupportedResponse:
            del request
            return PlannerUnsupportedResponse("observation_complete")

    observer = AssertionObserver()
    result = compose_run_coordinator(
        observer=observer,
        executor=FakeExecutor(),
    ).run_sync(_semantic_envelope("assertion-trace"))

    events = [node.kind for node in result.trace.nodes]
    assert "SourceAssertionsCollected" in events
    assert "SourceAssertionsArbitrated" in events
    assert "TargetedPerceptionRequested" in events
    assert "TargetedPerceptionCaptured" in events
    assert observer.targeted_calls == 1
    assert result.state.active_perception_count == 1
    collected = next(node for node in result.trace.nodes if node.kind == "SourceAssertionsCollected")
    assert collected.payload["assertions"][0]["evidence_refs"] == ["artifact:dom"]
    assert "value" not in collected.payload["assertions"][0]


def test_coordinator_bounds_repeated_targeted_perception_requests() -> None:
    snapshot = _snapshot(1)
    assertions = (
        SourceAssertion(
            "checked-true",
            "semantic:save",
            "checked",
            True,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
        ),
        SourceAssertion(
            "checked-false",
            "semantic:save",
            "checked",
            False,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
        ),
    )
    arbitration = SourceAssertionArbiter().arbitrate(assertions, snapshot.observation)
    unresolved = replace(
        snapshot,
        source_assertions=assertions,
        assertion_decisions=arbitration.decisions,
        active_perception_requests=arbitration.active_perception_requests,
    )

    class LoopingObserver:
        targeted_calls = 0

        def capture(self) -> BrowserSnapshot:
            return unresolved

        def capture_targeted(self, requests: object) -> BrowserSnapshot:
            assert isinstance(requests, tuple) and len(requests) == 1
            assert requests[0].entity_key == "semantic:save"
            assert requests[0].property_key == "checked"
            self.targeted_calls += 1
            return unresolved

    class FinishPlanner:
        def propose(self, request: PlanningRequest) -> PlannerUnsupportedResponse:
            del request
            return PlannerUnsupportedResponse("observation_complete")

    observer = LoopingObserver()
    result = compose_run_coordinator(
        observer=observer,
        executor=FakeExecutor(),
        budget=RunBudget(max_active_perception_observations=2),
    ).run_sync(_semantic_envelope("bounded-perception"))

    assert observer.targeted_calls == 2
    assert result.state.active_perception_count == 2
    assert "TargetedPerceptionBudgetExhausted" in [node.kind for node in result.trace.nodes]


class DriftingObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(2),  # authoritative action observation O1
            _snapshot(3, saved=True),
            _snapshot(3, saved=True, snapshot_id="snapshot-3-targeted"),
            _snapshot(4, saved=True),
            _snapshot(5, saved=True),
            _snapshot(6, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


def test_coordinator_reobserves_drift_before_execution() -> None:
    executor = FakeExecutor()
    result = asyncio.run(
        compose_run_coordinator(
            observer=DriftingObserver(),
            executor=executor,
            contract_builder=_metadata_builder("saved"),
            task_planner=SingleStageTaskPlanner(),
        ).run(_semantic_envelope("run-drift"))
    )

    assert result.status == RuntimeStep.DONE
    assert result.state.step_count == 1
    assert result.state.recovery_count == 0
    event_kinds = [node.kind for node in result.trace.nodes]
    assert "CommittedObservationPreflightChecked" in event_kinds
    assert "ContractRebuiltAtPreflight" not in event_kinds


def test_authoritative_action_observation_effect_change_blocks_dispatch() -> None:
    class EffectDriftObserver:
        def __init__(self) -> None:
            self.snapshots = [
                _snapshot(1),
                _snapshot(
                    2,
                    operation_ref="resource.delete@v1",
                    effect_class="delete",
                    externality="external_system",
                    reversibility="irreversible",
                ),
            ]

        def capture(self) -> BrowserSnapshot:
            if len(self.snapshots) == 1:
                return self.snapshots[0]
            return self.snapshots.pop(0)

    class RecordingExecutor(FakeExecutor):
        calls = 0

        def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
            self.calls += 1
            return super().execute(contract, observation)

    executor = RecordingExecutor()
    result = compose_run_coordinator(
        observer=EffectDriftObserver(),
        executor=executor,
        contract_builder=_metadata_builder("saved"),
        task_planner=SingleStageTaskPlanner(),
    ).run_sync(_semantic_envelope("preflight-effect-drift"))

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PLANNER_FAILED
    assert executor.calls == 0


class StableObserver:
    def __init__(self) -> None:
        self.capture_count = 0

    def capture(self) -> BrowserSnapshot:
        self.capture_count += 1
        return _snapshot(1, snapshot_id=f"snapshot-stable-{self.capture_count}")


class TwoStageObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1, snapshot_id="snapshot-1-preflight"),
            _snapshot(1, snapshot_id="snapshot-1-targeted"),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True, snapshot_id="snapshot-2-preflight"),
            _snapshot(2, saved=True, snapshot_id="snapshot-2-targeted"),
            _snapshot(2, saved=True, snapshot_id="snapshot-2-followup"),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class ReplanObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1, snapshot_id="snapshot-1-preflight"),
            _snapshot(1, snapshot_id="snapshot-1-targeted"),
            _snapshot(2),
            _snapshot(2, snapshot_id="snapshot-2-preflight"),
            _snapshot(2, snapshot_id="snapshot-2-targeted"),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class SingleStageTaskPlanner:
    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        refs = (SourceReference("request-flow", "unit:setting"),)
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="coordinator-single-stage-fixture",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=(
                legacy_step_spec(
                    step_id="subgoal-1",
                    objective=context.task_spec.objective,
                    interaction=ElementIntent("Save", refs),
                    completion_criteria=(
                        StateCriterion(
                            criterion_id="criterion:subgoal-1",
                            source_refs=refs,
                            subject="Save",
                            relation=StateCriterionRelation.IS_COMPLETED,
                            expected_value=None,
                            evidence_policy=CriterionEvidencePolicy(
                                EvidenceStrength.INDEPENDENT,
                                ("dom_state",),
                            ),
                        ),
                    ),
                    source_refs=refs,
                    requirement_refs=("requirement:test",),
                    effect_authorization_refs=("requirement:test",),
                    effectful=True,
                ),
            ),
            source_refs=refs,
        )


class FinalRecheckTaskPlanner:
    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        refs = (SourceReference("request-flow", "unit:setting"),)
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="coordinator-final-recheck-fixture",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=(
                StepSpec(
                    "subgoal-final-recheck",
                    context.task_spec.objective,
                    ElementIntent("Save", refs),
                    (
                        PredicateExpr(
                            "criterion:final-recheck",
                            SubjectExpr("resource", "resource:settings"),
                            PredicateOperator.EQUALS,
                            CriterionPolicy(
                                validity=EvidenceValidityMode.FINAL_RECHECK,
                                minimum_assurance=AssuranceLevel.AUTHORITATIVE,
                                allowed_source_kinds=(EvidenceSourceKind.API_STATE,),
                            ),
                            LiteralValue("saved"),
                        ),
                    ),
                    refs,
                    tuple(item.requirement_id for item in context.task_spec.requirements),
                    effect_authorization_refs=tuple(context.task_spec.allowed_effect_refs),
                    effectful=True,
                ),
            ),
            source_refs=refs,
        )


class OpenSemanticTaskPlanner:
    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        refs = (SourceReference("request-flow", "anchor:tone"),)
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="coordinator-open-semantic-fixture",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=(
                StepSpec(
                    "subgoal-open-semantic",
                    context.task_spec.objective,
                    ElementIntent("Save", refs),
                    (
                        OpenSemanticCriterion(
                            "criterion:tone",
                            "sounds_natural",
                            (("register", "professional"),),
                            ("anchor:tone",),
                            CriterionPolicy(),
                        ),
                    ),
                    refs,
                    tuple(item.requirement_id for item in context.task_spec.requirements),
                ),
            ),
            source_refs=refs,
        )


class FinalRecheckObserver:
    def __init__(self) -> None:
        preflight = _snapshot(1, snapshot_id="snapshot-final-preflight")
        targeted = _snapshot(1, snapshot_id="snapshot-final-targeted")
        post = _snapshot(3, saved=True, snapshot_id="snapshot-final-current")
        metadata = dict(post.observation.metadata)
        metadata.update(
            {
                "latest_final_recheck_ref": "recheck:settings:3",
                "resource_versions": {"resource:settings": "v3"},
                "predicate_evidence": {
                    "resource:settings": {
                        "evidence_ref": "evidence:settings:3",
                        "observed_value": "saved",
                        "source_kind": "api_state",
                        "assurance": "authoritative",
                        "authoritative_final_recheck": True,
                        "final_recheck_ref": "recheck:settings:3",
                        "resource_version": "v3",
                    }
                },
            }
        )
        post = replace(post, observation=replace(post.observation, metadata=metadata))
        self.snapshots = [_snapshot(1), preflight, targeted, post]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]


class TwoStageTaskPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        self.calls += 1
        refs = (SourceReference("request-flow", "unit:setting"),)

        def step(step_id: str, depends_on: tuple[str, ...] = ()) -> StepSpec:
            return legacy_step_spec(
                step_id=step_id,
                objective=f"{step_id} settings",
                interaction=ElementIntent("Save", refs),
                completion_criteria=(
                    StateCriterion(
                        criterion_id=f"criterion:{step_id}",
                        source_refs=refs,
                        subject="Save",
                        relation=StateCriterionRelation.IS_COMPLETED,
                        evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
                    ),
                ),
                source_refs=refs,
                depends_on=depends_on,
                requirement_refs=("requirement:test",),
                effect_authorization_refs=("requirement:test",),
                effectful=True,
            )

        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="two-stage-test-planner",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=(step("write"), step("confirm", ("write",))),
            source_refs=refs,
        )


class AsyncTwoStageTaskPlanner(TwoStageTaskPlanner):
    async def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        return super().propose(context)


class SubgoalAwarePlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse:
        active_id = request.step.active_step.step_id if request.step.active_step else "step"
        return PlannerProposalResponse(
            proposal=_activate_first(request, f"proposal-{active_id}"),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
        )


class CurrentStateReadOnlyTaskPlanner:
    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        refs = (SourceReference("current-state-read-only-request", "request:task"),)
        first = legacy_step_spec(
            step_id="text-field-changed",
            objective="text field has changed",
            interaction=ElementIntent("text field", refs),
            completion_criteria=(
                StateCriterion(
                    criterion_id="criterion:text-changed",
                    source_refs=refs,
                    subject="text field",
                    relation=StateCriterionRelation.HAS_CHANGED,
                    evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
                ),
            ),
            source_refs=refs,
        )
        second = legacy_step_spec(
            step_id="submit-button-available",
            objective="submit button is available",
            interaction=ElementIntent("submit_button", refs),
            completion_criteria=(
                StateCriterion(
                    criterion_id="criterion:submit-available",
                    source_refs=refs,
                    subject="submit_button",
                    relation=StateCriterionRelation.IS_AVAILABLE,
                    evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
                ),
            ),
            source_refs=refs,
            depends_on=("text-field-changed",),
        )
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="current-state-test-planner",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=(first, second),
            source_refs=refs,
        )


class CurrentStateReadOnlyPlanner:
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if not request.step.compatibility_active_step_objective:
            return PlannerDoneResponse(result={"completed_active_subgoal": "submit-button-available"})
        target = next(
            item for item in request.observation.affordances if {"type", "type_text"} & set(item.supported_actions)
        )
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id="change-text-field",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal=request.step.compatibility_active_step_objective,
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_affordance_id=target.target_id,
                parameters={"text": "changed"},
            ),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
        )


class InitialAlreadySatisfiedTaskPlanner:
    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        raise AssertionError(f"initially complete task unexpectedly planned: {context.reason}")


class InitialAlreadySatisfiedPlanner:
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerDoneResponse:
        del request
        return PlannerDoneResponse(result={"completed_from_current_state": True})


class CurrentStateReadOnlyObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _current_state_read_only_snapshot(1, text_changed=False),
            _current_state_read_only_snapshot(1, text_changed=False, snapshot_id="snapshot-read-only-1-preflight"),
            _current_state_read_only_snapshot(1, text_changed=False, snapshot_id="snapshot-read-only-1-targeted"),
            _current_state_read_only_snapshot(2, text_changed=True),
            _current_state_read_only_snapshot(2, text_changed=True, snapshot_id="snapshot-read-only-2-preflight"),
            _current_state_read_only_snapshot(2, text_changed=True, snapshot_id="snapshot-read-only-2-targeted"),
            _current_state_read_only_snapshot(2, text_changed=True, snapshot_id="snapshot-read-only-2-followup"),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


def _current_state_read_only_snapshot(
    sequence: int,
    *,
    text_changed: bool,
    snapshot_id: str | None = None,
) -> BrowserSnapshot:
    environment_revision = f"environment-read-only-{sequence}"
    snapshot_id = snapshot_id or f"snapshot-read-only-{sequence}"
    model = DomAdapter().transduce(
        """
        <main>
          <input id='text-field' value='Kanesha'>
          <button id='submit-button'>Submit</button>
        </main>
        """,
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-read-only-{sequence}",
    )
    observation = Observation(
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-read-only-{sequence}",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        metadata={
            "text_changed": text_changed,
            "criterion_evaluations": {
                "criterion:submit-available": {
                    "status": "satisfied",
                    "evidence_refs": [f"observation:{snapshot_id}:submit-available"],
                },
                "criterion:text-changed": {
                    "status": "satisfied" if text_changed else "unsatisfied",
                    "evidence_refs": [f"observation:{snapshot_id}:text-changed"],
                },
            },
        },
    )
    return BrowserSnapshot(observation, model)


def _current_state_availability_task() -> TaskSpec:
    return TaskSpec(
        task_id="current-state-availability",
        revision=1,
        objective="Confirm submit button is available",
        operation_class=OperationClass.READ_ONLY,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:submit-available",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="submit button",
                    target_identity="Submit",
                    operation_class=OperationClass.READ_ONLY,
                ),
                source_anchor_refs=("current-state-availability-request:whole_request",),
            ),
        ),
        allowed_effect_refs=("requirement:submit-available",),
        success=SuccessExpression(
            expression_id="success:submit-available",
            operator="criterion",
            criterion_id="criterion:submit-available",
            requirement_refs=("requirement:submit-available",),
        ),
        capability_ceiling=(),
        source_request_ref="current-state-availability-request",
    )


def test_coordinator_advances_serial_task_plan_only_after_verifier_evidence() -> None:
    task_planner = AsyncTwoStageTaskPlanner()
    result = compose_run_coordinator(
        observer=TwoStageObserver(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved", include_task_success=False),
        task_planner=task_planner,
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.ABORTED
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_step_ids == ()
    assert task_planner.calls == 1
    events = [node.kind for node in result.trace.nodes]
    assert events.count("StepCompleted") == 0
    assert "TaskPlanAccepted" in events


def test_coordinator_prechecks_initial_already_satisfied_step_before_planning() -> None:
    result = compose_run_coordinator(
        observer=CurrentStateReadOnlyObserver(),
        executor=FakeExecutor(),
        task_planner=InitialAlreadySatisfiedTaskPlanner(),
    ).run_sync(legacy_run_request(task_spec=_current_state_availability_task()))

    assert result.status != RuntimeStep.DONE
    events = [node.kind for node in result.trace.nodes]
    assert "TaskCompleted" not in events
    assert "RecoveryStrategySelected" not in events
    assert "TaskPlanRejected" in events
    assert "TaskReplanned" not in events


class EarlyFinishPlanner:
    def propose(self, request: PlanningRequest) -> PlannerDoneResponse:
        del request
        return PlannerDoneResponse(result={"unverified": True})


def test_task_plan_rejects_planner_finish_without_verifier_backed_progress() -> None:
    result = compose_run_coordinator(
        observer=FakeObserver(),
        executor=FakeExecutor(),
        task_planner=TwoStageTaskPlanner(),
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_step_ids == ()


class ReplanningTaskPlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[TaskPlanningContext] = []

    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        self.calls += 1
        self.contexts.append(context)
        refs = (SourceReference("request-flow", "unit:setting"),)
        return PlanCandidate(
            task_spec_identity=context.task_spec.identity,
            task_revision=context.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="replanning-test-planner",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=(
                legacy_step_spec(
                    step_id="write",
                    objective="Write settings",
                    interaction=ElementIntent("Save", refs),
                    completion_criteria=(
                        StateCriterion(
                            criterion_id="criterion:write",
                            source_refs=refs,
                            subject="Save",
                            relation=StateCriterionRelation.IS_COMPLETED,
                            evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
                        ),
                    ),
                    source_refs=refs,
                    requirement_refs=("requirement:test",),
                    effect_authorization_refs=("requirement:test",),
                    effectful=True,
                    max_actions=2 if context.failures else 1,
                ),
            ),
            source_refs=refs,
        )


def test_coordinator_does_not_replan_into_an_unverified_non_idempotent_repeat() -> None:
    planner = ReplanningTaskPlanner()
    result = compose_run_coordinator(
        observer=ReplanObserver(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=planner,
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PRECONDITION_FAILED
    assert planner.calls == 1
    assert result.state.task_progress is not None
    assert result.state.task_progress.replan_count == 0
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryStateInspected" in events
    assert "RecoveryAborted" in events
    assert "TaskReplanned" not in events
    (initial,) = planner.contexts
    assert initial.reason == "initial"
    assert initial.environment.affordances[0].label == "Save"
    assert initial.current_plan_version == 0


class EvidencePreservingObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1, saved=True),
            _snapshot(1, saved=True, snapshot_id="snapshot-1-planning"),
            _snapshot(1, saved=True, snapshot_id="snapshot-1-preflight"),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True, snapshot_id="snapshot-2-planning"),
            _snapshot(2, saved=True, snapshot_id="snapshot-2-preflight"),
            _snapshot(2, saved=True, snapshot_id="snapshot-2-targeted"),
            _snapshot(3, saved=True),
            _snapshot(3, saved=True, snapshot_id="snapshot-3-planning"),
            _snapshot(3, saved=True, snapshot_id="snapshot-3-preflight"),
            _snapshot(3, saved=True, snapshot_id="snapshot-3-targeted"),
            _snapshot(4, saved=True),
            _snapshot(4, saved=True, snapshot_id="snapshot-4-planning"),
            _snapshot(4, saved=True, snapshot_id="snapshot-4-preflight"),
            _snapshot(4, saved=True, snapshot_id="snapshot-4-targeted"),
            _snapshot(4, saved=True, snapshot_id="snapshot-4-followup"),
        ]

    def capture(self) -> BrowserSnapshot:
        if len(self.snapshots) == 1:
            return self.snapshots[0]
        return self.snapshots.pop(0)


class EvidenceAwareTaskPlanner:
    def __init__(self) -> None:
        self.contexts: list[TaskPlanningContext] = []

    def propose(self, context: TaskPlanningContext) -> PlanCandidate:
        self.contexts.append(context)
        task = context.task_spec
        discovered = any(item.step_id == "discover" and item.evidence_ids for item in context.criteria_evidence_ledger)
        refs = (SourceReference("request-flow", "unit:setting"),)
        discover = legacy_step_spec(
            step_id="discover",
            objective="Discover saved state",
            interaction=ElementIntent("Save", refs),
            completion_criteria=(
                StateCriterion(
                    criterion_id="criterion:discover",
                    source_refs=refs,
                    subject="saved state",
                    relation=StateCriterionRelation.IS_COMPLETED,
                    evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
                ),
            ),
            source_refs=refs,
            requirement_refs=("requirement:test",),
            effect_authorization_refs=("requirement:test",),
            effectful=True,
        )
        apply = legacy_step_spec(
            step_id="apply",
            objective=(
                "Apply using verified saved-state evidence" if discovered else "Apply using the initial assumption"
            ),
            interaction=ElementIntent("Save", refs),
            depends_on=("discover",),
            completion_criteria=(
                StateCriterion(
                    criterion_id="criterion:apply",
                    source_refs=refs,
                    subject="Save",
                    relation=StateCriterionRelation.IS_COMPLETED,
                    evidence_policy=CriterionEvidencePolicy(EvidenceStrength.INDEPENDENT, ("dom_state",)),
                ),
            ),
            source_refs=refs,
            requirement_refs=("requirement:test",),
            effect_authorization_refs=("requirement:test",),
            effectful=True,
            max_actions=1,
        )
        return PlanCandidate(
            task_spec_identity=task.identity,
            task_revision=task.revision,
            generated_by=TaskPlanGeneratorSource.RULE,
            generator_id="evidence-aware-test-planner",
            based_on_observation_ref=context.environment.snapshot_id,
            based_on_state_version=context.state_version,
            steps=((replace(apply, depends_on=()),) if discovered else (discover, apply)),
            assumptions=("the initial apply route is sufficient",),
            source_refs=refs,
        )


class EvidenceAwareActionPlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse:
        return PlannerProposalResponse(
            proposal=_activate_first(
                request,
                f"evidence-action-{len(request.recent_outcomes)}",
            ),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
        )


class EvidenceAwareRouteEncoder:
    def verifier_kinds(self, semantic_target_id, snapshot):
        del semantic_target_id, snapshot
        return ("observation_metadata",)

    def encode_canonical_choice(self, choice, task_spec, state, snapshot, affordance):
        del choice, task_spec, snapshot
        active_id = state.task_progress.active_step_id if state.task_progress else ""
        plan_version = state.task_plan.plan_version if state.task_plan else 0
        bound_id = active_id if active_id == "discover" or plan_version >= 2 else "unrelated"
        verifier = VerifierSpec(
            "observation_metadata",
            "saved",
            True,
            criterion_ids=(
                f"criterion:{bound_id}",
                *(("criterion:task-success",) if active_id == "apply" and plan_version >= 2 else ()),
                *(("criterion:apply-success",) if active_id == "apply" and plan_version >= 2 else ()),
            ),
            requirement_ids=(evidence_requirement_id("step", bound_id, 0),),
        )
        return affordance.action, None, (verifier,)

def test_replan_uses_verified_evidence_and_preserves_progress_across_versions() -> None:
    task_planner = EvidenceAwareTaskPlanner()
    task = _semantic_task().model_copy(
        update={
            "success": SuccessExpression(
                expression_id="success:apply",
                operator="criterion",
                criterion_id="criterion:apply-success",
                requirement_refs=("requirement:test",),
            )
        }
    )
    result = compose_benchmark_run_coordinator(
        observer=EvidencePreservingObserver(),
        executor=FakeExecutor(),
        contract_builder=ContractBuilder(route_encoder=EvidenceAwareRouteEncoder()),
        task_planner=task_planner,
    ).run_sync(legacy_run_request(task_spec=task, capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert result.state.task_plan is not None
    assert result.state.task_plan.plan_version == 2
    assert result.state.task_plan.supersedes_plan_id
    assert result.state.task_plan.steps[0].objective == "Apply using verified saved-state evidence"
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_step_ids == ("discover", "apply")
    assert len(task_planner.contexts) == 2
    replacement_context = task_planner.contexts[1]
    assert replacement_context.criteria_evidence_ledger[0].step_id == "discover"
    assert replacement_context.criteria_evidence_ledger[0].evidence_ids
    assert replacement_context.failures[0].error_code == "step_action_budget_exhausted"
    replanned = next(node for node in result.trace.nodes if node.kind == "TaskReplanned")
    assert replanned.payload["planning_context"]["criteria_evidence_ledger"]


class RepeatingPlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse:
        return PlannerProposalResponse(
            proposal=_activate_first(request, "repeat-save", "repeat save"),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
        )


@dataclass
class AlwaysFailExecutor:
    backend: str = "dom"
    supported_backends = ("dom",)
    supported_actions = FakeExecutor.supported_actions
    provider_capabilities = FakeExecutor.provider_capabilities
    adapter_capabilities = provider_capabilities

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract.id,
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            error_code=RuntimeErrorCode.EXECUTION_FAILED,
            message="request encoding failed before send",
            transport_state=TransportState.NOT_SENT,
            provider_ack=ProviderAck.NOT_APPLICABLE,
        )


def test_coordinator_excludes_failed_candidate_and_aborts_without_blind_retry() -> None:
    result = asyncio.run(
        compose_run_coordinator(
            observer=StableObserver(),
            executor=AlwaysFailExecutor(),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        idempotency_key="repeat-save:1",
                        verifier_plan=(VerifierSpec("observation_metadata", "saved", True),),
                    )
                }
            ),
            task_planner=SingleStageTaskPlanner(),
        ).run(_semantic_envelope("run-loop"))
    )

    assert result.status == RuntimeStep.ABORTED
    assert result.state.current_failure is not None
    assert result.state.current_failure.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value
    recovery_outcomes = [
        node.payload["outcome"] for node in result.trace.nodes if node.kind == "RecoveryOutcomeRecorded"
    ]
    assert recovery_outcomes
    assert recovery_outcomes[-1]["success"] is False
    assert result.state.step_count == 1
    assert any(
        node.kind == "RecoveryStrategySelected"
        and node.payload["decision"]["kind"] == "reground"
        for node in result.trace.nodes
    )
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryOutcomeRecorded" in events
    assert "RecoveryStrategySelected" in events


@dataclass
class AsyncSemanticSavePlanner:
    revision: int = 1

    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"saved": True})
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=PlannerProposal(
                proposal_id="proposal-save",
                based_on_task_revision=self.revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="Save settings",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=request.observation.affordances[0].target_id,
                expected_effects=("settings are saved",),
                evidence_requirements=("saved observation",),
            ),
        )


@dataclass
class ActiveSubgoalSavePlanner(AsyncSemanticSavePlanner):
    """Test planner that consumes Runtime-owned normalized subgoal ids."""

    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        response = await super().propose(request)
        if isinstance(response, PlannerDoneResponse):
            return response
        return replace(
            response,
            proposal=response.proposal.model_copy(
                update={
                    "subgoal": request.step.compatibility_active_step_objective,
                }
            ),
        )


def _semantic_task() -> TaskSpec:
    return TaskSpec(
        task_id="semantic-run",
        revision=1,
        objective="Save settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:test",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="Save",
                    target_identity="Save",
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    capability="settings.write",
                    effect_authorization_scope=EffectAuthorizationScope(
                        requirement_ref="requirement:test",
                        effect_class=EffectClass.UPDATE,
                        resource_scope=ResourceScopeRef(
                            "dom_button_1",
                            ("semantic-request:whole_request",),
                        ),
                        operation_constraint="resource.update@v1",
                        required_capabilities=frozenset({"settings.write"}),
                    ),
                ),
                source_anchor_refs=("semantic-request:whole_request",),
            ),
        ),
        allowed_effect_refs=("requirement:test",),
        capability_ceiling=("settings.write",),
        success=SuccessExpression(
            expression_id="success:settings-saved",
            operator="criterion",
            criterion_id="criterion:task-success",
            requirement_refs=("requirement:test",),
        ),
        source_request_ref="semantic-request",
    )


def _semantic_envelope(task_id: str = "semantic-run") -> RunRequest:
    task = _semantic_task().model_copy(update={"task_id": task_id})
    return legacy_run_request(task_spec=task, capabilities=["settings.write"])


def _activate_first(
    request: PlanningRequest,
    proposal_id: str,
    subgoal: str = "",
) -> PlannerProposal:
    return PlannerProposal(
        proposal_id=proposal_id,
        based_on_task_revision=request.identity.task_revision,
        based_on_state_version=request.identity.evaluated_at_state_version,
        snapshot_id=request.identity.snapshot_id,
        subgoal=subgoal or request.step.compatibility_active_step_objective,
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=request.observation.affordances[0].target_id,
    )


def _metadata_builder(
    key: str,
    expected: object = True,
    *,
    capability: str = "settings.write",
    target_id: str = "dom_button_1",
    include_task_success: bool = True,
) -> ContractBuilder:
    return ContractBuilder(
        requirements={
            target_id: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "observation_metadata",
                        key,
                        expected,
                        criterion_ids=(("criterion:task-success",) if include_task_success else ()),
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                ),
                required_capabilities=(capability,),
            )
        }
    )


def test_coordinator_awaits_semantic_planner_and_builds_contract() -> None:
    task = _semantic_task()
    result = asyncio.run(
        compose_run_coordinator(
            observer=FakeObserver(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        verifier_plan=(
                                VerifierSpec(
                                    "observation_metadata",
                                    "saved",
                                    True,
                                    criterion_ids=("criterion:subgoal-1", "criterion:task-success"),
                                requirement_ids=("unit:setting",),
                            ),
                        ),
                        required_capabilities=("settings.write",),
                        idempotency_key="semantic-save-v1",
                        compensation="restore settings",
                    )
                }
            ),
            task_planner=SingleStageTaskPlanner(),
        ).run(legacy_run_request(task_spec=task, capabilities=["settings.write"]))
    )

    assert result.status == RuntimeStep.DONE
    events = [node.kind for node in result.trace.nodes]
    assert events.count("PlannerProposalProduced") == 0
    assert events.count("ActionChoiceSelected") == 1
    assert result.state.latest_planner_proposal
    assert result.state.latest_planner_proposal["selection_id"].startswith("choice:")
    contract_event = next(node for node in result.trace.nodes if node.kind == "ContractBuilt")
    assert "proposal_id" not in contract_event.payload
    assert contract_event.payload["choice_id"].startswith("choice:")


@dataclass
class RepeatingSemanticPlanner:
    calls: int = 0

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        self.calls += 1
        if self.calls >= 3:
            return PlannerDoneResponse(result={"guarded": True})
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=_activate_first(
                request,
                f"proposal-repeat-{len(request.recent_proposals)}",
            ),
        )


class StableSavedObserver:
    def __init__(self, *, saved: bool) -> None:
        self.saved = saved
        self.capture_count = 0

    def capture(self) -> BrowserSnapshot:
        self.capture_count += 1
        return _snapshot(
            1,
            saved=self.saved,
            snapshot_id=f"snapshot-stable-saved-{self.capture_count}",
        )


@dataclass
class CountingExecutor(FakeExecutor):
    calls: int = 0

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        self.calls += 1
        return super().execute(contract, observation)


def _semantic_guard_builder() -> ContractBuilder:
    return ContractBuilder(
        requirements={
            "dom_button_1": ContractRequirements(
                verifier_plan=(VerifierSpec("observation_metadata", "saved", True),),
                required_capabilities=("settings.write",),
                idempotency_key="semantic-repeat-v1",
            )
        }
    )


def test_progress_guard_blocks_already_verified_semantic_action() -> None:
    executor = CountingExecutor()
    result = compose_run_coordinator(
        observer=StableSavedObserver(saved=True),
        executor=executor,
        contract_builder=_semantic_guard_builder(),
    ).run_sync(legacy_run_request(task_spec=_semantic_task(), capabilities=["settings.write"]))

    assert result.status != RuntimeStep.DONE
    assert executor.calls == 1
    assert result.state.latest_progress_guard is not None
    assert result.state.latest_progress_guard["reason"] == "effect_already_satisfied"
    blocked = [node for node in result.trace.nodes if node.kind == "PlannerProgressBlocked"]
    assert blocked[-1].payload["error_code"] == RuntimeErrorCode.EFFECT_ALREADY_SATISFIED.value


def test_failed_effect_is_not_repeated_without_a_validated_recovery_delta(tmp_path) -> None:
    executor = CountingExecutor()
    result = compose_run_coordinator(
        observer=StableSavedObserver(saved=False),
        executor=executor,
        contract_builder=_semantic_guard_builder(),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
    ).run_sync(legacy_run_request(task_spec=_semantic_task(), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PRECONDITION_FAILED
    assert executor.calls == 1
    assert result.state.latest_progress_guard is None
    assert result.state.current_failure is not None
    assert result.state.current_failure.message == "verifier failed: observation_metadata:saved"
    assert result.state.current_failure.verification_ref.endswith("verification_0001.json")
    assert result.state.current_failure.evidence_refs == (result.state.current_failure.verification_ref,)
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryStateInspected" in events
    assert "RecoveryAborted" in events


def test_progress_guard_allows_repeated_verified_delta_until_effect_is_satisfied() -> None:
    state = StateKernel("slider", "move slider several steps")
    state.remember_observation_commit(ObservationCommit(ObservationRef("epoch-rev-2", "sha256:test"), "rev-2", "rev-2"))
    signature = json.dumps(
        {"action_kind": "press_key", "target": "slider", "parameters": {"key": "ArrowRight"}},
        sort_keys=True,
        separators=(",", ":"),
    )
    state.record_action_progress(
        signature,
        "rev-2",
        verification_passed=True,
        effect_satisfied=False,
    )

    assert state.check_progress_guard(signature) is None


def test_progress_guard_blocks_an_alternating_return_to_a_satisfied_effect() -> None:
    state = StateKernel("task-1", "Select controls")
    state.remember_observation_commit(
        ObservationCommit(ObservationRef("epoch-rev-3", "sha256:test"), "rev-3", "page-1")
    )
    checkbox_a = json.dumps(
        {"action_kind": "activate", "target": "checkbox-a", "parameters": {}},
        sort_keys=True,
        separators=(",", ":"),
    )
    checkbox_b = json.dumps(
        {"action_kind": "activate", "target": "checkbox-b", "parameters": {}},
        sort_keys=True,
        separators=(",", ":"),
    )
    state.record_action_progress(
        checkbox_a,
        "rev-1",
        verification_passed=True,
        effect_satisfied=True,
        post_page_revision="page-1",
    )
    state.record_action_progress(
        checkbox_b,
        "rev-2",
        verification_passed=True,
        effect_satisfied=True,
        post_page_revision="page-1",
    )

    assert state.check_progress_guard(checkbox_a) == ProgressGuardReason.EFFECT_ALREADY_SATISFIED


T = TypeVar("T", bound=BaseModel)


@dataclass
class _PipelineIntentModel:
    provider: str = "fixed"
    model: str = "fixed"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del config
        request_payload = json.loads(messages[-1].content)
        source_ref = request_payload["source_envelope"]["anchors"][0]["anchor_id"]
        return output_schema.model_validate(
            {
                "objective": "Save settings",
                "requested_effects": [
                    {
                        "operation_class": "reversible_write",
                        "target": "dom_button_1",
                        "capability": "settings.write",
                        "source_ref": source_ref,
                        "operation_ref": "resource.update@v1",
                    }
                ],
                "success": SuccessExpression(
                    expression_id="success:pipeline-save",
                    operator="criterion",
                    criterion_id="criterion:task-success",
                    requirement_refs=("requirement:effect:1",),
                ).model_dump(mode="json"),
            }
        )


class _PipelineObserver(FakeObserver):
    def capture(self) -> BrowserSnapshot:
        snapshot = super().capture()
        metadata = dict(snapshot.observation.metadata)
        metadata["criterion_evaluations"] = {
            "criterion:task-success": {
                "status": "satisfied" if metadata.get("saved") is True else "unsatisfied",
                "evidence_refs": [f"observation:{snapshot.observation.snapshot_id}:task-success"],
            }
        }
        return replace(
            snapshot,
            observation=replace(snapshot.observation, metadata=metadata),
        )


def test_raw_request_pipeline_preserves_compiler_to_contract_lineage() -> None:
    pipeline = GeneralistTaskPipeline(
        compiler=LLMIntentCompiler(_PipelineIntentModel()),
        coordinator=compose_run_coordinator(
            observer=_PipelineObserver(),
            executor=FakeExecutor(),
            contract_builder=_metadata_builder("saved"),
        ),
        granted_capabilities=("settings.write", "admin.unrequested"),
    )

    result = asyncio.run(pipeline.run(UserRequest(request_id="pipeline-run", raw_text="Save my settings")))

    assert result.status == "done"
    assert result.coordinator is not None
    assert [node.kind for node in result.trace.nodes][:6] == [
        "UserRequestReceived",
        "SourceEnvelopeBuilt",
        "MinimalIntentProposalProduced",
        "SemanticAuditEvaluated",
        "TaskSpecAdmissionDecided",
        "TaskCreated",
    ]
    assert "ActionChoiceCatalogBuilt" in [node.kind for node in result.trace.nodes]
    assert "ActionChoiceSelected" in [node.kind for node in result.trace.nodes]
    assert "ContractBuilt" in [node.kind for node in result.trace.nodes]


def test_async_planner_resolution_works_inside_an_existing_event_loop() -> None:
    async def decide() -> PlannerDecision:
        return PlannerDecision(done=True, result={"ok": True})

    async def outer() -> PlannerDecision:
        return _resolve_planner_decision(decide())

    assert asyncio.run(outer()).result == {"ok": True}


class MissingProvenancePlanner(AsyncSemanticSavePlanner):
    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        response = await super().propose(request)
        return (
            replace(response, proposal_provenance=None) if isinstance(response, PlannerProposalResponse) else response
        )


class ClarifyingPlanner(AsyncSemanticSavePlanner):
    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerClarificationResponse:
        del request
        return PlannerClarificationResponse("Which settings profile should be changed?")


class QuotaExhaustedPlanner:
    def propose(self, request: PlanningRequest) -> PlannerDoneResponse:
        del request
        raise ProviderModelError(ProviderFailureKind.QUOTA_EXHAUSTED, retry_after_s=60)


class UnsupportedChoicePlanner:
    def propose(self, request: PlanningRequest) -> PlannerUnsupportedResponse:
        del request
        return PlannerUnsupportedResponse(
            reason_code="no_feasible_action_choice",
            message="Runtime could not construct an active-step action choice.",
        )


class LegacyNoProposalPlanner:
    def propose(self, request: PlanningRequest) -> PlannerUnsupportedResponse:
        del request
        return PlannerUnsupportedResponse(
            reason_code="legacy_decision_without_proposal",
            message="legacy planner did not produce an action",
        )
