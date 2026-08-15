from dataclasses import asdict, replace

import pytest

from affordance_runtime.actions import (
    ActionOption,
    ActionRisk,
    ActionSpace,
    ActionSpaceBuilder,
)
from affordance_runtime.agent import Wait
from affordance_runtime.agent.control_transition import ControlTransitionScope
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.model.context.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.model.context.context_builder import ContextBuilder
from affordance_runtime.model.context.world_projection import project_model_world
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationConflict,
    ObservationSourceProfile,
    SemanticInventorySummary,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def test_source_inventory_projection_is_one_way_wire_truth_and_budget_invariant() -> None:
    targets = (
        SemanticTarget("target:inventory:1", "button", "Disabled one"),
        SemanticTarget("target:inventory:2", "button", "Disabled two"),
    )
    inventory = SemanticInventorySummary.assessed(
        "fixture-profile.v1",
        recognized_target_count=3,
        projected_target_count=2,
        actionable_target_count=0,
        non_executable_target_count=2,
        omitted_target_count=1,
        informational_target_count=0,
    )
    source = SurfaceObservation(
        "source:inventory",
        "dom",
        "revision:inventory",
        ObservationSourceProfile.dom(),
        targets=targets,
        coverage=CoverageState.COMPLETE,
        semantic_inventory=inventory,
    )
    observation = WorldObservation(
        "world:inventory",
        targets,
        (),
        (),
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )

    full = project_model_world(observation, ContextProjectionBudget(max_targets=2))
    clipped = project_model_world(observation, ContextProjectionBudget(max_targets=1))

    assert full.sources == clipped.sources
    summary = full.sources[0]
    assert summary.projection_coverage == "complete"
    assert summary.coverage == "complete"
    assert summary.semantic_inventory.profile_id == "fixture-profile.v1"
    assert summary.semantic_inventory.status == "partial"
    assert summary.semantic_inventory.recognized_target_count == 3
    wire = asdict(summary)
    assert "projection_coverage" in wire
    assert "coverage" not in wire
    assert "semantic_inventory" in wire


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


def test_model_artifact_view_exposes_resolvable_identity_but_not_private_value() -> None:
    source = SurfaceObservation(
        "surface:artifact",
        "visual",
        "revision:1",
        ObservationSourceProfile.visual(),
        artifacts={"receipt": {"path": "/private/receipt.pdf", "credential": "secret"}},
    )
    observation = WorldObservation(
        "world:artifact",
        (),
        (),
        (),
        {"visual": CoverageState.COMPLETE},
        sources=(source,),
    )
    task = TaskGoal("artifact", "Inspect receipt")
    evaluation = TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.INCOMPLETE, "pending")

    context = ContextBuilder().build(
        task,
        AgentLoopState(observation),
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    artifact = context.world.artifact_summaries.items[0]
    assert artifact.evidence_ref == "artifact:surface:artifact:receipt"
    assert WorldEvidenceIndex.from_observation(observation).resolve(artifact.evidence_ref)
    assert artifact.kind == "receipt"
    assert "/private/receipt.pdf" not in repr(context)
    assert "secret" not in repr(context)


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
        "properties": {"text": {"type": "string", "description": "x" * 240}},
        "required": ["text"],
        "additionalProperties": False,
    }
    options = tuple(
        ActionOption(
            f"action:{index}",
            observation.observation_id,
            "type_text",
            "target:0",
            "local_reversible",
            schema,
            "schema:large",
            (f"binding:{index}",),
            "type target " + "x" * 3_000,
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
                "drag_to",
            "target:0",
            "external",
            {"type": "object", "properties": {}, "additionalProperties": False},
            "schema:1",
            (f"binding:{index}",),
                f"drag {index}",
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
    with pytest.raises(ValueError, match="schema_contract_mismatch"):
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
    state = AgentLoopState(observation)
    _append_abort_transitions(state, ("oldest", "middle", "newest"))

    context = ContextBuilder(ContextProjectionBudget(max_history_turns=2)).build(
        task,
        state,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    assert tuple(item.semantic_summary["reason"] for item in context.history.items) == (
        "oldest",
        "middle",
    )
    assert context.last_transition is not None
    assert context.last_transition.previous_decision.details["reason"] == "newest"
    assert context.history.total_count == 2 and not context.history.truncated


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
    state = AgentLoopState(observation)
    _append_abort_transitions(state, reasons)
    unbounded = ContextBuilder(ContextProjectionBudget(max_history_turns=6)).build(
        task,
        state,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )
    newest_only = replace(
        unbounded,
        history=BoundedSection((unbounded.history.items[-1],), unbounded.history.total_count, True),
    )
    budget = ContextProjectionBudget(
        max_history_turns=6,
        max_total_serialized_bytes=serialized_size(newest_only),
    )

    context = ContextBuilder(budget).build(
        task,
        state,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    assert context.history.truncated
    assert context.history.items[-1].semantic_summary["reason"] == reasons[-2]
    assert context.last_transition is not None
    assert context.last_transition.previous_decision.details["reason"] == reasons[-1][:239] + "…"


def _append_abort_transitions(state: AgentLoopState, reasons: tuple[str, ...]) -> None:
    for reason in reasons:
        decision = Wait("context:1", reason, 1)
        scope = ControlTransitionScope(state, decision)
        scope.set_reason("history_recorded")
        scope.finalize(state, None)
