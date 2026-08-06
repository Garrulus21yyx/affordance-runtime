import time
from dataclasses import replace
from typing import Callable

import pytest
from pydantic import ValidationError

from affordance_runtime.action_contract_builder import ActionContractMaterializer as ContractBuilder
from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import (
    Affordance,
    AffordanceLease,
    Observation,
    ProgressEvidenceScope,
    RiskLevel,
    Surface,
    VerifierSpec,
)
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.grounding import UnifiedAffordance
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
    PlannerProposalValidator,
    ProposalRejected,
    ProposalRejectionCode,
    StepEvidenceBinder,
    TaskPlanProgressTarget,
    resolve_task_plan_progress_target,
)
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    InteractionIntent,
    SourceReference,
    StateCriterion,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.task_plan_contracts import TaskPlan, TaskPlanGeneratorSource
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)
from runtime_test_support import (
    canonical_observation,
    legacy_step_spec,
    make_interaction,
    remember_observation,
)

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="planning-test-fixture",
)


def _interaction(target: str, *, role: str = "", ordinal: int | None = None) -> ElementIntent:
    return ElementIntent(
        target,
        (SourceReference("request-1", "request-1:whole"),),
        role=role,
        ordinal=ordinal,
    )


def _step(
    step_id: str,
    objective: str,
    interaction: InteractionIntent,
    *,
    subject: str | None = None,
    relation: CriterionRelation = CriterionRelation.HAS_CHANGED,
    expected_value: str | None = None,
    depends_on: tuple[str, ...] = (),
) -> StepSpec:
    requirement_id = evidence_requirement_id("subgoal", step_id, 0)
    source_refs = (SourceReference("request-1", requirement_id),)
    return legacy_step_spec(
        step_id=step_id,
        objective=objective,
        interaction=interaction,
        completion_criteria=(
            StateCriterion(
                criterion_id=criterion_id("subgoal", step_id, 0),
                source_refs=source_refs,
                subject=subject or objective,
                relation=relation,
                expected_value=expected_value,
                evidence_policy=EvidencePolicy(
                    minimum_strength=EvidenceStrength.INDEPENDENT,
                    allowed_source_kinds=("dom_state",),
                ),
            ),
        ),
        source_refs=source_refs,
        depends_on=depends_on,
    )


def _active_plan_state() -> StateKernel:
    state = StateKernel("task-plan", "Observe the saved state")
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-1",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=0,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "observe",
                    "The saved state is visible",
                    make_interaction("The saved state is visible"),
                    relation=CriterionRelation.IS_VISIBLE,
                ),
            ),
        )
    )
    state.activate_next_step()
    return state


def test_subgoal_evidence_binder_never_infers_links_from_active_timing() -> None:
    state = _active_plan_state()
    unbound = VerifierSpec("observation_metadata", "saved", True)

    bound = StepEvidenceBinder().bind((unbound,), state)

    assert bound == (unbound,)


def test_subgoal_evidence_binder_preserves_explicit_current_pairs() -> None:
    state = _active_plan_state()
    explicit = VerifierSpec(
        "observation_metadata",
        "saved",
        True,
        criterion_ids=(criterion_id("subgoal", "observe", 0),),
        requirement_ids=(evidence_requirement_id("subgoal", "observe", 0),),
    )

    bound = StepEvidenceBinder().bind((explicit,), state)

    assert bound == (explicit,)


@pytest.mark.parametrize(
    ("kind", "scope", "expected_bound"),
    (
        ("observation_metadata", ProgressEvidenceScope.ACTIVE_SUBGOAL, True),
        ("state_delta_or_terminal", ProgressEvidenceScope.TASK_TERMINAL, True),
        ("observation_metadata", ProgressEvidenceScope.TASK_TERMINAL, True),
    ),
)
def test_subgoal_evidence_binder_materializes_only_valid_owner_scopes(
    kind: str,
    scope: ProgressEvidenceScope,
    expected_bound: bool,
) -> None:
    state = _active_plan_state()
    declared = VerifierSpec(kind, "saved", True, progress_scope=scope)

    (bound,) = StepEvidenceBinder().bind((declared,), state)

    assert bool(bound.criterion_ids) is expected_bound
    assert bool(bound.requirement_ids) is expected_bound


