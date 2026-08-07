from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime.action_choice_authority import (
    authorize_choice,
    authorize_runtime_signature,
    contract_matches_task_authority,
)
from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.approval_contracts import present_approval
from affordance_runtime.choice_contracts import ActionChoice, ChoiceRole
from affordance_runtime.contracts import (
    ActionContract,
    AffordanceLease,
    GestureBinding,
    GestureTargetBinding,
    Observation,
    RiskLevel,
    RuntimeErrorCode,
)
from affordance_runtime.criteria import PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.effect_authority_contracts import (
    AuthorityStatus,
    EffectAuthorizationScope,
    EffectClass,
    Externality,
    ParameterAuthorization,
    ResourceScopeRef,
    Reversibility,
    RuntimeRiskTier,
)
from affordance_runtime.grounding import DomGroundingPayload, GroundingCandidate, GroundingSource
from affordance_runtime.high_risk_effect_policy import HIGH_RISK_EFFECT_POLICIES, policy_for_effect
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.simplified_runtime_contracts import ElementIntent, SourceReference, StepSpec
from affordance_runtime.task_intake import OperationClass, TaskRequirement, TaskSemanticPayload, TaskSpec
from affordance_runtime.unified_grounding import candidate_from_affordance
from affordance_runtime.unified_observation import (
    ActionSupport,
    CanonicalTarget,
    ConflictStatus,
    CoverageCompleteness,
    CoverageStatus,
    CoverageTermination,
    Freshness,
    SourceCoverage,
    UnifiedObservation,
    UnifiedObservationTarget,
)
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceValidityMode,
    SatisfactionMode,
    SuccessExpression,
)


def _task(signature: EffectAuthorizationScope, operation_class: OperationClass) -> TaskSpec:
    high_risk = policy_for_effect(signature.effect_class, signature.operation_constraint)
    requirement = TaskRequirement(
        requirement_id=signature.requirement_ref,
        payload=TaskSemanticPayload(
            kind="effect",
            subject=signature.resource_scope.resource_ref,
            target_identity=signature.resource_scope.resource_ref,
            operation_class=operation_class,
            capability=next(iter(signature.required_capabilities), ""),
            effect_authorization_scope=signature,
        ),
        source_anchor_refs=("request:authority:whole",),
    )
    return TaskSpec(
        task_id="task:authority",
        revision=1,
        objective="typed authority fixture",
        operation_class=operation_class,
        requirements=(requirement,),
        allowed_effect_refs=(signature.requirement_ref,),
        capability_ceiling=tuple(signature.required_capabilities),
        success=(
            SuccessExpression(
                expression_id="success:authority",
                operator="all_of",
                children=(
                    SuccessExpression(
                        expression_id="success:authority-effect",
                        operator="criterion",
                        criterion_id="criterion:authority-effect",
                        requirement_refs=(signature.requirement_ref,),
                        policy=CriterionPolicy(
                            satisfaction=SatisfactionMode.ACTION_CAUSED,
                            validity=EvidenceValidityMode.RECENT_ACTION,
                            causal_lineage_required=True,
                        ),
                    ),
                    SuccessExpression(
                        expression_id="success:authority-final",
                        operator="criterion",
                        criterion_id="criterion:authority-final",
                        requirement_refs=(signature.requirement_ref,),
                        policy=CriterionPolicy(
                            validity=EvidenceValidityMode.FINAL_RECHECK,
                            minimum_assurance=AssuranceLevel.AUTHORITATIVE,
                        ),
                    ),
                ),
            )
            if high_risk
            else SuccessExpression(
                expression_id="success:authority",
                operator="criterion",
                criterion_id="criterion:authority",
                requirement_refs=(signature.requirement_ref,),
            )
        ),
        external_effect_criterion_ids=(("criterion:authority-effect",) if high_risk else ()),
        final_recheck_criterion_ids=(("criterion:authority-final",) if high_risk else ()),
        source_request_ref="request:authority",
    )


