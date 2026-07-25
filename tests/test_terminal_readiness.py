import pytest

from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import (
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
from affordance_runtime.terminal_readiness import (
    ObligationState,
    TaskObligationEvidence,
    TaskObligationView,
    TaskObligationViewCompiler,
    TerminalCandidate,
    TerminalEffectBinding,
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
        "subgoal_id": "settings:submitted",
        "task_revision": 2,
        "observation_epoch_id": "snapshot-2",
        "target_fingerprint": "sha256:submit",
    }
    values.update(changes)
    return TerminalEffectBinding(**values)  # type: ignore[arg-type]


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
        target_fingerprints={"semantic:submit": "sha256:submit"},
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