@pytest.mark.parametrize("foreign_side", ("criterion", "requirement", "both"))
def test_subgoal_evidence_binder_removes_partial_or_foreign_subgoal_authority(
    foreign_side: str,
) -> None:
    state = _active_plan_state()
    criterion_owner = "other" if foreign_side in {"criterion", "both"} else "observe"
    requirement_owner = "other" if foreign_side in {"requirement", "both"} else "observe"
    invalid = VerifierSpec(
        "observation_metadata",
        "saved",
        True,
        criterion_ids=(criterion_id("subgoal", criterion_owner, 0), "skill:one:criterion:0"),
        requirement_ids=(
            evidence_requirement_id("subgoal", requirement_owner, 0),
            "skill:one:evidence-requirement:0",
        ),
    )

    (validated,) = StepEvidenceBinder().bind((invalid,), state)

    assert validated.criterion_ids == ("skill:one:criterion:0",)
    assert validated.requirement_ids == ("skill:one:evidence-requirement:0",)


@pytest.mark.parametrize("linked_side", ("criterion", "requirement"))
def test_subgoal_evidence_binder_removes_one_sided_active_links(
    linked_side: str,
) -> None:
    state = _active_plan_state()
    partial = VerifierSpec(
        "observation_metadata",
        "saved",
        True,
        criterion_ids=((criterion_id("subgoal", "observe", 0),) if linked_side == "criterion" else ()),
        requirement_ids=((evidence_requirement_id("subgoal", "observe", 0),) if linked_side == "requirement" else ()),
    )

    (validated,) = StepEvidenceBinder().bind((partial,), state)

    assert validated.criterion_ids == ()
    assert validated.requirement_ids == ()


def test_subgoal_evidence_binder_can_bind_runtime_owned_progress_target() -> None:
    state = StateKernel("task-1", "Move slider, then check the box")
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-1",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=0,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "slider-changed",
                    "slider value has changed",
                    _interaction("semantic:slider", role="slider"),
                ),
                _step(
                    "checkbox-changed",
                    "checkbox state has changed",
                    make_interaction("checkbox state has changed"),
                    depends_on=("slider-changed",),
                ),
            ),
        )
    )
    state.activate_next_step()
    state.complete_step("slider-changed", ("evidence:slider",))
    state.activate_next_step()
    verifier = VerifierSpec(
        "control_state",
        "checkbox-3",
        {"field": "checked", "changed_from": False},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )
    target = TaskPlanProgressTarget(
        plan_id="plan-1",
        plan_version=1,
        step_id="checkbox-changed",
        based_on_state_version=state.version,
    )

    (bound,) = StepEvidenceBinder().bind(
        (verifier,),
        state,
        progress_target=target,
    )

    assert bound.progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL
    assert bound.criterion_ids == (criterion_id("subgoal", "checkbox-changed", 0),)
    assert bound.requirement_ids == (evidence_requirement_id("subgoal", "checkbox-changed", 0),)


def test_subgoal_evidence_binder_rejects_stale_progress_target_without_active_fallback() -> None:
    state = _active_plan_state()
    verifier = VerifierSpec(
        "observation_metadata",
        "saved",
        True,
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )
    stale_target = TaskPlanProgressTarget(
        plan_id="plan-1",
        plan_version=1,
        step_id="observe",
        based_on_state_version=state.version + 1,
    )

    (bound,) = StepEvidenceBinder().bind(
        (verifier,),
        state,
        progress_target=stale_target,
    )

    assert bound.criterion_ids == ()
    assert bound.requirement_ids == ()


