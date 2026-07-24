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
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_planning import (
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)


def _fixture() -> tuple[TaskEnvelope, StateKernel, BrowserSnapshot]:
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
    state.remember_observation(observation)
    return TaskEnvelope(task_spec=task, capabilities=["settings.write"]), state, BrowserSnapshot(observation, model)


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


def test_builder_exposes_typed_active_subgoal_action_family() -> None:
    envelope, state, snapshot = _fixture()
    task = envelope.task_spec
    assert task is not None
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-context",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="enter-name",
                    objective="display name input equals Ada",
                    success_criteria=("display name input equals Ada",),
                    evidence_requirements=("fresh input-value observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                ),
            ),
        )
    )

    context = PlannerContextBuilder().build(envelope, state, snapshot)

    assert context.active_subgoal == "display name input equals Ada"
    assert context.active_subgoal_action_family == "type_text"


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
            TaskEnvelope("legacy", "Save the display name"),
            state,
            snapshot,
        )
