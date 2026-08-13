from __future__ import annotations

from affordance_runtime.agent import AgentLoopState
from affordance_runtime.evaluation import ActionEvaluationStatus, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary import ContextBuilder
from affordance_runtime.task import (
    FactEquals,
    PredicateTruth,
    RiskProfile,
    SetDisposition,
    SetEvidenceNeedKind,
    SetObjectiveStateError,
    SetObjectiveStateErrorCode,
    SetQuantifier,
    TaskGoal,
    VisualConcept,
)
from affordance_runtime.task.set_objective_state import (
    establish_set_objective_state,
    install_semantic_assessments,
    refresh_set_objective_state,
    set_allowed_action_ids,
    set_evidence_obligations,
)
from affordance_runtime.world import (
    ActionOption,
    ActionRisk,
    ActionSpace,
    CoverageState,
    SemanticTarget,
    WorldObservation,
)


def _world(epoch: int, values: tuple[str | None, ...]) -> WorldObservation:
    return WorldObservation(
        f"observation:{epoch}",
        tuple(
            SemanticTarget(
                f"entity:{index}",
                "clickable",
                "",
                {} if value is None else {"kind": value},
            )
            for index, value in enumerate(values)
        ),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )


def _space(world: WorldObservation) -> ActionSpace:
    return ActionSpace(
        world.observation_id,
        tuple(
            ActionOption(
                f"action:{index}:{world.observation_id}",
                world.observation_id,
                "activate",
                target.target_id,
                "interaction",
                {"type": "object", "properties": {}, "additionalProperties": False},
                f"schema:{index}",
                (f"binding:{index}",),
                "activate target",
                risk=ActionRisk.LOW,
            )
            for index, target in enumerate(world.targets)
        ),
    )


def test_set_state_persists_more_than_recent_history_and_predicate_flip() -> None:
    initial = _world(1, tuple("blue" if index < 13 else "red" for index in range(20)))
    state = establish_set_objective_state(
        predicate=FactEquals("kind", "blue"),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in initial.targets),
        observation=initial,
    )

    assert len(state.obligations) == 13
    assert state.reduction.disposition is SetDisposition.READY_FOR_NEXT_MEMBER
    first = state.reduction.next_entity_id

    changed = _world(2, tuple("red" if index == 0 or index >= 13 else "blue" for index in range(20)))
    advanced = refresh_set_objective_state(
        state,
        changed,
        acted_entity_id=first,
        action_status=ActionEvaluationStatus.EFFECT_CONFIRMED,
        effect_evidence_refs=("evidence:item-effect",),
    )

    persisted = next(item for item in advanced.obligations if item.entity_id == first)
    assert persisted.membership_status.value == "false"
    assert persisted.action_status.value == "effect_confirmed"
    assert len(advanced.obligations) == 13


def test_missing_candidate_fact_is_unknown_not_removed_from_universe() -> None:
    world = _world(1, ("blue", None, "red"))
    state = establish_set_objective_state(
        predicate=FactEquals("kind", "blue"),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in world.targets),
        observation=world,
    )

    assert state.universe.entity_ids == tuple(item.target_id for item in world.targets)
    assert state.reduction.disposition is SetDisposition.NEED_UNKNOWN_RESOLUTION


def test_zero_match_requires_fresh_stability_before_certificate() -> None:
    initial = _world(1, ("red", "red"))
    state = establish_set_objective_state(
        predicate=FactEquals("kind", "blue"),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in initial.targets),
        observation=initial,
    )
    assert state.reduction.disposition is SetDisposition.NEED_STABILITY_CHECK

    stable = refresh_set_objective_state(state, _world(2, ("red", "red")))

    assert stable.reduction.disposition is SetDisposition.CERTIFIED
    assert stable.certificate is not None


