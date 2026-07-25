import pytest

from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    UnifiedAffordance,
)
from affordance_runtime.task_intake import (
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
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskObligationOutcomeCompiler,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanningBudgetSummary,
    TaskPlanningContext,
    TaskPlanSource,
)
from affordance_runtime.terminal_readiness import (
    ObligationState,
    TaskObligationEvidence,
    TaskObligationView,
    TaskObligationViewCompiler,
    TerminalCandidate,
    TerminalEffectBinding,
    TerminalEffectBindingResolver,
    TerminalReadinessEvaluator,
    TerminalReadinessStatus,
)


def _evidence(
    obligation_id: str,
    state: ObligationState,
    *,
    revision: int = 2,
    epoch: str = "snapshot-2",
    current: bool = False,
) -> TaskObligationEvidence:
    return TaskObligationEvidence(
        obligation_id,
        state,
        revision,
        verification_refs=(f"artifact:{obligation_id}",)
        if state == ObligationState.SATISFIED
        else (),
        observation_epoch_id=epoch if current else "",
        require_current_epoch=current,
    )


def test_direct_terminal_with_complete_empty_dependencies_is_ready() -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(TerminalCandidate("semantic:submit", dependencies_complete=True),),
        obligations=(),
    )

    assert decision.ready_target_ids == ("semantic:submit",)
    assert decision.blocked_target_ids == ()


def test_open_prerequisite_blocks_terminal() -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:submit",
                prerequisite_obligation_ids=("field:value",),
                dependencies_complete=True,
            ),
        ),
        obligations=(_evidence("field:value", ObligationState.OPEN),),
    )

    candidate = decision.candidates[0]
    assert candidate.status == TerminalReadinessStatus.BLOCKED
    assert candidate.blocking_obligation_ids == ("field:value",)


@pytest.mark.parametrize("dependencies_complete", [False, True])
def test_incomplete_or_missing_dependency_evidence_is_unknown(
    dependencies_complete: bool,
) -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:send",
                prerequisite_obligation_ids=("draft:body",),
                dependencies_complete=dependencies_complete,
            ),
        ),
        obligations=(),
    )

    assert decision.candidates[0].status == TerminalReadinessStatus.UNKNOWN
    assert decision.ready_target_ids == ()


@pytest.mark.parametrize(
    ("revision", "epoch", "current"),
    [(1, "snapshot-2", False), (2, "snapshot-1", True)],
)
def test_stale_revision_or_required_epoch_cannot_satisfy_terminal(
    revision: int,
    epoch: str,
    current: bool,
) -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:submit",
                prerequisite_obligation_ids=("selection:chosen",),
                dependencies_complete=True,
            ),
        ),
        obligations=(
            _evidence(
                "selection:chosen",
                ObligationState.SATISFIED,
                revision=revision,
                epoch=epoch,
                current=current,
            ),
        ),
    )

    assert decision.candidates[0].status == TerminalReadinessStatus.UNKNOWN


def test_current_verified_prerequisites_admit_only_their_terminal() -> None:
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=(
            TerminalCandidate(
                "semantic:submit",
                prerequisite_obligation_ids=("selection:chosen",),
                dependencies_complete=True,
            ),
            TerminalCandidate(
                "semantic:publish",
                prerequisite_obligation_ids=("approval:granted",),
                dependencies_complete=True,
            ),
        ),
        obligations=(
            _evidence(
                "selection:chosen",
                ObligationState.SATISFIED,
                current=True,
            ),
            _evidence("approval:granted", ObligationState.OPEN),
        ),
    )

    assert decision.ready_target_ids == ("semantic:submit",)
    assert decision.blocked_target_ids == ("semantic:publish",)


def test_satisfied_obligation_requires_verification_reference() -> None:
    with pytest.raises(ValueError, match="verification evidence"):
        TaskObligationEvidence("field:value", ObligationState.SATISFIED, 2)


def _plan(*, prerequisite_outcome: bool = True, terminal_outcome: bool = True) -> TaskPlan:
    return TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=2,
        plan_version=1,
        based_on_state_version=4,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="field:value",
                objective="field equals dark",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=(
                    SubgoalOutcome(
                        subject="field",
                        relation=SubgoalOutcomeRelation.EQUALS,
                        value="dark",
                    )
                    if prerequisite_outcome
                    else None
                ),
            ),
            SubgoalSpec(
                subgoal_id="settings:submitted",
                objective="settings submission is completed",
                depends_on=("field:value",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=(
                    SubgoalOutcome(
                        subject="settings submission",
                        relation=SubgoalOutcomeRelation.IS_COMPLETED,
                    )
                    if terminal_outcome
                    else None
                ),
            ),
        ),
    )


