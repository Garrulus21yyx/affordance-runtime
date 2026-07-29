from affordance_runtime.obligation_attribution import (
    EvidenceSourceKind,
    EvidenceStrength,
    ObligationAttributionResult,
    PostActionEvidenceFact,
    PostVerificationObligationAttributor,
    ProgressAttributionTicket,
)
from affordance_runtime.obligation_progress import ObligationProgressStateView
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
    minimum_strength: str = "independent",
    source_ref: str = "post_action_observation",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        kind=EvidenceKind.DOM_STATE,
        subject=subject,
        relation=relation,
        minimum_strength=minimum_strength,
        source_constraints=(source_ref,),
    )


def _obligation(
    obligation_id: str,
    *,
    subject: str = "semantic:slider",
    relation: TaskObligationRelation = TaskObligationRelation.EQUALS,
    expected_value: str = "7",
    depends_on: tuple[str, ...] = (),
    terminal: bool = True,
    blocking: bool = True,
    typed_evidence: tuple[EvidenceRequirement, ...] | None = None,
) -> TaskObligationSpec:
    value_source = (
        TaskObligationValueSource.LITERAL
        if relation
        in {
            TaskObligationRelation.EQUALS,
            TaskObligationRelation.CONTAINS,
            TaskObligationRelation.MATCHES,
            TaskObligationRelation.IS_SELECTED,
        }
        else TaskObligationValueSource.NONE
    )
    return TaskObligationSpec(
        obligation_id=obligation_id,
        kind=TaskObligationKind.EFFECT,
        subject=subject,
        relation=relation,
        value_source=value_source,
        expected_value=expected_value if value_source == TaskObligationValueSource.LITERAL else "",
        claim_ids=(f"claim:{obligation_id}",),
        depends_on=depends_on,
        evidence_requirements=(f"evidence:{obligation_id}",),
        typed_evidence_requirements=typed_evidence
        if typed_evidence is not None
        else (_typed_evidence(subject=subject, relation=relation),),
        blocking=blocking,
        terminal=terminal,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _task_spec(obligations: tuple[TaskObligationSpec, ...]) -> TaskSpec:
    return TaskSpec(
        task_id="task-odg-9",
        revision=5,
        objective="attribute post-action verifier evidence",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("semantic:slider",),
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


def _progress(
    task_spec: TaskSpec,
    *,
    satisfied: tuple[str, ...] = (),
    failed: tuple[str, ...] = (),
    state_version: int = 23,
    task_spec_identity: str | None = None,
) -> ObligationProgressStateView:
    return ObligationProgressStateView(
        task_spec_identity=task_spec.identity
        if task_spec_identity is None
        else task_spec_identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=state_version,
        known_obligation_ids=tuple(
            obligation.obligation_id for obligation in task_spec.obligations
        ),
        satisfied_obligation_ids=satisfied,
        failed_obligation_ids=failed,
    )


def _ticket(
    task_spec: TaskSpec,
    *,
    candidates: tuple[str, ...],
    task_spec_identity: str | None = None,
    task_revision: int | None = None,
    contract_id: str = "contract-1",
    contract_hash: str = "sha256:contract-1",
) -> ProgressAttributionTicket:
    return ProgressAttributionTicket(
        ticket_id="ticket:slider",
        task_spec_identity=task_spec.identity
        if task_spec_identity is None
        else task_spec_identity,
        task_revision=task_spec.revision if task_revision is None else task_revision,
        issued_at_state_version=17,
        contract_id=contract_id,
        contract_hash=contract_hash,
        semantic_target_id="semantic:slider",
        action_kind="press_key",
        candidate_obligation_ids=candidates,
        pre_snapshot_id="snapshot-pre",
        pre_page_revision="page-pre",
        pre_environment_revision="env-pre",
    )


def _fact(
    *,
    subject: str = "semantic:slider",
    relation: TaskObligationRelation = TaskObligationRelation.EQUALS,
    before_value: object | None = None,
    after_value: object | None = "7",
    expected_value: object | None = "7",
    strength: EvidenceStrength = EvidenceStrength.INDEPENDENT,
    source_kind: EvidenceSourceKind = EvidenceSourceKind.POST_ACTION_OBSERVATION,
    contract_id: str = "contract-1",
    contract_hash: str = "sha256:contract-1",
    pre_snapshot_id: str = "snapshot-pre",
    post_snapshot_id: str = "snapshot-post",
    evidence_ref: str = "evidence:slider",
) -> PostActionEvidenceFact:
    return PostActionEvidenceFact(
        contract_id=contract_id,
        contract_hash=contract_hash,
        pre_snapshot_id=pre_snapshot_id,
        post_snapshot_id=post_snapshot_id,
        post_page_revision="page-post",
        post_environment_revision="env-post",
        action_semantic_target_id="semantic:slider",
        evidence_subject_id=subject,
        relation=relation,
        before_value=before_value,  # type: ignore[arg-type]
        after_value=after_value,  # type: ignore[arg-type]
        expected_value=expected_value,  # type: ignore[arg-type]
        verifier_kind="control_state",
        source_kind=source_kind,
        strength=strength,
        passed=True,
        evidence_refs=(evidence_ref,),
        criterion_ids=("criterion:slider",),
        requirement_ids=("requirement:slider",),
    )


def _attribute(
    *,
    task_spec: TaskSpec,
    ticket: ProgressAttributionTicket,
    progress: ObligationProgressStateView | None = None,
    facts: tuple[PostActionEvidenceFact, ...],
) -> ObligationAttributionResult:
    return PostVerificationObligationAttributor().attribute(
        task_spec=task_spec,
        progress=progress or _progress(task_spec),
        ticket=ticket,
        facts=facts,
    )


def test_slider_multi_candidate_fact_satisfies_only_matching_expected_value() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:slider-5", expected_value="5", terminal=False, blocking=False),
            _obligation("obligation:slider-7", expected_value="7", terminal=True),
        ),
    )

    result = _attribute(
        task_spec=task_spec,
        ticket=_ticket(
            task_spec,
            candidates=("obligation:slider-5", "obligation:slider-7"),
        ),
        facts=(
            _fact(
                relation=TaskObligationRelation.EQUALS,
                before_value="5",
                after_value="7",
                expected_value="7",
            ),
        ),
    )

    assert result.status == "satisfied"
    assert result.preparation is not None
    assert result.preparation.obligation_id == "obligation:slider-7"
    assert result.preparation.task_spec_identity == task_spec.identity
    assert result.preparation.evaluated_at_state_version == 23
    assert result.preparation.evidence_refs == ("evidence:slider",)