def test_subgoal_evidence_binder_rejects_progress_target_until_dependencies_complete() -> None:
    state = StateKernel("task-1", "Move slider, then check the box")
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-1",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=0,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "slider-changed",
                    "slider value has changed",
                    make_interaction("slider value has changed"),
                ),
                _step(
                    "checkbox-changed",
                    "checkbox state has changed",
                    make_interaction("checkbox state has changed"),
                    depends_on=("slider-changed",),
                ),
            ),
        )
    )
    state.activate_next_step()
    verifier = VerifierSpec(
        "control_state",
        "checkbox-3",
        {"field": "checked", "changed_from": False},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )
    target = TaskPlanProgressTarget(
        plan_id="plan-1",
        plan_version=1,
        step_id="checkbox-changed",
        based_on_state_version=state.version,
    )

    (bound,) = StepEvidenceBinder().bind(
        (verifier,),
        state,
        progress_target=target,
    )

    assert bound.criterion_ids == ()
    assert bound.requirement_ids == ()


def test_resolve_task_plan_progress_target_uses_runtime_target_not_stale_proposal_subgoal() -> None:
    state = StateKernel("task-1", "Move slider, then check checkbox-3")
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-1",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=0,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "slider-changed",
                    "slider value has changed",
                    _interaction("semantic:slider", role="slider"),
                    subject="slider value",
                ),
                _step(
                    "checkbox-changed",
                    "checkbox-3 state has changed",
                    _interaction("semantic:checkbox-3", role="checkbox"),
                    depends_on=("slider-changed",),
                    subject="checkbox-3 state",
                ),
            ),
        )
    )
    state.activate_next_step()
    state.complete_step("slider-changed", ("evidence:slider",))
    state.activate_next_step()
    checkbox = Affordance(
        "semantic:checkbox-3",
        Surface.DOM,
        "checkbox",
        "checkbox-3",
        "activate",
        {"selector": "#checkbox-3"},
        AffordanceLease.issue(
            environment_revision="rev-1",
            snapshot_id="snapshot-1",
            page_revision="page-1",
        ),
    )
    snapshot = BrowserSnapshot(
        Observation("rev-1", snapshot_id="snapshot-1", page_revision="page-1"),
        PageAffordanceModel(
            "page-1",
            "http://example.test",
            "rev-1",
            "snapshot-1",
            "page-1",
            [checkbox],
            1,
            1,
        ),
    )
    proposal = PlannerProposal(
        proposal_id="click-checkbox",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        subgoal="slider value has changed",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=checkbox.id,
    )

    target = resolve_task_plan_progress_target(proposal, state, snapshot)

    assert target == TaskPlanProgressTarget(
        plan_id="plan-1",
        plan_version=1,
        step_id="checkbox-changed",
        based_on_state_version=state.version,
    )


def test_resolve_task_plan_progress_target_uses_current_target_state_for_value_subject() -> None:
    state = StateKernel("task-1", "Select 7 with the slider")
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-1",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=0,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "slider-value-7",
                    "slider_value_7 has changed",
                    _interaction("semantic:ui-slider-handle", role="slider"),
                    subject="slider_value_7",
                ),
            ),
        )
    )
    state.activate_next_step()
    slider = Affordance(
        "semantic:ui-slider-handle",
        Surface.DOM,
        "slider",
        "ui-slider-handle",
        "press",
        {"selector": ".ui-slider-handle"},
        AffordanceLease.issue(
            environment_revision="rev-1",
            snapshot_id="snapshot-1",
            page_revision="page-1",
        ),
        state={"context_text": "7"},
    )
    snapshot = BrowserSnapshot(
        Observation("rev-1", snapshot_id="snapshot-1", page_revision="page-1"),
        PageAffordanceModel(
            "page-1",
            "http://example.test",
            "rev-1",
            "snapshot-1",
            "page-1",
            [slider],
            1,
            1,
        ),
    )
    proposal = PlannerProposal(
        proposal_id="press-slider",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id=slider.id,
        parameters={"key": "ArrowRight"},
    )

    target = resolve_task_plan_progress_target(proposal, state, snapshot)

    assert target is not None
    assert target.step_id == "slider-value-7"


