"""Pure typed scope subsumption and versioned enabling-action policy."""

from __future__ import annotations

from typing import cast

from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.choice_contracts import ActionChoice, ChoiceRole
from affordance_runtime.effect_authority_contracts import (
    AUTHORITY_EVALUATOR_POLICY_VERSION,
    ActionAuthorityProof,
    AuthorityStatus,
    EffectAuthorizationScope,
    EffectClass,
    Externality,
    Reversibility,
    RuntimeEffectSignature,
    externality_rank,
    reversibility_rank,
)
from affordance_runtime.high_risk_effect_policy import policy_for_effect
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import AssuranceLevel

ENABLING_ACTION_POLICY_VERSION = "enabling-action@v1"


def authorize_choice(
    choice: ActionChoice,
    step: StepSpec,
    task_spec: TaskSpec,
    observation: UnifiedObservation,
) -> ActionAuthorityProof:
    signature = classify_action(
        observation,
        target_id=choice.target_id,
        destination_id=choice.destination_id,
        action_kind=choice.action_kind.value,
        parameters=choice.parameters,
    )
    return authorize_runtime_signature(
        task_spec=task_spec,
        step=step,
        signature=signature,
        requirement_refs=choice.requirement_refs,
        choice_role=choice.role,
    )


def authorize_runtime_signature(
    *,
    task_spec: TaskSpec,
    step: StepSpec | None,
    signature: RuntimeEffectSignature,
    requirement_refs: tuple[str, ...],
    choice_role: ChoiceRole = ChoiceRole.DIRECT,
) -> ActionAuthorityProof:
    known = {item.requirement_id: item for item in task_spec.requirements}
    if not requirement_refs or set(requirement_refs) - set(known):
        return _proof(task_spec, signature, AuthorityStatus.DENY, ("TASK_REQUIREMENT_TRACE_MISSING",))
    if step is not None and (
        not set(requirement_refs).issubset(step.requirement_refs)
        or not set(step.effect_authorization_refs).issubset(requirement_refs)
    ):
        return _proof(task_spec, signature, AuthorityStatus.DENY, ("STEP_EFFECT_TRACE_MISMATCH",))
    if choice_role != ChoiceRole.DIRECT:
        return _authorize_enabling(task_spec, signature, requirement_refs)

    scopes = tuple(
        cast(EffectAuthorizationScope, known[ref].payload.effect_authorization_scope)
        for ref in requirement_refs
        if ref in task_spec.allowed_effect_refs and known[ref].payload.effect_authorization_scope is not None
    )
    if not scopes:
        return _proof(task_spec, signature, AuthorityStatus.UNPROVEN, ("AUTHORIZATION_SCOPE_MISSING",))
    decisions = tuple(_subsumes(scope, signature, task_spec) for scope in scopes)
    allowed = next((scope for scope, status, _ in decisions if status == AuthorityStatus.ALLOW), None)
    if allowed is not None:
        return _proof(
            task_spec,
            signature,
            AuthorityStatus.ALLOW,
            (
                "OPERATION_MATCHED",
                "RESOURCE_SCOPE_MATCHED",
                "NAMED_PARAMETERS_MATCHED",
                "EFFECT_POLICY_MATCHED",
                "SOURCE_POLICY_MATCHED",
            ),
            allowed,
            effect_refs=(allowed.requirement_ref,),
        )
    status = (
        AuthorityStatus.DENY if any(item[1] == AuthorityStatus.DENY for item in decisions) else AuthorityStatus.UNPROVEN
    )
    reasons = tuple(
        dict.fromkeys(reason for _, item_status, codes in decisions if item_status == status for reason in codes)
    )
    return _proof(task_spec, signature, status, reasons)


