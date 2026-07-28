import pytest

from affordance_runtime.obligation_progress import (
    ObligationExecutionRole,
    ObligationProgressLedger,
    ObligationProgressStateView,
    ObligationRoleDecision,
    ObligationRoleDecisionStatus,
    ReadyObligationProjection,
    decide_obligation_execution_roles,
    project_ready_obligations,
)
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


def _typed_evidence(subject: str, relation: TaskObligationRelation) -> EvidenceRequirement:
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
    kind: TaskObligationKind = TaskObligationKind.EFFECT,
    subject: str = "field",
    relation: TaskObligationRelation = TaskObligationRelation.HAS_CHANGED,
    terminal: bool = False,
    blocking: bool = True,
    depends_on: tuple[str, ...] = (),
    expected_value: str = "",
    value_source: TaskObligationValueSource = TaskObligationValueSource.NONE,
) -> TaskObligationSpec:
    return TaskObligationSpec(
        obligation_id=obligation_id,
        kind=kind,
        subject=subject,
        relation=relation,
        value_source=value_source,
        expected_value=expected_value,
        claim_ids=(f"claim:{obligation_id}",),
        depends_on=depends_on,
        evidence_requirements=(f"evidence:{obligation_id}",),
        typed_evidence_requirements=(_typed_evidence(subject, relation),),
        blocking=blocking,
        terminal=terminal,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _task_spec(obligations: tuple[TaskObligationSpec, ...]) -> TaskSpec:
    return TaskSpec(
        task_id="task-role-projection",
        revision=7,
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


def test_role_decisions_assign_effect_roles_without_task_names_or_planner_state() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:first"),
            _obligation(
                "obligation:terminal",
                terminal=True,
                depends_on=("obligation:first",),
            ),
        )
    )

    decisions = decide_obligation_execution_roles(task_spec)

    assert decisions == (
        ObligationRoleDecision(
            obligation_id="obligation:first",
            status=ObligationRoleDecisionStatus.ASSIGNED,
            role=ObligationExecutionRole.PROGRESS_EFFECT,
            reason_code="effect_nonterminal",
        ),
        ObligationRoleDecision(
            obligation_id="obligation:terminal",
            status=ObligationRoleDecisionStatus.ASSIGNED,
            role=ObligationExecutionRole.TERMINAL_EFFECT,
            reason_code="effect_terminal",
        ),
    )


def test_role_decisions_fail_closed_for_ambiguous_terminal_availability_predicates() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:submit-available",
                kind=TaskObligationKind.PREDICATE,
                subject="submit_button",
                relation=TaskObligationRelation.IS_AVAILABLE,
                terminal=True,
            ),
        )
    )

    decisions = decide_obligation_execution_roles(task_spec)

    assert decisions == (
        ObligationRoleDecision(
            obligation_id="obligation:submit-available",
            status=ObligationRoleDecisionStatus.PENDING,
            role=None,
            reason_code="blocking_availability_predicate_pending",
        ),
    )


def test_nonblocking_availability_predicates_are_preconditions_not_progress() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:button-visible",
                kind=TaskObligationKind.PREDICATE,
                subject="submit_button",
                relation=TaskObligationRelation.IS_VISIBLE,
                terminal=False,
                blocking=False,
            ),
            _obligation("obligation:terminal", terminal=True),
        )
    )

    decisions = decide_obligation_execution_roles(task_spec)

    assert decisions[0].role == ObligationExecutionRole.PRECONDITION
    assert decisions[1].role == ObligationExecutionRole.TERMINAL_EFFECT


def test_ready_projection_returns_role_pending_instead_of_throwing() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:submit-available",
                kind=TaskObligationKind.PREDICATE,
                subject="submit_button",
                relation=TaskObligationRelation.IS_AVAILABLE,
                terminal=True,
            ),
        )
    )
    progress = ObligationProgressLedger.from_task_spec(task_spec).to_view(
        evaluated_at_state_version=3,
    )

    projection = project_ready_obligations(
        task_spec,
        progress,
        decide_obligation_execution_roles(task_spec),
    )

    assert projection == ReadyObligationProjection(
        status="role_pending",
        ready_obligations=(),
        pending_role_obligation_ids=("obligation:submit-available",),
        reason="blocking_availability_predicate_pending",
    )


def test_ready_projection_returns_ready_views_for_assigned_progress_roles() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:first"),
            _obligation(
                "obligation:terminal",
                terminal=True,
                depends_on=("obligation:first",),
            ),
        )
    )
    ledger = ObligationProgressLedger.from_task_spec(task_spec)
    ledger.record_satisfaction("obligation:first", ("evidence:first",))
    progress = ledger.to_view(evaluated_at_state_version=3)

    projection = project_ready_obligations(
        task_spec,
        progress,
        decide_obligation_execution_roles(task_spec),
    )

    assert projection.status == "ready"
    assert tuple(item.obligation_id for item in projection.ready_obligations) == (
        "obligation:terminal",
    )
    assert projection.pending_role_obligation_ids == ()


def test_ready_projection_reports_stale_or_invalid_progress_without_runtime_crash() -> None:
    task_spec = _task_spec((_obligation("obligation:terminal", terminal=True),))
    decisions = decide_obligation_execution_roles(task_spec)

    stale = ObligationProgressStateView(
        task_spec_identity="sha256:wrong",
        task_revision=task_spec.revision,
        evaluated_at_state_version=3,
        known_obligation_ids=("obligation:terminal",),
    )
    invalid = ObligationProgressStateView(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=3,
        known_obligation_ids=("obligation:terminal", "obligation:extra"),
    )

    assert project_ready_obligations(task_spec, stale, decisions).status == "stale_progress"
    assert project_ready_obligations(task_spec, invalid, decisions).status == "invalid_progress"


def test_role_decision_status_and_role_are_consistent() -> None:
    with pytest.raises(ValueError, match="assigned role decision requires role"):
        ObligationRoleDecision(
            obligation_id="obligation:first",
            status=ObligationRoleDecisionStatus.ASSIGNED,
            role=None,
            reason_code="broken",
        )

    with pytest.raises(ValueError, match="pending role decision cannot include role"):
        ObligationRoleDecision(
            obligation_id="obligation:first",
            status=ObligationRoleDecisionStatus.PENDING,
            role=ObligationExecutionRole.PROGRESS_EFFECT,
            reason_code="broken",
        )