def test_dom_content_cannot_promote_its_source_assurance_to_authoritative() -> None:
    model = DomAdapter().transduce(
        '<button data-runtime-operation="external.commit@v1" '
        'data-runtime-effect-class="invoke" '
        'data-runtime-externality="external_system" '
        'data-runtime-reversibility="reversible" '
        'data-runtime-source-assurance="authoritative">Export</button>',
        environment_revision="environment:untrusted-dom",
        snapshot_id="observation:untrusted-dom",
        page_revision="page:untrusted-dom",
    )
    affordance = model.affordances[0]
    observation = Observation(
        "environment:untrusted-dom",
        snapshot_id="observation:untrusted-dom",
        page_revision="page:untrusted-dom",
    )
    candidate = candidate_from_affordance(
        affordance,
        observation,
        semantic_target_id="semantic:untrusted-export",
    )
    signature = classify_action(
        UnifiedObservation(
            snapshot_id=observation.snapshot_id,
            page_revision=observation.page_revision,
            environment_revision=observation.environment_revision,
            observed_text="",
            targets=(),
        ),
        target_id="semantic:untrusted-export",
        action_kind="activate",
        parameters={},
        candidate=candidate,
    )

    assert affordance.authority_source_assurance == AssuranceLevel.STRUCTURAL.value
    assert candidate.authority_source_assurance == AssuranceLevel.STRUCTURAL.value
    assert signature.assurance == AssuranceLevel.STRUCTURAL


def _step(ref: str) -> StepSpec:
    source = SourceReference("request:authority", "request:authority:whole")
    return StepSpec(
        step_id="step:authority",
        objective="execute typed effect",
        interaction=ElementIntent("typed resource", (source,)),
        completion_criteria=(
            PredicateExpr(
                "criterion:authority",
                SubjectExpr("semantic_target", "typed resource"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=(source,),
        requirement_refs=(ref,),
        effect_authorization_refs=(ref,),
        effectful=True,
    )


def _observation(
    *,
    target_id: str,
    operation_ref: str,
    effect_class: EffectClass,
    risk: RiskLevel,
    assurance: AssuranceLevel,
    label: str = "display alias",
    externality: Externality | None = None,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
) -> UnifiedObservation:
    return UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id=target_id,
                surface="dom",
                role="control",
                label=label,
                supported_actions=("activate", "type_text"),
                state={},
                risk=risk,
                risk_asserted=True,
                operation_ref=operation_ref,
                effect_class=effect_class.value,
                source_assurance=assurance,
                externality=(
                    externality
                    or (
                        Externality.EXTERNAL_SYSTEM
                        if effect_class in {EffectClass.PAY, EffectClass.SEND, EffectClass.SHARE}
                        else Externality.LOCAL
                    )
                ).value,
                reversibility=reversibility.value,
                source_refs=("assertion:typed-operation",),
            ),
        ),
        source_coverage=(
            SourceCoverage(
                GroundingSource.DOM,
                "test-complete@v1",
                1,
                False,
                0,
                CoverageCompleteness.COMPLETE,
                CoverageStatus.OBSERVED,
                acquisition_epoch_ref="observation:authority",
                source_scope="document",
                exhaustive=True,
                termination_reason=CoverageTermination.EXHAUSTED,
            ),
        ),
    )


def _choice(ref: str, target_id: str, action: PlannerActionKind, parameters=None, role=ChoiceRole.DIRECT):
    return ActionChoice(
        choice_id="choice:authority",
        task_revision=1,
        state_version=0,
        snapshot_id="observation:authority",
        active_step_id="step:authority",
        action_kind=action,
        target_id=target_id,
        parameters=parameters or {},
        requirement_refs=(ref,),
        role=role,
    )


def _binding(candidate_id: str, target_id: str, *, operation_ref: str = "resource.move@v1"):
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id=target_id,
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(selector=f"#{candidate_id}"),
        compatible_executor="browser",
        observation_epoch_id="observation:authority",
        environment_revision="environment:authority",
        page_revision="page:authority",
        target_fingerprint="",
        supported_actions=frozenset({"activate", "drag"}),
        evidence_kinds=frozenset(),
        operation_ref=operation_ref,
        effect_class=EffectClass.UPDATE.value,
        externality=Externality.LOCAL.value,
        reversibility=Reversibility.REVERSIBLE.value,
        authority_source_assurance=AssuranceLevel.STRUCTURAL.value,
    )


