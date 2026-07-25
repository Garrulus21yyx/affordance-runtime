import pytest
from pydantic import ValidationError

from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.task_intake import (
    AmbiguityRisk,
    CompilationPolicy,
    CompilationStatus,
    FieldProvenance,
    IntentAmbiguity,
    IntentDraft,
    IntentDraftValidator,
    IntentEntity,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    SemanticValueRelation,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskStructure,
    UserRequest,
)


def _request() -> UserRequest:
    return UserRequest(request_id="request-1", raw_text="Update the theme to dark")


def _draft(**changes: object) -> IntentDraft:
    values = {
        "objective": "Set the theme to dark",
        "requested_effects": (
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="theme",
                capability="settings.write",
                source_ref="request-1:0-24",
            ),
        ),
        "candidate_success_criteria": ("theme is dark",),
        "candidate_evidence_requirements": ("settings API confirms dark",),
        "source_map": (FieldProvenance(field="objective", source_ref="request-1:0-24"),),
    }
    values.update(changes)
    return IntentDraft(**values)


def _derived_claims_and_obligations() -> tuple[
    tuple[SourcedTaskClaim, ...],
    tuple[TaskObligationSpec, ...],
]:
    claims = (
        SourcedTaskClaim(
            claim_id="claim:source-value",
            kind=TaskClaimKind.VALUE,
            statement="derive the requested value from the current source",
            source_ref="request-1:0-24",
        ),
        SourcedTaskClaim(
            claim_id="claim:write-value",
            kind=TaskClaimKind.EFFECT,
            statement="write the derived value to the destination",
            source_ref="request-1:0-24",
        ),
        SourcedTaskClaim(
            claim_id="claim:submit",
            kind=TaskClaimKind.TERMINAL,
            statement="submit after the destination is correct",
            source_ref="request-1:0-24",
        ),
    )
    obligations = (
        TaskObligationSpec(
            obligation_id="obligation:source-value",
            kind=TaskObligationKind.PREDICATE,
            subject="requested value in current source",
            relation=TaskObligationRelation.IS_AVAILABLE,
            value_source=TaskObligationValueSource.OBSERVATION,
            claim_ids=("claim:source-value",),
            evidence_requirements=("current source value evidence",),
        ),
        TaskObligationSpec(
            obligation_id="obligation:destination-value",
            kind=TaskObligationKind.PREDICATE,
            subject="destination value",
            relation=TaskObligationRelation.EQUALS,
            value_source=TaskObligationValueSource.OBLIGATION_OUTPUT,
            value_obligation_id="obligation:source-value",
            claim_ids=("claim:write-value",),
            depends_on=("obligation:source-value",),
            evidence_requirements=("current destination value evidence",),
        ),
        TaskObligationSpec(
            obligation_id="obligation:submitted",
            kind=TaskObligationKind.EFFECT,
            subject="submission",
            relation=TaskObligationRelation.IS_COMPLETED,
            claim_ids=("claim:submit",),
            depends_on=("obligation:destination-value",),
            evidence_requirements=("independent submission evidence",),
            terminal=True,
        ),
    )
    return claims, obligations


