from dataclasses import replace

import pytest

from affordance_runtime.agent import Abort
from affordance_runtime.agent.state import AgentLoopState, Turn
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.model_boundary.budgets import ContextProjectionBudget, serialized_size
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.model_boundary.world_projection import project_model_world
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ActionOption,
    ActionRisk,
    ActionSpace,
    ActionSpaceBuilder,
    CoverageState,
    ObservationConflict,
    SemanticTarget,
    StateFact,
    WorldObservation,
)


def test_model_world_projection_is_bounded_and_route_free() -> None:
    observation = WorldObservation(
        "world:private-observation",
        tuple(
            SemanticTarget(
                f"target:{index}",
                "button",
                "label " + "x" * 500,
                {**{f"field:{item}": "v" * 300 for item in range(12)}, "selector": "#private"},
                {f"relation:{item}": f"target:{item}" for item in range(12)},
            )
            for index in range(5)
        ),
        tuple(StateFact(f"fact:{index}", "target:0", "ready", True, "source:private") for index in range(9)),
        (),
        {"dom": CoverageState.COMPLETE},
        (ObservationConflict("conflict:private", "target:0", "ready", "sources disagree"),),
    )
    budget = ContextProjectionBudget(max_targets=2, max_facts=3, max_facts_per_target=2)

    view = project_model_world(observation, budget)

    assert len(view.targets.items) == 2 and view.targets.truncated
    assert len(view.facts.items) == 2 and view.facts.truncated
    assert len(view.targets.items[0].state) <= 8
    assert len(view.targets.items[0].relations) <= 8
    representation = repr(view)
    for private in ("world:private-observation", "source:private", "selector", "#private", "conflict:private"):
        assert private not in representation


def test_progress_verified_facts_require_evaluation_evidence() -> None:
    observation = WorldObservation(
        "world:progress",
        (SemanticTarget("target:1", "status", "Status"),),
        (
            StateFact("fact:weak", "target:1", "weak", True, "source:1"),
            StateFact("fact:verified", "target:1", "verified", True, "source:1"),
        ),
        (),
        {"dom": CoverageState.COMPLETE},
    )
    criterion = {"criterion_id": "criterion:verified", "target_id": "target:1"}
    task = TaskGoal("progress", "Inspect verified state", success_criteria=(criterion,))
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.COMPLETE,
        "validated",
        criteria=(
            CriterionEvaluation(
                "criterion:verified",
                CriterionEvaluationStatus.SATISFIED,
                ("fact:verified",),
                "supported",
            ),
        ),
        completion_evidence_refs=("fact:verified",),
    )

    context = ContextBuilder().build(
        task,
        AgentLoopState(observation),
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    assert tuple(item.fact_ref for item in context.progress.verified_public_facts) == ("fact:verified",)
    assert context.budgets.remaining_wait_ms == 120_000


def test_target_state_filters_private_fields_before_applying_public_limit() -> None:
    private = {f"selector_{index}": f"#{index}" for index in range(8)}
    public = {"api_token_enabled": True, "public_after_private": "visible"}
    observation = WorldObservation(
        "world:filter-order",
        (SemanticTarget("target:1", "region", "Target", {**private, **public}),),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )

    target = project_model_world(observation, ContextProjectionBudget()).targets.items[0]

    assert target.state["api_token_enabled"] is True
    assert target.state["public_after_private"] == "visible"
    assert target.state_total_count == 2
    assert not target.state_truncated


def test_complete_agent_context_respects_total_serialized_byte_budget() -> None:
    observation = WorldObservation(
        "world:bounded",
        tuple(
            SemanticTarget(
                f"target:{index}",
                "region",
                "x" * 240,
                {f"field:{item}": "v" * 240 for item in range(8)},
                {f"relation:{item}": "r" * 240 for item in range(8)},
            )
            for index in range(64)
        ),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )
    task = TaskGoal("bounded", "Inspect the bounded context")
    state = AgentLoopState(observation)
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )
    budget = ContextProjectionBudget(max_total_serialized_bytes=8 * 1024)

    context = ContextBuilder(budget).build(
        task,
        state,
        ActionSpaceBuilder().build(task, observation),
        evaluation,
    )

    assert serialized_size(context) <= budget.max_total_serialized_bytes
    assert context.world.targets.truncated
    assert context.budgets.section_truncation["targets"]