def _fixture() -> tuple[TaskSpec, StateKernel, BrowserSnapshot]:
    model = DomAdapter().transduce(
        '<input id="theme" aria-label="Theme">',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Set theme")
    remember_observation(state, observation)
    spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Set theme to dark",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("theme",), OperationClass.REVERSIBLE_WRITE, "request-1", ("settings.write",)
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("theme",)),
        capability_ceiling=("settings.write",),
        source_request_ref="request-1",
        created_at_s=time.time(),
    )
    return spec, state, BrowserSnapshot(observation, model)


def _proposal(state: StateKernel, **changes: object) -> PlannerProposal:
    values = {
        "proposal_id": "proposal-1",
        "based_on_task_revision": 2,
        "based_on_state_version": state.version,
        "snapshot_id": "snapshot-1",
        "subgoal": "Set theme to dark",
        "action_kind": PlannerActionKind.TYPE_TEXT,
        "target_affordance_id": "dom_input_1",
        "parameters": {"text": "dark"},
        "expected_effects": ("theme is dark",),
        "evidence_requirements": ("saved theme evidence",),
    }
    values.update(changes)
    return PlannerProposal(**values)


def test_contract_builder_binds_current_target_authority_and_verifier() -> None:
    spec, state, snapshot = _fixture()
    builder = ContractBuilder(
        requirements={
            "dom_input_1": ContractRequirements(
                verifier_plan=(VerifierSpec("evidence", "saved_theme", "dark"),),
                compensation="restore previous theme",
            )
        }
    )

    contract = builder.build(_proposal(state), spec, state, snapshot)

    assert contract.locator == {"selector": "#theme", "strategy": "css"}
    assert contract.backend == "dom"
    assert contract.parameters == {"value": "dark"}
    assert contract.required_capabilities == ["settings.write"]
    assert contract.risk == RiskLevel.MEDIUM
    assert contract.verifier_plan == [VerifierSpec("evidence", "saved_theme", "dark")]
    assert contract.compensation == "restore previous theme"
    assert contract.idempotency_key


def test_core_contract_builder_resolves_semantic_target_to_selected_candidate() -> None:
    class Page:
        url = "https://example.test/settings"

        def content(self) -> str:
            return '<input id="theme" aria-label="Theme">'

        def evaluate(self, script: str) -> object:
            if "Object.fromEntries" in script:
                return {}
            return ""

        def screenshot(self, **kwargs: object) -> bytes:
            del kwargs
            return b""

    snapshot = BrowserSession(Page(), lease_ttl_ms=60_000).capture()
    semantic_target = snapshot.unified_affordances[0].semantic_target_id
    state = StateKernel("task-semantic", "Set theme")
    remember_observation(state, snapshot.observation)
    spec = TaskSpec(
        task_id="task-semantic",
        revision=1,
        objective="Set theme to dark",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(("theme",), OperationClass.REVERSIBLE_WRITE, "request-semantic", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("theme",)),
        source_request_ref="request-semantic",
    )
    proposal = PlannerProposal(
        proposal_id="proposal-semantic",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        subgoal="Set theme to dark",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=semantic_target,
        parameters={"text": "dark"},
    )

    contract = ContractBuilder(
        requirements={
            semantic_target: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "dom_attribute",
                        "theme",
                        {"target_attribute": "id", "attribute": "value", "value": "dark"},
                    ),
                )
            )
        }
    ).build(proposal, spec, state, snapshot)

    assert contract.affordance_id == semantic_target
    assert contract.grounding_candidate is not None
    assert contract.route_plan is not None
    assert contract.backend == contract.grounding_candidate.compatible_executor == "dom"
    assert contract.locator["selector"] == "#theme"
    assert contract.target_fingerprint_key == contract.grounding_candidate.fingerprint_key