@pytest.mark.parametrize("policy", HIGH_RISK_EFFECT_POLICIES, ids=lambda item: item.policy_ref)
def test_every_high_risk_matrix_row_is_live_in_catalog_authority(policy) -> None:
    operation_ref = min(policy.operation_refs)
    values = {slot: f"authorized:{slot}" for slot in policy.required_material_fields}
    externality = (
        Externality.PHYSICAL_WORLD
        if policy.policy_ref.startswith("safety-device")
        else Externality.LOCAL
        if policy.effect_class == EffectClass.DELETE
        else Externality.EXTERNAL_SYSTEM
    )
    scope = EffectAuthorizationScope(
        requirement_ref=f"requirement:{policy.policy_ref}",
        effect_class=policy.effect_class,
        resource_scope=ResourceScopeRef(f"resource:{policy.policy_ref}"),
        operation_constraint=operation_ref,
        parameters=tuple(ParameterAuthorization(slot, value) for slot, value in sorted(values.items())),
        externality=externality,
        reversibility=Reversibility.REVERSIBLE,
        required_capabilities=frozenset({policy.required_capability}),
        risk_policy_ref=policy.policy_ref,
        minimum_source_assurance=policy.minimum_assurance,
        approval_policy_ref="exact-contract@v1",
    )
    task = _task(scope, OperationClass.EXTERNAL_SIDE_EFFECT)
    observation = _observation(
        target_id=scope.resource_scope.resource_ref,
        operation_ref=operation_ref,
        effect_class=policy.effect_class,
        risk=RiskLevel.HIGH,
        assurance=policy.minimum_assurance,
        externality=externality,
    )
    proof = authorize_choice(
        _choice(scope.requirement_ref, scope.resource_scope.resource_ref, PlannerActionKind.ACTIVATE, values),
        _step(scope.requirement_ref),
        task,
        observation,
    )

    assert proof.status == AuthorityStatus.ALLOW
    assert proof.authorization_scope_ref == scope.requirement_ref


def test_navigation_signature_denies_type_text_operation() -> None:
    signature = EffectAuthorizationScope(
        requirement_ref="requirement:navigate",
        operation_constraint="navigation.navigate@v1",
        resource_scope=ResourceScopeRef("resource:settings"),
        effect_class=EffectClass.NAVIGATE,
    )
    proof = authorize_choice(
        _choice(signature.requirement_ref, "resource:settings", PlannerActionKind.TYPE_TEXT, {"text": "x"}),
        _step(signature.requirement_ref),
        _task(signature, OperationClass.NAVIGATION),
        _observation(
            target_id="resource:settings",
            operation_ref="field.set@v1",
            effect_class=EffectClass.UPDATE,
            risk=RiskLevel.MEDIUM,
            assurance=AssuranceLevel.STRUCTURAL,
        ),
    )
    assert proof.status == AuthorityStatus.DENY
    assert "OPERATION_MISMATCH" in proof.reason_codes


def test_named_parameter_swap_is_denied() -> None:
    signature = EffectAuthorizationScope(
        requirement_ref="requirement:payment",
        operation_constraint="payment.commit@v1",
        resource_scope=ResourceScopeRef("account:alice"),
        parameters=(ParameterAuthorization("recipient", "Alice"), ParameterAuthorization("amount", "100")),
        effect_class=EffectClass.PAY,
        externality=Externality.EXTERNAL_SYSTEM,
        required_capabilities=frozenset({"payment.commit"}),
        approval_policy_ref="exact-contract@v1",
        minimum_source_assurance=AssuranceLevel.AUTHORITATIVE,
    )
    proof = authorize_choice(
        _choice(
            signature.requirement_ref,
            "account:alice",
            PlannerActionKind.ACTIVATE,
            {"recipient": "100", "amount": "Alice"},
        ),
        _step(signature.requirement_ref),
        _task(signature, OperationClass.REVERSIBLE_WRITE),
        _observation(
            target_id="account:alice",
            operation_ref="payment.commit@v1",
            effect_class=EffectClass.PAY,
            risk=RiskLevel.HIGH,
            assurance=AssuranceLevel.AUTHORITATIVE,
        ),
    )
    assert proof.status == AuthorityStatus.DENY
    assert set(proof.reason_codes) >= {"PARAMETER_MISMATCH:recipient", "PARAMETER_MISMATCH:amount"}


def test_uninstrumented_dom_control_has_unknown_risk() -> None:
    model = DomAdapter().transduce(
        "<button id='delete'>Delete account</button>",
        environment_revision="environment:dom",
    )
    assert not model.affordances[0].risk_asserted
    descriptor = classify_action(
        UnifiedObservation(
            snapshot_id="observation:dom",
            page_revision="page:dom",
            environment_revision="environment:dom",
            observed_text="",
            targets=(
                UnifiedObservationTarget(
                    target_id="dom:delete",
                    surface="dom",
                    role="button",
                    label="Delete account",
                    supported_actions=("activate",),
                    state={},
                ),
            ),
        ),
        target_id="dom:delete",
        action_kind="activate",
        parameters={},
    )
    assert descriptor.effect_class is None
    assert descriptor.runtime_risk.value == "critical"


