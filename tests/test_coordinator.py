import asyncio
import json
from dataclasses import dataclass, replace
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.coordinator import RunBudget
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.execution_phase import ActionStageInput
from affordance_runtime.failure_envelope import RemainingRecoveryBudgets
from affordance_runtime.grounding import GroundingSource, SourceAssertion
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ProviderFailureKind,
    ProviderModelError,
)
from affordance_runtime.planning import (
    ContractBuilder,
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
from affordance_runtime.recovery_protocol import FailureOwner, classify_failure
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_committer import runtime_state_snapshot
from affordance_runtime.simplified_runtime_contracts import ElementIntent, SourceReference
from affordance_runtime.source_assertions import SourceAssertionArbiter
from affordance_runtime.stage_protocol import LoopDirective
from affordance_runtime.state_kernel import ProgressGuardReason, StateKernel
from affordance_runtime.task_intake import (
    IntentDraft,
    OperationClass,
    RequestedEffect,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
    UserRequest,
)
from affordance_runtime.task_pipeline import GeneralistTaskPipeline
from affordance_runtime.task_planning import (
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanningContext,
    TaskPlanSource,
)
from affordance_runtime.trace import TraceDag
from runtime_test_support import make_interaction

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="coordinator-test-planner",
)


def _resolve_planner_decision(value: object) -> PlannerDecision:
    resolved = resolve_awaitable(value) if hasattr(value, "__await__") else value
    assert isinstance(resolved, PlannerDecision)
    return resolved


def _snapshot(sequence: int, *, saved: bool = False) -> BrowserSnapshot:
    environment_revision = f"environment-{sequence}"
    snapshot_id = f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        "<main><button id='save'>Save</button></main>",
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
    )
    observation = Observation(
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        metadata={"saved": saved},
    )
    return BrowserSnapshot(observation, model)


class FakeObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1),
            _snapshot(1),
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
    backend: str = "fake"

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
    result = asyncio.run(
        compose_run_coordinator(
            observer=FakeObserver(),
            planner=SavePlanner(),
            executor=FakeExecutor(),
            contract_builder=_metadata_builder("saved"),
            artifacts=ArtifactStore(tmp_path / "artifacts"),
            task_planner=SingleStageTaskPlanner(),
        ).run(_semantic_envelope("run-1"))
    )

    assert result.status == RuntimeStep.DONE
    assert result.result == {
        "task_plan_id": "plan-single-stage",
        "completed_subgoal_ids": ["subgoal-1"],
    }
    assert result.verification is not None and result.verification.passed
    assert result.state.observation_count == 4
    event_types = [node.kind for node in result.trace.nodes]
    assert event_types.count("PlanningTurnEvaluated") == 1
    assert "ActionCompleted" not in event_types
    assert event_types.count("ActionOutcomeRecorded") == 1
    assert event_types.count("PostActionEvaluated") == 1
    assert event_types.index("PostActionObservationCaptured") < event_types.index("ActionOutcomeRecorded")
    outcome = next(node for node in result.trace.nodes if node.kind == "ActionOutcomeRecorded")
    assert outcome.payload["contract_id"] == "contract_dom_button_1"
    assert outcome.payload["status"] == "verified_effect"
    assert outcome.payload["receipt_success"] is True
    assert outcome.payload["verification_status"] == "passed"
    assert outcome.payload["post_snapshot_id"] == "snapshot-2"
    evaluated = next(
        node for node in result.trace.nodes if node.kind == "PostActionEvaluated"
    )
    assert evaluated.payload["action_effect_status"] == "passed"
    assert evaluated.payload["active_step_status"] == "completed"
    assert evaluated.payload["task_completion_status"] == "completed"
    assert evaluated.payload["progress_committed"] is True
    assert (tmp_path / "artifacts/run-1/events.jsonl").exists()
    assert (tmp_path / "artifacts/run-1/run.json").exists()


def test_coordinator_continues_an_upstream_compiler_trace() -> None:
    trace = TraceDag("run-upstream")
    compiler_node = trace.add("TaskSpecCreated", {"task_revision": 1})

    result = compose_run_coordinator(
        observer=FakeObserver(),
        planner=SavePlanner(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
                     task_planner=None,
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
        planner=FinishPlanner(),
        executor=FakeExecutor(),
             task_planner=None,
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
        planner=FinishPlanner(),
        executor=FakeExecutor(),
        budget=RunBudget(max_active_perception_observations=2),
           task_planner=None,
    ).run_sync(_semantic_envelope("bounded-perception"))

    assert observer.targeted_calls == 2
    assert result.state.active_perception_count == 2
    assert "TargetedPerceptionBudgetExhausted" in [node.kind for node in result.trace.nodes]


class DriftingObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(2),  # injected drift between planning and preflight
            _snapshot(3),
            _snapshot(3),
            _snapshot(3),
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
            planner=SavePlanner(),
            executor=executor,
            contract_builder=_metadata_builder("saved"),
            task_planner=SingleStageTaskPlanner(),
        ).run(
            _semantic_envelope("run-drift")
        )
    )

    assert result.status == RuntimeStep.DONE
    assert result.state.step_count == 1
    assert result.state.recovery_count == 1
    assert "EnvironmentDriftDetected" in [node.kind for node in result.trace.nodes]
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase.value == "preflight"
    assert "RecoveryOutcomeRecorded" in [node.kind for node in result.trace.nodes]