def test_core_reroute_excludes_failed_candidate_and_binds_fresh_contract_lineage() -> None:
    model = DomAdapter().transduce(
        '<button bid="save">Save</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
        ttl_ms=60_000,
    )
    dom = model.affordances[0]
    accessibility = replace(
        dom,
        id="a11y_button_1",
        surface=Surface.ACCESSIBILITY,
        locator={"selector": "role=button[name='Save']"},
        backend_candidates=["a11y"],
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    candidates = (
        candidate_from_affordance(dom, observation, semantic_target_id="pending"),
        candidate_from_affordance(accessibility, observation, semantic_target_id="pending"),
    )
    target: UnifiedAffordance = SemanticEntityResolver().resolve(
        tuple(CandidateDescriptor("button", "Save", "click", "", candidate) for candidate in candidates)
    )[0]
    observation = replace(
        observation,
        target_fingerprints=candidate_fingerprints((target,)),
    )
    snapshot = BrowserSnapshot(
        observation,
        replace(model, affordances=[dom, accessibility], kept_node_count=2),
        grounding_candidates=target.grounding_candidates,
        unified_affordances=(target,),
    )
    state = StateKernel("task-reroute", "Save")
    remember_observation(state, observation)
    spec = TaskSpec(
        task_id="task-reroute",
        revision=1,
        objective="Save",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("Save",), OperationClass.READ_ONLY, "request-reroute", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("Save",)),
        source_request_ref="request-reroute",
    )
    builder = ContractBuilder(
        requirements={
            target.semantic_target_id: ContractRequirements(verifier_plan=(VerifierSpec("state_delta", "save", True),))
        }
    )
    first_proposal = PlannerProposal(
        proposal_id="proposal-first",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=observation.snapshot_id,
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=target.semantic_target_id,
    )
    first = builder.build(first_proposal, spec, state, snapshot)

    state.record_grounding_reroute(first, "first candidate failed deterministically")
    second = builder.build(
        first_proposal.model_copy(
            update={
                "proposal_id": "proposal-second",
                "based_on_state_version": state.version,
            }
        ),
        spec,
        state,
        snapshot,
    )

    assert first.grounding_candidate is not None
    assert second.grounding_candidate is not None
    assert first.grounding_candidate.source.value == "dom"
    assert second.grounding_candidate.source.value == "accessibility"
    assert second.contract_hash != first.contract_hash
    assert second.supersedes_contract_id == first.id
    assert second.source_contract_id == first.id
    assert second.fallback_reason == "first candidate failed deterministically"
    assert second.route_plan is not None
    failed_gate = next(
        item
        for item in second.route_plan.hard_gate_results
        if item.candidate_id == first.grounding_candidate.candidate_id
    )
    assert failed_gate.reasons == ("candidate_excluded",)


def test_core_contract_builder_binds_both_semantic_drag_endpoints() -> None:
    class Page:
        url = "https://example.test/sortable"

        def content(self) -> str:
            return (
                '<li bid="source" class="ui-sortable-handle">Source</li>'
                '<li bid="destination" class="ui-sortable-handle">Destination</li>'
            )

        def evaluate(self, script: str) -> object:
            if "Object.fromEntries" in script:
                return {}
            return ""

        def screenshot(self, **kwargs: object) -> bytes:
            del kwargs
            return b""

    snapshot = BrowserSession(Page(), lease_ttl_ms=60_000).capture()
    target_by_label = {item.label: item.semantic_target_id for item in snapshot.unified_affordances}
    source_id = target_by_label["Source"]
    destination_id = target_by_label["Destination"]
    state = StateKernel("task-drag", "Reorder items")
    remember_observation(state, snapshot.observation)
    spec = TaskSpec(
        task_id="task-drag",
        revision=1,
        objective="Drag Source to Destination",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(
            ("Source", "Destination"), OperationClass.READ_ONLY, "request-drag", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("Source", "Destination")),
        source_request_ref="request-drag",
    )
    proposal = PlannerProposal(
        proposal_id="proposal-drag",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id=source_id,
        destination_affordance_id=destination_id,
    )

    contract = ContractBuilder(
        requirements={source_id: ContractRequirements(verifier_plan=(VerifierSpec("state_delta", "sortable", True),))}
    ).build(proposal, spec, state, snapshot)

    assert contract.gesture_binding is not None
    assert contract.gesture_binding.source.semantic_target_id == source_id
    assert contract.gesture_binding.destination.semantic_target_id == destination_id
    assert contract.gesture_binding.source.candidate_id.startswith("candidate:dom:")
    assert contract.gesture_binding.destination.candidate_id.startswith("candidate:dom:")
    assert contract.gesture_binding.source.snapshot_id == contract.gesture_binding.destination.snapshot_id
    assert contract.gesture_binding.selected_route == contract.backend == "dom"


