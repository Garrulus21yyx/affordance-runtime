import pytest

from affordance_runtime.obligation_attribution import (
    EvidenceStrength,
    ObligationSatisfactionPreparation,
    PostActionEvidenceFact,
    ProgressAttributionTicket,
)
from affordance_runtime.obligation_progress import (
    ObligationExecutionRole,
    ObligationProgressStateView,
    TaskObligationExecutionView,
    ready_obligation_ids,
    task_obligation_execution_views,
    task_obligations_completed,
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


def _typed_evidence(
    *,
    subject: str,
    relation: TaskObligationRelation,
    source_ref: str = "source:request:clause:0",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        kind=EvidenceKind.DOM_STATE,
        subject=subject,
        relation=relation,
        minimum_strength="independent",
        source_constraints=(source_ref,),
    )


def _obligation(
    obligation_id: str,
    *,
    kind: TaskObligationKind = TaskObligationKind.EFFECT,
    subject: str = "field",
    relation: TaskObligationRelation = TaskObligationRelation.HAS_CHANGED,
    depends_on: tuple[str, ...] = (),
    terminal: bool = False,
    blocking: bool = True,
    value_source: TaskObligationValueSource = TaskObligationValueSource.NONE,
    expected_value: str = "",
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
        typed_evidence_requirements=(
            _typed_evidence(subject=subject, relation=relation),
        ),
        blocking=blocking,
        terminal=terminal,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _task_spec(obligations: tuple[TaskObligationSpec, ...]) -> TaskSpec:
    claims = tuple(
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
    )
    return TaskSpec(
        task_id="task-obligation-progress",
        revision=3,
        objective="complete the canonical graph",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("field",),
        success_criteria=("terminal effect satisfied",),
        source_request_ref="source:request",
        source_claims=claims,
        obligations=obligations,
        evidence_requirements=("independent evidence",),
    )


def _progress(
    *,
    satisfied: tuple[str, ...] = (),
    failed: tuple[str, ...] = (),
) -> ObligationProgressStateView:
    return ObligationProgressStateView(
        task_revision=3,
        evaluated_at_state_version=8,
        satisfied_obligation_ids=satisfied,
        failed_obligation_ids=failed,
        evidence_by_obligation={item: (f"evidence-ref:{item}",) for item in satisfied},
        attempt_count_by_obligation={},
    )


def test_ready_obligations_come_from_graph_dependencies_and_progress_roles() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:precondition",
                kind=TaskObligationKind.PREDICATE,
                relation=TaskObligationRelation.IS_AVAILABLE,
                blocking=False,
            ),
            _obligation("obligation:first"),
            _obligation("obligation:second", depends_on=("obligation:first",), terminal=True),
            _obligation(
                "obligation:evidence-only",
                kind=TaskObligationKind.PREDICATE,
                relation=TaskObligationRelation.IS_VISIBLE,
                blocking=False,
            ),
        )
    )
    views = (
        TaskObligationExecutionView.from_obligation(
            task_spec.obligations[0],
            role=ObligationExecutionRole.PRECONDITION,
        ),
        TaskObligationExecutionView.from_obligation(
            task_spec.obligations[1],
            role=ObligationExecutionRole.PROGRESS_EFFECT,
        ),
        TaskObligationExecutionView.from_obligation(
            task_spec.obligations[2],
            role=ObligationExecutionRole.TERMINAL_EFFECT,
        ),
        TaskObligationExecutionView.from_obligation(
            task_spec.obligations[3],
            role=ObligationExecutionRole.EVIDENCE_ONLY,
        ),
    )

    assert ready_obligation_ids(task_spec, _progress(), views) == ("obligation:first",)
    assert ready_obligation_ids(task_spec, _progress(satisfied=("obligation:first",)), views) == (
        "obligation:second",
    )


