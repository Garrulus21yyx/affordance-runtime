"""Typed TaskSpec authorization for concrete Runtime action choices."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from affordance_runtime.choice_contracts import ActionChoice, ChoiceRole
from affordance_runtime.contracts import RiskLevel
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.task_intake import OperationClass, TaskRequirement, TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation


@dataclass(frozen=True)
class ChoiceAuthorityDecision:
    """Runtime-owned proof that a concrete choice is within admitted meaning."""

    authorized: bool
    effect_refs: tuple[str, ...] = ()
    effectful: bool = False
    risk: RiskLevel = RiskLevel.LOW
    target_identity: str = ""
    destination_identity: str = ""
    scope_digest: str = ""
    reason_code: str = "TASK_EFFECT_TARGET_MISMATCH"


def authorize_choice(
    choice: ActionChoice,
    step: StepSpec,
    task_spec: TaskSpec,
    observation: UnifiedObservation,
) -> ChoiceAuthorityDecision:
    """Prove concrete scope using exact typed identities; ambiguity denies authority."""

    known = {item.requirement_id: item for item in task_spec.requirements}
    if not choice.requirement_refs or set(choice.requirement_refs) - set(known):
        return ChoiceAuthorityDecision(False, reason_code="TASK_REQUIREMENT_TRACE_MISSING")

    target = next((item for item in observation.targets if item.target_id == choice.target_id), None)
    destination = next((item for item in observation.targets if item.target_id == choice.destination_id), None)
    if target is None or (choice.destination_id and destination is None):
        return ChoiceAuthorityDecision(False)

    # Enabling/information choices carry requirement traceability but cannot
    # inherit effect authority merely because the Planner assigned a role.
    if choice.role != ChoiceRole.DIRECT:
        if choice.effect_refs or choice.effectful:
            return ChoiceAuthorityDecision(False, reason_code="ENABLING_CHOICE_CLAIMS_EFFECT_AUTHORITY")
        if choice.action_kind.value not in {"focus", "scroll", "wait", "navigate"}:
            return ChoiceAuthorityDecision(False, reason_code="ENABLING_CHOICE_EFFECT_CLASS_UNPROVEN")
        return _decision(
            choice,
            (),
            False,
            RiskLevel.LOW,
            target.label,
            destination.label if destination is not None else "",
        )

    requested_refs = tuple(
        ref
        for ref in (step.effect_authorization_refs or step.requirement_refs)
        if ref in task_spec.allowed_effect_refs
    )
    if not requested_refs:
        return ChoiceAuthorityDecision(False, reason_code="TASK_EFFECT_AUTHORIZATION_MISSING")

    matches = tuple(
        requirement
        for ref in requested_refs
        if (requirement := known.get(ref)) is not None
        and _matches_exact_scope(requirement, target.target_id, target.label, destination)
        and _parameters_are_admitted(choice, requirement.requirement_id, task_spec)
    )
    if not matches:
        return ChoiceAuthorityDecision(False)

    effect_refs = tuple(item.requirement_id for item in matches)
    operation = max(
        (item.payload.operation_class or OperationClass.READ_ONLY for item in matches),
        key=_operation_rank,
    )
    effectful = operation in {
        OperationClass.REVERSIBLE_WRITE,
        OperationClass.EXTERNAL_SIDE_EFFECT,
        OperationClass.IRREVERSIBLE,
    }
    risk = _operation_risk(operation)
    observed_risk = _observed_action_risk(target, choice.action_kind.value)
    if _risk_rank(observed_risk) > _risk_rank(risk):
        return ChoiceAuthorityDecision(False, reason_code="CONCRETE_ACTION_RISK_EXCEEDS_TASK_AUTHORITY")
    return _decision(
        choice,
        effect_refs,
        effectful,
        risk,
        target.label,
        destination.label if destination is not None else "",
    )


def contract_matches_task_authority(
    *,
    task_spec: TaskSpec,
    requirement_refs: tuple[str, ...],
    effect_refs: tuple[str, ...],
    target_identity: str,
    destination_identity: str,
    action_kind: str,
    choice_role: str,
    parameters: object,
    effectful: bool,
    risk: RiskLevel,
    scope_digest: str,
) -> bool:
    """Independently revalidate the immutable proof at the Task gate."""

    known = {item.requirement_id: item for item in task_spec.requirements}
    if not requirement_refs or set(requirement_refs) - set(known):
        return False
    if choice_role != ChoiceRole.DIRECT.value:
        if effect_refs or effectful or risk != RiskLevel.LOW:
            return False
        if action_kind not in {"focus", "scroll", "wait", "navigate"}:
            return False
        return scope_digest == _scope_digest(
            (), target_identity, destination_identity, parameters, False, RiskLevel.LOW, action_kind, choice_role
        )
    if (
        not effect_refs
        or set(effect_refs) - set(task_spec.allowed_effect_refs)
        or set(effect_refs) - set(requirement_refs)
    ):
        return False
    matches = tuple(
        known[ref]
        for ref in effect_refs
        if ref in known
        and _identity(known[ref].payload.target_identity) == _identity(target_identity)
        and _identity(known[ref].payload.destination_identity) == _identity(destination_identity)
    )
    if len(matches) != len(effect_refs):
        return False
    operation = max(
        (item.payload.operation_class or OperationClass.READ_ONLY for item in matches),
        key=_operation_rank,
    )
    expected_effectful = operation in {
        OperationClass.REVERSIBLE_WRITE,
        OperationClass.EXTERNAL_SIDE_EFFECT,
        OperationClass.IRREVERSIBLE,
    }
    expected_risk = _operation_risk(operation)
    expected_digest = _scope_digest(
        effect_refs,
        target_identity,
        destination_identity,
        parameters,
        expected_effectful,
        expected_risk,
        action_kind,
        choice_role,
    )
    return effectful == expected_effectful and risk == expected_risk and scope_digest == expected_digest


def _matches_exact_scope(
    requirement: TaskRequirement,
    target_id: str,
    target_label: str,
    destination: object | None,
) -> bool:
    target_identity = _identity(requirement.payload.target_identity)
    if target_identity not in {_identity(target_id), _identity(target_label)}:
        return False
    expected_destination = _identity(requirement.payload.destination_identity)
    if not expected_destination:
        return destination is None
    if destination is None:
        return False
    return expected_destination in {
        _identity(str(getattr(destination, "target_id", ""))),
        _identity(str(getattr(destination, "label", ""))),
    }


def _parameters_are_admitted(choice: ActionChoice, requirement_ref: str, task_spec: TaskSpec) -> bool:
    material_values = {
        _identity(item.value) for item in task_spec.inputs if item.requirement_ref == requirement_ref
    }
    if not material_values:
        return True
    concrete_values = {
        _identity(str(value))
        for value in choice.parameters.values()
        if isinstance(value, (str, int, float, bool))
    }
    return material_values.issubset(concrete_values)


def _decision(
    choice: ActionChoice,
    effect_refs: tuple[str, ...],
    effectful: bool,
    risk: RiskLevel,
    target_identity: str,
    destination_identity: str,
) -> ChoiceAuthorityDecision:
    return ChoiceAuthorityDecision(
        True,
        effect_refs,
        effectful,
        risk,
        target_identity,
        destination_identity,
        _scope_digest(
            effect_refs,
            target_identity,
            destination_identity,
            choice.parameters,
            effectful,
            risk,
            choice.action_kind.value,
            choice.role.value,
        ),
        "",
    )


def _scope_digest(
    effect_refs: tuple[str, ...],
    target_identity: str,
    destination_identity: str,
    parameters: object,
    effectful: bool,
    risk: RiskLevel,
    action_kind: str,
    choice_role: str,
) -> str:
    payload = {
        "effect_refs": effect_refs,
        "target_identity": _identity(target_identity),
        "destination_identity": _identity(destination_identity),
        "parameters": to_json_compatible(parameters),
        "effectful": effectful,
        "risk": risk.value,
        "action_kind": action_kind,
        "choice_role": choice_role,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _identity(value: str) -> str:
    return " ".join(value.casefold().split())


def _operation_rank(value: OperationClass) -> int:
    return {
        OperationClass.READ_ONLY: 0,
        OperationClass.NAVIGATION: 1,
        OperationClass.REVERSIBLE_WRITE: 2,
        OperationClass.EXTERNAL_SIDE_EFFECT: 3,
        OperationClass.IRREVERSIBLE: 4,
    }[value]


def _operation_risk(value: OperationClass) -> RiskLevel:
    return {
        OperationClass.READ_ONLY: RiskLevel.LOW,
        OperationClass.NAVIGATION: RiskLevel.LOW,
        OperationClass.REVERSIBLE_WRITE: RiskLevel.MEDIUM,
        OperationClass.EXTERNAL_SIDE_EFFECT: RiskLevel.HIGH,
        OperationClass.IRREVERSIBLE: RiskLevel.IRREVERSIBLE,
    }[value]


def _observed_action_risk(target: object, action_kind: str) -> RiskLevel:
    action_support = tuple(getattr(target, "action_support", ()))
    support = next((item for item in action_support if item.action_kind == action_kind), None)
    value = getattr(support, "risk", None) if support is not None else getattr(target, "risk", RiskLevel.LOW)
    return value if isinstance(value, RiskLevel) else RiskLevel(str(value))


def _risk_rank(value: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.IRREVERSIBLE: 3,
    }[value]