def contract_matches_task_authority(
    *,
    task_spec: TaskSpec,
    runtime_signature: RuntimeEffectSignature | None = None,
    requirement_refs: tuple[str, ...],
    choice_role: str,
    sealed_proof: ActionAuthorityProof | None = None,
    **_: object,
) -> ActionAuthorityProof:
    if runtime_signature is None or sealed_proof is None:
        return _proof(
            task_spec,
            runtime_signature or _empty_signature(),
            AuthorityStatus.UNPROVEN,
            ("CURRENT_RUNTIME_SIGNATURE_MISSING",),
        )
    proof = authorize_runtime_signature(
        task_spec=task_spec,
        step=None,
        signature=runtime_signature,
        requirement_refs=requirement_refs,
        choice_role=ChoiceRole(choice_role),
    )
    if proof.status != AuthorityStatus.ALLOW:
        return proof
    if (
        proof.proof_digest != sealed_proof.proof_digest
        or proof.runtime_effect_signature_digest != sealed_proof.runtime_effect_signature_digest
        or proof.candidate_binding_digest != sealed_proof.candidate_binding_digest
        or proof.evaluator_policy_version != sealed_proof.evaluator_policy_version
    ):
        return _proof(task_spec, runtime_signature, AuthorityStatus.DENY, ("SEALED_PROOF_MISMATCH",))
    return proof


def _subsumes(
    scope: EffectAuthorizationScope,
    signature: RuntimeEffectSignature,
    task_spec: TaskSpec,
) -> tuple[EffectAuthorizationScope, AuthorityStatus, tuple[str, ...]]:
    unknown: list[str] = []
    denied: list[str] = []
    if signature.effect_class in {None, EffectClass.UNKNOWN}:
        unknown.append("EFFECT_UNKNOWN")
    elif signature.effect_class != scope.effect_class:
        denied.append("EFFECT_CLASS_MISMATCH")
    if signature.operation_ref is None:
        unknown.append("OPERATION_UNPROVEN")
    elif scope.operation_constraint and signature.operation_ref != scope.operation_constraint:
        denied.append("OPERATION_MISMATCH")
    if signature.resource_ref is None:
        unknown.append("TARGET_SCOPE_UNPROVEN")
    elif signature.resource_ref != scope.resource_scope.resource_ref:
        denied.append("TARGET_SCOPE_MISMATCH")
    expected_destination = scope.destination_scope.resource_ref if scope.destination_scope else None
    if signature.destination_ref != expected_destination:
        denied.append("DESTINATION_SCOPE_MISMATCH")
    authorized_slots = {parameter.slot for parameter in scope.parameters}
    unexpected_slots = set(signature.parameter_values) - authorized_slots
    if unexpected_slots:
        denied.extend(f"PARAMETER_NOT_AUTHORIZED:{slot}" for slot in sorted(unexpected_slots))
    for parameter in scope.parameters:
        if parameter.slot not in signature.parameter_values:
            unknown.append(f"PARAMETER_SCOPE_UNPROVEN:{parameter.slot}")
        elif signature.parameter_values[parameter.slot] != parameter.value:
            denied.append(f"PARAMETER_MISMATCH:{parameter.slot}")
    if signature.externality is None:
        unknown.append("EXTERNALITY_UNPROVEN")
    elif externality_rank(signature.externality) > externality_rank(scope.externality):
        denied.append("EXTERNALITY_EXCEEDS_SCOPE")
    if signature.reversibility is None or signature.reversibility == Reversibility.UNKNOWN:
        unknown.append("REVERSIBILITY_UNPROVEN")
    elif reversibility_rank(signature.reversibility) > reversibility_rank(scope.reversibility):
        denied.append("REVERSIBILITY_EXCEEDS_SCOPE")
    if not scope.required_capabilities.issubset(task_spec.capability_ceiling):
        denied.append("CAPABILITY_EXCEEDS_TASK_CEILING")
    if scope.requirement_ref in task_spec.forbidden_effect_refs:
        denied.append("FORBIDDEN_EFFECT")
    constraint_status = _hard_constraints(scope, signature, task_spec)
    if constraint_status is not None:
        (denied if constraint_status[0] == AuthorityStatus.DENY else unknown).extend(constraint_status[1])
    if _assurance_rank(signature.assurance) < _assurance_rank(scope.minimum_source_assurance):
        unknown.append("INSUFFICIENT_SOURCE_ASSURANCE")
    if signature.conflict_status in {"material_conflict", "inconclusive"}:
        unknown.append("MATERIAL_SOURCE_CONFLICT")
    if not signature.coverage_complete:
        unknown.append("COVERAGE_INSUFFICIENT")
    if not scope.risk_policy_ref:
        denied.append("RISK_POLICY_MISSING")
    high_risk_policy = policy_for_effect(signature.effect_class, signature.operation_ref)
    if high_risk_policy is not None:
        actual_slots = set(signature.parameter_values)
        if high_risk_policy.required_material_fields - actual_slots:
            unknown.append("HIGH_RISK_MATERIAL_FIELDS_UNPROVEN")
        if _assurance_rank(signature.assurance) < _assurance_rank(high_risk_policy.minimum_assurance):
            unknown.append("HIGH_RISK_ASSURANCE_INSUFFICIENT")
        if high_risk_policy.required_capability not in scope.required_capabilities:
            denied.append("HIGH_RISK_CAPABILITY_POLICY_MISMATCH")
        if not scope.approval_policy_ref:
            denied.append("HIGH_RISK_APPROVAL_POLICY_MISSING")
        if high_risk_policy.causal_evidence_required and not task_spec.external_effect_criterion_ids:
            denied.append("HIGH_RISK_CAUSAL_EVIDENCE_POLICY_MISSING")
        if high_risk_policy.authoritative_final_recheck and not task_spec.final_recheck_criterion_ids:
            denied.append("HIGH_RISK_FINAL_RECHECK_POLICY_MISSING")
    if denied:
        return scope, AuthorityStatus.DENY, tuple(denied)
    if unknown:
        return scope, AuthorityStatus.UNPROVEN, tuple(unknown)
    return scope, AuthorityStatus.ALLOW, ()