def test_ready_projection_rejects_missing_or_extra_execution_role_views() -> None:
    task_spec = _task_spec((_obligation("obligation:first", terminal=True),))
    view = TaskObligationExecutionView.from_obligation(
        task_spec.obligations[0],
        role=ObligationExecutionRole.TERMINAL_EFFECT,
    )

    with pytest.raises(ValueError, match="missing obligation execution role"):
        ready_obligation_ids(task_spec, _progress(), ())

    extra = TaskObligationExecutionView(
        obligation_id="obligation:extra",
        role=ObligationExecutionRole.TERMINAL_EFFECT,
        subject="extra",
        relation=TaskObligationRelation.IS_COMPLETED,
        expected_value="",
        evidence_requirements=("evidence:extra",),
        dependency_ids=(),
        terminal=True,
        blocking=True,
    )
    with pytest.raises(ValueError, match="unknown obligation execution role"):
        ready_obligation_ids(task_spec, _progress(), (view, extra))


def test_task_completion_uses_blocking_effect_obligations_not_taskplan_state() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:first", terminal=False),
            _obligation("obligation:optional", terminal=False, blocking=False),
            _obligation("obligation:terminal", depends_on=("obligation:first",), terminal=True),
        )
    )
    views = task_obligation_execution_views(
        task_spec,
        {
            "obligation:first": ObligationExecutionRole.PROGRESS_EFFECT,
            "obligation:optional": ObligationExecutionRole.PROGRESS_EFFECT,
            "obligation:terminal": ObligationExecutionRole.TERMINAL_EFFECT,
        },
    )

    assert not task_obligations_completed(
        task_spec,
        _progress(satisfied=("obligation:first", "obligation:optional")),
        views,
    )
    assert task_obligations_completed(
        task_spec,
        _progress(satisfied=("obligation:first", "obligation:terminal")),
        views,
    )


def test_attribution_ticket_and_satisfaction_preparation_are_identity_bound() -> None:
    ticket = ProgressAttributionTicket(
        ticket_id="ticket-1",
        task_revision=3,
        issued_at_state_version=8,
        contract_id="contract-1",
        semantic_target_id="semantic:field",
        action_kind="type_text",
        candidate_obligation_ids=("obligation:first",),
        pre_snapshot_id="snapshot-pre",
        pre_page_revision="page-pre",
        pre_environment_revision="env-pre",
    )
    fact = PostActionEvidenceFact(
        contract_id=ticket.contract_id,
        pre_snapshot_id=ticket.pre_snapshot_id,
        post_snapshot_id="snapshot-post",
        post_page_revision="page-post",
        post_environment_revision="env-post",
        semantic_target_id=ticket.semantic_target_id,
        relation=TaskObligationRelation.HAS_CHANGED,
        before_value="",
        after_value="Kanesha",
        strength=EvidenceStrength.INDEPENDENT,
        evidence_refs=("verification:1",),
    )
    preparation = ObligationSatisfactionPreparation(
        task_revision=ticket.task_revision,
        evaluated_at_state_version=9,
        obligation_id="obligation:first",
        contract_id=ticket.contract_id,
        post_snapshot_id=fact.post_snapshot_id,
        evidence_refs=fact.evidence_refs,
        source="post_verification",
    )

    assert ticket.candidate_obligation_ids == ("obligation:first",)
    assert preparation.evidence_refs == ("verification:1",)
    assert preparation.source == "post_verification"


def test_attribution_contracts_fail_closed_on_blank_or_duplicate_identity() -> None:
    with pytest.raises(ValueError, match="candidate obligation ids must be unique"):
        ProgressAttributionTicket(
            ticket_id="ticket-1",
            task_revision=3,
            issued_at_state_version=8,
            contract_id="contract-1",
            semantic_target_id="semantic:field",
            action_kind="type_text",
            candidate_obligation_ids=("obligation:first", "obligation:first"),
            pre_snapshot_id="snapshot-pre",
            pre_page_revision="page-pre",
            pre_environment_revision="env-pre",
        )

    with pytest.raises(ValueError, match="satisfaction evidence refs cannot be empty"):
        ObligationSatisfactionPreparation(
            task_revision=3,
            evaluated_at_state_version=9,
            obligation_id="obligation:first",
            contract_id="contract-1",
            post_snapshot_id="snapshot-post",
            evidence_refs=(),
            source="post_verification",
        )
