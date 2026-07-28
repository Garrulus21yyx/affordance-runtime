from affordance_runtime.adapters.dom import PageAffordanceModel
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.obligation_progress_shadow import (
    ObligationProgressShadowClassification,
)
from affordance_runtime.obligation_progress_shadow_flow import (
    LEGACY_VERIFIED_PROJECTION,
    prepare_obligation_progress_shadow_trace,
    project_verified_legacy_progress,
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
from affordance_runtime.task_planning import (
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)


def _task_spec(*obligations: TaskObligationSpec) -> TaskSpec:
    return TaskSpec(
        task_id="task-shadow",
        revision=2,
        objective="exercise shadow projection",
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


def _obligation(
    obligation_id: str,
    *,
    terminal: bool = False,
    depends_on: tuple[str, ...] = (),
    kind: TaskObligationKind = TaskObligationKind.EFFECT,
    relation: TaskObligationRelation = TaskObligationRelation.HAS_CHANGED,
    blocking: bool = True,
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
        blocking=blocking,
        terminal=terminal,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _plan(task_spec: TaskSpec, *subgoal_ids: str) -> TaskPlan:
    return TaskPlan(
        plan_id="plan-shadow",
        task_id=task_spec.task_id,
        task_revision=task_spec.revision,
        plan_version=1,
        based_on_state_version=0,
        generated_by=TaskPlanSource.RULE,
        subgoals=tuple(
            SubgoalSpec(
                subgoal_id=subgoal_id,
                objective=f"complete {subgoal_id}",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="field",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
                success_criteria=(f"criterion:{subgoal_id}",),
                evidence_requirements=(f"evidence:{subgoal_id}",),
            )
            for subgoal_id in subgoal_ids
        ),
    )


def _snapshot() -> BrowserSnapshot:
    observation = Observation(
        environment_revision="env-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
    )
    return BrowserSnapshot(
        observation=observation,
        affordance_model=PageAffordanceModel(
            page_id="page",
            url="",
            environment_revision="env-1",
            snapshot_id="snapshot-1",
            page_revision="page-1",
            affordances=[],
            raw_node_count=0,
            kept_node_count=0,
        ),
    )


def _state_with_plan(task_spec: TaskSpec, plan: TaskPlan) -> StateKernel:
    state = StateKernel(task_id=task_spec.task_id, goal=task_spec.objective)
    state.install_task_plan(plan)
    state.activate_next_subgoal()
    state.remember_observation(_snapshot().observation)
    return state


def test_shadow_trace_projection_is_absent_without_task_or_plan_progress() -> None:
    snapshot = _snapshot()
    task_spec = _task_spec(_obligation("obligation:first", terminal=True))
    empty_state = StateKernel(task_id=task_spec.task_id, goal=task_spec.objective)

    assert prepare_obligation_progress_shadow_trace(None, empty_state, snapshot) is None
    assert prepare_obligation_progress_shadow_trace(task_spec, empty_state, snapshot) is None


def test_legacy_projection_uses_exact_id_mapping_and_requires_evidence() -> None:
    task_spec = _task_spec(
        _obligation("obligation:first"),
        _obligation("obligation:terminal", terminal=True, depends_on=("obligation:first",)),
    )
    state = _state_with_plan(
        task_spec,
        _plan(task_spec, "obligation:first", "legacy-only"),
    )
    assert state.plan_progress is not None
    state.plan_progress.complete("obligation:first", ("evidence:first",))
    state.plan_progress.complete("legacy-only", ("evidence:legacy",))

    progress = project_verified_legacy_progress(task_spec, state)

    assert progress.satisfied_obligation_ids == ("obligation:first",)
    assert tuple(
        (entry.obligation_id, entry.evidence_refs)
        for entry in progress.evidence_by_obligation
    ) == (("obligation:first", ("evidence:first",)),)


def test_completed_subgoal_without_evidence_is_not_satisfied_obligation() -> None:
    task_spec = _task_spec(_obligation("obligation:first", terminal=True))
    state = _state_with_plan(task_spec, _plan(task_spec, "obligation:first"))
    assert state.plan_progress is not None
    state.plan_progress.complete("obligation:first", ())

    progress = project_verified_legacy_progress(task_spec, state)

    assert progress.satisfied_obligation_ids == ()


def test_shadow_trace_projection_is_read_only_and_uses_legacy_source() -> None:
    task_spec = _task_spec(
        _obligation("obligation:first"),
        _obligation("obligation:terminal", terminal=True, depends_on=("obligation:first",)),
    )
    state = _state_with_plan(
        task_spec,
        _plan(task_spec, "obligation:first", "obligation:terminal"),
    )
    assert state.plan_progress is not None
    state.plan_progress.complete("obligation:first", ("evidence:first",))
    version_before = state.version

    projection = prepare_obligation_progress_shadow_trace(task_spec, state, _snapshot())

    assert projection is not None
    assert projection.obligation_progress_source == LEGACY_VERIFIED_PROJECTION
    assert projection.evaluated_at_state_version == version_before
    assert projection.task_spec_identity == task_spec.identity
    assert projection.task_revision == task_spec.revision
    assert projection.task_plan_id == "plan-shadow"
    assert projection.task_plan_version == 1
    assert projection.comparison is not None
    assert projection.comparison.ready_obligation_ids == ("obligation:terminal",)
    assert state.version == version_before
    assert state.obligation_progress is None


def test_role_pending_projection_remains_diagnostic_not_runtime_failure() -> None:
    task_spec = _task_spec(
        _obligation(
            "obligation:submit-available",
            terminal=True,
            kind=TaskObligationKind.PREDICATE,
            relation=TaskObligationRelation.IS_AVAILABLE,
        ),
    )
    state = _state_with_plan(task_spec, _plan(task_spec, "obligation:submit-available"))

    projection = prepare_obligation_progress_shadow_trace(task_spec, state, _snapshot())

    assert projection is not None
    assert projection.comparison is not None
    assert (
        projection.comparison.classification
        == ObligationProgressShadowClassification.LEGACY_ACTIVE_NON_PROGRESS_PREDICATE
    )
