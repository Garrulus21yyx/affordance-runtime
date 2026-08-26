"""Bounded reconciliation facts for one retained GUI effect across task revision."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.execution.contracts import CommittedEffect, DispatchStatus


class EffectRevisionDisposition(StrEnum):
    NO_EFFECT = "no_effect"
    COMPATIBLE = "compatible"
    COMPENSATION_REQUIRED = "compensation_required"
    NON_COMPENSABLE = "non_compensable"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class EffectRevisionReason(StrEnum):
    NO_COMMITTED_EFFECT = "no_committed_effect"
    REVISED_GOAL_ALREADY_SATISFIED = "revised_goal_already_satisfied"
    EFFECT_COMPENSATION_REQUIRED = "effect_compensation_required"
    EFFECT_NON_COMPENSABLE = "effect_non_compensable"
    EFFECT_DISPATCH_UNKNOWN = "effect_dispatch_unknown"
    EFFECT_LINEAGE_MISSING = "effect_lineage_missing"
    EFFECT_SEMANTICS_UNKNOWN = "effect_semantics_unknown"
    MULTIPLE_EFFECTS_UNSUPPORTED = "multiple_effects_unsupported"


@dataclass(frozen=True)
class EffectRevisionAssessment:
    disposition: EffectRevisionDisposition
    reason: EffectRevisionReason
    effect: CommittedEffect | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, EffectRevisionDisposition) or not isinstance(
            self.reason,
            EffectRevisionReason,
        ):
            raise TypeError("effect revision assessment must be typed")
        allowed_reasons = {
            EffectRevisionDisposition.NO_EFFECT: {
                EffectRevisionReason.NO_COMMITTED_EFFECT,
            },
            EffectRevisionDisposition.COMPATIBLE: {
                EffectRevisionReason.REVISED_GOAL_ALREADY_SATISFIED,
            },
            EffectRevisionDisposition.COMPENSATION_REQUIRED: {
                EffectRevisionReason.EFFECT_COMPENSATION_REQUIRED,
            },
            EffectRevisionDisposition.NON_COMPENSABLE: {
                EffectRevisionReason.EFFECT_NON_COMPENSABLE,
            },
            EffectRevisionDisposition.UNKNOWN: {
                EffectRevisionReason.EFFECT_DISPATCH_UNKNOWN,
                EffectRevisionReason.EFFECT_LINEAGE_MISSING,
                EffectRevisionReason.EFFECT_SEMANTICS_UNKNOWN,
            },
            EffectRevisionDisposition.UNSUPPORTED: {
                EffectRevisionReason.MULTIPLE_EFFECTS_UNSUPPORTED,
            },
        }
        if self.reason not in allowed_reasons[self.disposition]:
            raise ValueError("effect assessment disposition and reason disagree")
        effect_optional = (
            self.disposition is EffectRevisionDisposition.NO_EFFECT
            or self.reason is EffectRevisionReason.EFFECT_LINEAGE_MISSING
            or self.disposition is EffectRevisionDisposition.UNSUPPORTED
        )
        if effect_optional:
            if (
                self.disposition is EffectRevisionDisposition.NO_EFFECT
                and self.effect is not None
            ):
                raise ValueError("no-effect assessment cannot retain an effect")
        elif self.effect is None:
            raise ValueError("effect assessment requires exact committed lineage")


def assess_effect_revision(
    *,
    execution_count: int,
    latest_effect: CommittedEffect | None,
    revised_goal_satisfied: bool,
) -> EffectRevisionAssessment:
    """Classify only facts established by receipt lineage and the fresh evaluator."""

    if (
        type(execution_count) is not int
        or execution_count < 0
        or type(revised_goal_satisfied) is not bool
        or (latest_effect is not None and not isinstance(latest_effect, CommittedEffect))
    ):
        raise ValueError("effect revision facts are invalid")
    if execution_count == 0:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.NO_EFFECT,
            EffectRevisionReason.NO_COMMITTED_EFFECT,
        )
    if execution_count != 1:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.UNSUPPORTED,
            EffectRevisionReason.MULTIPLE_EFFECTS_UNSUPPORTED,
            latest_effect,
        )
    if latest_effect is None:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.UNKNOWN,
            EffectRevisionReason.EFFECT_LINEAGE_MISSING,
        )
    if revised_goal_satisfied:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.COMPATIBLE,
            EffectRevisionReason.REVISED_GOAL_ALREADY_SATISFIED,
            latest_effect,
        )
    if latest_effect.dispatch_status is DispatchStatus.SENT_UNKNOWN:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.UNKNOWN,
            EffectRevisionReason.EFFECT_DISPATCH_UNKNOWN,
            latest_effect,
        )
    if latest_effect.reversibility in {
        Reversibility.REVERSIBLE,
        Reversibility.COMPENSATABLE,
    }:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.COMPENSATION_REQUIRED,
            EffectRevisionReason.EFFECT_COMPENSATION_REQUIRED,
            latest_effect,
        )
    if latest_effect.reversibility is Reversibility.IRREVERSIBLE:
        return EffectRevisionAssessment(
            EffectRevisionDisposition.NON_COMPENSABLE,
            EffectRevisionReason.EFFECT_NON_COMPENSABLE,
            latest_effect,
        )
    return EffectRevisionAssessment(
        EffectRevisionDisposition.UNKNOWN,
        EffectRevisionReason.EFFECT_SEMANTICS_UNKNOWN,
        latest_effect,
    )


class EffectReconciliationStatus(StrEnum):
    PENDING = "pending"
    COMPENSATED = "compensated"
    NEEDS_INPUT = "needs_input"


class EffectReconciliationReason(StrEnum):
    EFFECT_COMPENSATION_REQUIRED = "effect_compensation_required"
    COMPENSATION_VERIFIED = "compensation_verified"
    COMPENSATION_UNAVAILABLE = "compensation_unavailable"
    COMPENSATION_NOT_SENT = "compensation_not_sent"
    COMPENSATION_EFFECT_UNKNOWN = "compensation_effect_unknown"
    COMPENSATION_UNVERIFIED = "compensation_unverified"
    COMPENSATION_RESOURCE_MISMATCH = "compensation_resource_mismatch"
    COMPENSATION_ACTION_NOT_ALLOWED = "compensation_action_not_allowed"
    COMPENSATION_MULTIPLE_EFFECTS = "compensation_multiple_effects"


@dataclass(frozen=True)
class EffectReconciliation:
    """One bounded Runtime-owned requirement; never an effect ledger."""

    original_effect: CommittedEffect
    revised_task_revision: int
    status: EffectReconciliationStatus = EffectReconciliationStatus.PENDING
    reason: EffectReconciliationReason = EffectReconciliationReason.EFFECT_COMPENSATION_REQUIRED
    compensation_effect: CommittedEffect | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.original_effect, CommittedEffect)
            or type(self.revised_task_revision) is not int
            or self.revised_task_revision <= self.original_effect.task_revision
            or not isinstance(self.status, EffectReconciliationStatus)
            or not isinstance(self.reason, EffectReconciliationReason)
            or self.original_effect.dispatch_status is not DispatchStatus.SENT
            or self.original_effect.reversibility
            not in {Reversibility.REVERSIBLE, Reversibility.COMPENSATABLE}
        ):
            raise ValueError("effect reconciliation identity is invalid")
        if self.status is EffectReconciliationStatus.PENDING:
            if (
                self.compensation_effect is not None
                or self.reason is not EffectReconciliationReason.EFFECT_COMPENSATION_REQUIRED
            ):
                raise ValueError("pending reconciliation cannot contain a compensation result")
        elif self.status is EffectReconciliationStatus.COMPENSATED:
            if (
                self.compensation_effect is None
                or self.reason is not EffectReconciliationReason.COMPENSATION_VERIFIED
                or self.compensation_effect.dispatch_status is not DispatchStatus.SENT
                or self.compensation_effect.resource_ref
                != self.original_effect.resource_ref
            ):
                raise ValueError("compensated reconciliation requires its verified receipt")
        elif self.reason in {
            EffectReconciliationReason.EFFECT_COMPENSATION_REQUIRED,
            EffectReconciliationReason.COMPENSATION_VERIFIED,
        }:
            raise ValueError("needs-input reconciliation requires a closed failure reason")
        compensation = self.compensation_effect
        if compensation is not None and compensation.task_revision != self.revised_task_revision:
            raise ValueError("compensation receipt belongs to another task revision")

    def needs_input(
        self,
        reason: EffectReconciliationReason,
        compensation_effect: CommittedEffect | None = None,
    ) -> EffectReconciliation:
        if self.status is not EffectReconciliationStatus.PENDING:
            raise ValueError("only pending reconciliation can require input")
        return replace(
            self,
            status=EffectReconciliationStatus.NEEDS_INPUT,
            reason=reason,
            compensation_effect=compensation_effect,
        )

    def close_attempt(
        self,
        effect: CommittedEffect,
        *,
        verified: bool,
    ) -> EffectReconciliation:
        if self.status is not EffectReconciliationStatus.PENDING:
            raise ValueError("only pending reconciliation can close an attempt")
        if effect.resource_ref != self.original_effect.resource_ref:
            return self.needs_input(
                EffectReconciliationReason.COMPENSATION_RESOURCE_MISMATCH,
                effect,
            )
        if effect.dispatch_status is DispatchStatus.SENT_UNKNOWN:
            return self.needs_input(
                EffectReconciliationReason.COMPENSATION_EFFECT_UNKNOWN,
                effect,
            )
        if not verified:
            return self.needs_input(
                EffectReconciliationReason.COMPENSATION_UNVERIFIED,
                effect,
            )
        return replace(
            self,
            status=EffectReconciliationStatus.COMPENSATED,
            reason=EffectReconciliationReason.COMPENSATION_VERIFIED,
            compensation_effect=effect,
        )

    def public_summary(self) -> dict[str, object]:
        """Return only model/UI-safe semantic facts, never private routing data."""

        return {
            "status": self.status.value,
            "reason": self.reason.value,
            "original_effect_ref": self.original_effect.effect_ref,
            "original_action": self.original_effect.semantic_action,
            "resource_ref": self.original_effect.resource_ref,
            "semantic_effects": self.original_effect.semantic_effects,
            "reversibility": self.original_effect.reversibility.value,
            "compensation_effect_ref": (
                self.compensation_effect.effect_ref
                if self.compensation_effect is not None
                else ""
            ),
        }


__all__ = [
    "EffectReconciliation",
    "EffectReconciliationReason",
    "EffectReconciliationStatus",
    "EffectRevisionAssessment",
    "EffectRevisionDisposition",
    "EffectRevisionReason",
    "assess_effect_revision",
]
