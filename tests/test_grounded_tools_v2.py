from __future__ import annotations

import json

import numpy as np
from browsergym_adapter_support import ax_node, raw_observation

from affordance_runtime.agent import AgentDecisionPackage, SelectAction
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.benchmarks.external_smoke.browsergym_backend import _effective_visibility
from affordance_runtime.benchmarks.external_smoke.browsergym_entity_identity import BrowserGymEntityIdentityMap
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import project_browsergym_observation
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import PRIVATE_CONTROL_PROPERTIES_KEY
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import BrowserGymVerifierSnapshot
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary import ContextBuilder
from affordance_runtime.model_policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model_policy.grounded_tool_port_bridge import GroundedToolCommandPayload
from affordance_runtime.model_policy.tool_contracts import ToolCall
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ActionSpaceBuilder

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


def _context():
    raw = raw_observation(
        ax_node("username", "textbox", ""),
        ax_node("password", "textbox", ""),
        ax_node("login", "button", "Login"),
        goal='Enter username "donovan", password "UV", then press Login.',
    )
    raw["screenshot"] = np.full((160, 320, 3), 255, dtype=np.uint8)
    for bid, bbox, label in (
        ("username", [10, 10, 140, 30], "Username"),
        ("password", [10, 55, 140, 30], "Password"),
        ("login", [10, 100, 80, 30], "Login"),
    ):
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = bbox
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["label_hint"] = label
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:grounded",
        source_revision="revision:grounded",
        page_identity="page:grounded",
        episode_identity="episode:grounded",
        verifier=BrowserGymVerifierSnapshot(
            "run:grounded",
            "observation:grounded",
            "observation:grounded",
            VerifierFactSource.RESET,
            ExternalVerifierStatus.INCOMPLETE,
            ExternalVerifierReason.VERIFIED_RUNNING,
        ),
        entity_identity=_IDENTITY,
    )
    task = TaskGoal(
        "task:grounded",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    state = AgentLoopState(projection.world, remaining_turns=5)
    return ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(task.task_id, projection.world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
    )


def test_grounding_projection_is_public_and_contains_no_runtime_identity() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context)
    public = json.dumps(to_json_compatible({
        "index": catalog.view.grounding_index,
        "state": catalog.view.current_state,
        "tools": [item.input_schema for item in catalog.specs],
    }))
    assert [item.ref for item in context.grounding.entities] == ["E1", "E2", "E3"]
    assert all(item.marked for item in context.grounding.entities)
    assert "bbox" not in public
    assert "entity:" not in public and "action:" not in public and "binding:" not in public


def test_schema_equivalent_actions_resolve_privately_to_current_action_ids() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context)
    assert {item.name for item in catalog.specs} == {"fill", "click"}
    refs = {item.label: item.ref for item in context.grounding.entities}
    package = resolve_grounded_tool_call(
        catalog,
        ToolCall("fill", {"target": refs["Password"], "text": "UV"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(package, AgentDecisionPackage)
    assert isinstance(package.decision, SelectAction)
    assert package.decision.parameters == {"value": "UV"}
    assert package.decision.action_id.startswith("action:")


def test_action_catalog_and_command_payload_contain_no_semantic_constructors() -> None:
    catalog = compile_grounded_tool_catalog(_context())
    assert not any(item.name.startswith("establish_") for item in catalog.specs)
    assert set(GroundedToolCommandPayload.model_json_schema()["properties"]) == {
        "op", "target", "text", "value"
    }


def test_aria_hidden_ancestor_removes_layout_only_control_from_execution_visibility() -> None:
    assert _effective_visibility(True, {"ariaHiddenByAncestor": True}) is False
    assert _effective_visibility(True, {"ariaHiddenByAncestor": False}) is True
