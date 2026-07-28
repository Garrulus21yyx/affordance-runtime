import pytest

from affordance_runtime.obligation_attribution import ObligationSatisfactionPreparation
from affordance_runtime.obligation_current_state import (
    CurrentObservationAffordanceFact,
    CurrentObservationObligationSatisfactionEvaluator,
)
from affordance_runtime.obligation_progress import (
    ObligationEvidenceLedgerEntry,
    ObligationExecutionRole,
    ObligationProgressStateView,
    TaskObligationExecutionView,
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
    subject: str = "submit_button",
    relation: TaskObligationRelation = TaskObligationRelation.IS_AVAILABLE,
    kind: TaskObligationKind = TaskObligationKind.PREDICATE,
    depends_on: tuple[str, ...] = (),
    terminal: bool = True,
    blocking: bool = True,
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
        task_id="task-current-observation-obligation",
        revision=5,
        objective="complete the canonical graph",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("submit_button",),
        success_criteria=("terminal obligation satisfied",),
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


def _progress(
    task_spec: TaskSpec,
    *,
    satisfied: tuple[str, ...] = (),
    failed: tuple[str, ...] = (),
    task_spec_identity: str | None = None,
    task_revision: int | None = None,
) -> ObligationProgressStateView:
    return ObligationProgressStateView(
        task_spec_identity=task_spec.identity
        if task_spec_identity is None
        else task_spec_identity,
        task_revision=task_spec.revision if task_revision is None else task_revision,
        evaluated_at_state_version=13,
        known_obligation_ids=tuple(
            obligation.obligation_id for obligation in task_spec.obligations
        ),
        satisfied_obligation_ids=satisfied,
        failed_obligation_ids=failed,
        evidence_by_obligation=tuple(
            ObligationEvidenceLedgerEntry(
                obligation_id=obligation_id,
                evidence_refs=(f"evidence-ref:{obligation_id}",),
            )
            for obligation_id in satisfied
        ),
    )


def _views(
    task_spec: TaskSpec,
    *,
    role: ObligationExecutionRole = ObligationExecutionRole.TERMINAL_EFFECT,
) -> tuple[TaskObligationExecutionView, ...]:
    return tuple(
        TaskObligationExecutionView.from_obligation(obligation, role=role)
        for obligation in task_spec.obligations
    )


def _fact(
    *,
    subject: str = "submit_button",
    semantic_target_id: str = "submit-button",
    relation: TaskObligationRelation = TaskObligationRelation.IS_AVAILABLE,
    visible: bool | None = True,
    enabled: bool | None = True,
    snapshot_id: str = "snapshot-1",
    page_revision: str = "page-1",
    environment_revision: str = "env-1",
    evidence_refs: tuple[str, ...] = ("current-observation:submit-button",),
) -> CurrentObservationAffordanceFact:
    return CurrentObservationAffordanceFact(
        snapshot_id=snapshot_id,
        page_revision=page_revision,
        environment_revision=environment_revision,
        semantic_target_id=semantic_target_id,
        subject=subject,
        relation=relation,
        visible=visible,
        enabled=enabled,
        evidence_refs=evidence_refs,
    )


def test_current_available_obligation_can_prepare_satisfaction_without_taskplan() -> None:
    task_spec = _task_spec(
        (_obligation("obligation:submit-available"),),
    )

    preparation = CurrentObservationObligationSatisfactionEvaluator().evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec),
        execution_views=_views(task_spec),
        facts=(_fact(),),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    )

    assert preparation == ObligationSatisfactionPreparation(
        task_revision=task_spec.revision,
        evaluated_at_state_version=13,
        obligation_id="obligation:submit-available",
        contract_id="current-observation:snapshot-1",
        post_snapshot_id="snapshot-1",
        evidence_refs=("current-observation:submit-button",),
        source="current_observation",
    )


def test_current_visible_obligation_can_prepare_satisfaction() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:submit-visible",
                relation=TaskObligationRelation.IS_VISIBLE,
            ),
        ),
    )

    preparation = CurrentObservationObligationSatisfactionEvaluator().evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec),
        execution_views=_views(task_spec),
        facts=(
            _fact(
                relation=TaskObligationRelation.IS_VISIBLE,
                enabled=None,
            ),
        ),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    )

    assert preparation is not None
    assert preparation.obligation_id == "obligation:submit-visible"


