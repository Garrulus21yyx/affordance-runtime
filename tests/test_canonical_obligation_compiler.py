import pytest

from affordance_runtime.canonical_obligation_compiler import (
    CanonicalEffectInput,
    CanonicalObligationCompiler,
    CanonicalProposalGraph,
)
from affordance_runtime.source_ledger import SourceLedgerBuilder
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    GraphConstructionSource,
    OperationClass,
    RequestedEffect,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskInteractionOperationKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    UserRequest,
    _validate_task_obligation_graph,
)


def _ledger():
    return SourceLedgerBuilder().build(
        UserRequest(request_id="canonical-1", raw_text="Save the requested report.")
    )


def _ledger_for(raw_text: str):
    return SourceLedgerBuilder().build(
        UserRequest(request_id="canonical-sequence", raw_text=raw_text)
    )


def _required_clause_units(ledger) -> tuple[str, ...]:
    return tuple(unit.source_unit_id for unit in ledger.units if unit.required_candidate)


def _effect(unit_id: str) -> CanonicalEffectInput:
    return CanonicalEffectInput(
        operation_class=OperationClass.REVERSIBLE_WRITE,
        target="requested report",
        source_unit_ids=(unit_id,),
        evidence=(
            EvidenceRequirement(
                kind=EvidenceKind.API_STATE,
                subject="requested report",
                relation=TaskObligationRelation.IS_COMPLETED,
                minimum_strength="independent",
                source_constraints=(unit_id,),
            ),
        ),
    )


def test_canonical_proposal_graph_claim_id_map_is_immutable_from_source_mapping() -> None:
    ledger = _ledger()
    graph = CanonicalObligationCompiler().compile(ledger, (_effect(ledger.raw_text_unit_id),))
    proposal_claim_ids = {"provider-read": graph.claims[0].claim_id}

    proposal = CanonicalProposalGraph(graph=graph, proposal_claim_ids=proposal_claim_ids)
    proposal_claim_ids["provider-read"] = "claim:polluted"

    assert proposal.proposal_claim_ids["provider-read"] == graph.claims[0].claim_id
    with pytest.raises(TypeError):
        proposal.proposal_claim_ids["provider-read"] = "claim:polluted"


def test_canonical_compiler_owns_ids_provenance_and_typed_evidence() -> None:
    ledger = _ledger()
    graph = CanonicalObligationCompiler().compile(ledger, (_effect(ledger.raw_text_unit_id),))

    assert graph.claims[0].claim_id.startswith("claim:")
    assert graph.claims[0].source_unit_ids == (ledger.raw_text_unit_id,)
    assert graph.claims[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    assert graph.obligations[0].obligation_id.startswith("obligation:")
    assert graph.obligations[0].terminal
    assert graph.obligations[0].typed_evidence_requirements[0].kind == EvidenceKind.API_STATE
    assert graph.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    _validate_task_obligation_graph(graph.claims, graph.obligations)


def test_canonical_compiler_rejects_unknown_source_unit_before_graph_construction() -> None:
    with pytest.raises(ValueError, match="unknown source unit"):
        CanonicalObligationCompiler().compile(_ledger(), (_effect("invented-source"),))


def test_canonical_compiler_constructs_flat_graph_from_requested_effect_without_proposal_ids() -> None:
    ledger = _ledger()
    graph = CanonicalObligationCompiler().compile_requested_effects(
        ledger,
        (
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="requested report",
                source_ref=ledger.raw_text_unit_id,
            ),
        ),
    )

    assert graph.claims[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    assert graph.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    assert graph.obligations[0].relation == TaskObligationRelation.HAS_CHANGED
    assert graph.obligations[0].typed_evidence_requirements[0].kind == EvidenceKind.DOM_STATE
    assert graph.obligations[0].evidence_requirements == ("dom_state:requested report",)


def test_flat_navigation_effect_with_click_success_criterion_is_completed_action() -> None:
    ledger = _ledger_for("Click the No button.")

    graph = CanonicalObligationCompiler().compile_requested_effects(
        ledger,
        (
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="button:label:no",
                source_ref=ledger.raw_text_unit_id,
            ),
        ),
        success_criteria=("The No button was clicked.",),
    )

    obligation = graph.obligations[0]
    assert obligation.kind == TaskObligationKind.EFFECT
    assert obligation.relation == TaskObligationRelation.IS_COMPLETED


