from dataclasses import replace

from affordance_runtime.actions import ActionOption, ActionRisk, ActionSpace
from affordance_runtime.agent.context.budgets import ContextProjectionBudget, serialized_size
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.world_projection import project_model_world
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationConflict,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.world import fused_world


def _evaluation(task: TaskGoal, observation_id: str) -> TaskEvaluation:
    return TaskEvaluation(
        task.task_id,
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )


def test_model_world_projection_is_bounded_and_route_free() -> None:
    observation = fused_world(
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
        surface="dom",
    )
    observation = replace(
        observation,
        conflicts=(ObservationConflict("conflict:private", "target:0", "ready", "sources disagree"),),
    )

    view = project_model_world(
        observation,
        ContextProjectionBudget(max_targets=2, max_facts=3, max_facts_per_target=2),
    )

    assert len(view.targets.items) == 2 and view.targets.truncated
    assert len(view.facts.items) == 2 and view.facts.truncated
    representation = repr(view)
    for private in ("world:private-observation", "source:private", "selector", "#private", "conflict:private"):
        assert private not in representation


def test_task_view_contains_only_evaluator_supported_facts() -> None:
    observation = fused_world(
        "world:progress",
        (SemanticTarget("target:1", "status", "Status"),),
        (
            StateFact("fact:weak", "target:1", "weak", True, "source:1"),
            StateFact("fact:verified", "target:1", "verified", True, "source:1"),
        ),
        surface="dom",
    )
    task = TaskGoal(
        "progress",
        "Inspect verified state",
        success_criteria=({
            "id": "criterion:verified",
            "kind": "fact_equals",
            "subject_id": "target:1",
            "predicate": "verified",
            "expected_value": True,
        },),
    )
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.COMPLETE,
        "validated",
        criteria=(CriterionEvaluation(
            "criterion:verified",
            CriterionEvaluationStatus.SATISFIED,
            ("fact:verified",),
            "supported",
        ),),
        completion_evidence_refs=("fact:verified",),
    )

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    verified_facts = context.task.evaluation.verified_public_facts
    assert tuple(item.fact_ref for item in verified_facts) == ("F1",)
    assert tuple(item.subject_id for item in verified_facts) == ("E1",)
    verified = verified_facts[0]
    matching = tuple(
        fact
        for document in context.actor_world.documents
        for root in document.roots
        for fact in root.facts
        if fact.field == "verified"
    )
    assert matching[0].evidence_ref == verified.fact_ref
    assert not hasattr(context, "budgets")


def test_model_artifact_is_resolvable_without_exposing_its_private_value() -> None:
    source = SurfaceObservation(
        "surface:artifact",
        "visual",
        "revision:1",
        ObservationSourceProfile.visual(),
        artifacts={"receipt": {"path": "/private/receipt.pdf", "credential": "secret"}},
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    observation = fused.observation
    task = TaskGoal("artifact", "Inspect receipt")

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )

    artifact = context.actor_world.artifacts[0]
    assert artifact["evidence_ref"] == "A1"
    assert artifact["kind"] == "receipt"
    assert "/private/receipt.pdf" not in repr(context)
    assert "secret" not in repr(context)


def test_complete_context_respects_one_total_byte_budget() -> None:
    observation = fused_world(
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
        surface="dom",
    )
    task = TaskGoal("bounded", "Inspect the bounded context")
    budget = ContextProjectionBudget(max_total_serialized_bytes=8 * 1024)

    context = ContextBuilder(budget).build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )

    assert serialized_size(context) <= budget.max_total_serialized_bytes
    assert context.actor_world.traversal is not None
    assert context.actor_world.traversal.status != "complete"


def test_action_page_reports_runtime_membership_and_truncation_truthfully() -> None:
    observation = fused_world(
        "world:actions",
        (SemanticTarget("target:0", "form", "Target"),),
        surface="dom",
    )
    options = tuple(
        ActionOption(
            f"action:{index}",
            observation.observation_id,
            "read",
            "target:0",
            "observation",
            {"type": "object", "properties": {}, "additionalProperties": False},
            "schema:read",
            (f"binding:{index}",),
            f"read target {index}",
            (),
            ActionRisk.LOW,
        )
        for index in range(5)
    )
    task = TaskGoal("bounded-actions", "Inspect actions")
    budget = ContextProjectionBudget(max_action_options=2)

    context = ContextBuilder(budget).build(
        task,
        observation,
        ActionSpace(observation.observation_id, options),
        _evaluation(task, observation.observation_id),
    )

    assert len(context.actions.options) == 2
    assert context.actions.total_count == 5
    assert context.actions.truncated and context.actions.has_more


def test_recent_steps_keep_only_the_latest_eight_mechanically() -> None:
    observation = fused_world("world:history", surface="dom")
    task = TaskGoal("history", "Inspect recent steps")
    steps = tuple(
        AgentTurnView("abort", reason=f"step:{index}")
        for index in range(10)
    )

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
        steps,
    )

    assert context.recent_steps.total_count == 10
    assert context.recent_steps.truncated
    assert tuple(item.reason for item in context.recent_steps.items) == tuple(
        f"step:{index}" for index in range(2, 10)
    )