def test_checkbox_and_terminal_submit_can_be_attributed_from_strong_facts() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:slider", expected_value="7", terminal=False),
            _obligation(
                "obligation:checkbox",
                subject="semantic:checkbox",
                relation=TaskObligationRelation.IS_CHECKED,
                depends_on=("obligation:slider",),
                terminal=False,
            ),
            _obligation(
                "obligation:submit",
                subject="semantic:submit",
                relation=TaskObligationRelation.IS_COMPLETED,
                depends_on=("obligation:checkbox",),
                terminal=True,
                typed_evidence=(
                    _typed_evidence(
                        subject="semantic:submit",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        source_ref="independent_api",
                    ),
                ),
            ),
        ),
    )

    checkbox = _attribute(
        task_spec=task_spec,
        progress=_progress(task_spec, satisfied=("obligation:slider",)),
        ticket=_ticket(task_spec, candidates=("obligation:checkbox",)),
        facts=(
            _fact(
                subject="semantic:checkbox",
                relation=TaskObligationRelation.IS_CHECKED,
                after_value=True,
                expected_value=True,
                evidence_ref="evidence:checkbox",
            ),
        ),
    )
    submit = _attribute(
        task_spec=task_spec,
        progress=_progress(
            task_spec,
            satisfied=("obligation:slider", "obligation:checkbox"),
        ),
        ticket=_ticket(task_spec, candidates=("obligation:submit",)),
        facts=(
            _fact(
                subject="semantic:submit",
                relation=TaskObligationRelation.IS_COMPLETED,
                after_value=True,
                expected_value=True,
                source_kind=EvidenceSourceKind.INDEPENDENT_API,
                strength=EvidenceStrength.AUTHORITATIVE,
                evidence_ref="evidence:submit",
            ),
        ),
    )

    assert checkbox.status == "satisfied"
    assert checkbox.preparation is not None
    assert checkbox.preparation.obligation_id == "obligation:checkbox"
    assert submit.status == "satisfied"
    assert submit.preparation is not None
    assert submit.preparation.obligation_id == "obligation:submit"


