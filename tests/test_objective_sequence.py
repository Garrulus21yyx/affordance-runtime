from __future__ import annotations

from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.objective_sequence import (
    EntitySelector,
    ObjectiveSequence,
    ObjectiveStep,
    SequenceDisposition,
    establish_objective_sequence_state,
    refresh_objective_sequence_state,
    sequence_allowed_action_ids,
)
from affordance_runtime.task.set_objective import ActionTemplate, FactEquals, VisualConcept
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
                EntitySelector(VisualConcept("held-out fruit")),
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
