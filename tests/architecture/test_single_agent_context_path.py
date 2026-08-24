"""Architecture redlines for the canonical grounded AgentContext path."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
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
        "model/policy/pydantic_ai_bridge.py",
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


def test_model_request_and_agent_context_each_have_one_context_authority() -> None:
    assert {item.name for item in fields(ModelDecisionRequest)} == {
        "request_id", "agent_context", "last_step",
    }
    assert next(item for item in fields(ModelDecisionRequest) if item.name == "last_step").metadata[
        "serialize"
    ] is False
    assert "world" not in {item.name for item in fields(AgentContext)}
    assert "actor_world" in {item.name for item in fields(AgentContext)}


def test_deleted_parallel_model_input_chain_stays_absent() -> None:
    policy_root = RUNTIME / "model" / "policy"
    for name in ("spec.py", "parser.py", "serialization.py", "schema_identity.py"):
        assert not (policy_root / name).exists()
    production = "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME.rglob("*.py"))
    for token in (
        "serialized_context",
        "requires_serialized_context",
        "AgentDecisionPayload",
        "payload_to_decision",
    ):
        assert token not in production


def test_context_builder_does_not_construct_a_second_agent_world_view() -> None:
    builder = _source("agent/context/context_builder.py")
    assert "build_agent_world_view" not in builder
    assert "project_actor_world_snapshot" in builder
    assert not (RUNTIME / "world/view.py").exists()