def test_point_activate_binds_semantic_svg_target_without_planner_coordinates() -> None:
    spec, state, snapshot = _fixture()
    point = Affordance(
        id="svg_circle_1",
        surface=Surface.SVG,
        role="point",
        label="(-1,0)",
        action="point_activate",
        locator={"bbox": [20.0, 30.0, 8.0, 8.0], "coordinate_space": "viewport_pixels"},
        lease=AffordanceLease.issue(
            environment_revision=snapshot.observation.environment_revision,
            ttl_ms=60_000,
            snapshot_id=snapshot.observation.snapshot_id,
            page_revision=snapshot.observation.page_revision,
            target_fingerprint="svg-fingerprint",
        ),
        backend_candidates=["visual"],
    )
    point_snapshot = BrowserSnapshot(
        replace(
            snapshot.observation,
            target_fingerprints={"svg_circle_1": "svg-fingerprint"},
        ),
        replace(snapshot.affordance_model, affordances=[point], kept_node_count=1),
    )
    remember_observation(state, point_snapshot.observation)
    spec = spec.model_copy(
        update={
            "objective": "Activate the current SVG point",
            "targets": (point.label,),
            "evidence_requirements": ("current spatial SVG evidence",),
        }
    )
    proposal = _proposal(
        state,
        action_kind=PlannerActionKind.POINT_ACTIVATE,
        target_affordance_id="svg_circle_1",
        parameters={},
    )

    contract = ContractBuilder(
        requirements={
            point.id: ContractRequirements(
                verifier_plan=(VerifierSpec("observation_metadata", "point_activated", True),)
            )
        }
    ).build(proposal, spec, state, point_snapshot)

    assert contract.action == "point_activate"
    assert contract.affordance_id == "svg_circle_1"
    assert contract.backend == "visual"
    assert contract.parameters == {}


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"based_on_task_revision": 1}, ProposalRejectionCode.STALE_TASK_REVISION),
        ({"based_on_state_version": 99}, ProposalRejectionCode.STALE_STATE_VERSION),
        ({"snapshot_id": "old"}, ProposalRejectionCode.STALE_SNAPSHOT),
        ({"target_affordance_id": "missing"}, ProposalRejectionCode.MISSING_TARGET),
        ({"action_kind": PlannerActionKind.ACTIVATE, "parameters": {}}, ProposalRejectionCode.UNSUPPORTED_ACTION),
    ],
)
def test_contract_builder_rejects_stale_missing_or_incompatible_proposal(
    changes: dict[str, object],
    code: ProposalRejectionCode,
) -> None:
    spec, state, snapshot = _fixture()
    with pytest.raises(ProposalRejected) as caught:
        ContractBuilder().build(_proposal(state, **changes), spec, state, snapshot)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("proposal", "code"),
    [
        (
            lambda state: _proposal(state, based_on_task_revision=1),
            ProposalRejectionCode.STALE_TASK_REVISION,
        ),
        (
            lambda state: _proposal(state, based_on_state_version=99),
            ProposalRejectionCode.STALE_STATE_VERSION,
        ),
        (
            lambda state: _proposal(state, snapshot_id="old"),
            ProposalRejectionCode.STALE_SNAPSHOT,
        ),
        (
            lambda state: _proposal(state, target_affordance_id="missing"),
            ProposalRejectionCode.MISSING_TARGET,
        ),
        (
            lambda state: _proposal(
                state,
                action_kind=PlannerActionKind.ACTIVATE,
                parameters={},
            ),
            ProposalRejectionCode.UNSUPPORTED_ACTION,
        ),
        (
            lambda state: _proposal(
                state,
                action_kind=PlannerActionKind.FINISH,
                target_affordance_id="dom_input_1",
                parameters={},
            ),
            ProposalRejectionCode.UNEXPECTED_TARGET,
        ),
        (
            lambda state: _proposal(
                state,
                action_kind=PlannerActionKind.DRAG,
                target_affordance_id="dom_input_1",
                destination_affordance_id="dom_input_1",
                parameters={},
            ),
            ProposalRejectionCode.IDENTICAL_DRAG_TARGETS,
        ),
    ],
)
def test_proposal_validator_is_the_source_neutral_prebinding_gate(
    proposal: Callable[[StateKernel], PlannerProposal],
    code: ProposalRejectionCode,
) -> None:
    spec, state, snapshot = _fixture()
    candidate = proposal(state)

    with pytest.raises(ProposalRejected) as caught:
        PlannerProposalValidator().validate(
            candidate,
            TEST_PROPOSAL_PROVENANCE,
            spec,
            state,
            canonical_observation(snapshot),
        )

    assert caught.value.code == code


