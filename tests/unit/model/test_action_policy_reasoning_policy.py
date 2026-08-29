from __future__ import annotations

from types import SimpleNamespace

import pytest

from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyInvocationPhase,
    ActionPolicyInvocationTrigger,
    ActionPolicyReasoningPolicy,
)
from tests.support.legacy_compact_json_decision_port import _semantic_choice


def _context(kind: str = "", signature: str = "", *, recovery_attempt: int = 1):
    return SimpleNamespace(
        control_feedback=(
            {
                "kind": kind,
                "stable_signature": signature,
                "recovery_attempt": recovery_attempt,
            }
            if kind
            else {}
        )
    )


def test_ordinary_deliberate_and_repair_profiles_are_disjoint_and_bounded() -> None:
    policy = ActionPolicyReasoningPolicy(768, 1536, 384)
    ordinary = policy.select(_context())
    deliberate = policy.select(_context("grounding_stall", "event:one"))
    repair = policy.repair()

    assert (ordinary.phase, ordinary.trigger, ordinary.max_output_tokens, ordinary.thinking_mode) == (
        ActionPolicyInvocationPhase.ORDINARY,
        ActionPolicyInvocationTrigger.ORDINARY,
        768,
        "disabled",
    )
    assert (deliberate.phase, deliberate.trigger, deliberate.max_output_tokens, deliberate.thinking_mode) == (
        ActionPolicyInvocationPhase.DELIBERATE,
        ActionPolicyInvocationTrigger.GROUNDING_GAP,
        1536,
        "enabled",
    )
    assert (repair.phase, repair.trigger, repair.max_output_tokens, repair.thinking_mode) == (
        ActionPolicyInvocationPhase.REPRESENTATION_REPAIR,
        ActionPolicyInvocationTrigger.REPRESENTATION_ERROR,
        384,
        "disabled",
    )


def test_active_recovery_epoch_keeps_every_action_policy_call_deliberate() -> None:
    policy = ActionPolicyReasoningPolicy()
    context = _context("control_stall", "epoch:stable")

    profiles = tuple(policy.select(context) for _ in range(4))

    assert {item.phase for item in profiles} == {ActionPolicyInvocationPhase.DELIBERATE}
    assert {item.trigger for item in profiles} == {ActionPolicyInvocationTrigger.CONTROL_STALL}
    assert {item.thinking_mode for item in profiles} == {"enabled"}


@pytest.mark.parametrize(
    ("kind", "trigger"),
    (
        ("grounding_stall", ActionPolicyInvocationTrigger.GROUNDING_GAP),
        ("capability_gap", ActionPolicyInvocationTrigger.EVIDENCE_GAP),
        ("control_stall", ActionPolicyInvocationTrigger.CONTROL_STALL),
        ("effect_stall", ActionPolicyInvocationTrigger.OPERATIONAL_STALL),
        ("uncertain_effect", ActionPolicyInvocationTrigger.OPERATIONAL_STALL),
        ("state_oscillation", ActionPolicyInvocationTrigger.OPERATIONAL_STALL),
        ("strategy_review", ActionPolicyInvocationTrigger.OPERATIONAL_STALL),
    ),
)
def test_each_supported_monitor_recovery_kind_owns_one_deliberate_lease(
    kind: str,
    trigger: ActionPolicyInvocationTrigger,
) -> None:
    profile = ActionPolicyReasoningPolicy().select(_context(kind, f"event:{kind}"))

    assert profile.phase is ActionPolicyInvocationPhase.DELIBERATE
    assert profile.trigger is trigger
    assert profile.thinking_mode == "enabled"


def test_recovery_kind_without_epoch_identity_cannot_enable_deliberate_mode() -> None:
    profile = ActionPolicyReasoningPolicy().select(_context("control_stall", ""))

    assert profile.phase is ActionPolicyInvocationPhase.ORDINARY
    assert profile.trigger is ActionPolicyInvocationTrigger.ORDINARY
    assert profile.thinking_mode == "disabled"


def test_representation_semantic_choice_is_operation_and_target_stable() -> None:
    original = _semantic_choice({"name": "activate", "arguments": {"target": "E2", "extra": "ignored"}})
    same = _semantic_choice({"name": "activate", "arguments": {"target": "E2"}})
    changed = _semantic_choice({"name": "activate", "arguments": {"target": "E3"}})
    assert original == same
    assert changed != original
