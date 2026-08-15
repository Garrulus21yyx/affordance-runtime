"""Architecture redlines for the canonical grounded AgentContext path."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolCatalog

ROOT = Path(__file__).parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"


def _source(relative: str) -> str:
    return (RUNTIME / relative).read_text(encoding="utf-8")


def test_grounded_catalog_cannot_become_a_second_context_owner() -> None:
    field_names = {item.name for item in fields(GroundedToolCatalog)}
    assert field_names.isdisjoint(
        {"view", "workspace", "task_state", "working_memory", "agent_context"}
    )


def test_grounded_action_path_has_no_mandatory_semantic_updater() -> None:
    governed = (
        "model/policy/grounded_tool_port_bridge.py",
        "model/policy/grounded_policy_context.py",
        "model/policy/prompts/grounded_agent.yaml",
    )
    banned = (
        "task_state_updater",
        "GroundedTaskStatePayload",
        "AgentWorkingMemory",
        "_update_task_state",
    )
    for relative in governed:
        source = _source(relative)
        assert all(token not in source for token in banned), relative


def test_removed_working_memory_contract_stays_absent() -> None:
    assert not (RUNTIME / "agent/working_memory.py").exists()