def test_proposal_validator_accepts_a_current_semantic_proposal() -> None:
    spec, state, snapshot = _fixture()

    PlannerProposalValidator().validate(
        _proposal(state),
        TEST_PROPOSAL_PROVENANCE,
        spec,
        state,
        canonical_observation(snapshot),
    )


def test_proposal_validator_enforces_exact_active_step_scope_when_available() -> None:
    model = DomAdapter().transduce(
        '<input id="theme" aria-label="Theme"><button id="submit">Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Set theme")
    remember_observation(state, observation)
    target_ids = tuple(item.id for item in model.affordances)
    active_target, cross_step_target = target_ids[0], target_ids[1]
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-active-scope",
            task_id=state.task_id,
            task_revision=2,
            plan_version=1,
            based_on_state_version=state.version,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "step:theme",
                    "Set theme to dark",
                    _interaction(active_target),
                    subject=active_target,
                    relation=CriterionRelation.EQUALS,
                    expected_value="dark",
                ),
                _step(
                    "step:submit",
                    "Submit the form",
                    _interaction(cross_step_target),
                    depends_on=("step:theme",),
                    subject=cross_step_target,
                    relation=CriterionRelation.IS_COMPLETED,
                ),
            ),
        )
    )
    state.activate_next_step()
    spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Set theme to dark and submit",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("theme", "submit"), OperationClass.REVERSIBLE_WRITE, "request-1", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("theme", "submit")),
        source_request_ref="request-1",
    )
    proposal = _proposal(
        state,
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=cross_step_target,
        parameters={},
    )

    with pytest.raises(ProposalRejected) as caught:
        PlannerProposalValidator().validate(
            proposal,
            TEST_PROPOSAL_PROVENANCE,
            spec,
            state,
            canonical_observation(BrowserSnapshot(observation, model)),
        )

    assert caught.value.code == ProposalRejectionCode.TARGET_OUT_OF_SCOPE
    assert caught.value.reason_code == "target_outside_active_step"


