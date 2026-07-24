from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.collection_window import OrdinalRouteConstraint, OrdinalRouteKind
from affordance_runtime.contracts import Observation, ScopeRelationKind, VerifierSpec
from affordance_runtime.grounding import (
    CandidateScopeEvidence,
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    UnifiedAffordance,
)
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
    PlannerProposalValidator,
    ProposalRejected,
    ProposalRejectionCode,
)
from affordance_runtime.scope_authorization import (
    ProposalScopeEvaluator,
    ScopeRejectionKind,
    ScopeRejectionReason,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec

PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="scope-test",
)


def _candidate(
    *,
    candidate_id: str,
    target_id: str,
    context: str = "",
    group: str = "",
    position: int | None = None,
) -> tuple[GroundingCandidate, Observation]:
    fingerprint = f"fp-{candidate_id}"
    candidate = GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id=target_id,
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(backend_handle=candidate_id),
        compatible_executor="dom",
        observation_epoch_id="snapshot-1",
        environment_revision="revision-1",
        page_revision="page-1",
        target_fingerprint=fingerprint,
        fingerprint_key=candidate_id,
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
        evidence_refs=("artifact:dom",),
        scope_evidence=CandidateScopeEvidence(
            container_context=context,
            group_context=group,
            collection_position=position,
        ),
    )
    observation = Observation(
        "revision-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        target_fingerprints={candidate_id: fingerprint},
    )
    return candidate, observation


def _target(candidate: GroundingCandidate, *, label: str, role: str = "link") -> UnifiedAffordance:
    return UnifiedAffordance(
        semantic_target_id=candidate.semantic_target_id,
        role=role,
        label=label,
        supported_actions=candidate.supported_actions,
        grounding_candidates=(candidate,),
    )


def test_entity_property_relation_requires_entity_and_requested_property() -> None:
    candidate, observation = _candidate(
        candidate_id="candidate:phone",
        target_id="semantic:phone",
        context="Phone: 358-832-9871",
        group="Catherina Phone: 358-832-9871 Address: Main Street",
    )
    target = _target(candidate, label="358-832-9871")
    evaluator = ProposalScopeEvaluator()

    accepted = evaluator.evaluate(
        action_kind="activate",
        target_id=target.semantic_target_id,
        target_label=target.label,
        target_role=target.role,
        parameters={},
        objective="Find Catherina in the contact book and click on their phone number.",
        targets=("contact_book_entry:Catherina",),
        unified_affordances=(target,),
        observation=observation,
        selected_candidate=candidate,
    )
    wrong_property = evaluator.evaluate(
        action_kind="activate",
        target_id=target.semantic_target_id,
        target_label=target.label,
        target_role=target.role,
        parameters={},
        objective="Find Catherina in the contact book and click on their address.",
        targets=("contact_book_entry:Catherina",),
        unified_affordances=(target,),
        observation=observation,
        selected_candidate=candidate,
    )
    wrong_entity = evaluator.evaluate(
        action_kind="activate",
        target_id=target.semantic_target_id,
        target_label=target.label,
        target_role=target.role,
        parameters={},
        objective="Find Charil in the contact book and click on their phone number.",
        targets=("contact_book_entry:Charil",),
        unified_affordances=(target,),
        observation=observation,
        selected_candidate=candidate,
    )

    assert accepted.authorization is not None
    assert accepted.authorization.relation == ScopeRelationKind.ENTITY_PROPERTY
    assert wrong_property.rejection == ScopeRejectionKind.TARGET_OUT_OF_SCOPE
    assert wrong_entity.rejection == ScopeRejectionKind.TARGET_OUT_OF_SCOPE
    assert wrong_property.reason == ScopeRejectionReason.RELATIONAL_EVIDENCE_NOT_PROVEN
    assert wrong_entity.reason == ScopeRejectionReason.RELATIONAL_EVIDENCE_NOT_PROVEN


def test_ordinal_relation_requires_the_requested_collection_position() -> None:
    fourth, observation = _candidate(
        candidate_id="candidate:fourth",
        target_id="semantic:ashlea",
        context="Ashlea result summary",
        position=4,
    )
    target = _target(fourth, label="Ashlea")
    evaluator = ProposalScopeEvaluator()

    accepted = evaluator.evaluate(
        action_kind="activate",
        target_id=target.semantic_target_id,
        target_label=target.label,
        target_role=target.role,
        parameters={},
        objective="Click the 4th search result.",
        targets=("search_page", "4th_search_result"),
        unified_affordances=(target,),
        observation=observation,
        selected_candidate=fourth,
    )
    wrong_position = evaluator.evaluate(
        action_kind="activate",
        target_id=target.semantic_target_id,
        target_label=target.label,
        target_role=target.role,
        parameters={},
        objective="Click the 3rd search result.",
        targets=("search_page", "3rd_search_result"),
        unified_affordances=(target,),
        observation=observation,
        selected_candidate=fourth,
    )

    assert accepted.authorization is not None
    assert accepted.authorization.relation == ScopeRelationKind.ORDINAL_COLLECTION_ITEM
    assert wrong_position.rejection == ScopeRejectionKind.TARGET_OUT_OF_SCOPE


