from __future__ import annotations

from affordance_runtime.agent import AgentLoopState
from affordance_runtime.evaluation import ActionEvaluationStatus, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model_boundary import ContextBuilder
from affordance_runtime.task import (
    And,
    FactEquals,
    PredicateTruth,
    RiskProfile,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
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
    install_visual_leaf_assessments,
    refresh_set_objective_state,
    set_allowed_action_ids,
    set_evidence_obligations,
)
from affordance_runtime.world import (
    ActionBinding,
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


def _binding(world_id: str, target_id: str) -> ActionBinding:
    return ActionBinding(
        f"binding:{target_id}",
        world_id,
        world_id,
        f"revision:{world_id}",
        f"fingerprint:{target_id}",
        target_id,
        target_id,
        "dom",
        "dom",
        "activate",
        "click",
        "local_reversible",
        ("ui_activated",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"selector": f"#{target_id}"},
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


def test_action_member_domain_excludes_informational_scope_entities() -> None:
    world_id = "observation:action-domain"
    actionable = (
        SemanticTarget("entity:grid-a", "clickable", "", {"grid_coordinate": {"x": 0, "y": 0}}),
        SemanticTarget("entity:grid-b", "clickable", "", {"grid_coordinate": {"x": 1, "y": -2}}),
    )
    label = SemanticTarget("entity:axis-label", "generic", "-2")
    world = WorldObservation(
        world_id,
        (*actionable, label),
        (),
        tuple(_binding(world_id, target.target_id) for target in actionable),
        {"dom": CoverageState.COMPLETE},
    )

    state = establish_set_objective_state(
        predicate=FactEquals("grid_coordinate", {"x": 1, "y": -2}),
        quantifier=SetQuantifier.EXACTLY_ONE,
        semantic_action="activate",
        candidate_entity_ids=tuple(target.target_id for target in world.targets),
        observation=world,
    )

    assert state.universe.entity_ids == ("entity:grid-a", "entity:grid-b")
    assert state.reduction.disposition is SetDisposition.READY_FOR_NEXT_MEMBER
    assert state.reduction.next_entity_id == "entity:grid-b"


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


def test_empty_closed_action_domain_is_valid_for_all_quantifier() -> None:
    initial = _world(1, ())
    state = establish_set_objective_state(
        predicate=VisualConcept("held-out concept"),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=(),
        observation=initial,
        scope=ScopeSpec(
            "scope:empty-structured",
            "current-viewport",
            ScopeExtent.CURRENT_VIEWPORT,
            entity_domain=ScopeEntityDomain.STRUCTURED,
        ),
    )

    assert state.universe.entity_ids == ()
    assert state.reduction.disposition is SetDisposition.NEED_STABILITY_CHECK
    stable = refresh_set_objective_state(state, _world(2, ()))
    assert stable.reduction.disposition is SetDisposition.CERTIFIED


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
        scope=ScopeSpec(
            "scope:closed-structured-visual-candidates",
            "current-viewport",
            ScopeExtent.CURRENT_VIEWPORT,
            entity_domain=ScopeEntityDomain.STRUCTURED,
        ),
    )

    needs = set_evidence_obligations(state)
    assert len(needs) == 1
    assert needs[0].kind is SetEvidenceNeedKind.RESOLVE_UNKNOWN
    assert needs[0].entity_ids == state.universe.entity_ids

    classified = install_semantic_assessments(
        state,
        (
            ("entity:0", PredicateTruth.TRUE, 0.91),
            ("entity:1", PredicateTruth.FALSE, 0.87),
        ),
    )

    assert classified.reduction.disposition is SetDisposition.READY_FOR_NEXT_MEMBER
    assert set_evidence_obligations(classified) == ()


def test_compound_predicate_combines_structural_and_visual_leaf_evidence() -> None:
    world = _world(1, ("member", "other", "member"))
    leaf = VisualConcept("held-out fruit")
    state = establish_set_objective_state(
        predicate=And((FactEquals("kind", "member"), leaf)),
        quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
        semantic_action="activate",
        candidate_entity_ids=(),
        observation=world,
        scope=ScopeSpec(
            "scope:compound-structured-candidates",
            "current-viewport",
            ScopeExtent.CURRENT_VIEWPORT,
            entity_domain=ScopeEntityDomain.STRUCTURED,
        ),
    )

    classified = install_visual_leaf_assessments(
        state,
        world,
        leaf,
        (
            ("entity:0", PredicateTruth.TRUE),
            ("entity:1", PredicateTruth.TRUE),
            ("entity:2", PredicateTruth.FALSE),
        ),
        evaluator_id="fixture:open-vocabulary",
    )

    assert [item.truth for item in classified.assessments] == [
        PredicateTruth.TRUE,
        PredicateTruth.FALSE,
        PredicateTruth.FALSE,
    ]
    assert classified.reduction.disposition is SetDisposition.READY_FOR_NEXT_MEMBER


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
    loop_state.active_step_execution = active
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

    assert context.execution_control is not None
    assert context.execution_control.mode == "blocked"
    assert context.execution_control.disposition == "need_actionability_resolution"
    assert context.execution_control.allowed_action_ids == ()
    assert context.execution_control.evidence_needs == ("resolve_actionability",)


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
