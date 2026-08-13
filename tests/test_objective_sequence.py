from __future__ import annotations

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.evaluation import ActionEvaluationStatus, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary import ContextBuilder
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.local_objective import establish_local_objective, refresh_local_objective
from affordance_runtime.task.objective_sequence import (
    EntitySelector,
    ObjectiveSequence,
    ObjectiveStep,
    SequenceDisposition,
    establish_objective_sequence_state,
    refresh_objective_sequence_state,
    sequence_allowed_action_ids,
)
from affordance_runtime.task.set_objective import (
    ActionTemplate,
    FactEquals,
    ScopeEntityDomain,
    VisualConcept,
)
from affordance_runtime.world import (
    ActionBinding,
    ActionSpaceBuilder,
    CoverageState,
    SemanticTarget,
    WorldObservation,
)
from affordance_runtime.world.binder import ActionBinder


def _world(epoch: str, *labels: str) -> WorldObservation:
    targets = tuple(SemanticTarget(f"entity:{index}:{label}", "button", label) for index, label in enumerate(labels))
    bindings = tuple(
        ActionBinding(
            f"binding:{epoch}:{target.target_id}",
            epoch,
            epoch,
            f"revision:{epoch}",
            f"fingerprint:{epoch}:{target.target_id}",
            target.target_id,
            target.target_id,
            "dom",
            "dom",
            "activate",
            "click",
            "local_reversible",
            ("ui_activated",),
            {"type": "object", "properties": {}, "additionalProperties": False},
            {"selector": f"#{label}"},
        )
        for target, label in zip(targets, labels, strict=True)
    )
    return WorldObservation(epoch, targets, (), bindings, {"dom": CoverageState.COMPLETE})


def _sequence() -> ObjectiveSequence:
    zero = EntitySelector(FactEquals("identity.label", "0"))
    return ObjectiveSequence(
        "sequence:pie",
        (
            ObjectiveStep(
                "expand",
                EntitySelector(FactEquals("identity.label", "+")),
                ActionTemplate("activate"),
                zero,
            ),
            ObjectiveStep("select", zero, ActionTemplate("activate")),
        ),
    )


def _space(world: WorldObservation):
    task = TaskGoal(
        "task:sequence",
        "Activate plus and then zero",
        allowed_effects=("ui_activated",),
        risk_profile=RiskProfile.LOW,
    )
    return ActionSpaceBuilder().build(task, world)


def test_future_selector_resolves_new_identity_after_fresh_observation() -> None:
    before = _world("observation:before", "+")
    state = establish_objective_sequence_state(_sequence(), before)

    assert state.disposition is SequenceDisposition.READY
    assert state.resolved_target_id == "entity:0:+"
    assert len(sequence_allowed_action_ids(state, _space(before))) == 1

    after = _world("observation:after", "0")
    state = refresh_objective_sequence_state(
        state,
        after,
        acted_entity_id="entity:0:+",
        action_status=ActionEvaluationStatus.EFFECT_CONFIRMED,
        effect_evidence_refs=("evaluation:expand",),
    )

    assert state.active_index == 1
    assert state.disposition is SequenceDisposition.READY
    assert state.resolved_target_id == "entity:0:0"
    current_space = _space(after)
    allowed = sequence_allowed_action_ids(state, current_space)
    assert len(allowed) == 1
    option = next(item for item in current_space.options if item.action_id in allowed)
    selection = ActionSpaceBuilder().admit(option, {})
    bound = ActionBinder().bind(selection, after, "context:fresh")
    assert bound.binding.source_observation_id == "observation:after"
    assert bound.binding.binding_id.startswith("binding:observation:after:")


def test_selector_ambiguity_and_absence_fail_closed() -> None:
    ambiguous = establish_objective_sequence_state(_sequence(), _world("observation:ambiguous", "+", "+"))
    missing = establish_objective_sequence_state(_sequence(), _world("observation:missing", "other"))

    assert ambiguous.disposition is SequenceDisposition.AMBIGUOUS
    assert not sequence_allowed_action_ids(ambiguous, _space(_world("observation:ambiguous", "+", "+")))
    assert missing.disposition is SequenceDisposition.BLOCKED


