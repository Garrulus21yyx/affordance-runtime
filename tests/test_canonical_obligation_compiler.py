import pytest

from affordance_runtime.canonical_obligation_compiler import (
    CanonicalEffectInput,
    CanonicalObligationCompiler,
)
from affordance_runtime.source_ledger import SourceLedgerBuilder
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    GraphConstructionSource,
    OperationClass,
    TaskObligationRelation,
    UserRequest,
    _validate_task_obligation_graph,
)


def _ledger():
    return SourceLedgerBuilder().build(
        UserRequest(request_id="canonical-1", raw_text="Save the requested report.")
    )


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