def test_action_options_share_the_total_context_byte_budget_truthfully() -> None:
    observation = WorldObservation(
        "world:actions",
        (SemanticTarget("target:0", "form", "Target"),),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )
    schema = {
        "type": "object",
        "properties": {
            f"field_{index}": {"type": "string", "description": "x" * 240}
            for index in range(12)
        },
        "additionalProperties": False,
    }
    options = tuple(
        ActionOption(
            f"action:{index}",
            observation.observation_id,
            "activate",
            "target:0",
            "local_reversible",
            schema,
            "schema:large",
            (f"binding:{index}",),
            "activate target",
            ("changed",),
            ActionRisk.LOW,
        )
        for index in range(32)
    )
    task = TaskGoal("bounded-actions", "Inspect actions")
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )

    context = ContextBuilder().build(task, AgentLoopState(observation), ActionSpace("world:actions", options), evaluation)

    assert serialized_size(context) <= ContextProjectionBudget().max_total_serialized_bytes
    assert context.actions.truncated
    assert context.actions.total_count == 32


def test_context_budget_limits_actions_and_destinations_truthfully() -> None:
    targets = tuple(SemanticTarget(f"target:{index}", "option", f"Target {index}") for index in range(8))
    observation = WorldObservation("world:budget", targets, (), (), {"dom": CoverageState.COMPLETE})
    options = tuple(
        ActionOption(
            f"action:{index}",
            observation.observation_id,
            "send",
            "target:0",
            "external",
            {"type": "object", "properties": {}, "additionalProperties": False},
            "schema:1",
            (f"binding:{index}",),
            f"send {index}",
            ("sent",),
            ActionRisk.LOW,
            True,
            tuple(item.target_id for item in targets[1:]),
        )
        for index in range(5)
    )
    task = TaskGoal("budget", "Inspect budgeted actions")
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )
    budget = ContextProjectionBudget(max_action_options=2, max_destinations_per_option=3)

    context = ContextBuilder(budget).build(
        task,
        AgentLoopState(observation),
        ActionSpace(observation.observation_id, options),
        evaluation,
    )

    assert len(context.actions.options) == 2
    assert context.actions.total_count == 5
    assert context.actions.has_more and context.actions.next_cursor
    destinations = context.actions.options[0].destinations
    assert len(destinations.items) == 3
    assert destinations.total_count == 7 and destinations.truncated


def test_malformed_schema_is_rejected_before_action_page_projection() -> None:
    observation = WorldObservation(
        "world:schema-page",
        (SemanticTarget("target:0", "button", "Target"),),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )
    valid = ActionOption(
        "action:valid",
        observation.observation_id,
        "read",
        "target:0",
        "observation",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:valid",
        ("binding:valid",),
        "valid",
    )
    with pytest.raises(ValueError, match="unsupported schema type"):
        replace(valid, action_id="action:hidden", parameter_schema={"type": "array"})


def test_current_page_targets_are_pinned_into_bounded_model_world() -> None:
    targets = tuple(SemanticTarget(f"target:{index}", "button", f"Target {index}") for index in range(5))
    observation = WorldObservation("world:pinned", targets, (), (), {"dom": CoverageState.COMPLETE})
    option = ActionOption(
        "action:pinned",
        observation.observation_id,
        "read",
        "target:4",
        "observation",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:1",
        ("binding:pinned",),
        "read pinned target",
    )
    task = TaskGoal("pinned", "Inspect pinned target")
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )

    context = ContextBuilder(ContextProjectionBudget(max_targets=1)).build(
        task,
        AgentLoopState(observation),
        ActionSpace(observation.observation_id, (option,)),
        evaluation,
    )

    assert context.actions.options[0].target_id == "target:4"
    assert tuple(item.target_id for item in context.world.targets.items) == ("target:4",)


def test_history_bound_keeps_newest_semantic_turns() -> None:
    observation = WorldObservation("world:history", (), (), (), {"dom": CoverageState.COMPLETE})
    task = TaskGoal("history", "Keep newest history")
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )
    state = AgentLoopState(
        observation,
        recent_turns=tuple(
            Turn(observation.observation_id, Abort("context:1", reason, "policy"))
            for reason in ("oldest", "middle", "newest")
        ),
    )

    context = ContextBuilder(ContextProjectionBudget(max_history_turns=2)).build(
        task,
        state,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    assert tuple(item.semantic_summary["reason"] for item in context.history.items) == (
        "middle",
        "newest",
    )
    assert context.history.total_count == 3 and context.history.truncated


def test_total_byte_compaction_drops_oldest_history_before_newest() -> None:
    observation = WorldObservation("world:history-bytes", (), (), (), {"dom": CoverageState.COMPLETE})
    task = TaskGoal("history-bytes", "Keep the newest turn during byte compaction")
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )
    reasons = tuple(f"turn-{index}-" + "x" * 400 for index in range(6))
    state = AgentLoopState(
        observation,
        recent_turns=tuple(
            Turn(observation.observation_id, Abort("context:1", reason, "policy"))
            for reason in reasons
        ),
    )
    budget = ContextProjectionBudget(max_history_turns=6, max_total_serialized_bytes=3_000)

    context = ContextBuilder(budget).build(
        task,
        state,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    assert context.history.truncated
    assert context.history.items[-1].semantic_summary["reason"] == reasons[-1]