def test_typed_focus_operation_is_a_post_action_effect_without_lexical_target_match() -> None:
    ledger = _ledger_for("Focus into the renamed editor.")

    graph = CanonicalObligationCompiler().compile_requested_effects(
        ledger,
        (
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="application:textbox",
                source_ref=ledger.raw_text_unit_id,
                interaction_operation=TaskInteractionOperationKind.FOCUS,
            ),
        ),
        success_criteria=("The renamed editor is focused.",),
    )

    obligation = graph.obligations[0]
    assert obligation.kind == TaskObligationKind.EFFECT
    assert obligation.relation == TaskObligationRelation.IS_COMPLETED
    assert obligation.interaction_operation == TaskInteractionOperationKind.FOCUS


@pytest.mark.parametrize(
    ("provider_target", "semantic_target"),
    (
        ("button[text()='Archive']", "button:label='Archive'"),
        ('link[text()="Reports"]', "link:label='Reports'"),
    ),
)
def test_canonical_compiler_repairs_bounded_text_selector_to_semantic_identity(
    provider_target: str,
    semantic_target: str,
) -> None:
    ledger = _ledger_for("Activate the named control.")

    graph = CanonicalObligationCompiler().compile_requested_effects(
        ledger,
        (
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target=provider_target,
                source_ref=ledger.raw_text_unit_id,
            ),
        ),
        success_criteria=("The named control was activated.",),
    )

    obligation = graph.obligations[0]
    assert obligation.subject == semantic_target
    assert obligation.typed_evidence_requirements[0].subject == semantic_target
    assert "text()" not in obligation.subject


def test_requested_effect_sequence_preserves_dependency_and_terminal_boundary() -> None:
    ledger = _ledger_for("Activate Alpha. Then activate Beta.")
    alpha_source, beta_source = _required_clause_units(ledger)

    graph = CanonicalObligationCompiler().compile_requested_effects(
        ledger,
        (
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="Alpha activation",
                source_ref=alpha_source,
            ),
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="Beta activation",
                source_ref=beta_source,
            ),
        ),
        preserve_sequence=True,
    )

    alpha, beta = graph.obligations
    assert alpha.relation != TaskObligationRelation.IS_AVAILABLE
    assert not alpha.terminal
    assert beta.terminal
    assert beta.depends_on == (alpha.obligation_id,)


def test_requested_effect_sequence_default_preserves_independent_flat_effects() -> None:
    ledger = _ledger_for("Activate Alpha and activate Beta.")

    graph = CanonicalObligationCompiler().compile_requested_effects(
        ledger,
        (
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="Alpha activation",
                source_ref=ledger.raw_text_unit_id,
            ),
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="Beta activation",
                source_ref=ledger.raw_text_unit_id,
            ),
        ),
    )

    assert tuple(item.terminal for item in graph.obligations) == (True, True)
    assert all(not item.depends_on for item in graph.obligations)


def test_canonical_compiler_rebuilds_multistage_proposal_nodes_and_value_flow() -> None:
    ledger = _ledger()
    source_unit_id = ledger.raw_text_unit_id
    proposal = CanonicalObligationCompiler().compile_proposed_graph(
        ledger,
        (
            SourcedTaskClaim(
                claim_id="provider-read",
                kind=TaskClaimKind.DEPENDENCY,
                statement="read current value",
                source_ref=source_unit_id,
            ),
            SourcedTaskClaim(
                claim_id="provider-write",
                kind=TaskClaimKind.EFFECT,
                statement="write current value",
                source_ref=source_unit_id,
            ),
        ),
        (
            TaskObligationSpec(
                obligation_id="provider-read-obligation",
                kind=TaskObligationKind.PREDICATE,
                subject="current value",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source=TaskObligationValueSource.OBSERVATION,
                claim_ids=("provider-read",),
                evidence_requirements=("provider-authored evidence",),
            ),
            TaskObligationSpec(
                obligation_id="provider-write-obligation",
                kind=TaskObligationKind.PREDICATE,
                subject="destination value",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.OBLIGATION_OUTPUT,
                value_obligation_id="provider-read-obligation",
                claim_ids=("provider-write",),
                depends_on=("provider-read-obligation",),
                evidence_requirements=("another provider-authored description",),
                terminal=True,
            ),
        ),
        construction_source=GraphConstructionSource.MODEL_PROPOSAL,
    )

    graph = proposal.graph
    assert not proposal.issues
    assert proposal.proposal_claim_ids["provider-read"] == graph.claims[0].claim_id
    assert all("provider" not in item.obligation_id for item in graph.obligations)
    assert graph.obligations[1].depends_on == (graph.obligations[0].obligation_id,)
    assert graph.obligations[1].value_obligation_id == graph.obligations[0].obligation_id
    assert graph.obligations[0].evidence_requirements == ("dom_state:current value",)
    assert graph.obligations[0].typed_evidence_requirements[0].source_constraints == (
        source_unit_id,
    )
    _validate_task_obligation_graph(graph.claims, graph.obligations)
