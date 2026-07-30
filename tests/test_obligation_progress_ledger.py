import pytest

from affordance_runtime.obligation_progress import ObligationProgressLedger
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    GraphConstructionSource,
    OperationClass,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
    TaskStructure,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle


def _evidence(subject: str, relation: TaskObligationRelation) -> EvidenceRequirement:
    return EvidenceRequirement(
        kind=EvidenceKind.DOM_STATE,
        subject=subject,
        relation=relation,
        minimum_strength="independent",
        source_constraints=("source:request:clause:0",),
    )


def _obligation(
    obligation_id: str,
    *,
    subject: str = "field",
    relation: TaskObligationRelation = TaskObligationRelation.HAS_CHANGED,
    terminal: bool = False,
    depends_on: tuple[str, ...] = (),
) -> TaskObligationSpec:
    return TaskObligationSpec(
        obligation_id=obligation_id,
        kind="effect",
        subject=subject,
        relation=relation,
        value_source=TaskObligationValueSource.NONE,
        expected_value="",
        claim_ids=(f"claim:{obligation_id}",),
        depends_on=depends_on,
        evidence_requirements=(f"evidence:{obligation_id}",),
        typed_evidence_requirements=(_evidence(subject, relation),),
        blocking=True,
        terminal=terminal,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _task_spec() -> TaskSpec:
    obligations = (
        _obligation("obligation:first"),
        _obligation(
            "obligation:terminal",
            terminal=True,
            depends_on=("obligation:first",),
        ),
    )
    return TaskSpec(
        task_id="task-obligation-ledger",
        revision=5,
        objective="complete the canonical graph",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("field",),
        success_criteria=("terminal effect satisfied",),
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


def test_ledger_initializes_from_exact_task_spec_identity_and_graph_order() -> None:
    task_spec = _task_spec()
    ledger = ObligationProgressLedger.from_task_spec(task_spec)

    assert ledger.task_spec_identity == task_spec.identity
    assert ledger.task_revision == task_spec.revision
    assert ledger.known_obligation_ids == (
        "obligation:first",
        "obligation:terminal",
    )


def test_ledger_rejects_unknown_progress_mutations() -> None:
    ledger = ObligationProgressLedger.from_task_spec(_task_spec())

    with pytest.raises(ValueError, match="unknown obligation id"):
        ledger.record_satisfaction("obligation:typo", ("evidence:1",))
    with pytest.raises(ValueError, match="unknown obligation id"):
        ledger.record_failure("obligation:typo")
    with pytest.raises(ValueError, match="unknown obligation id"):
        ledger.record_attempt("obligation:typo")


def test_ledger_rejects_satisfied_failed_overlap() -> None:
    ledger = ObligationProgressLedger.from_task_spec(_task_spec())

    ledger.record_satisfaction("obligation:first", ("evidence:1",))

    with pytest.raises(ValueError, match="already satisfied"):
        ledger.record_failure("obligation:first")


def test_ledger_rejects_satisfaction_without_evidence() -> None:
    ledger = ObligationProgressLedger.from_task_spec(_task_spec())

    with pytest.raises(ValueError, match="satisfaction evidence refs cannot be empty"):
        ledger.record_satisfaction("obligation:first", ())


def test_ledger_deduplicates_evidence_and_satisfaction_is_idempotent() -> None:
    ledger = ObligationProgressLedger.from_task_spec(_task_spec())

    ledger.record_satisfaction(
        "obligation:first",
        ("evidence:1", "evidence:1", "evidence:2"),
    )
    ledger.record_satisfaction("obligation:first", ("evidence:2", "evidence:3"))
    view = ledger.to_view(evaluated_at_state_version=11)

    assert view.satisfied_obligation_ids == ("obligation:first",)
    assert view.evidence_by_obligation[0].evidence_refs == (
        "evidence:1",
        "evidence:2",
        "evidence:3",
    )


def test_ledger_rejects_failed_to_satisfied_without_explicit_recovery() -> None:
    ledger = ObligationProgressLedger.from_task_spec(_task_spec())

    ledger.record_failure("obligation:first", ("failure:evidence",))

    with pytest.raises(ValueError, match="already failed"):
        ledger.record_satisfaction("obligation:first", ("evidence:1",))


def test_ledger_view_is_deeply_immutable_and_not_shared_with_mutable_ledger() -> None:
    ledger = ObligationProgressLedger.from_task_spec(_task_spec())
    ledger.record_attempt("obligation:first")
    ledger.record_satisfaction("obligation:first", ("evidence:1",))

    view = ledger.to_view(evaluated_at_state_version=11)
    ledger.record_satisfaction("obligation:first", ("evidence:2",))
    ledger.record_attempt("obligation:first")

    assert view.evidence_by_obligation[0].evidence_refs == ("evidence:1",)
    assert view.attempt_count_by_obligation[0].attempt_count == 1


def test_obligation_ledger_remains_external_to_default_statekernel() -> None:
    task_spec = _task_spec()
    state = StateKernel(task_id=task_spec.task_id, goal=task_spec.objective)
    before = state.version

    ledger = ObligationProgressLedger.from_task_spec(task_spec)
    view = ledger.to_view(evaluated_at_state_version=state.version)

    assert state.version == before
    assert view.task_spec_identity == task_spec.identity
    assert not hasattr(state, "obligation_progress")
    assert not hasattr(state, "obligation_progress_view")


def test_state_kernel_ledger_does_not_affect_taskplan_lifecycle_or_runtime_surfaces() -> None:
    task_spec = _task_spec()
    state = StateKernel(task_id=task_spec.task_id, goal=task_spec.objective)

    ledger = ObligationProgressLedger.from_task_spec(task_spec)
    ledger.record_attempt("obligation:first")
    assert TaskPlanLifecycle.completed(state) is False
    assert state.task_plan is None
    assert state.plan_progress is None
    assert state.current_failure is None
