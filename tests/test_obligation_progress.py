import pytest

from affordance_runtime.obligation_attribution import (
    EvidenceStrength,
    ObligationAttributionResult,
    ObligationSatisfactionPreparation,
    PostActionEvidenceFact,
    PostVerificationSatisfactionSource,
    ProgressAttributionTicket,
)
from affordance_runtime.obligation_progress import (
    ObligationAttemptCount,
    ObligationEvidenceLedgerEntry,
    ObligationExecutionRole,
    ObligationProgressStateView,
    TaskObligationExecutionView,
    ready_obligation_ids,
    task_obligation_execution_views,
    task_obligations_completed,
    validate_obligation_progress_state,
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
    task_spec: TaskSpec | None = None,
    *,
    satisfied: tuple[str, ...] = (),
    failed: tuple[str, ...] = (),
) -> ObligationProgressStateView:
    known_ids = (
        tuple(obligation.obligation_id for obligation in task_spec.obligations)
        if task_spec is not None
        else (
            "obligation:precondition",
            "obligation:first",
            "obligation:second",
            "obligation:evidence-only",
            "obligation:optional",
            "obligation:terminal",
        )
    )
    return ObligationProgressStateView(
        task_spec_identity=task_spec.identity if task_spec is not None else "sha256:test-task",
        task_revision=3,
        evaluated_at_state_version=8,
        known_obligation_ids=known_ids,
        satisfied_obligation_ids=satisfied,
        failed_obligation_ids=failed,
        evidence_by_obligation=tuple(
            ObligationEvidenceLedgerEntry(
                obligation_id=item,
                evidence_refs=(f"evidence-ref:{item}",),
            )
            for item in satisfied
        ),
        attempt_count_by_obligation=(),
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

    assert ready_obligation_ids(task_spec, _progress(task_spec), views) == ("obligation:first",)
    assert ready_obligation_ids(task_spec, _progress(task_spec, satisfied=("obligation:first",)), views) == (
        "obligation:second",
    )


def test_ready_projection_rejects_missing_or_extra_execution_role_views() -> None:
    task_spec = _task_spec((_obligation("obligation:first", terminal=True),))
    view = TaskObligationExecutionView.from_obligation(
        task_spec.obligations[0],
        role=ObligationExecutionRole.TERMINAL_EFFECT,
    )

    with pytest.raises(ValueError, match="missing obligation execution role"):
        ready_obligation_ids(task_spec, _progress(task_spec), ())

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
        ready_obligation_ids(task_spec, _progress(task_spec), (view, extra))


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
        _progress(task_spec, satisfied=("obligation:first", "obligation:optional")),
        views,
    )
    assert task_obligations_completed(
        task_spec,
        _progress(task_spec, satisfied=("obligation:first", "obligation:terminal")),
        views,
    )


def test_progress_state_is_bound_to_exact_task_spec_identity_and_graph_ids() -> None:
    task_spec = _task_spec((_obligation("obligation:first", terminal=True),))

    with pytest.raises(ValueError, match="task spec identity"):
        validate_obligation_progress_state(
            task_spec,
            ObligationProgressStateView(
                task_spec_identity="sha256:wrong",
                task_revision=task_spec.revision,
                evaluated_at_state_version=8,
                known_obligation_ids=("obligation:first",),
            ),
        )

    with pytest.raises(ValueError, match="task revision"):
        validate_obligation_progress_state(
            task_spec,
            ObligationProgressStateView(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision + 1,
                evaluated_at_state_version=8,
                known_obligation_ids=("obligation:first",),
            ),
        )

    with pytest.raises(ValueError, match="known obligation ids"):
        validate_obligation_progress_state(
            task_spec,
            ObligationProgressStateView(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                evaluated_at_state_version=8,
                known_obligation_ids=("obligation:typo",),
            ),
        )


def test_ready_and_completion_reject_unknown_progress_ids() -> None:
    task_spec = _task_spec((_obligation("obligation:first", terminal=True),))
    views = task_obligation_execution_views(
        task_spec,
        {"obligation:first": ObligationExecutionRole.TERMINAL_EFFECT},
    )

    invalid_cases = (
        {"satisfied_obligation_ids": ("obligation:typo",)},
        {"failed_obligation_ids": ("obligation:typo",)},
        {
            "evidence_by_obligation": (
                ObligationEvidenceLedgerEntry(
                    obligation_id="obligation:typo",
                    evidence_refs=("evidence:1",),
                ),
            )
        },
        {
            "attempt_count_by_obligation": (
                ObligationAttemptCount(
                    obligation_id="obligation:typo",
                    attempt_count=1,
                ),
            )
        },
    )
    for invalid in invalid_cases:
        with pytest.raises(ValueError, match="unknown obligation progress id"):
            ObligationProgressStateView(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                evaluated_at_state_version=8,
                known_obligation_ids=("obligation:first",),
                **invalid,
            )

    stale_known_graph = ObligationProgressStateView(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=8,
        known_obligation_ids=("obligation:first", "obligation:stale"),
    )
    with pytest.raises(ValueError, match="known obligation ids"):
        ready_obligation_ids(task_spec, stale_known_graph, views)
    with pytest.raises(ValueError, match="known obligation ids"):
        task_obligations_completed(task_spec, stale_known_graph, views)