def test_ready_compilation_creates_immutable_versioned_task_spec_without_granting_capability() -> None:
    entity = IntentEntity(name="theme", value="dark", source_ref="request-1:20-24")
    result = IntentDraftValidator().compile(
        _request(),
        _draft(entities=(entity,)),
        revision=2,
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.revision == 2
    assert result.task_spec.operation_class == OperationClass.REVERSIBLE_WRITE
    assert result.task_spec.task_structure == TaskStructure.FLAT
    assert result.task_spec.requested_effects == _draft().requested_effects
    assert result.task_spec.requested_capabilities == ("settings.write",)
    assert result.task_spec.entities == (entity,)
    assert result.task_spec.evidence_requirements == ("settings API confirms dark",)
    assert "granted" not in result.task_spec.model_dump()
    with pytest.raises(ValidationError):
        result.task_spec.revision = 3  # type: ignore[misc]


def test_explicit_semantic_value_constraint_is_preserved_as_taskspec_authority() -> None:
    constraint = SemanticValueConstraint(
        relation=SemanticValueRelation.PREFIX,
        value="Com",
        target="item",
        source_ref="request-1:0-3",
    )
    result = IntentDraftValidator().compile(
        _request(),
        _draft(candidate_semantic_value_constraints=(constraint,)),
    )

    assert result.task_spec is not None
    assert result.task_spec.schema_version == "1.3"
    assert result.task_spec.semantic_value_constraints == (constraint,)


def test_sourced_dependency_graph_is_preserved_as_taskspec_authority() -> None:
    claims, obligations = _derived_claims_and_obligations()

    result = IntentDraftValidator().compile(
        _request(),
        _draft(
            candidate_source_claims=claims,
            candidate_obligations=obligations,
            task_structure=TaskStructure.MULTI_STAGE,
        ),
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.schema_version == "1.3"
    assert result.task_spec.source_claims == claims
    assert result.task_spec.obligations == obligations
    assert result.task_spec.obligations[-1].terminal


def test_required_claim_must_be_covered_by_obligation_graph() -> None:
    claims, obligations = _derived_claims_and_obligations()
    terminal_without_terminal_claim = obligations[-1].model_copy(
        update={"claim_ids": ("claim:write-value",)}
    )

    result = IntentDraftValidator().compile(
        _request(),
        _draft(
            candidate_source_claims=claims,
            candidate_obligations=(
                *obligations[:-1],
                terminal_without_terminal_claim,
            ),
        ),
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[-1].code == "invalid_task_obligation_graph"
    assert "required task claim" in result.issues[-1].detail


def test_obligation_output_value_must_name_declared_dependency() -> None:
    with pytest.raises(ValidationError, match="declared dependency"):
        TaskObligationSpec(
            obligation_id="obligation:destination-value",
            kind=TaskObligationKind.PREDICATE,
            subject="destination value",
            relation=TaskObligationRelation.EQUALS,
            value_source=TaskObligationValueSource.OBLIGATION_OUTPUT,
            value_obligation_id="obligation:source-value",
            claim_ids=("claim:write-value",),
            evidence_requirements=("current destination value evidence",),
        )


def test_obligation_graph_rejects_cycles_and_dangling_dependencies() -> None:
    claims, obligations = _derived_claims_and_obligations()
    cyclic = (
        obligations[0].model_copy(
            update={"depends_on": ("obligation:destination-value",)}
        ),
        obligations[1],
        obligations[2],
    )
    cyclic_result = IntentDraftValidator().compile(
        _request(),
        _draft(
            candidate_source_claims=claims,
            candidate_obligations=cyclic,
        ),
    )
    assert cyclic_result.status == CompilationStatus.UNSUPPORTED
    assert cyclic_result.issues[-1].code == "invalid_task_obligation_graph"
    assert "cannot contain a cycle" in cyclic_result.issues[-1].detail

    dangling = obligations[2].model_copy(
        update={"depends_on": ("obligation:missing",)}
    )
    dangling_result = IntentDraftValidator().compile(
        _request(),
        _draft(
            candidate_source_claims=claims,
            candidate_obligations=(*obligations[:-1], dangling),
        ),
    )
    assert dangling_result.status == CompilationStatus.UNSUPPORTED
    assert dangling_result.issues[-1].code == "invalid_task_obligation_graph"
    assert "unknown dependency" in dangling_result.issues[-1].detail


def test_unsourced_task_claim_cannot_become_taskspec_authority() -> None:
    claims, obligations = _derived_claims_and_obligations()
    unsourced = claims[0].model_copy(update={"source_ref": "page-observation"})

    result = IntentDraftValidator().compile(
        _request(),
        _draft(
            candidate_source_claims=(unsourced, *claims[1:]),
            candidate_obligations=obligations,
        ),
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[0].code == "unsourced_task_claim"


def test_claims_and_obligations_must_be_supplied_together() -> None:
    claims, _ = _derived_claims_and_obligations()

    result = IntentDraftValidator().compile(
        _request(),
        _draft(candidate_source_claims=claims),
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.issues[-1].code == "invalid_task_obligation_graph"
    assert "supplied together" in result.issues[-1].detail


def test_semantic_value_constraint_rejects_blank_or_unknown_relation() -> None:
    with pytest.raises(ValidationError):
        SemanticValueConstraint(
            relation="prefix",
            value=" ",
            source_ref="request-1",
        )
    with pytest.raises(ValidationError):
        SemanticValueConstraint(
            relation="contains",
            value="Com",
            source_ref="request-1",
        )


def test_unsourced_semantic_value_constraint_cannot_become_taskspec_authority() -> None:
    result = IntentDraftValidator().compile(
        _request(),
        _draft(
            candidate_semantic_value_constraints=(
                SemanticValueConstraint(
                    relation=SemanticValueRelation.PREFIX,
                    value="Com",
                    source_ref="page-observation",
                ),
            )
        ),
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[0].code == "unsourced_semantic_value_constraint"


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    (
        (
            {
                "requested_effects": (
                    RequestedEffect(
                        operation_class=OperationClass.REVERSIBLE_WRITE,
                        target="theme",
                        source_ref="page-observation",
                    ),
                )
            },
            "unsourced_requested_effect",
        ),
        (
            {
                "entities": (
                    IntentEntity(
                        name="theme",
                        value="dark",
                        source_ref="page-observation",
                    ),
                )
            },
            "unsourced_intent_entity",
        ),
    ),
)
def test_unsourced_effect_or_entity_cannot_become_taskspec_authority(
    changes: dict[str, object],
    expected_code: str,
) -> None:
    result = IntentDraftValidator().compile(_request(), _draft(**changes))

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[0].code == expected_code


def test_validated_intent_carries_explicit_multi_stage_routing_without_granting_authority() -> None:
    result = IntentDraftValidator().compile(
        _request(),
        _draft(task_structure=TaskStructure.MULTI_STAGE),
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.task_structure == TaskStructure.MULTI_STAGE
    assert result.task_spec.requested_capabilities == ("settings.write",)


def test_blocking_or_high_risk_ambiguity_stops_before_task_spec() -> None:
    draft = _draft(
        ambiguities=(
            IntentAmbiguity(
                field="recipient",
                reason="two recipients are referenced",
                blocking=False,
                risk=AmbiguityRisk.HIGH,
            ),
        )
    )

    result = IntentDraftValidator().compile(_request(), draft)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert result.issues[0].code == "blocking_ambiguity"


def test_blocking_ambiguity_takes_precedence_over_missing_derived_success_criterion() -> None:
    draft = _draft(
        candidate_success_criteria=(),
        ambiguities=(
            IntentAmbiguity(
                field="recipient",
                reason="recipient is missing",
                blocking=True,
                risk=AmbiguityRisk.HIGH,
            ),
        ),
    )

    result = IntentDraftValidator().compile(_request(), draft)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None


def test_policy_intersection_rejects_denied_capability_and_forbidden_effect() -> None:
    draft = _draft(candidate_forbidden_effects=("theme",))
    validator = IntentDraftValidator(
        CompilationPolicy(
            allowed_requested_capabilities=frozenset({"settings.read"}),
            denied_capabilities=frozenset({"settings.write"}),
        )
    )

    result = validator.compile(_request(), draft)

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert {issue.code for issue in result.issues} == {
        "capability_denied",
        "capability_not_allowed",
        "forbidden_effect",
    }


def test_missing_required_semantics_are_unsupported() -> None:
    result = IntentDraftValidator().compile(_request(), IntentDraft())

    assert result.status == CompilationStatus.UNSUPPORTED
    assert {item.code for item in result.issues} == {
        "missing_objective",
        "missing_effect",
        "missing_success_criteria",
    }


def test_taskspec_envelope_compatibility_and_revision_identity() -> None:
    first = IntentDraftValidator().compile(_request(), _draft(), revision=1).task_spec
    second = IntentDraftValidator().compile(_request(), _draft(), revision=2).task_spec
    assert first is not None and second is not None

    envelope = TaskEnvelope(task_spec=second)

    assert envelope.task_id == "request-1"
    assert envelope.goal == "Set the theme to dark"
    assert envelope.target == "theme"
    assert first.identity != second.identity
    with pytest.raises(ValueError, match="does not match"):
        TaskEnvelope(task_id="other", task_spec=second)
