from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary.budgets import ContextProjectionBudget, serialized_size
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.model_boundary.world_projection import project_model_world
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
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