def test_current_action_ids_are_rebound_from_stable_entity_membership() -> None:
    initial = _world(1, ("red", "blue", "red"))
    state = establish_set_objective_state(
        predicate=FactEquals("kind", "blue"),
        quantifier=SetQuantifier.EXACTLY_ONE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in initial.targets),
        observation=initial,
    )
    reordered = WorldObservation(
        "observation:2",
        tuple(reversed(initial.targets)),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )
    refreshed = refresh_set_objective_state(state, reordered)
    action_space = _space(reordered)

    allowed = set_allowed_action_ids(refreshed, action_space)
    selected = next(item for item in action_space.options if item.action_id in allowed)

    assert selected.target_id == "entity:1"
    assert len(allowed) == 1


def test_visual_predicate_creates_typed_evidence_obligation_then_admits_batch() -> None:
    world = _world(1, ("unknown-a", "unknown-b"))
    state = establish_set_objective_state(
        predicate=VisualConcept("arbitrary held-out concept"),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in world.targets),
        observation=world,
    )

    needs = set_evidence_obligations(state)
    assert len(needs) == 1
    assert needs[0].kind is SetEvidenceNeedKind.RESOLVE_UNKNOWN
    assert needs[0].entity_ids == state.universe.entity_ids

    classified = install_semantic_assessments(state, (
        ("entity:0", PredicateTruth.TRUE, 0.91),
        ("entity:1", PredicateTruth.FALSE, 0.87),
    ))

    assert classified.reduction.disposition is SetDisposition.READY_FOR_NEXT_MEMBER
    assert set_evidence_obligations(classified) == ()


def test_set_capacity_fails_typed_instead_of_truncating_members() -> None:
    world = _world(1, tuple("blue" for _ in range(257)))

    try:
        establish_set_objective_state(
            predicate=FactEquals("kind", "blue"),
            quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
            semantic_action="activate",
            candidate_entity_ids=tuple(item.target_id for item in world.targets),
            observation=world,
        )
    except SetObjectiveStateError as exc:
        assert exc.code is SetObjectiveStateErrorCode.SET_CAPACITY_EXCEEDED
    else:
        raise AssertionError("capacity overflow must fail closed")


def test_true_member_without_current_action_route_blocks_catalog_control() -> None:
    world = _world(1, ("red", "blue"))
    active = establish_set_objective_state(
        predicate=FactEquals("kind", "blue"),
        quantifier=SetQuantifier.EXACTLY_ONE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in world.targets),
        observation=world,
    )
    only_wrong_route = ActionSpace(world.observation_id, (_space(world).options[0],))
    loop_state = AgentLoopState(world, remaining_turns=3)
    loop_state.active_set_objective = active
    task = TaskGoal(
        "task:held-out-actionability",
        "Arbitrary semantic request",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    context = ContextBuilder().build(
        task,
        loop_state,
        only_wrong_route,
        TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    assert context.set_control is not None
    assert context.set_control.mode == "blocked"
    assert context.set_control.disposition == "need_actionability_resolution"
    assert context.set_control.allowed_action_ids == ()
    assert context.set_control.evidence_needs == ("resolve_actionability",)


def test_new_same_role_candidate_invalidates_scope_and_becomes_an_obligation() -> None:
    initial = _world(1, ("blue", "red"))
    state = establish_set_objective_state(
        predicate=FactEquals("kind", "blue"),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=tuple(item.target_id for item in initial.targets),
        observation=initial,
    )
    first = state.reduction.next_entity_id
    changed = _world(2, ("red", "red", "blue"))

    refreshed = refresh_set_objective_state(
        state,
        changed,
        acted_entity_id=first,
        action_status=ActionEvaluationStatus.EFFECT_CONFIRMED,
        effect_evidence_refs=("evidence:first",),
    )

    assert refreshed.candidate_entity_ids == ("entity:0", "entity:1", "entity:2")
    assert refreshed.reduction.disposition is SetDisposition.READY_FOR_NEXT_MEMBER
    assert refreshed.reduction.next_entity_id == "entity:2"
    assert {item.entity_id for item in refreshed.obligations} == {"entity:0", "entity:2"}