def test_pagination_transition_requires_independently_resolved_global_ordinal_route() -> None:
    page_two, observation = _candidate(
        candidate_id="candidate:page-two",
        target_id="semantic:page-two",
        context="1 2 3",
    )
    target = _target(page_two, label="2")
    constraint = OrdinalRouteConstraint(
        kind=OrdinalRouteKind.PAGE_TRANSITION,
        target_id=target.semantic_target_id,
        requested_ordinal=4,
        current_page=1,
        target_page=2,
        page_size=3,
        total_pages=3,
        pagination_owner="results-pages",
    )

    accepted = ProposalScopeEvaluator().evaluate(
        action_kind="activate",
        target_id=target.semantic_target_id,
        target_label=target.label,
        target_role=target.role,
        parameters={},
        objective="Click the 4th search result.",
        targets=("search result",),
        unified_affordances=(target,),
        observation=observation,
        selected_candidate=page_two,
        ordinal_constraint=constraint,
    )

    assert accepted.authorization is not None
    assert accepted.authorization.relation == ScopeRelationKind.PAGINATION_TRANSITION


class _Page:
    url = "https://example.test/autocomplete"

    def __init__(self, html: str) -> None:
        self.html = html

    def content(self) -> str:
        return self.html

    def evaluate(self, script: str) -> object:
        return {} if "Object.fromEntries" in script else ""

    def screenshot(self, **kwargs: object) -> bytes:
        del kwargs
        return b""


def _autocomplete_task() -> TaskSpec:
    return TaskSpec(
        task_id="autocomplete",
        revision=1,
        objective="Enter an item that starts with 'Com'.",
        operation_class=OperationClass.READ_ONLY,
        targets=("browser-input-field",),
        success_criteria=("An item starting with Com is entered.",),
        source_request_ref="scope-test",
    )


def test_unique_value_control_authorization_is_bound_into_contract_hash() -> None:
    snapshot = BrowserSession(_Page('<label>Tags<input id="tags"></label>')).capture()  # type: ignore[arg-type]
    target = snapshot.unified_affordances[0]
    state = StateKernel("autocomplete", "Enter Com")
    state.remember_observation(snapshot.observation)
    proposal = PlannerProposal(
        proposal_id="autocomplete-proposal",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=target.semantic_target_id,
        parameters={"text": "Com"},
    )

    PlannerProposalValidator().validate(proposal, PROVENANCE, _autocomplete_task(), state, snapshot)
    contract = ContractBuilder(
        requirements={
            target.semantic_target_id: ContractRequirements(
                verifier_plan=(VerifierSpec("state_delta", "tags", "Com"),),
            )
        }
    ).build(proposal, _autocomplete_task(), state, snapshot)

    assert contract.scope_authorization is not None
    assert contract.grounding_candidate is not None
    assert contract.scope_authorization.relation == ScopeRelationKind.SEMANTIC_VALUE_UNIQUE_CONTROL
    assert contract.scope_authorization.candidate_id == contract.grounding_candidate.candidate_id
    assert contract.scope_authorization.evidence_digest in str(contract.canonical_payload())


def test_value_does_not_authorize_an_arbitrary_control_or_mixed_option_list() -> None:
    snapshot = BrowserSession(
        _Page(  # type: ignore[arg-type]
            '<label>Tags<input id="tags"></label><label>Email<input id="email"></label>'
        )
    ).capture()
    tags = next(item for item in snapshot.unified_affordances if item.label == "Tags")
    state = StateKernel("autocomplete", "Enter Com")
    state.remember_observation(snapshot.observation)
    proposal = PlannerProposal(
        proposal_id="ambiguous-control",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=tags.semantic_target_id,
        parameters={"text": "Com"},
    )

    with pytest.raises(ProposalRejected) as caught:
        PlannerProposalValidator().validate(proposal, PROVENANCE, _autocomplete_task(), state, snapshot)

    assert caught.value.code == ProposalRejectionCode.TARGET_OUT_OF_SCOPE
    assert caught.value.reason_code == ScopeRejectionReason.RELATIONAL_EVIDENCE_NOT_PROVEN

    candidate, observation = _candidate(
        candidate_id="candidate:select",
        target_id="semantic:select",
    )
    candidate = replace(candidate, supported_actions=frozenset({"select_option"}))
    select = _target(candidate, label="Options", role="combobox")
    decision = ProposalScopeEvaluator().evaluate(
        action_kind="select_option",
        target_id=select.semantic_target_id,
        target_label=select.label,
        target_role=select.role,
        parameters={"option": ["Mars", "Delete all"]},
        objective="Choose Mars.",
        targets=("planet:Mars",),
        unified_affordances=(select,),
        observation=observation,
        selected_candidate=candidate,
    )
    assert decision.rejection == ScopeRejectionKind.TARGET_OUT_OF_SCOPE
    assert decision.reason == ScopeRejectionReason.SEMANTIC_VALUE_NOT_AUTHORIZED
