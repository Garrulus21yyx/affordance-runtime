import time
from dataclasses import replace
from typing import Callable

import pytest
from pydantic import ValidationError

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, RiskLevel, Surface, VerifierSpec
from affordance_runtime.grounding import UnifiedAffordance
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
    PlannerProposalValidator,
    ProposalRejected,
    ProposalRejectionCode,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="planning-test-fixture",
)


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
    state.remember_observation(observation)
    spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Set theme to dark",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme is dark",),
        requested_capabilities=("settings.write",),
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
    state.remember_observation(snapshot.observation)
    spec = TaskSpec(
        task_id="task-semantic",
        revision=1,
        objective="Set theme to dark",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme is dark",),
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
        tuple(
            CandidateDescriptor("button", "Save", "click", "", candidate)
            for candidate in candidates
        )
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
    state.remember_observation(observation)
    spec = TaskSpec(
        task_id="task-reroute",
        revision=1,
        objective="Save",
        operation_class=OperationClass.READ_ONLY,
        targets=("Save",),
        success_criteria=("saved",),
        source_request_ref="request-reroute",
    )
    builder = ContractBuilder(
        requirements={
            target.semantic_target_id: ContractRequirements(
                verifier_plan=(VerifierSpec("state_delta", "save", True),)
            )
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
        item for item in second.route_plan.hard_gate_results
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
    state.remember_observation(snapshot.observation)
    spec = TaskSpec(
        task_id="task-drag",
        revision=1,
        objective="Drag Source to Destination",
        operation_class=OperationClass.READ_ONLY,
        targets=("sortable",),
        success_criteria=("items are reordered",),
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
        requirements={
            source_id: ContractRequirements(
                verifier_plan=(VerifierSpec("state_delta", "sortable", True),)
            )
        }
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
    state.remember_observation(point_snapshot.observation)
    proposal = _proposal(
        state,
        action_kind=PlannerActionKind.POINT_ACTIVATE,
        target_affordance_id="svg_circle_1",
        parameters={},
    )

    contract = ContractBuilder().build(proposal, spec, state, point_snapshot)

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
            snapshot,
        )

    assert caught.value.code == code


def test_proposal_validator_accepts_a_current_semantic_proposal() -> None:
    spec, state, snapshot = _fixture()

    PlannerProposalValidator().validate(
        _proposal(state),
        TEST_PROPOSAL_PROVENANCE,
        spec,
        state,
        snapshot,
    )


def test_proposal_validator_rejects_missing_runtime_provenance() -> None:
    spec, state, snapshot = _fixture()

    with pytest.raises(ProposalRejected) as caught:
        PlannerProposalValidator().validate(_proposal(state), None, spec, state, snapshot)

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
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-1", revision=1, objective="Increase slider", operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider",), success_criteria=("slider increased",), source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="press", based_on_task_revision=1, based_on_state_version=state.version,
        snapshot_id="snapshot-1", action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id="dom_span_1", parameters={"key": "ArrowRight"},
    )

    contract = ContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))

    assert contract.action == "press"
    assert contract.parameters == {"key": "ArrowRight"}
