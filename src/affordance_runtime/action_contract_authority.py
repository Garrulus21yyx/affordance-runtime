"""Independent authority rebuild for a selected actual contract route."""

from __future__ import annotations

from affordance_runtime.action_choice_authority import authorize_runtime_signature
from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.choice_contracts import ActionChoice
from affordance_runtime.contracts import ActionContract
from affordance_runtime.effect_authority_contracts import (
    ActionAuthorityProof,
    AuthorityStatus,
    RuntimeEffectSignature,
)
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation


def rebuild_contract_authority(
    choice: ActionChoice,
    task_spec: TaskSpec,
    observation: UnifiedObservation,
    contract: ActionContract,
) -> tuple[RuntimeEffectSignature, ActionAuthorityProof]:
    candidate = contract.grounding_candidate
    destination_candidate = None
    if contract.gesture_binding is not None:
        destination_candidate = next(
            (
                item
                for item in observation.bindings
                if item.candidate_id == contract.gesture_binding.destination.candidate_id
            ),
            None,
        )
    signature = classify_action(
        observation,
        target_id=choice.target_id,
        destination_id=choice.destination_id,
        action_kind=contract.action,
        parameters=choice.parameters,
        candidate=candidate,
        destination_candidate=destination_candidate,
    )
    proof = authorize_runtime_signature(
        task_spec=task_spec,
        step=None,
        signature=signature,
        requirement_refs=choice.requirement_refs,
        choice_role=choice.role,
    )
    if proof.status != AuthorityStatus.ALLOW:
        raise ValueError(f"actual action binding is not authorized: {proof.reason_code}")
    catalog_proof = choice.action_authority_proof
    if catalog_proof is None or catalog_proof.authorization_scope_digest != proof.authorization_scope_digest:
        raise ValueError("actual action authority scope differs from Catalog authority proof")
    return signature, proof
