import copy
import json

from browsergym_adapter_support import ax_node, raw_observation

from affordance_runtime.benchmarks.external_smoke import browsergym_projection as projection_module
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import (
    project_browsergym_observation,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.model_policy.serialization import serialize_agent_context
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import CoverageState, SemanticInventoryStatus
from affordance_runtime.world.action_space import ActionSpaceBuilder


def test_structural_projection_is_bounded_truthful_and_private() -> None:
    raw = raw_observation(
        ax_node("private-1", "button", "okay"),
        ax_node("private-2", "textbox", "", properties=(("required", False),)),
        ax_node("private-3", "combobox", "", value="A", properties=(("expanded", False),)),
        ax_node("private-4", "option", "A"),
        ax_node("private-5", "option", "B"),
    )
    snapshot = BrowserGymVerifierSnapshot(
        "run:opaque", "obs:1", "obs:1", VerifierFactSource.RESET,
        ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING,
    )
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
    inventory = projected.world.sources[0].semantic_inventory
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (
        inventory.recognized_target_count,
        inventory.projected_target_count,
        inventory.actionable_target_count,
        inventory.non_executable_target_count,
        inventory.omitted_target_count,
        inventory.informational_target_count,
    ) == (3, 3, 3, 0, 0, 0)


def test_recognized_omission_adds_no_target_binding_action_or_coverage_change() -> None:
    baseline_raw = raw_observation(ax_node("button", "button", "Save"))
    omitted_raw = copy.deepcopy(baseline_raw)
    omitted_raw["axtree_object"]["nodes"].append(ax_node("check", "checkbox", "Remember"))
    baseline = _project(baseline_raw)
    omitted = _project(omitted_raw)

    assert omitted.world.targets == baseline.world.targets
    assert omitted.world.facts == baseline.world.facts
    assert omitted.world.bindings == baseline.world.bindings
    assert omitted.private_bindings == baseline.private_bindings
    assert omitted.world.coverage == baseline.world.coverage == {"browsergym": CoverageState.COMPLETE}
    task = TaskGoal("task:inventory", "Save", allowed_effects=("external_ui_interaction",))
    assert ActionSpaceBuilder().build(task, omitted.world) == ActionSpaceBuilder().build(task, baseline.world)
    inventory = omitted.world.sources[0].semantic_inventory
    assert inventory.status is SemanticInventoryStatus.PARTIAL
    assert (inventory.recognized_target_count, inventory.projected_target_count) == (2, 1)


def test_complete_projection_can_have_empty_profile_relative_inventory() -> None:
    projected = _project(raw_observation(ax_node("static", "StaticText", "Information")))
    inventory = projected.world.sources[0].semantic_inventory
    assert projected.world.coverage["browsergym"] is CoverageState.COMPLETE
    assert inventory.status is SemanticInventoryStatus.EMPTY
    assert inventory.recognized_target_count == 0
    assert projected.world.targets == projected.world.bindings == ()


def test_projected_non_executable_and_quota_omission_are_distinct(monkeypatch) -> None:
    disabled = raw_observation(ax_node("disabled", "button", "Disabled"))
    disabled[PRIVATE_CONTROL_PROPERTIES_KEY]["disabled"]["enabled"] = False
    disabled_projection = _project(disabled)
    disabled_inventory = disabled_projection.world.sources[0].semantic_inventory
    assert disabled_inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (disabled_inventory.projected_target_count, disabled_inventory.non_executable_target_count) == (1, 1)
    assert disabled_inventory.actionable_target_count == 0

    many_options = raw_observation(
        ax_node("select", "combobox", "Choice"),
        *(ax_node(f"option-{index}", "option", f"Choice {index}") for index in range(17)),
    )
    select_projection = _project(many_options)
    select_inventory = select_projection.world.sources[0].semantic_inventory
    assert select_inventory.status is SemanticInventoryStatus.REPRESENTED
    assert select_inventory.non_executable_target_count == 1
    assert not select_projection.world.bindings

    monkeypatch.setattr(projection_module, "MAX_TARGETS", 1)
    truncated = _project(raw_observation(
        ax_node("one", "button", "One"),
        ax_node("two", "button", "Two"),
        ax_node("radio", "radio", "Three"),
    ))
    truncated_inventory = truncated.world.sources[0].semantic_inventory
    assert truncated.world.coverage["browsergym"] is CoverageState.TRUNCATED
    assert truncated_inventory.status is SemanticInventoryStatus.PARTIAL
    assert (
        truncated_inventory.recognized_target_count,
        truncated_inventory.projected_target_count,
        truncated_inventory.omitted_target_count,
    ) == (3, 1, 2)


def test_fact_only_truncation_does_not_change_target_inventory(monkeypatch) -> None:
    monkeypatch.setattr(projection_module, "MAX_FACTS", 0)
    projected = _project(raw_observation(
        ax_node("field", "textbox", "Name", value="Ada", properties=(("required", True),)),
    ))
    inventory = projected.world.sources[0].semantic_inventory
    assert projected.world.coverage["browsergym"] is CoverageState.TRUNCATED
    assert inventory.status is SemanticInventoryStatus.REPRESENTED
    assert (inventory.recognized_target_count, inventory.projected_target_count) == (1, 1)


def test_private_handles_and_benchmark_identity_are_absent_from_agent_context() -> None:
    raw = raw_observation(ax_node("private-1", "button", "okay"))
    snapshot = BrowserGymVerifierSnapshot(
        "run:opaque", "obs:1", "obs:1", VerifierFactSource.RESET,
        ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING,
    )
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
    source_wire = json.loads(serialized)["world"]["sources"][0]
    assert source_wire["projection_coverage"] == "complete"
    assert "coverage" not in source_wire
    assert source_wire["semantic_inventory"]["status"] == "represented"


def _project(raw):
    snapshot = BrowserGymVerifierSnapshot(
        "run:opaque", "obs:1", "obs:1", VerifierFactSource.RESET,
        ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING,
    )
    return project_browsergym_observation(
        raw,
        observation_id="obs:1",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        verifier=snapshot,
    )
