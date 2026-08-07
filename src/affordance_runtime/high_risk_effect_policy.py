"""Small, operation-family policy matrix for material high-risk effects."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.effect_authority_contracts import EffectClass
from affordance_runtime.verification.contracts import AssuranceLevel


@dataclass(frozen=True)
class HighRiskEffectPolicy:
    policy_ref: str
    effect_class: EffectClass
    operation_refs: frozenset[str]
    required_material_fields: frozenset[str]
    minimum_assurance: AssuranceLevel
    required_capability: str
    exact_approval: bool = True
    preflight_required: bool = True
    causal_evidence_required: bool = True
    authoritative_final_recheck: bool = True
    required_collateral_verifiers: tuple[str, ...] = ("collateral_unintended_effects",)
    retry_policy: str = "authoritative_recheck_then_block_or_handoff"


HIGH_RISK_EFFECT_POLICIES = (
    HighRiskEffectPolicy(
        "external-communication@v1", EffectClass.SEND, frozenset({"message.send@v1"}),
        frozenset({"recipient", "content"}), AssuranceLevel.AUTHORITATIVE, "communication.send",
    ),
    HighRiskEffectPolicy(
        "external-sharing@v1", EffectClass.SHARE, frozenset({"resource.share@v1"}),
        frozenset({"recipient", "resource"}), AssuranceLevel.AUTHORITATIVE, "resource.share",
    ),
    HighRiskEffectPolicy(
        "financial-commit@v1", EffectClass.PAY, frozenset({"payment.commit@v1", "purchase.commit@v1"}),
        frozenset({"payee", "amount", "currency"}), AssuranceLevel.AUTHORITATIVE, "payment.commit",
    ),
    HighRiskEffectPolicy(
        "destructive-mutation@v1", EffectClass.DELETE, frozenset({"resource.delete@v1"}),
        frozenset(), AssuranceLevel.AUTHORITATIVE, "resource.delete",
    ),
    HighRiskEffectPolicy(
        "account-security@v1", EffectClass.UPDATE, frozenset({"account.security.update@v1", "permission.change@v1"}),
        frozenset({"principal", "permission"}), AssuranceLevel.AUTHORITATIVE, "account.security.write",
    ),
    HighRiskEffectPolicy(
        "safety-device-actuation@v1", EffectClass.INVOKE, frozenset({"device.actuate@v1", "wot.invokeaction@v1"}),
        frozenset({"device", "operation", "value"}), AssuranceLevel.AUTHORITATIVE, "device.actuate",
    ),
    HighRiskEffectPolicy(
        "safety-device-write@v1", EffectClass.UPDATE, frozenset({"wot.writeproperty@v1"}),
        frozenset({"device", "property", "value"}), AssuranceLevel.AUTHORITATIVE, "device.actuate",
    ),
)


def policy_for_effect(effect_class: EffectClass | None, operation_ref: str | None) -> HighRiskEffectPolicy | None:
    return next(
        (
            policy
            for policy in HIGH_RISK_EFFECT_POLICIES
            if policy.effect_class == effect_class and operation_ref in policy.operation_refs
        ),
        None,
    )