@pytest.mark.parametrize(
    "role",
    (
        ObligationExecutionRole.PRECONDITION,
        ObligationExecutionRole.EVIDENCE_ONLY,
    ),
)
def test_non_progress_roles_do_not_prepare_satisfaction(
    role: ObligationExecutionRole,
) -> None:
    task_spec = _task_spec((_obligation("obligation:submit-available"),))

    assert (
        CurrentObservationObligationSatisfactionEvaluator().evaluate(
            task_spec=task_spec,
            progress=_progress(task_spec),
            execution_views=_views(task_spec, role=role),
            facts=(_fact(),),
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
        )
        is None
    )


def test_dependency_must_be_satisfied_before_current_observation_completion() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:text-changed",
                kind=TaskObligationKind.EFFECT,
                subject="text_field",
                relation=TaskObligationRelation.HAS_CHANGED,
                terminal=False,
            ),
            _obligation(
                "obligation:submit-available",
                depends_on=("obligation:text-changed",),
            ),
        ),
    )

    assert (
        CurrentObservationObligationSatisfactionEvaluator().evaluate(
            task_spec=task_spec,
            progress=_progress(task_spec),
            execution_views=(
                TaskObligationExecutionView.from_obligation(
                    task_spec.obligations[0],
                    role=ObligationExecutionRole.PROGRESS_EFFECT,
                ),
                TaskObligationExecutionView.from_obligation(
                    task_spec.obligations[1],
                    role=ObligationExecutionRole.TERMINAL_EFFECT,
                ),
            ),
            facts=(_fact(),),
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
        )
        is None
    )


def test_current_observation_satisfaction_fails_closed_for_ambiguous_targets() -> None:
    task_spec = _task_spec((_obligation("obligation:submit-available"),))

    assert (
        CurrentObservationObligationSatisfactionEvaluator().evaluate(
            task_spec=task_spec,
            progress=_progress(task_spec),
            execution_views=_views(task_spec),
            facts=(
                _fact(semantic_target_id="submit-button-1"),
                _fact(semantic_target_id="submit-button-2"),
            ),
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
        )
        is None
    )


def test_hidden_or_disabled_affordance_does_not_satisfy_availability() -> None:
    task_spec = _task_spec((_obligation("obligation:submit-available"),))
    evaluator = CurrentObservationObligationSatisfactionEvaluator()

    assert evaluator.evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec),
        execution_views=_views(task_spec),
        facts=(_fact(visible=False),),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None
    assert evaluator.evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec),
        execution_views=_views(task_spec),
        facts=(_fact(enabled=False),),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None


def test_stale_task_or_observation_identity_is_rejected() -> None:
    task_spec = _task_spec((_obligation("obligation:submit-available"),))
    evaluator = CurrentObservationObligationSatisfactionEvaluator()

    assert evaluator.evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec, task_spec_identity="sha256:stale"),
        execution_views=_views(task_spec),
        facts=(_fact(),),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None
    assert evaluator.evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec, task_revision=task_spec.revision + 1),
        execution_views=_views(task_spec),
        facts=(_fact(),),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None
    assert evaluator.evaluate(
        task_spec=task_spec,
        progress=_progress(task_spec),
        execution_views=_views(task_spec),
        facts=(_fact(snapshot_id="snapshot-stale"),),
        snapshot_id="snapshot-1",
        page_revision="page-1",
        environment_revision="env-1",
    ) is None


def test_unsupported_relations_are_not_completed_from_current_observation() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:text-changed",
                kind=TaskObligationKind.EFFECT,
                subject="text_field",
                relation=TaskObligationRelation.HAS_CHANGED,
                terminal=True,
            ),
        ),
    )

    assert (
        CurrentObservationObligationSatisfactionEvaluator().evaluate(
            task_spec=task_spec,
            progress=_progress(task_spec),
            execution_views=_views(task_spec),
            facts=(
                _fact(
                    subject="text_field",
                    relation=TaskObligationRelation.HAS_CHANGED,
                ),
            ),
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
        )
        is None
    )
