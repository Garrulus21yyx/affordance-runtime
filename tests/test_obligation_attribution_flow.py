from dataclasses import replace

import pytest

from affordance_runtime.contracts import ActionContract
from affordance_runtime.obligation_attribution import (
    EvidenceSourceKind,
    EvidenceStrength,
    PostActionEvidenceFact,
    ProgressAttributionTicket,
)
from affordance_runtime.obligation_attribution_flow import (
    BoundActionExecution,
    prepare_post_verification_obligation_shadow,
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


def _contract() -> ActionContract:
    return ActionContract(
        id="contract-1",
        intent="set slider to 7",
        affordance_id="semantic:slider",
        action="press_key",
        backend="dom",
        environment_revision="env-pre",
        locator={"semantic_target_id": "semantic:slider"},
        snapshot_id="snapshot-pre",
        page_revision="page-pre",
    )


def _ticket(contract: ActionContract) -> ProgressAttributionTicket:
    return ProgressAttributionTicket(
        ticket_id="ticket-1",
        task_spec_identity=_task_spec().identity,
        task_revision=5,
        issued_at_state_version=23,
        contract_id=contract.id,
        contract_hash=contract.contract_hash,
        semantic_target_id="semantic:slider",
        action_kind=contract.action,
        candidate_obligation_ids=("obligation:slider-7",),
        pre_snapshot_id=contract.snapshot_id,
        pre_page_revision=contract.page_revision,
        pre_environment_revision=contract.environment_revision,
    )


def _obligation() -> TaskObligationSpec:
    return TaskObligationSpec(
        obligation_id="obligation:slider-7",
        kind=TaskObligationKind.EFFECT,
        subject="semantic:slider",
        relation=TaskObligationRelation.EQUALS,
        value_source=TaskObligationValueSource.LITERAL,
        expected_value="7",
        claim_ids=("claim:slider-7",),
        evidence_requirements=("evidence:slider-7",),
        typed_evidence_requirements=(
            EvidenceRequirement(
                kind=EvidenceKind.DOM_STATE,
                subject="semantic:slider",
                relation=TaskObligationRelation.EQUALS,
                minimum_strength="independent",
                source_constraints=("post_action_observation",),
            ),
        ),
        blocking=True,
        terminal=True,
        construction_source=GraphConstructionSource.CANONICAL_COMPILER,
    )


def _task_spec() -> TaskSpec:
    obligation = _obligation()
    return TaskSpec(
        task_id="task-odg-9-shadow",
        revision=5,
        objective="set slider to 7",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        task_structure=TaskStructure.FLAT,
        targets=("semantic:slider",),
        success_criteria=("slider equals 7",),
        source_request_ref="source:request",
        source_claims=(
            SourcedTaskClaim(
                claim_id="claim:slider-7",
                kind=TaskClaimKind.TERMINAL,
                statement="slider equals 7",
                source_ref="source:request:clause:0",
                source_unit_ids=("source:request:clause:0",),
                construction_source=GraphConstructionSource.CANONICAL_COMPILER,
            ),
        ),
        obligations=(obligation,),
        evidence_requirements=("independent slider evidence",),
    )


def _progress(task_spec: TaskSpec) -> ObligationProgressStateView:
    return ObligationProgressStateView(
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=24,
        known_obligation_ids=("obligation:slider-7",),
    )


def _fact(contract: ActionContract) -> PostActionEvidenceFact:
    return PostActionEvidenceFact(
        contract_id=contract.id,
        contract_hash=contract.contract_hash,
        pre_snapshot_id=contract.snapshot_id,
        post_snapshot_id="snapshot-post",
        post_page_revision="page-post",
        post_environment_revision="env-post",
        action_semantic_target_id="semantic:slider",
        evidence_subject_id="semantic:slider",
        relation=TaskObligationRelation.EQUALS,
        before_value="5",
        after_value="7",
        expected_value="7",
        verifier_kind="control_state",
        source_kind=EvidenceSourceKind.POST_ACTION_OBSERVATION,
        strength=EvidenceStrength.INDEPENDENT,
        passed=True,
        evidence_refs=("evidence:slider-7",),
    )


def test_bound_action_execution_carries_ticket_without_changing_action_contract_schema() -> None:
    contract = _contract()
    ticket = _ticket(contract)

    bound = BoundActionExecution(contract=contract, attribution_ticket=ticket)

    assert bound.contract is contract
    assert bound.attribution_ticket is ticket
    assert not hasattr(contract, "attribution_ticket")


def test_bound_action_execution_rejects_ticket_for_different_contract_identity() -> None:
    contract = _contract()
    wrong_ticket = replace(_ticket(contract), contract_hash="sha256:other")

    with pytest.raises(ValueError, match="ticket contract identity"):
        BoundActionExecution(contract=contract, attribution_ticket=wrong_ticket)


def test_post_verification_shadow_reports_candidate_satisfaction_without_commit_authority() -> None:
    task_spec = _task_spec()
    contract = _contract()
    bound = BoundActionExecution(contract=contract, attribution_ticket=_ticket(contract))

    projection = prepare_post_verification_obligation_shadow(
        task_spec=task_spec,
        progress=_progress(task_spec),
        bound_action=bound,
        facts=(_fact(contract),),
    )

    assert projection is not None
    assert projection.event_kind == "ObligationAttributionShadowCompared"
    assert projection.attribution_status == "satisfied"
    assert projection.prepared_obligation_id == "obligation:slider-7"
    assert projection.commit_authorized is False
    payload = projection.to_trace_payload()
    assert payload["schema_version"] == "1.0"
    assert payload["contract"]["contract_id"] == contract.id
    assert payload["ticket"]["ticket_id"] == bound.attribution_ticket.ticket_id
    assert payload["attribution"]["status"] == "satisfied"
    assert payload["attribution"]["would_commit"] is False


def test_post_verification_shadow_without_ticket_is_diagnostic_skip() -> None:
    task_spec = _task_spec()
    contract = _contract()

    projection = prepare_post_verification_obligation_shadow(
        task_spec=task_spec,
        progress=_progress(task_spec),
        bound_action=BoundActionExecution(contract=contract),
        facts=(_fact(contract),),
    )

    assert projection is not None
    assert projection.attribution_status == "not_ticketed"
    assert projection.prepared_obligation_id == ""
    assert projection.commit_authorized is False