def _binding(**changes: object) -> TerminalEffectBinding:
    values = {
        "semantic_target_id": "semantic:submit",
        "candidate_id": "candidate:dom:submit",
        "subgoal_id": "settings:submitted",
        "task_revision": 2,
        "observation_epoch_id": "snapshot-2",
        "target_fingerprint": "sha256:submit",
    }
    values.update(changes)
    return TerminalEffectBinding(**values)  # type: ignore[arg-type]


def _observation(*, fingerprint: str = "sha256:submit") -> Observation:
    return Observation(
        "rev-1",
        snapshot_id="snapshot-2",
        page_revision="page-1",
        target_fingerprints={"candidate:dom:submit": fingerprint},
    )


def _grounding_candidate(
    *,
    semantic_target_id: str = "semantic:submit",
    candidate_id: str = "candidate:dom:submit",
) -> GroundingCandidate:
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id=semantic_target_id,
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(backend_handle="submit"),
        compatible_executor="browsergym",
        observation_epoch_id="snapshot-2",
        environment_revision="rev-1",
        page_revision="page-1",
        target_fingerprint="sha256:submit",
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset({EvidenceKind.STRUCTURAL}),
    )


def _unified_terminal(
    *,
    semantic_target_id: str = "semantic:submit",
    candidate_id: str = "candidate:dom:submit",
    candidates: bool = True,
) -> UnifiedAffordance:
    grounding = (
        _grounding_candidate(
            semantic_target_id=semantic_target_id,
            candidate_id=candidate_id,
        ),
    ) if candidates else ()
    return UnifiedAffordance(
        semantic_target_id=semantic_target_id,
        role="button",
        label="settings submission",
        supported_actions=frozenset({"activate"}),
        grounding_candidates=grounding,
    )


def _compile(
    plan: TaskPlan,
    progress: PlanProgress,
    binding: TerminalEffectBinding | None = None,
) -> TaskObligationView:
    return TaskObligationViewCompiler().compile(
        plan=plan,
        progress=progress,
        bindings=(binding or _binding(),),
        task_revision=2,
        observation_epoch_id="snapshot-2",
        target_fingerprints={"candidate:dom:submit": "sha256:submit"},
    )


def test_compiler_binds_completed_plan_dependency_to_verified_terminal_readiness() -> None:
    progress = PlanProgress(
        completed_subgoal_ids=["field:value"],
        evidence_by_subgoal={"field:value": ["artifact:verification"]},
    )
    view = _compile(_plan(), progress)
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=view.candidates,
        obligations=view.obligations,
    )

    assert view.candidates[0].prerequisite_obligation_ids == ("field:value",)
    assert decision.ready_target_ids == ("semantic:submit",)


def test_compiled_taskspec_obligation_identity_reaches_terminal_readiness() -> None:
    read_claim = SourcedTaskClaim(
        claim_id="claim-read",
        kind=TaskClaimKind.DEPENDENCY,
        statement="read current code",
        source_ref="request-1",
    )
    submit_claim = SourcedTaskClaim(
        claim_id="claim-submit",
        kind=TaskClaimKind.TERMINAL,
        statement="submit code",
        source_ref="request-1",
    )
    task_spec = TaskSpec(
        task_id="task-compiled",
        revision=2,
        objective="Read then submit code",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("code submission",),
        success_criteria=("code submitted",),
        source_request_ref="request-1",
        source_claims=(read_claim, submit_claim),
        obligations=(
            TaskObligationSpec(
                obligation_id="obligation-read",
                kind=TaskObligationKind.PREDICATE,
                subject="current code",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source=TaskObligationValueSource.OBSERVATION,
                claim_ids=(read_claim.claim_id,),
                evidence_requirements=("fresh code observation",),
            ),
            TaskObligationSpec(
                obligation_id="obligation-submit",
                kind=TaskObligationKind.EFFECT,
                subject="code submission",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=(submit_claim.claim_id,),
                depends_on=("obligation-read",),
                evidence_requirements=("fresh submission confirmation",),
                terminal=True,
            ),
        ),
    )
    plan = TaskObligationOutcomeCompiler().compile(
        TaskPlanningContext(
            task_spec=task_spec,
            state_version=4,
            remaining_budget=TaskPlanningBudgetSummary(
                steps_remaining=10,
                observations_remaining=10,
                replans_remaining=2,
                recoveries_remaining=2,
                effectful_actions_remaining=2,
            ),
        )
    )
    view = TaskObligationViewCompiler().compile(
        plan=plan,
        progress=PlanProgress(
            completed_subgoal_ids=["obligation-read"],
            evidence_by_subgoal={"obligation-read": ["artifact:read"]},
        ),
        bindings=(
            TerminalEffectBinding(
                semantic_target_id="semantic:submit",
                candidate_id="candidate:submit",
                subgoal_id="obligation-submit",
                task_revision=2,
                observation_epoch_id="snapshot-2",
                target_fingerprint="sha256:submit",
            ),
        ),
        task_revision=2,
        observation_epoch_id="snapshot-2",
        target_fingerprints={"candidate:submit": "sha256:submit"},
    )
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=view.candidates,
        obligations=view.obligations,
    )

    assert view.candidates[0].prerequisite_obligation_ids == ("obligation-read",)
    assert decision.ready_target_ids == ("semantic:submit",)


