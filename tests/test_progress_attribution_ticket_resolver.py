from affordance_runtime.obligation_attribution import (
    AttributionActionView,
    AttributionTargetView,
    ProgressAttributionTicketResolution,
    ProgressAttributionTicketResolver,
)
from affordance_runtime.obligation_progress import (
    ObligationExecutionRole,
    ObligationProgressStateView,
    ReadyObligationProjection,
    ReadyObligationView,
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
    subject: str = "semantic:field",
    relation: TaskObligationRelation = TaskObligationRelation.EQUALS,
    kind: TaskObligationKind = TaskObligationKind.EFFECT,
    depends_on: tuple[str, ...] = (),
    terminal: bool = False,
    blocking: bool = True,
    expected_value: str = "Alice",
    value_source: TaskObligationValueSource = TaskObligationValueSource.LITERAL,
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
        task_id="task-ticket-resolver",
        revision=11,
        objective="complete ready obligations",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.MULTI_STAGE,
        targets=("semantic:field",),
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
    task_spec_identity: str | None = None,
    state_version: int = 17,
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


def _ready_projection(
    task_spec: TaskSpec,
    *,
    roles: tuple[ObligationExecutionRole, ...] | None = None,
    status: str = "ready",
    override_view: ReadyObligationView | None = None,
) -> ReadyObligationProjection:
    if status == "role_pending":
        return ReadyObligationProjection(
            status="role_pending",
            ready_obligations=(),
            pending_role_obligation_ids=(task_spec.obligations[0].obligation_id,),
            reason="role pending",
        )
    if status == "stale_progress":
        return ReadyObligationProjection(
            status="stale_progress",
            ready_obligations=(),
            pending_role_obligation_ids=(),
            reason="stale progress",
        )
    if status == "invalid_progress":
        return ReadyObligationProjection(
            status="invalid_progress",
            ready_obligations=(),
            pending_role_obligation_ids=(),
            reason="invalid progress",
        )
    resolved_roles = roles or tuple(
        ObligationExecutionRole.TERMINAL_EFFECT
        if obligation.terminal
        else ObligationExecutionRole.PROGRESS_EFFECT
        for obligation in task_spec.obligations
    )
    return ReadyObligationProjection(
        status="ready",
        ready_obligations=(override_view,)
        if override_view is not None
        else tuple(
            ReadyObligationView(
                obligation_id=obligation.obligation_id,
                role=role,
                subject=obligation.subject,
                relation=obligation.relation,
                expected_value=obligation.expected_value,
                evidence_requirements=obligation.evidence_requirements,
                dependency_ids=obligation.depends_on,
                terminal=obligation.terminal,
            )
            for obligation, role in zip(task_spec.obligations, resolved_roles, strict=True)
        ),
        pending_role_obligation_ids=(),
    )


def _action(
    task_spec: TaskSpec,
    *,
    semantic_target_id: str = "semantic:field",
    canonical_subject_ids: tuple[str, ...] | None = None,
    action_kind: str = "type_text",
    state_version: int = 17,
    snapshot_id: str = "snapshot-pre",
    contract_id: str = "contract-1",
    contract_hash: str = "sha256:contract-1",
) -> AttributionActionView:
    return AttributionActionView(
        contract_id=contract_id,
        contract_hash=contract_hash,
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        issued_at_state_version=state_version,
        target=AttributionTargetView(
            semantic_target_id=semantic_target_id,
            canonical_subject_ids=canonical_subject_ids or (semantic_target_id,),
        ),
        action_kind=action_kind,
        pre_snapshot_id=snapshot_id,
        pre_page_revision="page-pre",
        pre_environment_revision="env-pre",
    )


def test_single_text_effect_creates_identity_bound_ticket() -> None:
    task_spec = _task_spec((_obligation("obligation:text", terminal=True),))

    result = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(task_spec),
    )

    assert result.status == "ticket_created"
    assert result.ticket is not None
    assert result.ticket.task_spec_identity == task_spec.identity
    assert result.ticket.task_revision == task_spec.revision
    assert result.ticket.issued_at_state_version == 17
    assert result.ticket.contract_hash == "sha256:contract-1"
    assert result.ticket.candidate_obligation_ids == ("obligation:text",)
    assert result.ticket.pre_snapshot_id == "snapshot-pre"
    assert result.ticket.compatibility_plan_id == ""


def test_multiple_slider_value_candidates_remain_in_one_ticket() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:slider-5",
                subject="semantic:slider",
                expected_value="5",
                terminal=True,
            ),
            _obligation(
                "obligation:slider-7",
                subject="semantic:slider",
                expected_value="7",
                terminal=True,
            ),
        ),
    )

    result = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(
            task_spec,
            semantic_target_id="semantic:slider",
            action_kind="press_key",
        ),
    )

    assert result == ProgressAttributionTicketResolution(
        status="ticket_created",
        ticket=result.ticket,
    )
    assert result.ticket is not None
    assert result.ticket.candidate_obligation_ids == (
        "obligation:slider-5",
        "obligation:slider-7",
    )