def _authorize_enabling(
    task_spec: TaskSpec,
    signature: RuntimeEffectSignature,
    requirement_refs: tuple[str, ...],
) -> ActionAuthorityProof:
    if not set(requirement_refs).issubset({item.requirement_id for item in task_spec.requirements}):
        return _proof(task_spec, signature, AuthorityStatus.DENY, ("ENABLING_REQUIREMENT_TRACE_MISSING",))
    common_status = _enabling_common_status(signature)
    if common_status is not None:
        return _proof(task_spec, signature, common_status[0], common_status[1])
    if signature.effect_class == EffectClass.INTERACTION_ONLY:
        if (
            signature.action_kind not in {"focus", "hover", "scroll", "wait", "observe"}
            or signature.externality != Externality.LOCAL
            or signature.reversibility != Reversibility.REVERSIBLE
        ):
            return _proof(task_spec, signature, AuthorityStatus.DENY, ("ENABLING_EFFECT_POLICY_FAILED",))
        return _proof(
            task_spec,
            signature,
            AuthorityStatus.ALLOW,
            ("VERSIONED_ENABLING_POLICY_MATCHED",),
            enabling_policy_ref=ENABLING_ACTION_POLICY_VERSION,
        )
    if (
        signature.effect_class == EffectClass.UPDATE
        and signature.externality == Externality.LOCAL
        and signature.reversibility == Reversibility.REVERSIBLE
        and signature.action_kind in {"fill", "type", "type_text", "select", "select_option"}
    ):
        admitted = {item.field: item.value for item in task_spec.inputs if item.requirement_ref in requirement_refs}
        if not signature.parameter_values or any(
            slot not in admitted or admitted[slot] != value for slot, value in signature.parameter_values.items()
        ):
            return _proof(task_spec, signature, AuthorityStatus.DENY, ("ENABLING_DATA_DISCLOSURE",))
        return _proof(
            task_spec,
            signature,
            AuthorityStatus.ALLOW,
            ("LOCAL_REVERSIBLE_DRAFT_MATCHED",),
            enabling_policy_ref=ENABLING_ACTION_POLICY_VERSION,
        )
    status = AuthorityStatus.UNPROVEN if signature.effect_class in {None, EffectClass.UNKNOWN} else AuthorityStatus.DENY
    return _proof(task_spec, signature, status, ("ENABLING_EFFECT_POLICY_FAILED",))