def test_asserted_target_risk_is_a_raise_only_approval_floor() -> None:
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:read-sensitive",
        operation_constraint="resource.read@v1",
        resource_scope=ResourceScopeRef("resource:sensitive"),
        effect_class=EffectClass.READ,
        minimum_source_assurance=AssuranceLevel.AUTHORITATIVE,
    )
    task = _task(scope, OperationClass.READ_ONLY)
    observation = _observation(
        target_id="resource:sensitive",
        operation_ref="resource.read@v1",
        effect_class=EffectClass.READ,
        risk=RiskLevel.HIGH,
        assurance=AssuranceLevel.AUTHORITATIVE,
    )
    signature = classify_action(
        observation,
        target_id="resource:sensitive",
        action_kind="activate",
        parameters={},
    )
    proof = authorize_runtime_signature(
        task_spec=task,
        step=None,
        signature=signature,
        requirement_refs=(scope.requirement_ref,),
    )
    contract = ActionContract(
        id="contract:sensitive-read",
        intent="Read sensitive resource",
        affordance_id="resource:sensitive",
        action="activate",
        backend="dom",
        environment_revision="environment:authority",
        locator={},
        parameters={"destination_dir": "/tmp/runtime-report"},
        runtime_effect_signature=signature,
        action_authority_proof=proof,
        requirement_refs=(scope.requirement_ref,),
        selected_choice_id="choice:sensitive-read",
        risk=proof.risk,
    )

    assert signature.runtime_risk.value == "high"
    assert proof.status == AuthorityStatus.ALLOW
    assert proof.risk == RiskLevel.HIGH
    assert CapabilityGate().check(contract) == RuntimeErrorCode.APPROVAL_REQUIRED
    assert present_approval(contract).material_parameters == {
        "destination_dir": "/tmp/runtime-report"
    }


def test_destination_binding_is_in_route_risk_assurance_and_task_gate_rebuild() -> None:
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:move",
        operation_constraint="resource.move@v1",
        resource_scope=ResourceScopeRef("resource:source"),
        destination_scope=ResourceScopeRef("resource:destination"),
        effect_class=EffectClass.UPDATE,
        externality=Externality.EXTERNAL_SYSTEM,
        reversibility=Reversibility.COMPENSATABLE,
        minimum_source_assurance=AssuranceLevel.WEAK,
    )
    task = _task(scope, OperationClass.REVERSIBLE_WRITE)
    source_candidate = GroundingCandidate(
        candidate_id="candidate:source",
        semantic_target_id="resource:source",
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(selector="#source"),
        compatible_executor="browser",
        observation_epoch_id="observation:authority",
        environment_revision="environment:authority",
        page_revision="page:authority",
        target_fingerprint="",
        supported_actions=frozenset({"drag"}),
        evidence_kinds=frozenset(),
        evidence_refs=("assertion:source",),
        operation_ref="resource.move@v1",
        effect_class=EffectClass.UPDATE.value,
        externality=Externality.LOCAL.value,
        reversibility=Reversibility.REVERSIBLE.value,
        resource_sensitivity="moderate",
        authority_source_assurance=AssuranceLevel.AUTHORITATIVE.value,
    )
    destination_candidate = GroundingCandidate(
        candidate_id="candidate:destination",
        semantic_target_id="resource:destination",
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(selector="#destination"),
        compatible_executor="browser",
        observation_epoch_id="observation:authority",
        environment_revision="environment:authority",
        page_revision="page:authority",
        target_fingerprint="",
        supported_actions=frozenset({"drag"}),
        evidence_kinds=frozenset(),
        evidence_refs=("assertion:destination",),
        risk=RiskLevel.HIGH,
        risk_asserted=True,
        externality=Externality.EXTERNAL_SYSTEM.value,
        reversibility=Reversibility.COMPENSATABLE.value,
        resource_sensitivity="high",
        authority_source_assurance=AssuranceLevel.WEAK.value,
    )
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="resource:source",
                surface="dom",
                role="item",
                label="Source",
                supported_actions=("drag",),
                state={},
            ),
            UnifiedObservationTarget(
                target_id="resource:destination",
                surface="dom",
                role="region",
                label="Destination",
                supported_actions=("drag",),
                state={},
            ),
        ),
        bindings=(source_candidate, destination_candidate),
        source_coverage=(
            SourceCoverage(
                GroundingSource.DOM,
                "test-complete@v1",
                2,
                False,
                0,
                CoverageCompleteness.COMPLETE,
                CoverageStatus.OBSERVED,
                acquisition_epoch_ref="observation:authority",
                source_scope="document",
                exhaustive=True,
                termination_reason=CoverageTermination.EXHAUSTED,
            ),
        ),
    )
    signature = classify_action(
        observation,
        target_id="resource:source",
        destination_id="resource:destination",
        action_kind="drag",
        parameters={},
        candidate=source_candidate,
        destination_candidate=destination_candidate,
    )
    proof = authorize_runtime_signature(
        task_spec=task,
        step=None,
        signature=signature,
        requirement_refs=(scope.requirement_ref,),
    )
    lease = AffordanceLease.issue(
        environment_revision="environment:authority",
        snapshot_id="observation:authority",
        page_revision="page:authority",
    )
    contract = ActionContract(
        id="contract:move",
        intent="Move resource",
        affordance_id="resource:source",
        action="drag",
        backend="browser",
        environment_revision="environment:authority",
        locator={},
        snapshot_id="observation:authority",
        page_revision="page:authority",
        grounding_candidate=source_candidate,
        gesture_binding=GestureBinding(
            source=GestureTargetBinding(
                "resource:source",
                "candidate:source",
                {},
                "observation:authority",
                "page:authority",
                "",
                "candidate:source",
                lease,
            ),
            destination=GestureTargetBinding(
                "resource:destination",
                "candidate:destination",
                {},
                "observation:authority",
                "page:authority",
                "",
                "candidate:destination",
                lease,
            ),
            selected_route="browser",
        ),
        runtime_effect_signature=signature,
        action_authority_proof=proof,
        requirement_refs=(scope.requirement_ref,),
        effect_authorization_refs=(scope.requirement_ref,),
        selected_choice_id="choice:move",
        choice_role=ChoiceRole.DIRECT.value,
        risk=proof.risk,
    )
    rebuilt = TaskConstraintPolicy().evaluate_authority(contract, task, observation)

    assert signature.runtime_risk.value == "high"
    assert signature.assurance == AssuranceLevel.WEAK
    assert signature.externality == Externality.EXTERNAL_SYSTEM
    assert signature.reversibility == Reversibility.COMPENSATABLE
    assert signature.source_refs == ("assertion:source", "assertion:destination")
    assert rebuilt.status == AuthorityStatus.ALLOW, rebuilt.reason_codes
    assert rebuilt.proof_digest == proof.proof_digest


