"""Behavioral closure checks for typed control outcomes and reducer rejection."""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from affordance_runtime.agent.control_outcome import Continue, LoopDirective, Pause, Terminate
from affordance_runtime.agent.control_reducer import (
    AppendRoot,
    ApplyContinuation,
    ControlRejected,
    ControlState,
    reduce_control,
)
from affordance_runtime.agent.decision_control import accept_current_decision
from affordance_runtime.agent.state import AgentLoopStatus


def test_control_algebra_is_closed_and_carries_no_accounting() -> None:
    variants = (Continue("continued"), Pause(AgentLoopStatus.WAITING_USER, "user_pending"), Terminate(AgentLoopStatus.FAILED, "failed"))
    assert all(isinstance(item, LoopDirective.__args__) for item in variants)
    forbidden = {"observation_count", "execution_count", "currentness_probe_count"}
    assert all(not forbidden.intersection(item.name for item in fields(type(value))) for value in variants)


def test_unsupported_reducer_command_is_typed_and_deterministic() -> None:
    assert reduce_control(ControlState(), object()) == ControlRejected(
        "unsupported_control_command"
    )


def test_malformed_state_and_typed_command_shells_fail_closed() -> None:
    assert reduce_control(ControlState(total_count=-1), object()) == ControlRejected(
        "invalid_control_totals"
    )
    assert reduce_control(ControlState(), AppendRoot(object(), 1)) == ControlRejected(
        "invalid_root_transition"
    )
    assert reduce_control(ControlState(), ApplyContinuation(object())) == ControlRejected(
        "invalid_control_continuation"
    )


def test_raw_status_string_cannot_masquerade_as_agent_loop_status() -> None:
    with pytest.raises(TypeError, match="status must be typed"):
        Pause("waiting_user", "user_pending")


def test_attribute_only_fake_decision_fails_closed_without_consuming_context() -> None:
    session = SimpleNamespace(
        current_context_snapshot=SimpleNamespace(context_id="context:current"),
        consumed_context_id="",
    )
    fake = SimpleNamespace(context_id="context:current")

    assert accept_current_decision(session, fake) is False
    assert session.consumed_context_id == ""
