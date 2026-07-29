from __future__ import annotations

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.simplified_runtime_contracts import StepActivityStatus
from affordance_runtime.simplified_step_projection import LegacyStepProjectionStatus
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    OperationClass,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
)
from affordance_runtime.task_planning import (
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)


def _fixture() -> tuple[TaskEnvelope, StateKernel, BrowserSnapshot]:
    task = TaskSpec(
        task_id="request-task",
        revision=1,
        objective="Save the display name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("display name",),
        success_criteria=("display name is saved",),
        evidence_requirements=("fresh saved-state observation",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-source",
        source_claims=(
            SourcedTaskClaim(
                claim_id="claim:enter-name",
                kind=TaskClaimKind.EFFECT,
                statement="display name equals Ada",
                source_ref="request-source",
                source_unit_ids=("unit:enter-name",),
            ),
        ),
        obligations=(
            TaskObligationSpec(
                obligation_id="step:enter-name",
                kind=TaskObligationKind.EFFECT,
                subject="display name",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.LITERAL,
                expected_value="Ada",
                claim_ids=("claim:enter-name",),
                evidence_requirements=("fresh input-value observation",),
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="display name",
                        relation=TaskObligationRelation.EQUALS,
                        value_ref="Ada",
                        minimum_strength="independent",
                        source_constraints=("post_action_observation",),
                    ),
                ),
                terminal=True,
            ),
        ),
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


def test_builder_projects_identity_observation_and_budget_without_mutation() -> None:
    from affordance_runtime.planning_request_builder import (
        PlanningRequestBuilder,
        PlanningRequestLimits,
    )

    envelope, state, snapshot = _fixture()
    before_version = state.version

    request = PlanningRequestBuilder(
        limits=PlanningRequestLimits(
            max_affordances=2,
            max_artifact_refs=1,
        ),
        allow_finish=False,
    ).build(envelope, state, snapshot)

    assert request.identity.task_spec_identity == envelope.task_spec.identity
    assert request.identity.task_revision == 1
    assert request.identity.evaluated_at_state_version == before_version
    assert request.identity.snapshot_id == "snapshot-1"
    assert request.identity.page_revision == "page-1"
    assert request.identity.environment_revision == "environment-1"
    assert len(request.observation.observed_text) == 2_000
    assert len(request.observation.affordances) == 2
    assert request.observation.artifact_refs[0].startswith("artifact:sha256:")
    assert request.remaining_budget.steps == 20
    assert "finish" not in request.permitted_action_kinds
    assert state.version == before_version


def test_builder_does_not_activate_ready_legacy_step() -> None:
    from affordance_runtime.planning_request_builder import PlanningRequestBuilder

    envelope, state, snapshot = _fixture()
    task = envelope.task_spec
    assert task is not None
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-request",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                    SubgoalSpec(
                        subgoal_id="step:enter-name",
                        objective="display name input equals Ada",
                        outcome=None,
                        success_criteria=("display name input equals Ada",),
                    evidence_requirements=("fresh input-value observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                ),
            ),
        )
    )
    before_version = state.version

    request = PlanningRequestBuilder().build(envelope, state, snapshot)

    assert request.step.activity_status == StepActivityStatus.READY_NOT_ACTIVATED
    assert request.step.active_step is None
    assert request.step.progress is not None
    assert request.step.progress.ready_step_ids == ("step:enter-name",)
    assert state.plan_progress is not None
    assert state.plan_progress.active_subgoal_id == ""
    assert state.version == before_version


def test_builder_preserves_invalid_step_projection_instead_of_no_plan() -> None:
    from affordance_runtime.planning_request import PlannerStepProjectionStatus
    from affordance_runtime.planning_request_builder import PlanningRequestBuilder

    envelope, state, snapshot = _fixture()
    task = envelope.task_spec
    assert task is not None
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-request",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="unknown-step",
                    objective="unknown step",
                    outcome=None,
                    success_criteria=("unknown",),
                    evidence_requirements=("fresh input-value observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                ),
            ),
        )
    )

    request = PlanningRequestBuilder().build(envelope, state, snapshot)

    assert request.step.projection_status == PlannerStepProjectionStatus.PROJECTION_INVALID
    assert request.step.projection_reason
    assert request.step.activity_status == StepActivityStatus.NO_PLAN
    assert request.step.permits_effectful_actions is False
    assert not {
        "type_text",
        "activate",
        "select_option",
        "press_key",
        "drag",
        "navigate",
    } & set(request.permitted_action_kinds)
    assert request.step.projection_status.value == LegacyStepProjectionStatus.PROJECTION_INVALID.value
