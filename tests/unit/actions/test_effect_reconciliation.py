from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.reconciliation import (
    EffectReconciliation,
    EffectReconciliationReason,
    EffectReconciliationStatus,
    EffectRevisionDisposition,
    assess_effect_revision,
)
from affordance_runtime.execution import CommittedEffect, DispatchStatus


def _effect(
    *,
    suffix: str,
    task_revision: int,
    reversibility: Reversibility,
    dispatch_status: DispatchStatus = DispatchStatus.SENT,
    resource_ref: str = "account:second",
) -> CommittedEffect:
    return CommittedEffect(
        f"effect:sha256:{suffix * 64}",
        task_revision,
        f"request:{suffix}",
        "activate",
        resource_ref,
        ("account_checked",),
        reversibility,
        dispatch_status,
        f"observation:{suffix}:before",
        f"observation:{suffix}:after",
    )


@given(
    reversibility=st.sampled_from(tuple(Reversibility)),
    dispatch_status=st.sampled_from((DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN)),
)
def test_fresh_complete_revision_is_compatible_for_every_single_closed_effect(
    reversibility: Reversibility,
    dispatch_status: DispatchStatus,
) -> None:
    effect = _effect(
        suffix="a",
        task_revision=1,
        reversibility=reversibility,
        dispatch_status=dispatch_status,
    )

    assessment = assess_effect_revision(
        execution_count=1,
        latest_effect=effect,
        revised_goal_satisfied=True,
    )

    assert assessment.disposition is EffectRevisionDisposition.COMPATIBLE
    assert assessment.effect is effect


@given(reversibility=st.sampled_from(tuple(Reversibility)))
def test_incomplete_revision_uses_closed_receipt_algebra(
    reversibility: Reversibility,
) -> None:
    effect = _effect(
        suffix="b",
        task_revision=1,
        reversibility=reversibility,
    )

    assessment = assess_effect_revision(
        execution_count=1,
        latest_effect=effect,
        revised_goal_satisfied=False,
    )

    expected = {
        Reversibility.REVERSIBLE: EffectRevisionDisposition.COMPENSATION_REQUIRED,
        Reversibility.COMPENSATABLE: EffectRevisionDisposition.COMPENSATION_REQUIRED,
        Reversibility.IRREVERSIBLE: EffectRevisionDisposition.NON_COMPENSABLE,
        Reversibility.UNKNOWN: EffectRevisionDisposition.UNKNOWN,
    }[reversibility]
    assert assessment.disposition is expected


def test_unknown_dispatch_and_unrepresented_multiple_effects_fail_closed() -> None:
    unknown = _effect(
        suffix="c",
        task_revision=1,
        reversibility=Reversibility.REVERSIBLE,
        dispatch_status=DispatchStatus.SENT_UNKNOWN,
    )

    assert assess_effect_revision(
        execution_count=1,
        latest_effect=unknown,
        revised_goal_satisfied=False,
    ).disposition is EffectRevisionDisposition.UNKNOWN
    assert assess_effect_revision(
        execution_count=2,
        latest_effect=unknown,
        revised_goal_satisfied=True,
    ).disposition is EffectRevisionDisposition.UNSUPPORTED
    assert assess_effect_revision(
        execution_count=2,
        latest_effect=None,
        revised_goal_satisfied=False,
    ).disposition is EffectRevisionDisposition.UNSUPPORTED
    assert assess_effect_revision(
        execution_count=1,
        latest_effect=None,
        revised_goal_satisfied=False,
    ).disposition is EffectRevisionDisposition.UNKNOWN


@given(
    verified=st.booleans(),
    same_resource=st.booleans(),
    dispatch_status=st.sampled_from((DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN)),
)
def test_compensation_transition_preserves_original_and_appends_one_new_effect(
    verified: bool,
    same_resource: bool,
    dispatch_status: DispatchStatus,
) -> None:
    original = _effect(
        suffix="d",
        task_revision=1,
        reversibility=Reversibility.COMPENSATABLE,
    )
    compensation = _effect(
        suffix="e",
        task_revision=2,
        reversibility=Reversibility.REVERSIBLE,
        dispatch_status=dispatch_status,
        resource_ref=(original.resource_ref if same_resource else "account:first"),
    )
    pending = EffectReconciliation(original, 2)

    closed = pending.close_attempt(compensation, verified=verified)

    assert pending.status is EffectReconciliationStatus.PENDING
    assert pending.compensation_effect is None
    assert closed.original_effect is original
    assert closed.compensation_effect is compensation
    if same_resource and verified and dispatch_status is DispatchStatus.SENT:
        assert closed.status is EffectReconciliationStatus.COMPENSATED
        assert closed.reason is EffectReconciliationReason.COMPENSATION_VERIFIED
    else:
        assert closed.status is EffectReconciliationStatus.NEEDS_INPUT