def test_progress_state_view_uses_immutable_ledger_entries() -> None:
    task_spec = _task_spec((_obligation("obligation:first", terminal=True),))
    progress = ObligationProgressStateView(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=8,
        known_obligation_ids=("obligation:first",),
        evidence_by_obligation=(
            ObligationEvidenceLedgerEntry(
                obligation_id="obligation:first",
                evidence_refs=("evidence:1",),
            ),
        ),
        attempt_count_by_obligation=(
            ObligationAttemptCount(
                obligation_id="obligation:first",
                attempt_count=1,
            ),
        ),
    )

    assert progress.evidence_by_obligation[0].evidence_refs == ("evidence:1",)
    assert progress.attempt_count_by_obligation[0].attempt_count == 1


def test_attribution_ticket_and_satisfaction_preparation_are_identity_bound() -> None:
    ticket = ProgressAttributionTicket(
        ticket_id="ticket-1",
        task_spec_identity="sha256:test-task",
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
        task_spec_identity=ticket.task_spec_identity,
        task_revision=ticket.task_revision,
        evaluated_at_state_version=9,
        obligation_id="obligation:first",
        evidence_refs=fact.evidence_refs,
        source=PostVerificationSatisfactionSource(
            contract_id=ticket.contract_id,
            post_snapshot_id=fact.post_snapshot_id,
            post_page_revision=fact.post_page_revision,
            post_environment_revision=fact.post_environment_revision,
        ),
    )

    assert ticket.candidate_obligation_ids == ("obligation:first",)
    assert ticket.task_spec_identity == "sha256:test-task"
    assert preparation.task_spec_identity == "sha256:test-task"
    assert preparation.evidence_refs == ("verification:1",)
    assert preparation.source.contract_id == "contract-1"


def test_attribution_contracts_fail_closed_on_blank_or_duplicate_identity() -> None:
    with pytest.raises(ValueError, match="candidate obligation ids cannot be empty"):
        ProgressAttributionTicket(
            ticket_id="ticket-1",
            task_spec_identity="sha256:test-task",
            task_revision=3,
            issued_at_state_version=8,
            contract_id="contract-1",
            semantic_target_id="semantic:field",
            action_kind="type_text",
            candidate_obligation_ids=(),
            pre_snapshot_id="snapshot-pre",
            pre_page_revision="page-pre",
            pre_environment_revision="env-pre",
        )

    with pytest.raises(ValueError, match="candidate obligation ids must be unique"):
        ProgressAttributionTicket(
            ticket_id="ticket-1",
            task_spec_identity="sha256:test-task",
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
            task_spec_identity="sha256:test-task",
            task_revision=3,
            evaluated_at_state_version=9,
            obligation_id="obligation:first",
            evidence_refs=(),
            source=PostVerificationSatisfactionSource(
                contract_id="contract-1",
                post_snapshot_id="snapshot-post",
                post_page_revision="page-post",
                post_environment_revision="env-post",
            ),
        )

    with pytest.raises(ValueError, match="task spec identity cannot be blank"):
        ProgressAttributionTicket(
            ticket_id="ticket-1",
            task_spec_identity="",
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


def test_attribution_result_status_matches_satisfaction_preparation() -> None:
    preparation = ObligationSatisfactionPreparation(
        task_spec_identity="sha256:test-task",
        task_revision=3,
        evaluated_at_state_version=9,
        obligation_id="obligation:first",
        evidence_refs=("verification:1",),
        source=PostVerificationSatisfactionSource(
            contract_id="contract-1",
            post_snapshot_id="snapshot-post",
            post_page_revision="page-post",
            post_environment_revision="env-post",
        ),
    )

    assert ObligationAttributionResult(
        status="satisfied",
        preparation=preparation,
    ).preparation == preparation

    with pytest.raises(ValueError, match="satisfied attribution requires preparation"):
        ObligationAttributionResult(status="satisfied")

    with pytest.raises(ValueError, match="non-satisfied attribution cannot include preparation"):
        ObligationAttributionResult(status="no_match", preparation=preparation)
