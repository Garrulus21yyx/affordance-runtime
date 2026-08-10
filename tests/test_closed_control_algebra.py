from __future__ import annotations

import inspect
from dataclasses import fields
from pathlib import Path

from affordance_runtime.agent.control_outcome import Continue, LoopDirective, Pause, Terminate
from affordance_runtime.agent.state import AgentLoopStatus


def test_control_algebra_is_closed_and_carries_no_accounting() -> None:
    variants = (Continue("continued"), Pause(AgentLoopStatus.WAITING_USER, "user_pending"), Terminate(AgentLoopStatus.FAILED, "failed"))
    assert all(isinstance(item, LoopDirective.__args__) for item in variants)
    forbidden = {"observation_count", "execution_count", "currentness_probe_count"}
    assert all(not forbidden.intersection(item.name for item in fields(type(value))) for value in variants)


def test_control_seam_has_no_naked_object_or_tuple_dispatch() -> None:
    root = Path("src/affordance_runtime/agent")
    sources = "\n".join((root / name).read_text(encoding="utf-8") for name in (
        "decision_control.py", "loop.py", "execution_cycle.py", "control_transition.py",
    ))
    assert "Awaitable[object]" not in sources
    assert "-> object" not in sources
    assert "_apply_outcome" not in sources
    assert "add_counts(" not in sources
    assert "isinstance(outcome, tuple)" not in sources
    assert inspect.signature(__import__("affordance_runtime.agent.decision_control", fromlist=["run_policy_turn"]).run_policy_turn).return_annotation is not object
