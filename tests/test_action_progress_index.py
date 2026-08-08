import json

import pytest

import affordance_runtime.state_kernel as state_kernel
from affordance_runtime.contracts import Observation
from affordance_runtime.simplified_runtime_contracts import (
    CollateralSettlementStatus,
    EffectSettlement,
    EffectSettlementStatus,
)
from affordance_runtime.state_kernel import ProgressGuardReason, StateKernel
from runtime_test_support import remember_observation


def _signature(action_kind: str, target: str, parameters: dict[str, object]) -> str:
    return json.dumps(
        {
            "action_kind": action_kind,
            "target": target,
            "parameters": parameters,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def test_recent_action_outcome_index_uses_typed_bounded_keys() -> None:
    ActionKey = state_kernel.ActionKey
    RecentActionOutcomeIndex = state_kernel.RecentActionOutcomeIndex
    index = RecentActionOutcomeIndex(capacity=2)

    first = ActionKey.from_signature(_signature("activate", "target-a", {"x": 1}))
    second = ActionKey.from_signature(_signature("activate", "target-b", {"x": 2}))
    third = ActionKey.from_signature(_signature("activate", "target-c", {"x": 3}))
    index.record(first, "env-1", verification_passed=True, effect_satisfied=True)
    index.record(second, "env-2", verification_passed=False, effect_satisfied=False)
    index.record(third, "env-3", verification_passed=True, effect_satisfied=True)

    assert tuple(item.key for item in index.records) == (second, third)
    assert first.parameter_digest != second.parameter_digest
    assert index.latest(first) is None
    assert index.latest(third) is not None


def test_statekernel_action_dedupe_does_not_expose_legacy_action_progress_list() -> None:
    RecentActionOutcomeIndex = state_kernel.RecentActionOutcomeIndex
    state = StateKernel(task_id="task", goal="Click target")

    assert not hasattr(state, "action_progress")
    assert isinstance(state.recent_action_outcomes, RecentActionOutcomeIndex)


def test_progress_guard_uses_typed_recent_action_outcomes() -> None:
    state = StateKernel(task_id="task", goal="Click target")
    remember_observation(
        state,
        Observation("env-2", snapshot_id="snapshot-1", page_revision="page-1"),
    )
    signature = _signature("activate", "target-a", {})

    state.record_action_progress(
        signature,
        "env-1",
        verification_passed=True,
        effect_satisfied=True,
        post_page_revision="page-1",
    )

    assert state.check_progress_guard(signature) == ProgressGuardReason.EFFECT_ALREADY_SATISFIED


def test_action_key_rejects_unstructured_legacy_signature() -> None:
    ActionKey = state_kernel.ActionKey
    with pytest.raises(ValueError, match="action progress signature"):
        ActionKey.from_signature("activate:checkbox-a")


def test_unrelated_verified_absence_does_not_release_progress_guard() -> None:
    state = StateKernel(task_id="task", goal="Click target")
    remember_observation(state, Observation("env-1", snapshot_id="snapshot-1", page_revision="page-1"))
    signature = _signature("activate", "target-a", {})
    state.record_action_progress(
        signature,
        "env-1",
        verification_passed=False,
        effect_satisfied=False,
        attempt_id="attempt-a",
    )
    state.latest_effect_settlement = EffectSettlement(
        "attempt-b",
        EffectSettlementStatus.NOT_OCCURRED,
        ("evidence-b",),
        CollateralSettlementStatus.UNRESOLVED,
    )

    assert state.check_progress_guard(signature) == ProgressGuardReason.NO_PROGRESS_REPEAT


def test_matching_verified_absence_releases_progress_guard() -> None:
    state = StateKernel(task_id="task", goal="Click target")
    remember_observation(state, Observation("env-1", snapshot_id="snapshot-1", page_revision="page-1"))
    signature = _signature("activate", "target-a", {})
    state.record_action_progress(
        signature,
        "env-1",
        verification_passed=False,
        effect_satisfied=False,
        attempt_id="attempt-a",
    )
    state.latest_effect_settlement = EffectSettlement(
        "attempt-a",
        EffectSettlementStatus.NOT_OCCURRED,
        ("evidence-a",),
        CollateralSettlementStatus.UNRESOLVED,
    )

    assert state.check_progress_guard(signature) is None