def _canonical_endpoint(
    target_id: str,
    *,
    externality: Externality,
    assurance: AssuranceLevel,
    conflict: ConflictStatus = ConflictStatus.NO_MATERIAL_CONFLICT,
) -> CanonicalTarget:
    return CanonicalTarget(
        target_id=target_id,
        role="region",
        label=target_id,
        surfaces=(GroundingSource.DOM,),
        action_support=(
            ActionSupport(
                action_kind="drag",
                candidate_ids=(f"candidate:{target_id}",),
                resource_ref=target_id,
                operation_ref="resource.move@v1",
                effect_class=EffectClass.UPDATE.value,
                externality=externality.value,
                reversibility=Reversibility.COMPENSATABLE.value,
                resource_sensitivity="moderate",
                source_assurance=assurance.value,
            ),
        ),
        state_facts=(),
        binding_ids=(f"candidate:{target_id}",),
        conflict_status=conflict,
        conflicts=(),
        source_assertion_refs=(f"assertion:{target_id}",),
        freshness=Freshness(
            "observation:authority",
            "environment:authority",
            "page:authority",
            0.0,
        ),
    )


def test_destination_external_system_cannot_expand_cross_origin_scope() -> None:
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:move-cross-origin",
        operation_constraint="resource.move@v1",
        resource_scope=ResourceScopeRef("resource:source"),
        destination_scope=ResourceScopeRef("resource:destination"),
        effect_class=EffectClass.UPDATE,
        externality=Externality.CROSS_ORIGIN,
        reversibility=Reversibility.COMPENSATABLE,
        minimum_source_assurance=AssuranceLevel.WEAK,
    )
    task = _task(scope, OperationClass.REVERSIBLE_WRITE)
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            _canonical_endpoint(
                "resource:source",
                externality=Externality.CROSS_ORIGIN,
                assurance=AssuranceLevel.AUTHORITATIVE,
            ),
            _canonical_endpoint(
                "resource:destination",
                externality=Externality.EXTERNAL_SYSTEM,
                assurance=AssuranceLevel.AUTHORITATIVE,
            ),
        ),
    )
    signature = classify_action(
        observation,
        target_id="resource:source",
        destination_id="resource:destination",
        action_kind="drag",
        parameters={},
    )
    proof = authorize_choice(
        replace(
            _choice(
                scope.requirement_ref,
                "resource:source",
                PlannerActionKind.DRAG,
            ),
            destination_id="resource:destination",
        ),
        _step(scope.requirement_ref),
        task,
        observation,
    )

    assert signature.externality == Externality.EXTERNAL_SYSTEM
    assert proof.status == AuthorityStatus.DENY
    assert "EXTERNALITY_EXCEEDS_SCOPE" in proof.reason_codes


