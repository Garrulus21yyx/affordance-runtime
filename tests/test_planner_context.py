import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.planner_context import (
    PlannerContextBuilder,
    PlannerLimits,
    build_planner_context,
)
from affordance_runtime.planning_request_builder import (
    PlanningRequestBuilder,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength
from affordance_runtime.simplified_runtime_contracts import SourceReference, StateCriterion, StepSpec
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_plan_contracts import TaskPlan, TaskPlanGeneratorSource
from runtime_test_support import canonical_observation, make_interaction, remember_observation


def _fixture() -> tuple[RunRequest, StateKernel, BrowserSnapshot]:
    task = TaskSpec(
        task_id="context-task",
        revision=1,
        objective="Save the display name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("display name",),
        success_criteria=("display name is saved",),
        evidence_requirements=("fresh saved-state observation",),
        requested_capabilities=("settings.write",),
        source_request_ref="context-request",
    )
    model = DomAdapter().transduce(
        "<main><label>Name <input id='name'></label><button id='save'>Save</button></main>",
        environment_revision="environment-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
    )
    observation = Observation(
        environment_revision="environment-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        artifact_refs=["artifact:first", "artifact:last"],
        metadata={"visible_text": "x" * 2_100},
    )
    state = StateKernel(task_id=task.task_id, goal=task.objective)
    remember_observation(state, observation)
    return RunRequest(task_spec=task, capabilities=["settings.write"]), state, BrowserSnapshot(observation, model)


def test_builder_bounds_untrusted_context_and_exposes_only_semantic_inventory() -> None:
    envelope, state, snapshot = _fixture()
    builder = PlannerContextBuilder(
        limits=PlannerLimits(max_affordances=2, max_artifact_refs=1, max_accepted_knowledge=2),
        accepted_knowledge=("old", "current-a", "current-b"),
        allow_finish=False,
    )

    context = builder.build(envelope, state, snapshot)

    assert len(context.observed_text) == 2_000
    assert len(context.affordances) == 2
    assert len(context.selected_artifact_refs) == 1
    assert context.selected_artifact_refs[0].startswith("artifact:sha256:")
    assert "artifact:last" not in context.model_dump_json()
    assert context.accepted_knowledge == ("current-a", "current-b")
    assert context.granted_capabilities == ("settings.write",)
    assert "finish" not in context.permitted_action_kinds
    assert {item.action for item in context.affordances} == {"click", "type"}
    assert {"activate", "type_text"}.issubset(context.permitted_action_kinds)
    assert "selector" not in context.model_dump_json()
    assert "backend_handle" not in context.model_dump_json()
    assert "task_id" not in context.task_spec
    assert "context-task" not in context.model_dump_json()


def test_compatibility_function_matches_explicit_builder() -> None:
    envelope, state, snapshot = _fixture()
    limits = PlannerLimits(max_artifact_refs=1)

    direct = PlannerContextBuilder(limits=limits).build(envelope, state, snapshot)
    compatible = build_planner_context(envelope, state, snapshot, limits=limits)

    assert compatible == direct


def test_planning_request_builder_does_not_expose_legacy_pending_obligations() -> None:
    envelope, state, snapshot = _fixture()
    state.pending_obligations = ["legacy:string-obligation"]  # type: ignore[attr-defined]

    request = PlanningRequestBuilder().build(
        envelope, state, canonical_observation(snapshot)
    )
    context = PlannerContextBuilder().build(request)

    assert request.pending_evidence_obligations == ()
    assert context.pending_evidence_obligations == ()


def test_request_context_does_not_expose_ready_step_as_active() -> None:
    from affordance_runtime.planning_request import (
        PlannerObservationView,
        PlannerStepProjectionStatus,
        PlannerStepView,
        PlannerTaskView,
        PlanningRequest,
        PlanningRequestIdentity,
    )
    from affordance_runtime.simplified_runtime_contracts import (
        CriterionEvidencePolicy,
        ElementIntent,
        EvidenceStrength,
        SourceReference,
        StateCriterion,
        StateCriterionRelation,
        StepActivityStatus,
        StepProgressView,
        StepSpec,
        TaskPlanView,
    )

    criterion = StateCriterion(
        criterion_id="ready-step",
        subject="display name",
        relation=StateCriterionRelation.EQUALS,
        expected_value="Ada",
        evidence_policy=CriterionEvidencePolicy(
            minimum_strength=EvidenceStrength.INDEPENDENT,
            allowed_source_kinds=("dom_state",),
        ),
        source_refs=(
            SourceReference(
                source_id="source:user",
                source_unit_id="unit:ready-step",
            ),
        ),
    )
    step = StepSpec(
        step_id="ready-step",
        objective="display name input equals Ada",
        interaction=ElementIntent("display name input", criterion.source_refs),
        completion_criteria=(criterion,),
        source_refs=criterion.source_refs,
    )
    request = PlanningRequest(
        identity=PlanningRequestIdentity(
            task_spec_identity="sha256:task",
            task_revision=1,
            evaluated_at_state_version=4,
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
        ),
        task=PlannerTaskView(
            task_spec_identity="sha256:task",
            task_revision=1,
            objective="Save display name",
            constraints=(),
            capabilities=(),
            task_completion_criterion=None,
            task_completion_projection_status="pending",
        ),
        step=PlannerStepView(
            plan=TaskPlanView(
                plan_id="plan:1",
                plan_version=1,
                task_spec_identity="sha256:task",
                task_revision=1,
                steps=(step,),
                active_step_id=None,
            ),
            progress=StepProgressView(
                plan_id="plan:1",
                plan_version=1,
                active_step_id=None,
                activity_status=StepActivityStatus.READY_NOT_ACTIVATED,
                ready_step_ids=("ready-step",),
            ),
            active_step=None,
            activity_status=StepActivityStatus.READY_NOT_ACTIVATED,
            projection_status=PlannerStepProjectionStatus.PROJECTED,
        ),
        observation=PlannerObservationView(
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
            observed_text="",
            affordances=(),
            artifact_refs=(),
        ),
    )
    context = PlannerContextBuilder().build(request)

    assert context.active_subgoal == "Save display name"
    assert context.active_subgoal_action_family == ""


def _context_plan(task: TaskSpec, state: StateKernel) -> TaskPlan:
    source_refs = (SourceReference("request", "context-requirement"),)
    return TaskPlan(
        plan_id="plan-context",
        task_id=task.task_id,
        task_revision=task.revision,
        plan_version=1,
        based_on_state_version=state.version,
        based_on_observation_ref="snapshot-1",
        generated_by=TaskPlanGeneratorSource.RULE,
        steps=(
            StepSpec(
                step_id="enter-name",
                objective="display name input equals Ada",
                interaction=make_interaction("display name input equals Ada"),
                completion_criteria=(
                    StateCriterion(
                        criterion_id="criterion:enter-name",
                        source_refs=source_refs,
                        subject="display name input",
                        relation=CriterionRelation.EQUALS,
                        expected_value="Ada",
                        evidence_policy=EvidencePolicy(
                            minimum_strength=EvidenceStrength.INDEPENDENT,
                            allowed_source_kinds=("dom_state",),
                        ),
                    ),
                ),
                source_refs=source_refs,
            ),
        ),
    )


def test_builder_exposes_canonical_active_step_without_prescribing_action_family() -> None:
    envelope, state, snapshot = _fixture()
    task = envelope.task_spec
    assert task is not None
    state.install_task_plan(_context_plan(task, state))

    state.activate_next_step()

    context = PlannerContextBuilder().build(envelope, state, snapshot)

    assert context.active_subgoal == "display name input equals Ada"
    assert context.active_subgoal_action_family == ""


def test_builder_does_not_activate_next_step_while_building_read_only_context() -> None:
    envelope, state, snapshot = _fixture()
    task = envelope.task_spec
    assert task is not None
    state.install_task_plan(_context_plan(task, state))
    assert state.task_progress is not None
    assert state.task_progress.active_step_id == ""
    before_version = state.version

    context = PlannerContextBuilder().build(envelope, state, snapshot)

    assert context.active_subgoal == task.objective
    assert context.active_subgoal_action_family == ""
    assert state.task_progress.active_step_id == ""
    assert state.version == before_version


def test_builder_exposes_current_recoverable_proposal_rejection() -> None:
    envelope, state, snapshot = _fixture()
    state.current_failure = make_failure_envelope(
        run_id=state.task_id,
        phase=FailurePhase.PROPOSAL_VALIDATION,
        failure_class=FailureClass.VALIDATION,
        error_code="planner_proposal_rejected",
        message="target_out_of_scope:semantic:wrong-target",
        state_version=state.version,
        proposal_rejection=ProposalRejectionContext(
            code="target_out_of_scope",
            reason_code="relational_evidence_not_proven",
            semantic_target_id="semantic:wrong-target",
        ),
        recoverable=True,
        remaining_budgets=RemainingRecoveryBudgets(),
    )

    summary = PlannerContextBuilder().build(envelope, state, snapshot).recovery_summary

    assert summary == {
        "kind": "proposal_validation",
        "error_code": "planner_proposal_rejected",
        "message": "target_out_of_scope:semantic:wrong-target",
        "recoverable": True,
        "proposal_rejection": {
            "code": "target_out_of_scope",
            "reason_code": "relational_evidence_not_proven",
            "semantic_target_id": "semantic:wrong-target",
        },
    }


def test_builder_rejects_unvalidated_legacy_envelope() -> None:
    _envelope, state, snapshot = _fixture()

    with pytest.raises(ValueError, match="validated TaskSpec"):
        PlannerContextBuilder().build(
            RunRequest("legacy", "Save the display name"),
            state,
            snapshot,
        )