def test_compiler_keeps_unfinished_plan_dependency_blocking() -> None:
    view = _compile(_plan(), PlanProgress())
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=view.candidates,
        obligations=view.obligations,
    )

    assert decision.candidates[0].status == TerminalReadinessStatus.BLOCKED


@pytest.mark.parametrize(
    "plan",
    [_plan(prerequisite_outcome=False), _plan(terminal_outcome=False)],
)
def test_compiler_does_not_complete_dependencies_from_untyped_plan(plan: TaskPlan) -> None:
    view = _compile(plan, PlanProgress())

    assert not view.candidates[0].dependencies_complete


@pytest.mark.parametrize(
    "binding",
    [
        _binding(task_revision=1),
        _binding(observation_epoch_id="snapshot-1"),
        _binding(candidate_id="candidate:dom:stale"),
        _binding(target_fingerprint="sha256:stale"),
    ],
)
def test_compiler_marks_stale_terminal_binding_unknown(
    binding: TerminalEffectBinding,
) -> None:
    view = _compile(_plan(), PlanProgress(), binding)

    assert not view.candidates[0].dependencies_complete


def test_completed_plan_dependency_without_evidence_remains_unknown() -> None:
    view = _compile(
        _plan(),
        PlanProgress(completed_subgoal_ids=["field:value"]),
    )
    decision = TerminalReadinessEvaluator().evaluate(
        task_revision=2,
        observation_epoch_id="snapshot-2",
        candidates=view.candidates,
        obligations=view.obligations,
    )

    assert decision.candidates[0].status == TerminalReadinessStatus.UNKNOWN


def test_resolver_binds_unique_typed_completion_to_current_grounding() -> None:
    resolution = TerminalEffectBindingResolver().resolve(
        plan=_plan(),
        progress=PlanProgress(
            active_subgoal_id="settings:submitted",
            completed_subgoal_ids=["field:value"],
        ),
        unified_affordances=(_unified_terminal(),),
        observation=_observation(),
    )

    assert resolution.bindings == (_binding(),)
    assert resolution.unresolved_target_ids == ()


def test_resolver_does_not_treat_noncompletion_navigation_as_terminal() -> None:
    plan = _plan()
    terminal = plan.subgoals[1].model_copy(
        update={
            "objective": "open settings submission",
            "outcome": SubgoalOutcome(
                subject="settings submission",
                relation=SubgoalOutcomeRelation.IS_VISIBLE,
            ),
        }
    )

    resolution = TerminalEffectBindingResolver().resolve(
        plan=plan.model_copy(update={"subgoals": (plan.subgoals[0], terminal)}),
        progress=PlanProgress(
            active_subgoal_id="settings:submitted",
            completed_subgoal_ids=["field:value"],
        ),
        unified_affordances=(_unified_terminal(),),
        observation=_observation(),
    )

    assert resolution.bindings == ()
    assert resolution.unresolved_target_ids == ()


def test_resolver_does_not_infer_terminal_from_untyped_flat_outcome() -> None:
    resolution = TerminalEffectBindingResolver().resolve(
        plan=_plan(terminal_outcome=False),
        progress=PlanProgress(
            active_subgoal_id="settings:submitted",
            completed_subgoal_ids=["field:value"],
        ),
        unified_affordances=(_unified_terminal(),),
        observation=_observation(),
    )

    assert resolution.bindings == ()
    assert resolution.unresolved_target_ids == ()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_resolver_refuses_stale_or_ambiguous_terminal_grounding(
    ambiguous: bool,
) -> None:
    targets = (_unified_terminal(),)
    observation = _observation(fingerprint="sha256:stale")
    if ambiguous:
        targets += (
            _unified_terminal(
                semantic_target_id="semantic:submit-alternate",
                candidate_id="candidate:dom:submit-alternate",
            ),
        )
        observation = _observation()

    resolution = TerminalEffectBindingResolver().resolve(
        plan=_plan(),
        progress=PlanProgress(
            active_subgoal_id="settings:submitted",
            completed_subgoal_ids=["field:value"],
        ),
        unified_affordances=targets,
        observation=observation,
    )

    assert resolution.bindings == ()
    assert resolution.unresolved_target_ids == (
        ("semantic:submit", "semantic:submit-alternate")
        if ambiguous
        else ("semantic:submit",)
    )