def test_destination_material_conflict_makes_authority_unproven() -> None:
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:move-conflicted",
        operation_constraint="resource.move@v1",
        resource_scope=ResourceScopeRef("resource:source"),
        destination_scope=ResourceScopeRef("resource:destination"),
        effect_class=EffectClass.UPDATE,
        externality=Externality.EXTERNAL_SYSTEM,
        reversibility=Reversibility.COMPENSATABLE,
        minimum_source_assurance=AssuranceLevel.WEAK,
    )
    task = _task(scope, OperationClass.REVERSIBLE_WRITE)
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            _canonical_endpoint(
                "resource:source",
                externality=Externality.EXTERNAL_SYSTEM,
                assurance=AssuranceLevel.AUTHORITATIVE,
            ),
            _canonical_endpoint(
                "resource:destination",
                externality=Externality.EXTERNAL_SYSTEM,
                assurance=AssuranceLevel.AUTHORITATIVE,
                conflict=ConflictStatus.MATERIAL_CONFLICT,
            ),
        ),
    )
    signature = classify_action(
        observation,
        target_id="resource:source",
        destination_id="resource:destination",
        action_kind="drag",
        parameters={},
    )
    proof = authorize_runtime_signature(
        task_spec=task,
        step=None,
        signature=signature,
        requirement_refs=(scope.requirement_ref,),
    )

    assert signature.conflict_status == ConflictStatus.MATERIAL_CONFLICT.value
    assert proof.status == AuthorityStatus.UNPROVEN
    assert "MATERIAL_SOURCE_CONFLICT" in proof.reason_codes


def test_unasserted_visual_destination_lowers_actual_route_assurance() -> None:
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:move-visual",
        operation_constraint="resource.move@v1",
        resource_scope=ResourceScopeRef("resource:source"),
        destination_scope=ResourceScopeRef("resource:destination"),
        effect_class=EffectClass.UPDATE,
        externality=Externality.LOCAL,
        reversibility=Reversibility.REVERSIBLE,
        minimum_source_assurance=AssuranceLevel.STRUCTURAL,
    )
    task = _task(scope, OperationClass.REVERSIBLE_WRITE)
    source_candidate = GroundingCandidate(
        candidate_id="candidate:authoritative-source",
        semantic_target_id="resource:source",
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(selector="#source"),
        compatible_executor="browser",
        observation_epoch_id="observation:authority",
        environment_revision="environment:authority",
        page_revision="page:authority",
        target_fingerprint="",
        supported_actions=frozenset({"drag"}),
        evidence_kinds=frozenset(),
        operation_ref="resource.move@v1",
        effect_class=EffectClass.UPDATE.value,
        externality=Externality.LOCAL.value,
        reversibility=Reversibility.REVERSIBLE.value,
        authority_source_assurance=AssuranceLevel.AUTHORITATIVE.value,
    )
    visual_destination = GroundingCandidate(
        candidate_id="candidate:visual-destination",
        semantic_target_id="resource:destination",
        source=GroundingSource.VISUAL,
        payload=DomGroundingPayload(selector="#visual-destination"),
        compatible_executor="browser",
        observation_epoch_id="observation:authority",
        environment_revision="environment:authority",
        page_revision="page:authority",
        target_fingerprint="",
        supported_actions=frozenset({"drag"}),
        evidence_kinds=frozenset(),
        externality=Externality.LOCAL.value,
        reversibility=Reversibility.REVERSIBLE.value,
    )
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="resource:source",
                surface="dom",
                role="item",
                label="Source",
                supported_actions=("drag",),
                state={},
            ),
            UnifiedObservationTarget(
                target_id="resource:destination",
                surface="visual",
                role="region",
                label="Destination",
                supported_actions=("drag",),
                state={},
            ),
        ),
        bindings=(source_candidate, visual_destination),
    )
    signature = classify_action(
        observation,
        target_id="resource:source",
        destination_id="resource:destination",
        action_kind="drag",
        parameters={},
        candidate=source_candidate,
        destination_candidate=visual_destination,
    )
    proof = authorize_runtime_signature(
        task_spec=task,
        step=None,
        signature=signature,
        requirement_refs=(scope.requirement_ref,),
    )

    assert signature.assurance == AssuranceLevel.WEAK
    assert proof.status == AuthorityStatus.UNPROVEN
    assert "INSUFFICIENT_SOURCE_ASSURANCE" in proof.reason_codes