class StableObserver:
    def capture(self) -> BrowserSnapshot:
        return _snapshot(1)


class TwoStageObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1),
            _snapshot(1),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class ReplanObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1),
            _snapshot(1),
            _snapshot(2),
            _snapshot(2),
            _snapshot(2),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class SingleStageTaskPlanner:
    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        task = context.task_spec
        outcome = SubgoalOutcome(
            subject="Save",
            relation=SubgoalOutcomeRelation.IS_COMPLETED,
        )
        return TaskPlan(
            plan_id="plan-single-stage",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="subgoal-1",
                    objective=task.objective,
                    interaction=make_interaction("Save"),
                    success_criteria=task.success_criteria,
                    evidence_requirements=task.evidence_requirements,
                    operation_class=task.operation_class,
                    action_family=TaskPlanActionFamily.ACTIVATE,
                    outcome=outcome,
                ),
            ),
        )


class TwoStageTaskPlanner:
    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        task_spec = context.task_spec
        return TaskPlan(
            plan_id="plan-two-stage",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=1,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="write",
                    objective="Write settings",
                    interaction=make_interaction('Write settings'),
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                ),
                SubgoalSpec(
                    subgoal_id="confirm",
                    objective="Confirm settings",
                    interaction=make_interaction('Confirm settings'),
                    depends_on=("write",),
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                ),
            ),
        )


class AsyncTwoStageTaskPlanner(TwoStageTaskPlanner):
    async def plan(self, context: TaskPlanningContext) -> TaskPlan:
        return super().plan(context)


class UnsupportedThenValidTaskPlanner:
    def __init__(self, *, valid_replacement: bool = True) -> None:
        self.valid_replacement = valid_replacement

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        first = SubgoalSpec(
            subgoal_id="write",
            objective="Write settings",
            interaction=make_interaction('settings'),
            success_criteria=("settings are saved",),
            evidence_requirements=("saved observation",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            action_family=TaskPlanActionFamily.ACTIVATE,
            outcome=SubgoalOutcome(
                subject="settings",
                relation=SubgoalOutcomeRelation.HAS_CHANGED,
            ),
        )
        unsupported = SubgoalSpec(
            subgoal_id="confirm",
            objective="Save is checked",
            interaction=make_interaction('Save'),
            depends_on=("write",),
            success_criteria=("Save is checked",),
            evidence_requirements=("current checked state",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            action_family=TaskPlanActionFamily.ACTIVATE,
            outcome=SubgoalOutcome(
                subject="Save",
                relation=SubgoalOutcomeRelation.IS_CHECKED,
            ),
        )
        if not context.completed_subgoal_ids:
            subgoals = (first, unsupported)
        elif self.valid_replacement:
            subgoals = (
                SubgoalSpec(
                    subgoal_id="confirm-replacement",
                    objective="settings confirmation changed",
                    interaction=make_interaction('settings confirmation'),
                    depends_on=("write",),
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.ACTIVATE,
                    outcome=SubgoalOutcome(
                        subject="settings confirmation",
                        relation=SubgoalOutcomeRelation.HAS_CHANGED,
                    ),
                ),
            )
        else:
            subgoals = (unsupported,)
        return TaskPlan(
            plan_id=f"unsupported-flow-{context.current_plan_version + 1}",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=subgoals,
        )


class SubgoalAwarePlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse:
        active_id = request.step.active_step.step_id if request.step.active_step else "step"
        return PlannerProposalResponse(
            proposal=_activate_first(request, f"proposal-{active_id}"),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
        )


class CurrentStateReadOnlyTaskPlanner:
    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        return TaskPlan(
            plan_id="plan-current-read-only",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=1,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="text-field-changed",
                    objective="text field has changed",
                    interaction=make_interaction('text field'),
                    success_criteria=("text field has changed",),
                    evidence_requirements=("post-text evidence",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                    outcome=SubgoalOutcome(
                        subject="text field",
                        relation=SubgoalOutcomeRelation.HAS_CHANGED,
                    ),
                ),
                SubgoalSpec(
                    subgoal_id="submit-button-available",
                    objective="submit button is available",
                    interaction=make_interaction('submit_button'),
                    depends_on=("text-field-changed",),
                    success_criteria=("submit button is available",),
                    evidence_requirements=("current submit button observation",),
                    operation_class=OperationClass.READ_ONLY,
                    action_family=TaskPlanActionFamily.WAIT,
                    outcome=SubgoalOutcome(
                        subject="submit_button",
                        relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                    ),
                ),
            ),
        )


class CurrentStateReadOnlyPlanner:
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if not request.step.compatibility_active_step_objective:
            return PlannerDoneResponse(
                result={"completed_active_subgoal": "submit-button-available"}
            )
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id="change-text-field",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal=request.step.compatibility_active_step_objective,
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_affordance_id=request.observation.affordances[0].target_id,
                parameters={"text": "changed"},
            ),
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
        )


