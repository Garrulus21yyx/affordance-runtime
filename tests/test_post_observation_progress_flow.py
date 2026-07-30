from affordance_runtime.adapters.dom import PageAffordanceModel
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    Affordance,
    AffordanceLease,
    Observation,
    Surface,
)
from affordance_runtime.criteria import (
    CriteriaEvidenceMatchReport,
    CriterionEvidenceLink,
    SubgoalVerificationReport,
)
from affordance_runtime.obligation_progress_shadow import (
    ObligationProgressShadowClassification,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    GraphConstructionSource,
    OperationClass,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
    TaskStructure,
)
from affordance_runtime.task_plan_progress_flow import (
    commit_post_observation_progress,
    commit_task_skill_terminal_progress,
    commit_verified_task_progress,
)
from affordance_runtime.task_planning import (
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification import VerificationReport, VerificationStatus


class _Budget:
    max_steps = 10
    max_observations = 10
    max_replans = 10
    max_recoveries = 10
    max_effectful_actions = 10


class _PassingSubgoalVerifier:
    def verify(self, subgoal, report, observation):  # type: ignore[no-untyped-def]
        return SubgoalVerificationReport(
            subgoal.subgoal_id,
            CriteriaEvidenceMatchReport(
                passed=True,
                links=(
                    CriterionEvidenceLink(
                        criterion_id=f"criterion:{subgoal.subgoal_id}",
                        evidence_id="evidence:verified",
                        requirement_ids=(f"evidence:{subgoal.subgoal_id}",),
                    ),
                ),
            ),
        )


def _obligation(
    obligation_id: str,
    *,
    terminal: bool = False,
    depends_on: tuple[str, ...] = (),
    kind: TaskObligationKind = TaskObligationKind.EFFECT,
    relation: TaskObligationRelation = TaskObligationRelation.HAS_CHANGED,
) -> TaskObligationSpec:
    return TaskObligationSpec(
        obligation_id=obligation_id,
        kind=kind,
        subject="field",
        relation=relation,
        value_source=TaskObligationValueSource.NONE,
        expected_value="",
        claim_ids=(f"claim:{obligation_id}",),
        depends_on=depends_on,
        evidence_requirements=(f"evidence:{obligation_id}",),
        typed_evidence_requirements=(
            EvidenceRequirement(
                kind=EvidenceKind.DOM_STATE,
                subject="field",
                relation=relation,
                minimum_strength="independent",
                source_constraints=("source:request:clause:0",),
            ),
        ),
        blocking=True,
        terminal=terminal,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _task_spec(*obligations: TaskObligationSpec) -> TaskSpec:
    return TaskSpec(
        task_id="task-post-observation",
        revision=1,
        objective="advance progress",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("field",),
        success_criteria=("terminal satisfied",),
        source_request_ref="source:request",
        source_claims=tuple(
            SourcedTaskClaim(
                claim_id=f"claim:{obligation.obligation_id}",
                kind=TaskClaimKind.TERMINAL
                if obligation.terminal
                else TaskClaimKind.EFFECT,
                statement=f"{obligation.subject} {obligation.relation.value}",
                source_ref="source:request:clause:0",
                source_unit_ids=("source:request:clause:0",),
                construction_source=GraphConstructionSource.CANONICAL_COMPILER,
            )
            for obligation in obligations
        ),
        obligations=obligations,
        evidence_requirements=("independent evidence",),
    )


def _subgoal(
    subgoal_id: str,
    *,
    relation: SubgoalOutcomeRelation = SubgoalOutcomeRelation.HAS_CHANGED,
    depends_on: tuple[str, ...] = (),
    action_family: TaskPlanActionFamily = TaskPlanActionFamily.TYPE_TEXT,
    operation_class: OperationClass = OperationClass.REVERSIBLE_WRITE,
) -> SubgoalSpec:
    return SubgoalSpec(
        subgoal_id=subgoal_id,
        objective=f"complete {subgoal_id}",
        depends_on=depends_on,
        success_criteria=(f"criterion:{subgoal_id}",),
        evidence_requirements=(f"evidence:{subgoal_id}",),
        operation_class=operation_class,
        action_family=action_family,
        outcome=SubgoalOutcome(subject="field", relation=relation),
    )


def _plan(task_spec: TaskSpec, *subgoals: SubgoalSpec) -> TaskPlan:
    return TaskPlan(
        plan_id="plan-post-observation",
        task_id=task_spec.task_id,
        task_revision=task_spec.revision,
        plan_version=1,
        based_on_state_version=0,
        generated_by=TaskPlanSource.RULE,
        subgoals=subgoals,
    )


def _snapshot(*, submit_available: bool = False) -> BrowserSnapshot:
    observation = Observation(
        environment_revision="env-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
    )
    affordances = []
    if submit_available:
        affordances.append(
            Affordance(
                id="field",
                surface=Surface.DOM,
                role="button",
                label="field",
                action="click",
                locator={},
                lease=AffordanceLease(
                    environment_revision="env-1",
                    issued_at_s=0,
                    snapshot_id="snapshot-1",
                    page_revision="page-1",
                ),
                state={"visible": True, "enabled": True},
            )
        )
    return BrowserSnapshot(
        observation=observation,
        affordance_model=PageAffordanceModel(
            page_id="page",
            url="",
            environment_revision="env-1",
            snapshot_id="snapshot-1",
            page_revision="page-1",
            affordances=affordances,
            raw_node_count=len(affordances),
            kept_node_count=len(affordances),
        ),
    )


def _state(task_spec: TaskSpec, plan: TaskPlan) -> StateKernel:
    state = StateKernel(task_id=task_spec.task_id, goal=task_spec.objective)
    state.install_task_plan(plan)
    state.activate_next_subgoal()
    state.remember_observation(_snapshot().observation)
    return state


def test_post_observation_progress_traces_shadow_without_behavior_change() -> None:
    task_spec = _task_spec(
        _obligation("obligation:first"),
        _obligation("obligation:terminal", terminal=True, depends_on=("obligation:first",)),
    )
    state = _state(
        task_spec,
        _plan(
            task_spec,
            _subgoal("obligation:first"),
            _subgoal("obligation:terminal", depends_on=("obligation:first",)),
        ),
    )
    assert state.plan_progress is not None
    state.complete_subgoal("obligation:first", ("evidence:first",))
    trace = TraceDag("run")
    parent = trace.add("ObservationCaptured", {"state": state.phase})
    version_before = state.version

    commit = commit_post_observation_progress(
        task_spec,
        state,
        _snapshot(),
        _Budget(),
        trace,
        parent,
    )

    assert commit.parent.kind == "ObligationProgressShadowCompared"
    assert commit.legacy_completion_committed is False
    assert state.version == version_before
    payload = commit.parent.payload
    assert payload["comparison"]["classification"] == "aligned"
    assert payload["obligation_progress_source"] == "legacy_verified_projection"
    assert payload["task_spec_identity"] == task_spec.identity


def test_post_observation_progress_commits_current_state_then_traces_shadow() -> None:
    task_spec = _task_spec(
        _obligation("obligation:first"),
        _obligation(
            "obligation:terminal",
            terminal=True,
            depends_on=("obligation:first",),
            kind=TaskObligationKind.PREDICATE,
            relation=TaskObligationRelation.IS_AVAILABLE,
        ),
    )
    state = _state(
        task_spec,
        _plan(
            task_spec,
            _subgoal("obligation:first"),
            _subgoal(
                "obligation:terminal",
                relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                depends_on=("obligation:first",),
                action_family=TaskPlanActionFamily.WAIT,
                operation_class=OperationClass.READ_ONLY,
            ),
        ),
    )
    assert state.plan_progress is not None
    state.complete_subgoal("obligation:first", ("evidence:first",))
    trace = TraceDag("run")
    parent = trace.add("ObservationCaptured", {"state": state.phase})

    commit = commit_post_observation_progress(
        task_spec,
        state,
        _snapshot(submit_available=True),
        _Budget(),
        trace,
        parent,
    )

    assert commit.legacy_completion_committed is True
    assert state.plan_progress.completed_subgoal_ids == [
        "obligation:first",
        "obligation:terminal",
    ]
    assert [node.kind for node in trace.nodes] == [
        "ObservationCaptured",
        "SubgoalCompletedFromCurrentObservation",
        "TaskPlanCompleted",
        "ObligationProgressShadowCompared",
    ]
    assert commit.parent.kind == "ObligationProgressShadowCompared"
    assert (
        commit.parent.payload["comparison"]["classification"]
        == ObligationProgressShadowClassification.ROLE_PENDING.value
    )


def test_verified_task_progress_flow_commits_active_step_and_prepares_task_completion() -> None:
    task_spec = _task_spec(_obligation("obligation:terminal", terminal=True))
    state = _state(task_spec, _plan(task_spec, _subgoal("obligation:terminal")))
    trace = TraceDag("run")
    parent = trace.add("ActionOutcomeRecorded", {"state": state.phase})

    commit = commit_verified_task_progress(
        state=state,
        trace=trace,
        parent=parent,
        subgoal_verifier=_PassingSubgoalVerifier(),
        verification=VerificationReport(VerificationStatus.PASSED),
        observation=_snapshot().observation,
        task_planner_is_router=False,
        skill_complete=False,
    )

    assert commit.subgoal_completion_committed is True
    assert commit.task_completion_requested is True
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["obligation:terminal"]
    assert state.final_result == {
        "task_plan_id": "plan-post-observation",
        "completed_subgoal_ids": ["obligation:terminal"],
    }
    assert [node.kind for node in trace.nodes] == [
        "ActionOutcomeRecorded",
        "SubgoalCompleted",
        "TaskPlanCompleted",
    ]


def test_task_skill_progress_commit_does_not_request_task_completion() -> None:
    state = StateKernel("skill-task", "complete skill task")
    skill = TaskSkillRunState("skill-profile", "1.0")
    skill.completed_step_ids.append("step-1")
    trace = TraceDag("run")
    parent = trace.add("TaskSkillStepCompleted", {"state": state.phase})

    commit = commit_task_skill_terminal_progress(
        state=state,
        progress=skill,
        trace=trace,
        parent=parent,
    )

    assert commit.task_completion_requested is False
    assert commit.completed_step_ids == ("step-1",)
    assert state.phase != "done"
    assert [node.kind for node in trace.nodes] == [
        "TaskSkillStepCompleted",
        "TaskSkillCompleted",
    ]
