from __future__ import annotations

from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.task import (
    AggregateDisposition,
    AggregateObjective,
    AggregateOperator,
    AggregateOutputFormat,
    FactEquals,
    PredicateTruth,
    ScopeExtent,
    ScopeSpec,
    ValueExtractor,
    ValueExtractorKind,
    VisualConcept,
    aggregate_allowed_action_ids,
    establish_aggregate_objective_state,
    install_aggregate_visual_leaf_assessments,
    refresh_aggregate_objective_state,
)
from affordance_runtime.world import (
    ActionOption,
    ActionRisk,
    ActionSpace,
    CoverageState,
    SemanticTarget,
    WorldObservation,
)


def _objective(
    operator: AggregateOperator,
    *,
    extractor: ValueExtractor = ValueExtractor(ValueExtractorKind.CONSTANT, constant=1),
) -> AggregateObjective:
    return AggregateObjective(
        "aggregate-objective:held-out",
        ScopeSpec("scope:held-out", "current-viewport", ScopeExtent.CURRENT_VIEWPORT),
        FactEquals("kind", "member"),
        extractor,
        operator,
        FactEquals("identity.role", "textbox"),
        output_format=AggregateOutputFormat.INTEGER_STRING,
    )


def _world(epoch: int, values: tuple[int | None, ...], *, coverage=CoverageState.COMPLETE):
    members = tuple(
        SemanticTarget(
            f"entity:item-{index}",
            "generic",
            "",
            {"kind": "member", **({} if value is None else {"amount": value})},
        )
        for index, value in enumerate(values)
    )
    destination = SemanticTarget(
        "entity:answer",
        "textbox",
        "Answer",
        {"kind": "destination", "value": ""},
    )
    return WorldObservation(
        f"observation:{epoch}",
        (*members, destination),
        (),
        (),
        {"dom": coverage},
    )


def _space(world: WorldObservation) -> ActionSpace:
    return ActionSpace(
        world.observation_id,
        (
            ActionOption(
                f"action:{world.observation_id}",
                world.observation_id,
                "type_text",
                "entity:answer",
                "interaction",
                {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "schema:type-text",
                ("binding:type-text",),
                "type answer value",
                risk=ActionRisk.LOW,
            ),
        ),
    )


def test_count_derives_private_destination_parameter_from_closed_scope() -> None:
    world = _world(1, (None, None, None))
    state = establish_aggregate_objective_state(_objective(AggregateOperator.COUNT), world)

    assert state.disposition is AggregateDisposition.READY
    assert state.action_parameters == {"text": "3"}
    assert len(state.provenance_digest) == 64
    assert aggregate_allowed_action_ids(state, _space(world)) == {"action:observation:1"}


def test_sum_min_and_max_use_evidence_values_not_model_result() -> None:
    world = _world(1, (7, 2, 4))
    extractor = ValueExtractor(ValueExtractorKind.FACT, "amount")
    results = {}
    for operator in (AggregateOperator.SUM, AggregateOperator.MIN, AggregateOperator.MAX):
        state = establish_aggregate_objective_state(
            _objective(operator, extractor=extractor),
            world,
        )
        results[operator] = state.action_parameters["text"]

    assert results == {
        AggregateOperator.SUM: "13",
        AggregateOperator.MIN: "2",
        AggregateOperator.MAX: "7",
    }


def test_sum_of_empty_closed_member_set_is_zero() -> None:
    world = _world(1, ())
    state = establish_aggregate_objective_state(
        _objective(
            AggregateOperator.SUM,
            extractor=ValueExtractor(ValueExtractorKind.FACT, "amount"),
        ),
        world,
    )

    assert state.disposition is AggregateDisposition.READY
    assert state.action_parameters == {"text": "0"}


def test_unknown_value_and_partial_scope_fail_closed() -> None:
    extractor = ValueExtractor(ValueExtractorKind.FACT, "amount")
    missing = establish_aggregate_objective_state(
        _objective(AggregateOperator.SUM, extractor=extractor),
        _world(1, (2, None)),
    )
    partial = establish_aggregate_objective_state(
        _objective(AggregateOperator.COUNT),
        _world(1, (None,), coverage=CoverageState.TRUNCATED),
    )

    assert missing.disposition is AggregateDisposition.NEED_VALUES
    assert missing.action_parameters == {}
    assert partial.disposition is AggregateDisposition.NEED_SCOPE_CLOSURE
    assert partial.action_parameters == {}


def test_visual_member_leaf_is_evidence_not_aggregate_authority() -> None:
    world = _world(1, (None, None, None))
    leaf = VisualConcept("held-out fruit")
    objective = AggregateObjective(
        "aggregate-objective:visual-count",
        ScopeSpec("scope:visual-count", "current-viewport", ScopeExtent.CURRENT_VIEWPORT),
        leaf,
        ValueExtractor(ValueExtractorKind.CONSTANT, constant=1),
        AggregateOperator.COUNT,
        FactEquals("identity.role", "textbox"),
    )
    state = establish_aggregate_objective_state(objective, world)

    classified = install_aggregate_visual_leaf_assessments(
        state,
        world,
        leaf,
        (
            ("entity:item-0", PredicateTruth.TRUE),
            ("entity:item-1", PredicateTruth.FALSE),
            ("entity:item-2", PredicateTruth.TRUE),
            ("entity:answer", PredicateTruth.FALSE),
        ),
        evaluator_id="fixture:open-vocabulary",
    )

    assert classified.disposition is AggregateDisposition.READY
    assert classified.action_parameters == {"text": "2"}
    assert all(item.confidence is None for item in classified.semantic_leaf_assessments)


def test_visual_destination_uses_the_same_scope_evidence_lifecycle() -> None:
    objective = AggregateObjective(
        "aggregate-objective:visual-destination",
        ScopeSpec("scope:visual-destination", "current-viewport", ScopeExtent.CURRENT_VIEWPORT),
        FactEquals("kind", "member"),
        ValueExtractor(ValueExtractorKind.CONSTANT, constant=1),
        AggregateOperator.COUNT,
        VisualConcept("answer box"),
    )

    state = establish_aggregate_objective_state(objective, _world(1, (None,)))

    assert state.disposition is AggregateDisposition.NEED_DESTINATION
    assert state.destination_resolution is not None
    assert state.destination_resolution.scope.entity_domain.value == "all_visible"


def test_fresh_observation_rederives_before_action_and_effect_closes_after_action() -> None:
    state = establish_aggregate_objective_state(
        _objective(AggregateOperator.COUNT),
        _world(1, (None, None)),
    )
    changed = refresh_aggregate_objective_state(state, _world(2, (None, None, None)))
    settled = refresh_aggregate_objective_state(
        changed,
        _world(3, (None, None, None)),
        acted_entity_id="entity:answer",
        action_status=ActionEvaluationStatus.EFFECT_CONFIRMED,
        effect_evidence_refs=("evidence:answer-updated",),
    )

    assert changed.action_parameters == {"text": "3"}
    assert changed.provenance_digest != state.provenance_digest
    assert settled.disposition is AggregateDisposition.COMPLETE
    assert settled.effect_evidence_refs == ("evidence:answer-updated",)