class InitialAlreadySatisfiedTaskPlanner:
    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        return TaskPlan(
            plan_id="plan-initial-current-state",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=1,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="submit-button-available",
                    objective="submit button is available",
                    interaction=make_interaction('submit_button'),
                    success_criteria=("submit button is available",),
                    evidence_requirements=("current submit button observation",),
                    operation_class=OperationClass.READ_ONLY,
                    action_family=TaskPlanActionFamily.WAIT,
                    outcome=SubgoalOutcome(
                        subject="submit_button",
                        relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                    ),
                ),
            ),
        )


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
            _current_state_read_only_snapshot(1, text_changed=False),
            _current_state_read_only_snapshot(1, text_changed=False),
            _current_state_read_only_snapshot(2, text_changed=True),
            _current_state_read_only_snapshot(2, text_changed=True),
            _current_state_read_only_snapshot(2, text_changed=True),
            _current_state_read_only_snapshot(2, text_changed=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


def _current_state_read_only_snapshot(
    sequence: int,
    *,
    text_changed: bool,
) -> BrowserSnapshot:
    environment_revision = f"environment-read-only-{sequence}"
    snapshot_id = f"snapshot-read-only-{sequence}"
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
        metadata={"text_changed": text_changed},
    )
    return BrowserSnapshot(observation, model)


def _current_state_read_only_task() -> TaskSpec:
    text_claim = SourcedTaskClaim(
        claim_id="claim-text-changed",
        kind=TaskClaimKind.EFFECT,
        statement="text field has changed",
        source_ref="current-state-read-only-request",
    )
    submit_claim = SourcedTaskClaim(
        claim_id="claim-submit-available",
        kind=TaskClaimKind.DEPENDENCY,
        statement="submit button is available",
        source_ref="current-state-read-only-request",
    )
    return TaskSpec(
        task_id="current-state-read-only",
        revision=1,
        objective="Enter text and submit",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("text field", "submit button"),
        success_criteria=("text field has changed", "submit button is available"),
        evidence_requirements=("post-text evidence", "current submit button observation"),
        requested_capabilities=("text.write",),
        source_request_ref="current-state-read-only-request",
        source_claims=(text_claim, submit_claim),
        obligations=(
            TaskObligationSpec(
                obligation_id="text-field-changed",
                kind=TaskObligationKind.EFFECT,
                subject="text field",
                relation=TaskObligationRelation.HAS_CHANGED,
                claim_ids=(text_claim.claim_id,),
                evidence_requirements=("post-text evidence",),
                blocking=True,
            ),
            TaskObligationSpec(
                obligation_id="submit-button-available",
                kind=TaskObligationKind.PREDICATE,
                subject="submit_button",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source=TaskObligationValueSource.OBSERVATION,
                claim_ids=(submit_claim.claim_id,),
                depends_on=("text-field-changed",),
                evidence_requirements=("current submit button observation",),
                blocking=True,
                terminal=True,
            ),
        ),
    )


def _current_state_availability_task() -> TaskSpec:
    submit_claim = SourcedTaskClaim(
        claim_id="claim-submit-available",
        kind=TaskClaimKind.DEPENDENCY,
        statement="submit button is available",
        source_ref="current-state-availability-request",
    )
    return TaskSpec(
        task_id="current-state-availability",
        revision=1,
        objective="Confirm submit button is available",
        operation_class=OperationClass.READ_ONLY,
        targets=("submit button",),
        success_criteria=("submit button is available",),
        evidence_requirements=("current submit button observation",),
        requested_capabilities=(),
        source_request_ref="current-state-availability-request",
        source_claims=(submit_claim,),
        obligations=(
            TaskObligationSpec(
                obligation_id="submit-button-available",
                kind=TaskObligationKind.PREDICATE,
                subject="submit_button",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source=TaskObligationValueSource.OBSERVATION,
                claim_ids=(submit_claim.claim_id,),
                evidence_requirements=("current submit button observation",),
                blocking=True,
                terminal=True,
            ),
        ),
    )