def test_sequence_never_advances_on_unknown_effect() -> None:
    before = _world("observation:before", "+")
    state = establish_objective_sequence_state(_sequence(), before)
    after = _world("observation:after", "0")

    state = refresh_objective_sequence_state(
        state,
        after,
        acted_entity_id="entity:0:+",
        action_status=ActionEvaluationStatus.UNKNOWN,
    )

    assert state.active_index == 0
    assert state.disposition is SequenceDisposition.BLOCKED
    assert state.reason_code == "sequence_effect_unknown"


def test_visual_sequence_selector_enters_the_shared_scope_evidence_lifecycle() -> None:
    sequence = ObjectiveSequence(
        "sequence:visual",
        (
            ObjectiveStep(
                "visual-future-step",
                EntitySelector(
                    VisualConcept("held-out fruit"),
                    ScopeEntityDomain.ALL_VISIBLE,
                ),
                ActionTemplate("activate"),
            ),
        ),
    )

    state = establish_objective_sequence_state(
        sequence,
        _world("observation:visual", "candidate"),
    )

    assert state.disposition is SequenceDisposition.NEED_EVIDENCE
    assert state.selector_resolution is not None
    assert state.selector_resolution.scope.entity_domain.value == "all_visible"


def test_visual_selector_can_classify_a_structurally_closed_domain() -> None:
    sequence = ObjectiveSequence(
        "sequence:visual-over-dom",
        (
            ObjectiveStep(
                "visual-dom-step",
                EntitySelector(VisualConcept("held-out fruit"), ScopeEntityDomain.STRUCTURED),
                ActionTemplate("activate"),
            ),
        ),
    )

    state = establish_objective_sequence_state(
        sequence,
        _world("observation:visual-dom", "candidate"),
    )

    assert state.disposition is SequenceDisposition.NEED_EVIDENCE
    assert state.selector_resolution is not None
    assert state.selector_resolution.universe.coverage.value == "complete"
    assert state.selector_resolution.scope.entity_domain is ScopeEntityDomain.STRUCTURED


def test_local_objective_facade_projects_only_currently_resolved_action() -> None:
    before = _world("observation:before", "+", "distractor")
    task = TaskGoal(
        "task:sequence-projection",
        "Activate plus and then zero",
        allowed_effects=("ui_activated",),
        risk_profile=RiskProfile.LOW,
    )
    state = AgentLoopState(before)
    state.local_objective_state = establish_local_objective(
        _sequence(),
        before,
        enumerator=state.scope_enumerator,
    )
    before_space = ActionSpaceBuilder().build(task, before)
    before_page = ContextBuilder().page(before_space, state)

    assert len(before_page.visible_action_ids) == 1
    assert before_space.find(before_page.visible_action_ids[0]).target_id == "entity:0:+"

    after = _world("observation:after", "distractor", "0")
    state.current_observation = after
    state.local_objective_state = refresh_local_objective(
        state.local_objective_state,
        after,
        acted_entity_id="entity:0:+",
        semantic_action="activate",
        action_status=ActionEvaluationStatus.EFFECT_CONFIRMED,
        effect_evidence_refs=("evaluation:expand",),
        enumerator=state.scope_enumerator,
    )
    after_space = ActionSpaceBuilder().build(task, after)
    after_page = ContextBuilder().page(after_space, state)

    assert len(after_page.visible_action_ids) == 1
    option = after_space.find(after_page.visible_action_ids[0])
    assert option is not None and option.target_id == "entity:1:0"


def test_agent_context_marks_open_local_objective_without_projecting_future_identity() -> None:
    before = _world("observation:before", "+")
    task = TaskGoal(
        "task:sequence-context",
        "Activate plus and then zero",
        allowed_effects=("ui_activated",),
        risk_profile=RiskProfile.LOW,
    )
    state = AgentLoopState(before)
    state.local_objective_state = establish_local_objective(
        _sequence(),
        before,
        enumerator=state.scope_enumerator,
    )
    context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, before),
        TaskEvaluation(
            task.task_id,
            before.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    assert context.progress.local_objective_open
    assert "entity:0:0" not in repr(context)