def _enabling_common_status(
    signature: RuntimeEffectSignature,
) -> tuple[AuthorityStatus, tuple[str, ...]] | None:
    unknown: list[str] = []
    denied: list[str] = []
    if not signature.coverage_complete:
        unknown.append("COVERAGE_INSUFFICIENT")
    if signature.conflict_status in {"material_conflict", "inconclusive"}:
        unknown.append("MATERIAL_SOURCE_CONFLICT")
    if _assurance_rank(signature.assurance) < _assurance_rank(AssuranceLevel.STRUCTURAL):
        unknown.append("INSUFFICIENT_SOURCE_ASSURANCE")
    if signature.runtime_risk.value == "critical":
        unknown.append("ENABLING_RISK_UNPROVEN")
    if signature.risk_vector is not None and signature.risk_vector.capability.value != "low":
        denied.append("ENABLING_CAPABILITY_NOT_ALLOWED")
    if denied:
        return AuthorityStatus.DENY, tuple(denied)
    if unknown:
        return AuthorityStatus.UNPROVEN, tuple(unknown)
    return None


def _hard_constraints(scope, signature, task_spec):
    known = {item.requirement_id: item for item in task_spec.requirements}
    unknown: list[str] = []
    denied: list[str] = []
    for ref in task_spec.hard_constraint_refs:
        requirement = known.get(ref)
        if requirement is None:
            denied.append("HARD_CONSTRAINT_REF_INVALID")
            continue
        payload = requirement.payload
        if payload.relation == "equals" and payload.subject in signature.parameter_values:
            if signature.parameter_values[payload.subject] != payload.value:
                denied.append(f"HARD_CONSTRAINT_VIOLATED:{ref}")
        else:
            unknown.append(f"HARD_CONSTRAINT_UNPROVEN:{ref}")
    if denied:
        return AuthorityStatus.DENY, denied
    if unknown:
        return AuthorityStatus.UNPROVEN, unknown
    return None


def _proof(
    task_spec: TaskSpec,
    signature: RuntimeEffectSignature,
    status: AuthorityStatus,
    reasons: tuple[str, ...],
    scope: EffectAuthorizationScope | None = None,
    *,
    effect_refs: tuple[str, ...] = (),
    enabling_policy_ref: str | None = None,
) -> ActionAuthorityProof:
    return ActionAuthorityProof(
        status=status,
        task_ref=f"{task_spec.task_id}@{task_spec.revision}",
        authorization_scope_ref=scope.requirement_ref if scope else None,
        authorization_scope_digest=scope.digest if scope else None,
        enabling_policy_ref=enabling_policy_ref,
        runtime_effect_signature_digest=signature.digest,
        observation_ref=signature.observation_ref,
        candidate_binding_digest=signature.candidate_binding_digest,
        reason_codes=reasons,
        evaluator_policy_version=AUTHORITY_EVALUATOR_POLICY_VERSION,
        effect_refs=effect_refs,
        runtime_risk=signature.runtime_risk,
        effect_class=signature.effect_class,
    )


def _empty_signature() -> RuntimeEffectSignature:
    return RuntimeEffectSignature("missing", "", None, "", None, None, None)


def _assurance_rank(value: AssuranceLevel) -> int:
    return {AssuranceLevel.WEAK: 0, AssuranceLevel.STRUCTURAL: 1, AssuranceLevel.AUTHORITATIVE: 2}[value]