def test_proposal_validator_resolves_checkbox_ordinal_active_step_scope() -> None:
    model = DomAdapter().transduce(
        """
        <input type="checkbox" aria-label="First">
        <input type="checkbox" aria-label="Second">
        <input type="checkbox" aria-label="Third">
        """,
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Click the 3rd checkbox")
    remember_observation(state, observation)
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-checkbox-scope",
            task_id=state.task_id,
            task_revision=2,
            plan_version=1,
            based_on_state_version=state.version,
            based_on_observation_ref="snapshot-1",
            generated_by=TaskPlanGeneratorSource.RULE,
            steps=(
                _step(
                    "checkbox_3_state",
                    "checkbox_3_state has changed",
                    _interaction("checkbox", role="checkbox", ordinal=3),
                    subject="checkbox_3_state",
                ),
            ),
        )
    )
    state.activate_next_step()
    spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Click the 3rd checkbox",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("checkbox_3_state",), OperationClass.REVERSIBLE_WRITE, "request-1", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("checkbox_3_state",)),
        source_request_ref="request-1",
    )
    snapshot = BrowserSnapshot(observation, model)

    with pytest.raises(ProposalRejected) as caught:
        PlannerProposalValidator().validate(
            _proposal(
                state,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=model.affordances[0].id,
                parameters={},
            ),
            TEST_PROPOSAL_PROVENANCE,
            spec,
            state,
            canonical_observation(snapshot),
        )

    assert caught.value.code == ProposalRejectionCode.TARGET_OUT_OF_SCOPE
    assert caught.value.reason_code == "target_outside_active_step"

    PlannerProposalValidator().validate(
        _proposal(
            state,
            action_kind=PlannerActionKind.ACTIVATE,
            target_affordance_id=model.affordances[2].id,
            parameters={},
        ),
        TEST_PROPOSAL_PROVENANCE,
        spec,
        state,
        canonical_observation(snapshot),
    )


def test_proposal_validator_rejects_missing_runtime_provenance() -> None:
    spec, state, snapshot = _fixture()

    with pytest.raises(ProposalRejected) as caught:
        PlannerProposalValidator().validate(_proposal(state), None, spec, state, canonical_observation(snapshot))

    assert caught.value.code == ProposalRejectionCode.MISSING_PROVENANCE


def test_proposal_schema_rejects_surface_and_authority_fields() -> None:
    _, state, _ = _fixture()
    with pytest.raises(ValidationError, match="surface or authority"):
        _proposal(state, parameters={"text": "dark", "selector": "#theme"})
    with pytest.raises(ValidationError, match="surface or authority"):
        _proposal(state, parameters={"text": "dark", "capability": "settings.write"})
    with pytest.raises(ValidationError, match="unsupported semantic parameters"):
        _proposal(state, parameters={"text": "dark", "wait_for_seconds": 3})
    with pytest.raises(ValidationError, match="navigate requires a semantic destination"):
        _proposal(state, action_kind=PlannerActionKind.NAVIGATE, target_affordance_id="", parameters={})
    with pytest.raises(ValidationError, match="at least 1 character"):
        _proposal(state, snapshot_id="")
    with pytest.raises(ValidationError, match="select_option requires option"):
        _proposal(
            state,
            action_kind=PlannerActionKind.SELECT_OPTION,
            parameters={},
        )


def test_finish_and_ask_flags_are_deterministically_derived_from_action_kind() -> None:
    _, state, _ = _fixture()
    finish = _proposal(
        state,
        action_kind=PlannerActionKind.FINISH,
        target_affordance_id="",
        parameters={},
        done=False,
    )
    ask = _proposal(
        state,
        action_kind=PlannerActionKind.ASK_USER,
        target_affordance_id="",
        parameters={},
        requires_clarification=False,
    )

    assert finish.done is True
    assert ask.requires_clarification is True


def test_contract_builder_binds_semantic_key_press_without_surface_parameters() -> None:
    model = DomAdapter().transduce(
        '<span id="slider" tabindex="0" class="ui-slider-handle"></span>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Increase slider")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Increase slider",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(("slider",), OperationClass.REVERSIBLE_WRITE, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("slider",)),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="press",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id="dom_span_1",
        parameters={"key": "ArrowRight"},
    )

    contract = ContractBuilder(
        requirements={
            "dom_span_1": ContractRequirements(verifier_plan=(VerifierSpec("observation_metadata", "slider_value", 1),))
        }
    ).build(proposal, task, state, BrowserSnapshot(observation, model))

    assert contract.action == "press"
    assert contract.parameters == {"key": "ArrowRight"}
