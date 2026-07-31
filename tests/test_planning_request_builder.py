from __future__ import annotations

from dataclasses import replace

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    DomGroundingPayload,
    GroundingCandidate,
    GroundingSource,
    UnifiedAffordance,
)
from affordance_runtime.grounding import (
    EvidenceKind as GroundingEvidenceKind,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StepActivityStatus,
)
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
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
from runtime_test_support import make_interaction


def _fixture() -> tuple[RunRequest, StateKernel, BrowserSnapshot]:
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
    return RunRequest(task_spec=task, capabilities=["settings.write"]), state, BrowserSnapshot(observation, model)


def _name_interaction() -> ElementIntent:
    return ElementIntent(
        "Name",
        (SourceReference("request-source", "unit:enter-name", "claim:enter-name"),),
        role="textbox",
    )


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


def test_builder_preserves_bounded_semantic_state_before_incidental_keys() -> None:
    from affordance_runtime.planning_request_builder import PlanningRequestBuilder

    envelope, state, snapshot = _fixture()
    first = snapshot.affordance_model.affordances[0]
    noisy_state = {
        **{f"aria_noise_{index:02d}": f"noise-{index}" for index in range(20)},
        "element_tag": "input",
        "input_type": "text",
        "control_value": "exact value",
        "visible": True,
        "enabled": True,
    }
    affordance_model = replace(
        snapshot.affordance_model,
        affordances=[replace(first, state=noisy_state)],
    )
    bounded_snapshot = BrowserSnapshot(snapshot.observation, affordance_model)

    request = PlanningRequestBuilder().build(envelope, state, bounded_snapshot)
    projected_state = dict(request.observation.affordances[0].state)

    assert len(projected_state) <= 12
    assert projected_state["element_tag"] == "input"
    assert projected_state["input_type"] == "text"
    assert projected_state["control_value"] == "exact value"
    assert projected_state["visible"] is True
    assert projected_state["enabled"] is True


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
                        interaction=_name_interaction(),
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
    assert state.task_progress is not None
    assert state.task_progress.active_subgoal_id == ""
    assert state.version == before_version


def test_builder_projects_active_legacy_step_action_family() -> None:
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
                    interaction=_name_interaction(),
                    outcome=SubgoalOutcome(
                        subject="display name",
                        relation=SubgoalOutcomeRelation.EQUALS,
                        value="Ada",
                    ),
                    success_criteria=("display name input equals Ada",),
                    evidence_requirements=("fresh input-value observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                ),
            ),
        )
    )
    state.activate_next_step()

    request = PlanningRequestBuilder().build(envelope, state, snapshot)

    assert request.step.activity_status == StepActivityStatus.ACTIVE
    assert request.step.active_step_action_family == "type_text"


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
                    interaction=make_interaction('unknown step'),
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


def test_builder_does_not_embed_legacy_terminal_admission_without_mutation() -> None:
    from affordance_runtime.planning_request_builder import PlanningRequestBuilder

    envelope, state, snapshot = _fixture()
    task = envelope.task_spec
    assert task is not None
    terminal = TaskObligationSpec(
        obligation_id="step:submit",
        kind=TaskObligationKind.EFFECT,
        subject="settings submission",
        relation=TaskObligationRelation.IS_COMPLETED,
        depends_on=("step:enter-name",),
        claim_ids=("claim:enter-name",),
        evidence_requirements=("fresh submit observation",),
        typed_evidence_requirements=(
            EvidenceRequirement(
                kind=EvidenceKind.ACCESSIBILITY_STATE,
                subject="settings submission",
                relation=TaskObligationRelation.IS_COMPLETED,
                minimum_strength="independent",
                source_constraints=("post_action_observation",),
            ),
        ),
        terminal=True,
    )
    envelope = RunRequest(
        task_spec=task.model_copy(
            update={"obligations": (*task.obligations, terminal)}
        ),
        capabilities=["settings.write"],
    )
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
                    interaction=make_interaction('display name'),
                    outcome=SubgoalOutcome(
                        subject="display name",
                        relation=SubgoalOutcomeRelation.EQUALS,
                        value="Ada",
                    ),
                    success_criteria=("display name input equals Ada",),
                    evidence_requirements=("fresh input-value observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                ),
                SubgoalSpec(
                    subgoal_id="step:submit",
                    objective="settings submission is completed",
                    interaction=make_interaction('settings submission'),
                    depends_on=("step:enter-name",),
                    outcome=SubgoalOutcome(
                        subject="settings submission",
                        relation=SubgoalOutcomeRelation.IS_COMPLETED,
                    ),
                    success_criteria=("settings submission is completed",),
                    evidence_requirements=("fresh submit observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.ACTIVATE,
                ),
            ),
        )
    )
    state.task_progress = PlanProgress(
        active_subgoal_id="step:submit",
        completed_subgoal_ids=["step:enter-name"],
        evidence_by_subgoal={"step:enter-name": ["artifact:verification"]},
    )
    before_version = state.version
    snapshot = BrowserSnapshot(
        observation=replace(
            snapshot.observation,
            target_fingerprints={"candidate:dom:submit": "sha256:submit"},
        ),
        affordance_model=snapshot.affordance_model,
        unified_affordances=(
            UnifiedAffordance(
                semantic_target_id="semantic:submit",
                role="button",
                label="settings submission",
                supported_actions=frozenset({"activate"}),
                grounding_candidates=(
                    GroundingCandidate(
                        candidate_id="candidate:dom:submit",
                        semantic_target_id="semantic:submit",
                        source=GroundingSource.DOM,
                        payload=DomGroundingPayload(backend_handle="submit"),
                        compatible_executor="browsergym",
                        observation_epoch_id=snapshot.observation.snapshot_id,
                        environment_revision=snapshot.observation.environment_revision,
                        page_revision=snapshot.observation.page_revision,
                        target_fingerprint="sha256:submit",
                        supported_actions=frozenset({"activate"}),
                        evidence_kinds=frozenset({GroundingEvidenceKind.STRUCTURAL}),
                    ),
                ),
            ),
        ),
    )

    request = PlanningRequestBuilder().build(envelope, state, snapshot)

    assert request.admission is None
    assert state.version == before_version
