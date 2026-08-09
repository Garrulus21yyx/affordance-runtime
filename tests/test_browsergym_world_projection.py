import json

from browsergym_adapter_support import ax_node, raw_observation

from affordance_runtime.benchmarks.external_smoke.browsergym_projection import (
    project_browsergym_observation,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalVerifierStatus
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.model_policy.serialization import serialize_agent_context
from affordance_runtime.task import TaskGoal
from affordance_runtime.world.action_space import ActionSpaceBuilder


def test_structural_projection_is_bounded_truthful_and_private() -> None:
    raw = raw_observation(
        ax_node("private-1", "button", "okay"),
        ax_node("private-2", "textbox", "", properties=(("required", False),)),
        ax_node("private-3", "combobox", "", value="A", properties=(("expanded", False),)),
        ax_node("private-4", "option", "A"),
        ax_node("private-5", "option", "B"),
    )
    snapshot = BrowserGymVerifierSnapshot("run:opaque", "obs:1", "obs:1", ExternalVerifierStatus.INCOMPLETE, "")
    projected = project_browsergym_observation(
        raw, observation_id="obs:1", source_revision="revision:1",
        page_identity="page:opaque", episode_identity="0", verifier=snapshot,
    )
    assert len(projected.world.targets) == 3
    assert len(projected.world.bindings) == 3
    assert projected.target_count_total == 3
    assert str(projected.world.coverage["browsergym"]) == "complete"
    public = repr(projected.world)
    assert "private-" not in public
    assert "selector" not in public and "bid" not in public
    select = next(item for item in projected.world.bindings if item.semantic_action == "select")
    assert select.parameter_schema["properties"]["value"]["enum"] == ("A", "B")
    assert dict(projected.private_bindings[-1].option_values) == {"A": "A", "B": "B"}


def test_private_handles_and_benchmark_identity_are_absent_from_agent_context() -> None:
    raw = raw_observation(ax_node("private-1", "button", "okay"))
    snapshot = BrowserGymVerifierSnapshot("run:opaque", "obs:1", "obs:1", ExternalVerifierStatus.INCOMPLETE, "")
    world = project_browsergym_observation(
        raw, observation_id="obs:1", source_revision="revision:1",
        page_identity="page:opaque", episode_identity="0", verifier=snapshot,
    ).world
    task = TaskGoal("task:opaque", raw["goal"], allowed_effects=("external_ui_interaction",))
    state = __import__(
        "affordance_runtime.agent.state", fromlist=["AgentLoopState"],
    ).AgentLoopState(world, remaining_turns=2)
    evaluation = TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing")
    context = ContextBuilder().build(task, state, ActionSpaceBuilder().build(task, world), evaluation)
    serialized = serialize_agent_context(context)
    for forbidden in ("private-1", "browsergym/miniwob", "selector", "expected_answer", "RAW_REWARD_GLOBAL"):
        assert forbidden not in serialized
    assert json.loads(serialized)["task"]["instruction"] == raw["goal"]