def test_coordinator_advances_serial_task_plan_only_after_verifier_evidence() -> None:
    result = compose_run_coordinator(
        observer=TwoStageObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=AsyncTwoStageTaskPlanner(),
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.DONE
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_subgoal_ids == ["write", "confirm"]
    assert result.result["task_plan_id"] == "plan-two-stage"
    events = [node.kind for node in result.trace.nodes]
    assert events.count("SubgoalCompleted") == 2
    assert events.index("TaskPlanAccepted") < events.index("SubgoalCompleted")
    completed = [node for node in result.trace.nodes if node.kind == "SubgoalCompleted"]
    assert all(node.payload["criterion_evidence_links"] for node in completed)


def test_coordinator_completes_current_state_read_only_subgoal_without_replanning() -> None:
    result = compose_run_coordinator(
        observer=CurrentStateReadOnlyObserver(),
        planner=CurrentStateReadOnlyPlanner(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder(
            "text_changed",
            capability="text.write",
            target_id="dom_input_1",
        ),
        task_planner=CurrentStateReadOnlyTaskPlanner(),
    ).run_sync(
        RunRequest(
            task_spec=_current_state_read_only_task(),
            capabilities=["text.write"],
        )
    )

    assert result.status == RuntimeStep.DONE
    assert result.state.task_plan is not None
    assert result.state.task_plan.plan_id == "plan-current-read-only"
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_subgoal_ids == [
        "text-field-changed",
        "submit-button-available",
    ]
    events = [node.kind for node in result.trace.nodes]
    assert "TaskReplanned" not in events
    current_state_completion = next(
        node
        for node in result.trace.nodes
        if node.kind == "SubgoalCompletedFromCurrentObservation"
    )
    assert current_state_completion.payload["subgoal_id"] == "submit-button-available"


def test_coordinator_prechecks_initial_already_satisfied_step_before_planning() -> None:
    result = compose_run_coordinator(
        observer=CurrentStateReadOnlyObserver(),
        planner=InitialAlreadySatisfiedPlanner(),
        executor=FakeExecutor(),
        task_planner=InitialAlreadySatisfiedTaskPlanner(),
    ).run_sync(RunRequest(task_spec=_current_state_availability_task()))

    assert result.status == RuntimeStep.DONE
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_subgoal_ids == [
        "submit-button-available"
    ]
    events = [node.kind for node in result.trace.nodes]
    assert "PlannerProposalRejected" not in events
    assert "FailureDetected" not in events
    assert "RecoveryStrategySelected" not in events
    assert "TaskPlanRejected" not in events
    assert "TaskReplanned" not in events
    assert events.index("TaskPlanAccepted") < events.index(
        "SubgoalCompletedFromCurrentObservation"
    )


def test_coordinator_commits_typed_task_plan_flow_replacement_reason() -> None:
    result = compose_run_coordinator(
        observer=TwoStageObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=UnsupportedThenValidTaskPlanner(),
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.DONE
    replanned = next(node for node in result.trace.nodes if node.kind == "TaskReplanned")
    assert replanned.payload["reason"] == "active_subgoal_outcome_state_unsupported"
    assert replanned.payload["planning_context"]["reason"] == (
        "active_subgoal_outcome_state_unsupported"
    )


def test_coordinator_traces_typed_task_replan_validation_issue() -> None:
    result = compose_run_coordinator(
        observer=TwoStageObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=UnsupportedThenValidTaskPlanner(valid_replacement=False),
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.ABORTED
    rejected = next(
        node for node in result.trace.nodes if node.kind == "TaskReplanRejected"
    )
    assert rejected.payload["replacement_reason"] == (
        "active_subgoal_outcome_state_unsupported"
    )
    assert [item["code"] for item in rejected.payload["issues"]] == [
        "entry_outcome_state_unsupported"
    ]


class EarlyFinishPlanner:
    def propose(self, request: PlanningRequest) -> PlannerDoneResponse:
        del request
        return PlannerDoneResponse(result={"unverified": True})


def test_task_plan_rejects_planner_finish_without_verifier_backed_progress() -> None:
    result = compose_run_coordinator(
        observer=FakeObserver(),
        planner=EarlyFinishPlanner(),
        executor=FakeExecutor(),
        task_planner=TwoStageTaskPlanner(),
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_subgoal_ids == []


class ReplanningTaskPlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[TaskPlanningContext] = []

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        self.calls += 1
        self.contexts.append(context)
        task_spec = context.task_spec
        return TaskPlan(
            plan_id=f"plan-replanned-{self.calls}",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=self.calls,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="write",
                    objective="Write settings",
                    interaction=make_interaction('Write settings'),
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    max_actions=2 if context.failures else 1,
                ),
            ),
        )


def test_coordinator_does_not_replan_into_an_unverified_non_idempotent_repeat() -> None:
    planner = ReplanningTaskPlanner()
    result = compose_run_coordinator(
        observer=ReplanObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        contract_builder=_metadata_builder("saved"),
        task_planner=planner,
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PRECONDITION_FAILED
    assert planner.calls == 1
    assert result.state.task_progress is not None
    assert result.state.task_progress.task_replan_count == 0
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
            _snapshot(1, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(3, saved=True),
            _snapshot(3, saved=True),
            _snapshot(3, saved=True),
            _snapshot(4, saved=True),
            _snapshot(4, saved=True),
            _snapshot(4, saved=True),
            _snapshot(4, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        if len(self.snapshots) == 1:
            return self.snapshots[0]
        return self.snapshots.pop(0)


class EvidenceAwareTaskPlanner:
    def __init__(self) -> None:
        self.contexts: list[TaskPlanningContext] = []

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        self.contexts.append(context)
        task = context.task_spec
        discovered = any(
            item.subgoal_id == "discover" and item.evidence_ids for item in context.criteria_evidence_ledger
        )
        discover = SubgoalSpec(
            subgoal_id="discover",
            objective="Discover saved state",
            interaction=make_interaction('Discover saved state'),
            success_criteria=("saved state is observed",),
            evidence_requirements=("independent saved observation",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
        )
        apply = SubgoalSpec(
            subgoal_id="apply",
            objective=(
                "Apply using verified saved-state evidence" if discovered else "Apply using the initial assumption"
            ),
            interaction=make_interaction('test target'),
            depends_on=("discover",),
            success_criteria=("settings are saved",),
            evidence_requirements=("independent saved observation",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            max_actions=1,
        )
        return TaskPlan(
            plan_id=f"evidence-plan-{context.current_plan_version + 1}",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(discover, apply),
            assumptions=("the initial apply route is sufficient",),
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


class EvidenceAwareContractBuilder(ContractBuilder):
    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        contract = super().build(proposal, task_spec, state, snapshot)
        active_id = state.task_progress.active_subgoal_id if state.task_progress else ""
        plan_version = state.task_plan.plan_version if state.task_plan else 0
        bound_id = active_id if active_id == "discover" or plan_version >= 2 else "unrelated"
        return replace(
            contract,
            verifier_plan=[
                VerifierSpec(
                    "observation_metadata",
                    "saved",
                    True,
                    criterion_ids=(criterion_id("subgoal", bound_id, 0),),
                    requirement_ids=(
                        evidence_requirement_id("subgoal", bound_id, 0),
                    ),
                )
            ],
            contract_hash="",
        )


def test_replan_uses_verified_evidence_and_preserves_progress_across_versions() -> None:
    task_planner = EvidenceAwareTaskPlanner()
    result = compose_run_coordinator(
        observer=EvidencePreservingObserver(),
        planner=EvidenceAwareActionPlanner(),
        executor=FakeExecutor(),
        contract_builder=EvidenceAwareContractBuilder(),
        task_planner=task_planner,
    ).run_sync(_semantic_envelope())

    assert result.status == RuntimeStep.DONE
    assert result.state.task_plan is not None
    assert result.state.task_plan.plan_version == 2
    assert result.state.task_plan.supersedes_plan_id == "evidence-plan-1"
    assert result.state.task_plan.subgoals[1].objective == "Apply using verified saved-state evidence"
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_subgoal_ids == ["discover", "apply"]
    assert len(task_planner.contexts) == 2
    replacement_context = task_planner.contexts[1]
    assert replacement_context.criteria_evidence_ledger[0].subgoal_id == "discover"
    assert replacement_context.criteria_evidence_ledger[0].evidence_ids
    assert replacement_context.failures[0].error_code == "subgoal_action_budget_exhausted"
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
    backend: str = "fake"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract.id,
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            error_code=RuntimeErrorCode.EXECUTION_FAILED,
            message="Timeout 1000 while saving record 42",
        )


def test_coordinator_groups_repeated_failure_and_aborts_loop() -> None:
    result = asyncio.run(
        compose_run_coordinator(
            observer=StableObserver(),
            planner=RepeatingPlanner(),
            executor=AlwaysFailExecutor(),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        idempotency_key="repeat-save:1",
                    )
                }
            ),
            task_planner=SingleStageTaskPlanner(),
        ).run(_semantic_envelope("run-loop"))
    )

    assert result.status == RuntimeStep.ABORTED
    assert result.state.current_failure is not None
    assert result.state.current_failure.error_code == RuntimeErrorCode.EXECUTION_FAILED.value
    assert result.state.current_recovery_decision is None
    recovery_outcomes = [
        node.payload["outcome"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    ]
    assert recovery_outcomes
    assert recovery_outcomes[-1]["success"] is False
    assert result.state.step_count == 2
    assert any(
        node.kind == "RecoveryStrategySelected"
        and node.payload["decision"]["kind"] == "retry_idempotent"
        for node in result.trace.nodes
    )
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryOutcomeRecorded" in events
    assert "FailureOwnerRouted" in events


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
        targets=("settings",),
        success_criteria=("settings are saved",),
        evidence_requirements=("saved observation",),
        requested_capabilities=("settings.write",),
        source_request_ref="semantic-request",
    )


def _semantic_envelope(task_id: str = "semantic-run") -> RunRequest:
    task = _semantic_task().model_copy(update={"task_id": task_id})
    return RunRequest(task_spec=task, capabilities=["settings.write"])


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
) -> ContractBuilder:
    return ContractBuilder(
        requirements={
            target_id: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "observation_metadata",
                        key,
                        expected,
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
            planner=AsyncSemanticSavePlanner(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "observation_metadata",
                                "saved",
                                True,
                                criterion_ids=(criterion_id("subgoal", "subgoal-1", 0),),
                                requirement_ids=(
                                    evidence_requirement_id("subgoal", "subgoal-1", 0),
                                ),
                            ),
                        ),
                        required_capabilities=("settings.write",),
                        idempotency_key="semantic-save-v1",
                        compensation="restore settings",
                    )
                }
            ),
            task_planner=SingleStageTaskPlanner(),
        ).run(RunRequest(task_spec=task, capabilities=["settings.write"]))
    )

    assert result.status == RuntimeStep.DONE
    assert result.result == {
        "task_plan_id": "plan-single-stage",
        "completed_subgoal_ids": ["subgoal-1"],
    }
    events = [node.kind for node in result.trace.nodes]
    assert events.count("PlannerProposalProduced") == 1
    assert result.state.latest_planner_proposal
    assert result.state.latest_planner_proposal["provenance"]["producer_id"] == "coordinator-test-planner"
    produced = next(node for node in result.trace.nodes if node.kind == "PlannerProposalProduced")
    assert produced.payload["provenance"]["source"] == "deterministic_rule"
    contract_event = next(node for node in result.trace.nodes if node.kind == "ContractBuilt")
    assert contract_event.payload["proposal_id"] == "proposal-save"