def test_task_gate_rebuilds_from_wrong_actual_binding() -> None:
    signature = EffectAuthorizationScope(
        requirement_ref="requirement:send",
        operation_constraint="message.send@v1",
        resource_scope=ResourceScopeRef("recipient:alice"),
        effect_class=EffectClass.SEND,
        parameters=(
            ParameterAuthorization("recipient", "Alice"),
            ParameterAuthorization("content", "hello"),
        ),
        externality=Externality.EXTERNAL_SYSTEM,
        required_capabilities=frozenset({"communication.send"}),
        approval_policy_ref="exact-contract@v1",
        minimum_source_assurance=AssuranceLevel.AUTHORITATIVE,
    )
    task = _task(signature, OperationClass.REVERSIBLE_WRITE)
    alice_observation = _observation(
        target_id="recipient:alice",
        operation_ref="message.send@v1",
        effect_class=EffectClass.SEND,
        risk=RiskLevel.HIGH,
        assurance=AssuranceLevel.AUTHORITATIVE,
    )
    alice_choice = _choice(
        signature.requirement_ref,
        "recipient:alice",
        PlannerActionKind.ACTIVATE,
        {"recipient": "Alice", "content": "hello"},
    )
    copied_proof = authorize_choice(alice_choice, _step(signature.requirement_ref), task, alice_observation)
    bob_descriptor = classify_action(
        _observation(
            target_id="recipient:bob",
            operation_ref="message.send@v1",
            effect_class=EffectClass.SEND,
            risk=RiskLevel.HIGH,
            assurance=AssuranceLevel.AUTHORITATIVE,
            label="Alice",
        ),
        target_id="recipient:bob",
        action_kind="activate",
        parameters={"recipient": "Alice", "content": "hello"},
    )
    assert copied_proof.status == AuthorityStatus.ALLOW
    assert not contract_matches_task_authority(
        task_spec=task,
        runtime_signature=bob_descriptor,
        sealed_proof=copied_proof,
        requirement_refs=(signature.requirement_ref,),
        choice_role=ChoiceRole.DIRECT.value,
    ).authorized


def test_label_alias_does_not_equal_resource_identity_and_unknown_is_unproven() -> None:
    signature = EffectAuthorizationScope(
        requirement_ref="requirement:read",
        operation_constraint="resource.read@v1",
        resource_scope=ResourceScopeRef("resource:alice"),
        effect_class=EffectClass.READ,
    )
    task = _task(signature, OperationClass.READ_ONLY)
    proof = authorize_choice(
        _choice(signature.requirement_ref, "resource:bob", PlannerActionKind.ACTIVATE),
        _step(signature.requirement_ref),
        task,
        _observation(
            target_id="resource:bob",
            operation_ref="resource.read@v1",
            effect_class=EffectClass.READ,
            risk=RiskLevel.LOW,
            assurance=AssuranceLevel.STRUCTURAL,
            label="resource:alice",
        ),
    )
    assert proof.status == AuthorityStatus.DENY
    assert "TARGET_SCOPE_MISMATCH" in proof.reason_codes


def test_enabling_type_cannot_disclose_data() -> None:
    signature = EffectAuthorizationScope(
        requirement_ref="requirement:read",
        operation_constraint="resource.read@v1",
        resource_scope=ResourceScopeRef("resource:alice"),
        effect_class=EffectClass.READ,
    )
    proof = authorize_choice(
        _choice(
            signature.requirement_ref,
            "resource:alice",
            PlannerActionKind.TYPE_TEXT,
            {"text": "secret"},
            ChoiceRole.ENABLING,
        ),
        _step(signature.requirement_ref),
        _task(signature, OperationClass.READ_ONLY),
        _observation(
            target_id="resource:alice",
            operation_ref="field.set@v1",
            effect_class=EffectClass.UPDATE,
            risk=RiskLevel.MEDIUM,
            assurance=AssuranceLevel.STRUCTURAL,
        ),
    )
    assert proof.status == AuthorityStatus.DENY


@pytest.mark.parametrize("endpoint", ["source", "destination"])
def test_actual_candidate_identity_must_match_requested_endpoint(endpoint: str) -> None:
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="resource:source",
                surface="dom",
                role="item",
                label="Source",
                supported_actions=("drag",),
                state={},
            ),
            UnifiedObservationTarget(
                target_id="resource:destination",
                surface="dom",
                role="region",
                label="Destination",
                supported_actions=("drag",),
                state={},
            ),
        ),
    )
    kwargs = {
        "candidate": _binding("candidate:wrong-source", "resource:other") if endpoint == "source" else None,
        "destination_candidate": (
            _binding("candidate:wrong-destination", "resource:other") if endpoint == "destination" else None
        ),
    }
    with pytest.raises(ValueError, match=f"{endpoint} candidate semantic identity"):
        classify_action(
            observation,
            target_id="resource:source",
            destination_id="resource:destination",
            action_kind="drag",
            parameters={},
            **kwargs,
        )