def test_terminal_submit_effect_creates_ticket_after_dependencies_are_satisfied() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:checkbox", subject="semantic:checkbox"),
            _obligation(
                "obligation:submit",
                subject="semantic:submit",
                relation=TaskObligationRelation.IS_COMPLETED,
                depends_on=("obligation:checkbox",),
                terminal=True,
                expected_value="",
                value_source=TaskObligationValueSource.NONE,
            ),
        ),
    )

    result = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec, satisfied=("obligation:checkbox",)),
        ready_projection=_ready_projection(
            task_spec,
            roles=(
                ObligationExecutionRole.PROGRESS_EFFECT,
                ObligationExecutionRole.TERMINAL_EFFECT,
            ),
        ),
        action=_action(
            task_spec,
            semantic_target_id="semantic:submit",
            action_kind="activate",
        ),
    )

    assert result.status == "ticket_created"
    assert result.ticket is not None
    assert result.ticket.candidate_obligation_ids == ("obligation:submit",)


def test_blocked_precondition_evidence_only_or_finished_obligations_are_not_candidates() -> None:
    task_spec = _task_spec(
        (
            _obligation("obligation:first"),
            _obligation("obligation:second", depends_on=("obligation:first",), terminal=True),
        ),
    )

    blocked = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(
            task_spec,
            roles=(
                ObligationExecutionRole.PROGRESS_EFFECT,
                ObligationExecutionRole.PROGRESS_EFFECT,
            ),
        ),
        action=_action(task_spec),
    )
    precondition = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(
            task_spec,
            roles=(
                ObligationExecutionRole.PRECONDITION,
                ObligationExecutionRole.EVIDENCE_ONLY,
            ),
        ),
        action=_action(task_spec),
    )
    already_done = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec, satisfied=("obligation:first",)),
        ready_projection=_ready_projection(task_spec),
        action=_action(task_spec),
    )

    assert blocked.ticket is not None
    assert blocked.ticket.candidate_obligation_ids == ("obligation:first",)
    assert precondition.status == "no_candidate"
    assert already_done.ticket is not None
    assert "obligation:first" not in already_done.ticket.candidate_obligation_ids


def test_stale_identity_or_projection_is_reported_without_ticket() -> None:
    task_spec = _task_spec((_obligation("obligation:text", terminal=True),))
    resolver = ProgressAttributionTicketResolver()

    stale_task = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec, task_spec_identity="sha256:stale"),
        ready_projection=_ready_projection(task_spec),
        action=_action(task_spec),
    )
    stale_state = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(task_spec, state_version=18),
    )
    role_pending = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec, status="role_pending"),
        action=_action(task_spec),
    )
    stale_projection = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec, status="stale_progress"),
        action=_action(task_spec),
    )
    invalid_projection = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec, status="invalid_progress"),
        action=_action(task_spec),
    )

    assert stale_task.status == "stale"
    assert stale_state.status == "stale"
    assert role_pending.status == "role_pending"
    assert stale_projection.status == "stale"
    assert invalid_projection.status == "invalid"


def test_incompatible_action_or_target_has_no_candidate() -> None:
    task_spec = _task_spec((_obligation("obligation:text", terminal=True),))
    resolver = ProgressAttributionTicketResolver()

    wrong_action = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(task_spec, action_kind="activate"),
    )
    wrong_target = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(
            task_spec,
            semantic_target_id="semantic:other",
            canonical_subject_ids=("semantic:other",),
        ),
    )

    assert wrong_action.status == "no_candidate"
    assert wrong_target.status == "no_candidate"


def test_target_binding_uses_runtime_supplied_canonical_subject_ids() -> None:
    task_spec = _task_spec(
        (
            _obligation(
                "obligation:text",
                subject="source-derived-text-field",
                terminal=True,
            ),
        ),
    )

    result = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(
            task_spec,
            semantic_target_id="semantic:field",
            canonical_subject_ids=("source-derived-text-field",),
        ),
    )

    assert result.status == "ticket_created"
    assert result.ticket is not None
    assert result.ticket.semantic_target_id == "semantic:field"
    assert result.ticket.candidate_obligation_ids == ("obligation:text",)


def test_ready_projection_must_match_current_canonical_obligation() -> None:
    task_spec = _task_spec((_obligation("obligation:text", terminal=True),))
    mismatched_view = ReadyObligationView(
        obligation_id="obligation:text",
        role=ObligationExecutionRole.TERMINAL_EFFECT,
        subject="semantic:field",
        relation=TaskObligationRelation.HAS_CHANGED,
        expected_value="Alice",
        evidence_requirements=("evidence:obligation:text",),
        dependency_ids=(),
        terminal=True,
    )

    result = ProgressAttributionTicketResolver().resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec, override_view=mismatched_view),
        action=_action(task_spec),
    )

    assert result.status == "invalid"
    assert result.ticket is None


def test_ticket_id_uses_canonical_json_not_delimiter_concatenation() -> None:
    task_spec = _task_spec((_obligation("obligation:text", terminal=True),))
    resolver = ProgressAttributionTicketResolver()

    first = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(
            task_spec,
            contract_id="contract|1",
            contract_hash="hash",
        ),
    )
    second = resolver.resolve(
        task_spec=task_spec,
        progress=_progress(task_spec),
        ready_projection=_ready_projection(task_spec),
        action=_action(
            task_spec,
            contract_id="contract",
            contract_hash="1|hash",
        ),
    )

    assert first.ticket is not None
    assert second.ticket is not None
    assert first.ticket.ticket_id != second.ticket.ticket_id
