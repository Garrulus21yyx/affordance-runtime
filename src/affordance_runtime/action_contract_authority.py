"""Independent authority rebuild for a selected actual contract route."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from affordance_runtime.action_choice_authority import authorize_runtime_signature
from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.action_semantics import action_compatible
from affordance_runtime.choice_contracts import ActionChoice
from affordance_runtime.contracts import ActionContract
from affordance_runtime.effect_authority_contracts import (
    ActionAuthorityProof,
    AuthorityStatus,
    RuntimeEffectSignature,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.material_contracts import MaterialField
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation

_MISSING = object()
_MATERIAL_PARAMETER_SLOTS = frozenset(item.value for item in MaterialField)


def _assert_encoded_material_parameters_authorized(
    choice: ActionChoice,
    task_spec: TaskSpec,
    encoded_parameters: Mapping[str, Any],
) -> None:
    """Reject material values introduced after the canonical choice was authorized.

    A product route encoder is a trusted in-process edge, so this is not an
    attempt to sandbox arbitrary encoder code. It enforces the narrower MVP
    invariant that route mechanics (backend handles, schema wrappers, and so
    on) may not expand or change a typed task/effect parameter. Matching by
    typed slot keeps that check independent of any one provider schema.
    """

    canonical = {
        _normalized_slot(name): value for name, value in choice.parameters.items()
    }
    # Every canonical choice key is protected, even when it is not part of the
    # small cross-domain MaterialField vocabulary (for example ``text`` or
    # ``option``). Typed material/effect slots add protection for values that
    # appear only in a nested provider projection.
    protected_slots = set(_MATERIAL_PARAMETER_SLOTS) | set(canonical)
    requirements = {item.requirement_id: item for item in task_spec.requirements}
    for requirement_ref in choice.requirement_refs:
        requirement = requirements.get(requirement_ref)
        scope = (
            requirement.payload.effect_authorization_scope
            if requirement is not None
            else None
        )
        if scope is not None:
            protected_slots.update(
                _normalized_slot(parameter.slot) for parameter in scope.parameters
            )

    for slot, value in _named_parameter_values(encoded_parameters):
        normalized = _normalized_slot(slot)
        if normalized not in protected_slots:
            continue
        expected = canonical.get(normalized, _MISSING)
        if expected is _MISSING or to_json_compatible(value) != to_json_compatible(expected):
            raise ValueError(
                "encoded material parameter differs from authorized canonical "
                f"contract: {normalized}"
            )


def _named_parameter_values(value: object) -> tuple[tuple[str, object], ...]:
    found: list[tuple[str, object]] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for name, nested in item.items():
                found.append((str(name), nested))
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return tuple(found)


def _normalized_slot(value: object) -> str:
    acronym_separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(value))
    camel_separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", acronym_separated)
    return re.sub(r"[^a-z0-9]+", "_", camel_separated.casefold()).strip("_")


def rebuild_contract_authority(
    choice: ActionChoice,
    task_spec: TaskSpec,
    observation: UnifiedObservation,
    contract: ActionContract,
) -> tuple[RuntimeEffectSignature, ActionAuthorityProof]:
    if not action_compatible(choice.action_kind, contract.action):
        raise ValueError("actual contract action changes the authorized semantic action family")
    _assert_encoded_material_parameters_authorized(choice, task_spec, contract.parameters)
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
        target_id=contract.affordance_id,
        destination_id=(
            contract.gesture_binding.destination.semantic_target_id
            if contract.gesture_binding is not None
            else ""
        ),
        action_kind=choice.action_kind.value,
        # The provider projection was checked above for post-authorization
        # material values. Rebuild semantic authority from the canonical
        # parameters that the final contract hash also seals.
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