def test_destination_delete_cannot_be_hidden_by_source_update() -> None:
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:move",
        operation_constraint="resource.move@v1",
        resource_scope=ResourceScopeRef("resource:source"),
        destination_scope=ResourceScopeRef("resource:destination"),
        effect_class=EffectClass.UPDATE,
        externality=Externality.LOCAL,
        reversibility=Reversibility.REVERSIBLE,
        minimum_source_assurance=AssuranceLevel.STRUCTURAL,
    )
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="resource:source",
                surface="dom",
                role="item",
                label="Source",
                supported_actions=("drag",),
                state={},
                operation_ref="resource.move@v1",
                effect_class=EffectClass.UPDATE.value,
                source_assurance=AssuranceLevel.STRUCTURAL,
                externality=Externality.LOCAL.value,
                reversibility=Reversibility.REVERSIBLE.value,
            ),
            UnifiedObservationTarget(
                target_id="resource:destination",
                surface="dom",
                role="region",
                label="Destination",
                supported_actions=("drag",),
                state={},
                operation_ref="resource.delete@v1",
                effect_class=EffectClass.DELETE.value,
                source_assurance=AssuranceLevel.STRUCTURAL,
                externality=Externality.LOCAL.value,
                reversibility=Reversibility.IRREVERSIBLE.value,
            ),
        ),
    )
    signature = classify_action(
        observation,
        target_id="resource:source",
        destination_id="resource:destination",
        action_kind="drag",
        parameters={},
    )
    proof = authorize_runtime_signature(
        task_spec=_task(scope, OperationClass.REVERSIBLE_WRITE),
        step=None,
        signature=signature,
        requirement_refs=(scope.requirement_ref,),
    )

    assert signature.effect_class == EffectClass.UNKNOWN
    assert signature.operation_ref is None
    assert proof.status != AuthorityStatus.ALLOW


@pytest.mark.parametrize("defect", ["coverage", "conflict", "critical_risk"])
def test_enabling_policy_reuses_fail_closed_common_gates(defect: str) -> None:
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="resource:control",
                surface="dom",
                role="control",
                label="Control",
                supported_actions=("focus",),
                state={},
                source_assurance=AssuranceLevel.STRUCTURAL,
            ),
        ),
    )
    signature = classify_action(
        observation,
        target_id="resource:control",
        action_kind="focus",
        parameters={},
    )
    if defect == "coverage":
        signature = replace(signature, coverage_complete=False)
    elif defect == "conflict":
        signature = replace(signature, conflict_status=ConflictStatus.MATERIAL_CONFLICT.value)
    else:
        signature = replace(
            signature,
            risk_vector=replace(
                signature.risk_vector,
                effect_class=RuntimeRiskTier.CRITICAL,
            ),
        )
    scope = EffectAuthorizationScope(
        requirement_ref="requirement:read",
        operation_constraint="resource.read@v1",
        resource_scope=ResourceScopeRef("resource:control"),
        effect_class=EffectClass.READ,
    )
    proof = authorize_runtime_signature(
        task_spec=_task(scope, OperationClass.READ_ONLY),
        step=None,
        signature=signature,
        requirement_refs=(scope.requirement_ref,),
        choice_role=ChoiceRole.ENABLING,
    )
    assert proof.status != AuthorityStatus.ALLOW


def test_bounded_relevant_source_coverage_is_not_authority_complete() -> None:
    observation = UnifiedObservation(
        snapshot_id="observation:authority",
        page_revision="page:authority",
        environment_revision="environment:authority",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="resource:control",
                surface="dom",
                role="control",
                label="Control",
                supported_actions=("activate",),
                state={},
                operation_ref="resource.update@v1",
                effect_class=EffectClass.UPDATE.value,
                source_assurance=AssuranceLevel.STRUCTURAL,
                externality=Externality.LOCAL.value,
                reversibility=Reversibility.REVERSIBLE.value,
            ),
        ),
        source_coverage=(
            SourceCoverage(
                source=GroundingSource.DOM,
                capture_policy_id="bounded-dom",
                captured_item_count=1,
                truncated=False,
                omitted_item_count_estimate=None,
                completeness=CoverageCompleteness.BOUNDED,
                status=CoverageStatus.OBSERVED,
            ),
        ),
    )
    signature = classify_action(
        observation,
        target_id="resource:control",
        action_kind="activate",
        parameters={},
    )
    assert not signature.coverage_complete