def test_multiple_facts_must_cover_all_typed_evidence_requirements() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:combined",
                subject="semantic:field",
                typed_evidence=(
                    _typed_evidence(
                        subject="semantic:field",
                        relation=TaskObligationRelation.EQUALS,
                    ),
                    _typed_evidence(
                        subject="semantic:api",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        source_ref="independent_api",
                        minimum_strength="authoritative",
                    ),
                ),
            ),
        ),
    )

    partial = _attribute(
        task_spec=task_spec,
        ticket=_ticket(task_spec, candidates=("obligation:combined",)),
        facts=(
            _fact(subject="semantic:field", evidence_ref="evidence:dom"),
        ),
    )
    complete = _attribute(
        task_spec=task_spec,
        ticket=_ticket(task_spec, candidates=("obligation:combined",)),
        facts=(
            _fact(subject="semantic:field", evidence_ref="evidence:dom"),
            _fact(
                subject="semantic:api",
                relation=TaskObligationRelation.IS_COMPLETED,
                after_value=True,
                expected_value=True,
                source_kind=EvidenceSourceKind.INDEPENDENT_API,
                strength=EvidenceStrength.AUTHORITATIVE,
                evidence_ref="evidence:api",
            ),
        ),
    )

    assert partial.status == "no_match"
    assert complete.status == "satisfied"
    assert complete.preparation is not None
    assert complete.preparation.evidence_refs == ("evidence:dom", "evidence:api")


def test_identity_candidate_and_dependency_fail_closed() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:first", terminal=False),
            _obligation("obligation:second", depends_on=("obligation:first",)),
        ),
    )

    assert (
        _attribute(
            task_spec=task_spec,
            ticket=_ticket(
                task_spec,
                candidates=("obligation:second",),
                task_spec_identity="sha256:stale",
            ),
            facts=(_fact(),),
        ).status
        == "stale"
    )
    assert (
        _attribute(
            task_spec=task_spec,
            ticket=_ticket(task_spec, candidates=("obligation:missing",)),
            facts=(_fact(),),
        ).status
        == "invalid"
    )
    assert (
        _attribute(
            task_spec=task_spec,
            ticket=_ticket(task_spec, candidates=("obligation:second",)),
            facts=(_fact(),),
        ).status
        == "dependency_blocked"
    )
    assert (
        _attribute(
            task_spec=task_spec,
            progress=_progress(task_spec, satisfied=("obligation:second",)),
            ticket=_ticket(task_spec, candidates=("obligation:second",)),
            facts=(_fact(),),
        ).status
        == "no_match"
    )
    assert (
        _attribute(
            task_spec=task_spec,
            progress=_progress(task_spec, failed=("obligation:second",)),
            ticket=_ticket(task_spec, candidates=("obligation:second",)),
            facts=(_fact(),),
        ).status
        == "no_match"
    )


def test_fact_identity_relation_value_strength_and_cardinality_fail_closed() -> None:
    task_spec = _task_spec((_obligation("obligation:slider"),))
    ticket = _ticket(task_spec, candidates=("obligation:slider",))

    cases = (
        (_fact(contract_id="contract-other"), "stale"),
        (_fact(contract_hash="sha256:other"), "stale"),
        (_fact(pre_snapshot_id="snapshot-other"), "stale"),
        (_fact(subject="semantic:other"), "no_match"),
        (_fact(relation=TaskObligationRelation.IS_CHECKED, after_value=True, expected_value=True), "no_match"),
        (_fact(after_value="9", expected_value="9"), "no_match"),
        (_fact(strength=EvidenceStrength.WEAK), "weak_evidence"),
        (
            _fact(
                source_kind=EvidenceSourceKind.EXECUTION_RECEIPT,
                strength=EvidenceStrength.WEAK,
            ),
            "weak_evidence",
        ),
        (
            _fact(
                source_kind=EvidenceSourceKind.EXTERNAL_EVALUATOR,
                strength=EvidenceStrength.WEAK,
            ),
            "weak_evidence",
        ),
    )
    for fact, status in cases:
        assert (
            _attribute(task_spec=task_spec, ticket=ticket, facts=(fact,)).status
            == status
        )

    ambiguous_spec = _task_spec(
        (
            _obligation("obligation:first"),
            _obligation("obligation:second"),
        ),
    )
    ambiguous = _attribute(
        task_spec=ambiguous_spec,
        ticket=_ticket(
            ambiguous_spec,
            candidates=("obligation:first", "obligation:second"),
        ),
        facts=(_fact(),),
    )
    assert ambiguous.status == "ambiguous"


def test_taskplan_is_not_required_for_attribution() -> None:
    task_spec = _task_spec((_obligation("obligation:slider"),))

    result = _attribute(
        task_spec=task_spec,
        ticket=_ticket(task_spec, candidates=("obligation:slider",)),
        facts=(_fact(),),
    )

    assert result.status == "satisfied"
