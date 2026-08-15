"""Versioned exact operation semantics; operation names are never keyword-classified."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.actions.effect_authority import EffectClass, Externality, Reversibility


@dataclass(frozen=True)
class OperationSemantics:
    effect_class: EffectClass
    externality: Externality
    reversibility: Reversibility


OPERATION_SEMANTICS: dict[str, OperationSemantics] = {
    "resource.read@v1": OperationSemantics(EffectClass.READ, Externality.LOCAL, Reversibility.REVERSIBLE),
    "navigation.navigate@v1": OperationSemantics(
        EffectClass.NAVIGATE, Externality.SAME_ORIGIN, Reversibility.REVERSIBLE
    ),
    "field.set@v1": OperationSemantics(EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE),
    "resource.update@v1": OperationSemantics(EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE),
    "interaction.reveal@v1": OperationSemantics(
        EffectClass.INTERACTION_ONLY, Externality.LOCAL, Reversibility.REVERSIBLE
    ),
    "message.send@v1": OperationSemantics(
        EffectClass.SEND, Externality.EXTERNAL_SYSTEM, Reversibility.IRREVERSIBLE
    ),
    "resource.share@v1": OperationSemantics(
        EffectClass.SHARE, Externality.EXTERNAL_SYSTEM, Reversibility.COMPENSATABLE
    ),
    "payment.commit@v1": OperationSemantics(
        EffectClass.PAY, Externality.EXTERNAL_SYSTEM, Reversibility.IRREVERSIBLE
    ),
    "purchase.commit@v1": OperationSemantics(
        EffectClass.PAY, Externality.EXTERNAL_SYSTEM, Reversibility.IRREVERSIBLE
    ),
    "resource.delete@v1": OperationSemantics(
        EffectClass.DELETE, Externality.LOCAL, Reversibility.IRREVERSIBLE
    ),
    "account.security.update@v1": OperationSemantics(
        EffectClass.UPDATE, Externality.EXTERNAL_SYSTEM, Reversibility.COMPENSATABLE
    ),
    "permission.change@v1": OperationSemantics(
        EffectClass.UPDATE, Externality.EXTERNAL_SYSTEM, Reversibility.COMPENSATABLE
    ),
    "device.actuate@v1": OperationSemantics(
        EffectClass.INVOKE, Externality.PHYSICAL_WORLD, Reversibility.UNKNOWN
    ),
    "wot.invokeaction@v1": OperationSemantics(
        EffectClass.INVOKE, Externality.PHYSICAL_WORLD, Reversibility.UNKNOWN
    ),
    "wot.writeproperty@v1": OperationSemantics(
        EffectClass.UPDATE, Externality.PHYSICAL_WORLD, Reversibility.UNKNOWN
    ),
    "wot.readproperty@v1": OperationSemantics(
        EffectClass.READ, Externality.PHYSICAL_WORLD, Reversibility.REVERSIBLE
    ),
}


def semantics_for_operation(operation_ref: str) -> OperationSemantics | None:
    return OPERATION_SEMANTICS.get(operation_ref)