def test_action_stage_binds_terminal_verifier_to_explicit_active_progress_target() -> None:
    snapshot = _snapshot(1)
    state = StateKernel("generic-progress", "Record the Save control outcome")
    state.remember_observation(snapshot.observation)
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-generic-progress",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="save-observed",
                    objective="Save state is recorded",
                    interaction=ElementIntent(
                        "Save",
                        (SourceReference("request", "request:save"),),
                        role="button",
                    ),
                    success_criteria=("Save state is recorded",),
                    evidence_requirements=("post-action Save state",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.ACTIVATE,
                    outcome=SubgoalOutcome(
                        subject="Save",
                        relation=SubgoalOutcomeRelation.HAS_CHANGED,
                    ),
                ),
            ),
        )
    )
    state.activate_next_step()
    proposal = PlannerProposal(
        proposal_id="proposal-generic-progress",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        subgoal="Save state is recorded",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_button_1",
    )
    coordinator = compose_run_coordinator(
        observer=StableObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        contract_builder=ContractBuilder(
            requirements={
                "dom_button_1": ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "observation_metadata",
                            "saved",
                            True,
                            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
                        ),
                    ),
                    required_capabilities=("settings.write",),
                )
            }
        ),
        task_planner=None,
    )

    bound = coordinator.action_stage._bind(
        ActionStageInput(
            envelope=RunRequest(
                task_spec=_semantic_task().model_copy(update={"task_id": state.task_id}),
                capabilities=["settings.write"],
            ),
            decision=PlannerProposalResponse(
                proposal=proposal,
                proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            ),
            snapshot=snapshot,
            state_view=runtime_state_snapshot(state),
            remaining_budgets=RemainingRecoveryBudgets(),
        )
    )

    assert isinstance(bound, tuple)
    contract = bound[0]
    assert contract.verifier_plan[0].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL
    assert contract.verifier_plan[0].criterion_ids == (
        criterion_id("subgoal", "save-observed", 0),
    )
    assert contract.verifier_plan[0].requirement_ids == (
        evidence_requirement_id("subgoal", "save-observed", 0),
    )

    signature = bound[1]
    state.record_action_progress(
        signature,
        snapshot.observation.environment_revision,
        verification_passed=True,
        effect_satisfied=True,
        post_page_revision=snapshot.observation.page_revision,
    )
    repeated_proposal = proposal.model_copy(
        update={
            "proposal_id": "proposal-generic-progress-repeat",
            "based_on_state_version": state.version,
        }
    )
    blocked = coordinator.action_stage._bind(
        ActionStageInput(
            envelope=RunRequest(
                task_spec=_semantic_task().model_copy(update={"task_id": state.task_id}),
                capabilities=["settings.write"],
            ),
            decision=PlannerProposalResponse(
                proposal=repeated_proposal,
                proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            ),
            snapshot=snapshot,
            state_view=runtime_state_snapshot(state),
            remaining_budgets=RemainingRecoveryBudgets(),
        )
    )

    assert not isinstance(blocked, tuple)
    assert blocked.failure is not None
    assert blocked.failure.error_code == "progress_credit_invariant"
    assert blocked.failure.phase.value == "progress"
    assert classify_failure(blocked.failure).owner == FailureOwner.PROGRESS
    assert blocked.directive == LoopDirective.NEXT_STAGE


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

    def capture(self) -> BrowserSnapshot:
        return _snapshot(1, saved=self.saved)


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
        planner=RepeatingSemanticPlanner(),
        executor=executor,
        contract_builder=_semantic_guard_builder(),
        task_planner=None,
    ).run_sync(RunRequest(task_spec=_semantic_task(), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert executor.calls == 1
    assert result.state.latest_progress_guard is not None
    assert result.state.latest_progress_guard["reason"] == "effect_already_satisfied"
    blocked = [node for node in result.trace.nodes if node.kind == "PlannerProgressBlocked"]
    assert blocked[-1].payload["error_code"] == RuntimeErrorCode.EFFECT_ALREADY_SATISFIED.value


def test_failed_effect_is_not_repeated_without_a_validated_recovery_delta(tmp_path) -> None:
    executor = CountingExecutor()
    result = compose_run_coordinator(
        observer=StableSavedObserver(saved=False),
        planner=RepeatingSemanticPlanner(),
        executor=executor,
        contract_builder=_semantic_guard_builder(),
        task_planner=None,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
    ).run_sync(RunRequest(task_spec=_semantic_task(), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PRECONDITION_FAILED
    assert executor.calls == 1
    assert result.state.latest_progress_guard is None
    assert result.state.current_failure is not None
    assert result.state.current_failure.message == "verifier failed: observation_metadata:saved"
    assert result.state.current_failure.verification_ref.endswith("verification_0001.json")
    assert result.state.current_failure.evidence_refs == (
        result.state.current_failure.verification_ref,
    )
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryStateInspected" in events
    assert "RecoveryAborted" in events


def test_progress_guard_allows_repeated_verified_delta_until_effect_is_satisfied() -> None:
    state = StateKernel("slider", "move slider several steps")
    state.remember_observation(Observation("rev-2"))
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
    state.remember_observation(Observation("rev-3", page_revision="page-1"))
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
        del messages, config
        if output_schema.__name__ == "TaskObligationCoverageReview":
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": ["claim-save-settings"],
                }
            )
        return output_schema.model_validate(
            IntentDraft(
                objective="Save settings",
                requested_effects=(
                    RequestedEffect(
                        operation_class=OperationClass.REVERSIBLE_WRITE,
                        target="settings",
                        capability="settings.write",
                        source_ref="pipeline-run",
                    ),
                ),
                candidate_success_criteria=("settings are saved",),
                candidate_evidence_requirements=("saved observation",),
                candidate_source_claims=(
                    SourcedTaskClaim(
                        claim_id="claim-save-settings",
                        kind=TaskClaimKind.TERMINAL,
                        statement="save settings",
                        source_ref="pipeline-run",
                    ),
                ),
                candidate_obligations=(
                    TaskObligationSpec(
                        obligation_id="obligation-save-settings",
                        kind=TaskObligationKind.EFFECT,
                        subject="settings",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        claim_ids=("claim-save-settings",),
                        evidence_requirements=("saved observation",),
                        terminal=True,
                    ),
                ),
            ).model_dump()
        )


def test_raw_request_pipeline_preserves_compiler_to_contract_lineage() -> None:
    pipeline = GeneralistTaskPipeline(
        compiler=LLMIntentCompiler(_PipelineIntentModel()),
        coordinator=compose_run_coordinator(
            observer=FakeObserver(),
            planner=ActiveSubgoalSavePlanner(),
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
        "SourceLedgerBuilt",
        "IntentDraftProduced",
        "TaskObligationCoverageReviewed",
        "TaskSpecCreated",
        "TaskCreated",
    ]
    assert "PlannerProposalProduced" in [node.kind for node in result.trace.nodes]
    assert "ContractBuilt" in [node.kind for node in result.trace.nodes]


def test_async_planner_resolution_works_inside_an_existing_event_loop() -> None:
    async def decide() -> PlannerDecision:
        return PlannerDecision(done=True, result={"ok": True})

    async def outer() -> PlannerDecision:
        return _resolve_planner_decision(decide())

    assert asyncio.run(outer()).result == {"ok": True}


def test_coordinator_rejects_stale_task_revision_before_execution() -> None:
    task = _semantic_task()
    result = asyncio.run(
        compose_run_coordinator(
            observer=StableObserver(),
            planner=AsyncSemanticSavePlanner(revision=2),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(),
                         task_planner=None,
        ).run(RunRequest(task_spec=task))
    )

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.STALE_TASK_REVISION
    assert "PlannerProposalRejected" in [node.kind for node in result.trace.nodes]
    assert "PlannerProposalValidated" not in [node.kind for node in result.trace.nodes]
    assert "PlannerProposalProduced" not in [node.kind for node in result.trace.nodes]
    assert result.state.last_receipt is None


class MissingProvenancePlanner(AsyncSemanticSavePlanner):
    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        response = await super().propose(request)
        return replace(response, proposal_provenance=None) if isinstance(response, PlannerProposalResponse) else response


def test_coordinator_rejects_missing_proposal_provenance_before_execution() -> None:
    result = asyncio.run(
        compose_run_coordinator(
            observer=StableObserver(),
            planner=MissingProvenancePlanner(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(),
                         task_planner=None,
        ).run(RunRequest(task_spec=_semantic_task()))
    )

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
    rejected = next(node for node in result.trace.nodes if node.kind == "PlannerProposalRejected")
    assert rejected.payload["rejection_code"] == "missing_provenance"
    assert rejected.payload["provenance"] is None
    assert "PlannerProposalValidated" not in [node.kind for node in result.trace.nodes]
    assert result.state.last_receipt is None
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase.value == "proposal_validation"
    terminal = next(
        node for node in reversed(result.trace.nodes) if node.kind == "FailureOwnerRouted"
    )
    assert terminal.payload["owner"] == "terminal"


class ClarifyingPlanner(AsyncSemanticSavePlanner):
    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerClarificationResponse:
        del request
        return PlannerClarificationResponse(
            "Which settings profile should be changed?"
        )


def test_semantic_planner_can_request_clarification_without_contract_or_effect() -> None:
    result = asyncio.run(
        compose_run_coordinator(
            observer=StableObserver(),
            planner=ClarifyingPlanner(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(),
                         task_planner=None,
        ).run(RunRequest(task_spec=_semantic_task()))
    )

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert result.state.last_receipt is None
    assert result.result["clarification"] == "Which settings profile should be changed?"
    assert "ClarificationRequested" in [node.kind for node in result.trace.nodes]


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


def test_request_planner_unsupported_reason_reaches_recovery_failure() -> None:
    result = compose_run_coordinator(
        observer=StableObserver(),
        planner=UnsupportedChoicePlanner(),
        executor=FakeExecutor(),
             task_planner=None,
    ).run_sync(RunRequest(task_spec=_semantic_task()))

    assert result.state.last_receipt is None
    assert result.state.current_failure is not None
    assert result.state.current_failure.error_code == "no_feasible_action_choice"
    assert result.state.current_failure.message == (
        "Runtime could not construct an active-step action choice."
    )
    assert result.state.current_recovery_decision is None
    assert any(
        node.kind == "FailureOwnerRouted" and node.payload["owner"] == "terminal"
        for node in result.trace.nodes
    )


def test_legacy_planner_no_proposal_fails_closed_without_replan() -> None:
    result = compose_run_coordinator(
        observer=StableObserver(),
        planner=LegacyNoProposalPlanner(),
        executor=FakeExecutor(),
        budget=RunBudget(max_recoveries=2),
           task_planner=None,
    ).run_sync(RunRequest(task_spec=_semantic_task()))

    assert result.state.current_failure is not None
    assert result.state.current_failure.error_code == "legacy_decision_without_proposal"
    assert result.state.current_recovery_decision is None
    assert any(
        node.kind == "FailureOwnerRouted" and node.payload["owner"] == "terminal"
        for node in result.trace.nodes
    )
    assert result.state.replan_count == 0


def test_coordinator_checkpoints_typed_provider_failure_as_resumable_deferral(tmp_path) -> None:
    task = _semantic_task().model_copy(update={"task_id": "provider-defer"})
    result = compose_run_coordinator(
        observer=StableObserver(),
        planner=QuotaExhaustedPlanner(),
        executor=FakeExecutor(),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
              task_planner=None,
    ).run_sync(RunRequest(task_spec=task))

    assert result.status == RuntimeStep.DEFERRED
    assert result.error_code == RuntimeErrorCode.QUOTA_EXHAUSTED
    assert result.result == {
        "deferred": True,
        "provider_failure": "quota_exhausted",
        "retry_after_s": 60,
        "resumable": True,
    }
    event = next(node for node in result.trace.nodes if node.kind == "PlannerDeferred")
    assert event.payload["resumable"] is True
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase.value == "provider_context"
    handoff = next(
        node for node in reversed(result.trace.nodes) if node.kind == "FailureOwnerRouted"
    )
    assert handoff.payload["owner"] == "terminal"
    assert "FailureDetected" in [node.kind for node in result.trace.nodes]
    assert (tmp_path / "artifacts/provider-defer/run.json").exists()
