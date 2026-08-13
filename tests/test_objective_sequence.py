from __future__ import annotations

from dataclasses import replace

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.criteria import LiteralValue, PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StepSpec,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.objective_sequence import (
    EntitySelector,
    ObjectiveSequence,
    ObjectiveSequenceState,
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
from affordance_runtime.task.step_execution import EntityStepExecution
from affordance_runtime.task_plan_contracts import TaskPlan, TaskPlanGeneratorSource
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    SatisfactionMode,
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


def test_agent_state_materializes_execution_only_from_current_task_plan_step() -> None:
    world = _world("observation:plan", "+")
    refs = (SourceReference("request", "request:step"),)
    execution = EntityStepExecution(
        EntitySelector(FactEquals("identity.label", "+")),
        ActionTemplate("activate"),
    )
    step = StepSpec(
        "expand",
        "activate plus",
        ElementIntent("+", refs),
        (
            PredicateExpr(
                "criterion:expand",
                SubjectExpr("target", "+", "activated"),
                PredicateOperator.EQUALS,
                CriterionPolicy(
                    satisfaction=SatisfactionMode.ACTION_CAUSED,
                    minimum_assurance=AssuranceLevel.STRUCTURAL,
                    allowed_source_kinds=(EvidenceSourceKind.DOM_STATE,),
                    causal_lineage_required=True,
                ),
                LiteralValue(True),
            ),
        ),
        refs,
        ("requirement:test",),
        execution=execution,
    )
    choose_zero = replace(
        step,
        step_id="choose-zero",
        objective="activate zero",
        interaction=ElementIntent("0", refs),
        completion_criteria=(replace(step.completion_criteria[0], criterion_id="criterion:choose-zero"),),
        depends_on=("expand",),
        execution=EntityStepExecution(
            EntitySelector(FactEquals("identity.label", "0")),
            ActionTemplate("activate"),
        ),
    )
    plan = TaskPlan(
        plan_id="plan:canonical",
        task_id="task:sequence",
        task_revision=1,
        plan_version=1,
        based_on_state_version=0,
        based_on_observation_ref=world.observation_id,
        generated_by=TaskPlanGeneratorSource.RULE,
        steps=(step, choose_zero),
    )
    state = AgentLoopState(world, semantic_control_required=True)

    state.install_plan(plan, task_spec_identity="sha256:admitted-task")

    assert state.plan is plan
    assert state.task_spec_identity == "sha256:admitted-task"
    assert state.task_progress is not None
    assert state.task_progress.active_step_id == "expand"
    assert isinstance(state.active_step_execution, ObjectiveSequenceState)
    assert state.active_step_execution.resolved_target_id == "entity:0:+"

    after = _world("observation:after-expand", "0")
    state.current_observation = after
    active = state.active_step_execution
    state.active_step_execution = replace(
        active,
        active_index=1,
        observation_epoch=after.observation_id,
        disposition=SequenceDisposition.COMPLETE,
        completed_step_ids=("expand",),
        effect_evidence_refs=("effect:expand",),
    )
    state._advance_plan_after_execution()

    assert state.task_progress.active_step_id == "choose-zero"
    assert isinstance(state.active_step_execution, ObjectiveSequenceState)
    assert state.active_step_execution.observation_epoch == after.observation_id
    assert state.active_step_execution.resolved_target_id == "entity:0:0"


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
