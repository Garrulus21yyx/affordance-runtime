from __future__ import annotations

import json

import numpy as np
from browsergym_adapter_support import ax_node, raw_observation

from affordance_runtime.agent import SelectAction
from affordance_runtime.agent.local_objective_proposal import LocalObjectiveProposal
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
from affordance_runtime.model_policy.grounded_tool_contracts import GroundedToolPhase
from affordance_runtime.model_policy.grounded_tool_port_bridge import GroundedToolCommandPayload
from affordance_runtime.model_policy.tool_contracts import ToolCall
from affordance_runtime.task import (
    ActionTemplate,
    FactEquals,
    RiskProfile,
    ScopeExtent,
    ScopeSpec,
    SetObjective,
    SetQuantifier,
    TaskGoal,
)
from affordance_runtime.task.local_objective import establish_local_objective
from affordance_runtime.world import ActionSpaceBuilder

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


def _context(*, local_objective=None):
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
    if local_objective is not None:
        state.local_objective_state = establish_local_objective(
            local_objective,
            projection.world,
            enumerator=state.scope_enumerator,
        )
    return ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(task.task_id, projection.world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
    )


def test_grounding_projection_is_public_and_contains_no_runtime_identity() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
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
    context = _context(
        local_objective=SetObjective(
            "set-objective:fill-password",
            ScopeSpec("scope:viewport", "current-viewport", ScopeExtent.CURRENT_VIEWPORT),
            FactEquals("identity.label", "Password"),
            SetQuantifier.EXACTLY_ONE,
            ActionTemplate("fill", parameters={"value": "UV"}),
        )
    )
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    assert {item.name for item in catalog.specs} == {"fill"}
    decision = resolve_grounded_tool_call(
        catalog,
        ToolCall("fill", {"text": "UV"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(decision, SelectAction)
    assert decision.parameters == {"value": "UV"}
    assert decision.action_id.startswith("action:")


def test_catalog_has_one_local_objective_constructor_and_a_stable_command_envelope() -> None:
    catalog = compile_grounded_tool_catalog(_context(), GroundedToolPhase.OBJECTIVE_PROPOSAL)
    assert [item.name for item in catalog.specs] == ["propose_local_objective"]
    assert set(GroundedToolCommandPayload.model_json_schema()["properties"]) == {
        "op", "target", "text", "value"
    }
    assert all(item.name not in {"click", "fill", "select"} for item in catalog.specs)


def test_local_objective_tool_carries_semantics_without_pre_observation_target_identity() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.OBJECTIVE_PROPOSAL)
    decision = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "propose_local_objective",
            {
                "value": {
                    "kind": "set",
                    "predicate": {"any_of": [{"all_of": [{
                        "kind": "fact_equals", "field_name": "grid_coordinate",
                        "expected": {"x": 1, "y": -2},
                    }]}]},
                    "quantifier": "exactly_one",
                    "semantic_action": "activate",
                }
            },
        ),
        expected_context_id=context.context_id,
    )

    assert isinstance(decision, LocalObjectiveProposal)
    assert decision.objective.scope.root_entity_id == "current-viewport"


def test_aria_hidden_ancestor_removes_layout_only_control_from_execution_visibility() -> None:
    assert _effective_visibility(True, {"ariaHiddenByAncestor": True}) is False
    assert _effective_visibility(True, {"ariaHiddenByAncestor": False}) is True
