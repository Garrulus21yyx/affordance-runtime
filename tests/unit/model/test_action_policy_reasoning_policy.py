from __future__ import annotations

from types import SimpleNamespace

from affordance_runtime.model.policy.grounded_tool_port_bridge import _semantic_choice
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyInvocationPhase,
    ActionPolicyInvocationTrigger,
    ActionPolicyReasoningPolicy,
)


def _context(kind: str = "", signature: str = ""):
    return SimpleNamespace(
        control_feedback=(
            {
                "kind": kind,
                "stable_signature": signature,
                "recovery_attempt": 1,
            }
            if kind
            else {}
        )
    )


def test_ordinary_deliberate_and_repair_profiles_are_disjoint_and_bounded() -> None:
    policy = ActionPolicyReasoningPolicy(768, 1536, 384)
    ordinary = policy.select(_context(), frozenset())
    deliberate = policy.select(_context("grounding_stall", "event:one"), frozenset())
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


def test_one_recovery_event_purchases_at_most_one_deliberate_call() -> None:
    policy = ActionPolicyReasoningPolicy()
    context = _context("control_stall", "event:stable")
    first = policy.select(context, frozenset())
    second = policy.select(context, frozenset({"event:stable"}))
    assert first.phase is ActionPolicyInvocationPhase.DELIBERATE
    assert second.phase is ActionPolicyInvocationPhase.ORDINARY


def test_representation_semantic_choice_is_operation_and_target_stable() -> None:
    original = _semantic_choice(
        {"name": "activate", "arguments": {"target": "E2", "extra": "ignored"}}
    )
    same = _semantic_choice({"name": "activate", "arguments": {"target": "E2"}})
    changed = _semantic_choice({"name": "activate", "arguments": {"target": "E3"}})
    assert original == same
    assert changed != original
