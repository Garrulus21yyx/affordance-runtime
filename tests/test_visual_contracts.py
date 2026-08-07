from dataclasses import replace
from time import time

import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.benchmarks.browsergym import GeneralistBrowserGymContractBuilder
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, Surface, VerifierSpec
from affordance_runtime.grounding import (
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    RoutePlan,
    SourceObservation,
    SvgGroundingPayload,
    SvgTransform,
    UnifiedAffordance,
    VisualGroundingPayload,
)
from affordance_runtime.planning import PlannerActionKind, PlannerProposal
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression
from affordance_runtime.verification.mechanical import preflight
from affordance_runtime.visual_contracts import VisualContractBinder
from runtime_test_support import remember_observation


def _svg_candidate() -> GroundingCandidate:
    return GroundingCandidate(
        candidate_id="svg:target",
        semantic_target_id="semantic:target",
        source=GroundingSource.SVG,
        payload=SvgGroundingPayload(
            element_id="target",
            tag="circle",
            view_box=(0, 0, 100, 100),
            geometry_bbox_xywh=(10, 20, 4, 4),
            viewport_bbox_xywh=(120, 240, 8, 8),
            transform=SvgTransform(2, 0, 0, 2, 100, 200),
        ),
        compatible_executor="browsergym",
        observation_epoch_id="snap-1",
        environment_revision="rev-1",
        page_revision="page-1",
        target_fingerprint="svg-fingerprint",
        fingerprint_key="svg:target",
        supported_actions=frozenset({"point_activate"}),
        evidence_kinds=frozenset(
            {
                EvidenceKind.STRUCTURAL,
                EvidenceKind.SPATIAL,
                EvidenceKind.VISUAL_APPEARANCE,
            }
        ),
        expires_at_s=time() + 60,
    )


def _observation(**metadata: object) -> Observation:
    return Observation(
        "rev-1",
        screenshot_ref="screen.png",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"svg:target": "svg-fingerprint"},
        metadata={"viewport_size": [800, 600], **metadata},
    )


def test_visual_contract_binder_creates_fresh_svg_point_contract() -> None:
    candidate = _svg_candidate()
    route = RoutePlan("semantic:target", selected_candidate=candidate)
    observation = _observation()

    contract = VisualContractBinder().bind_point_activate(
        route,
        observation,
        intent="activate the blue point",
        verifier_plan=(VerifierSpec("state_delta_or_terminal", "target"),),
    )

    assert contract.grounding_candidate == candidate
    assert contract.locator["point"] == [124.0, 244.0]
    assert contract.affordance_id == "semantic:target"
    assert contract.target_fingerprint_key == "svg:target"
    assert contract.contract_hash.startswith("sha256:")
    assert preflight(contract, observation) is None


def test_visual_contract_binder_scales_screenshot_pixels_to_viewport() -> None:
    visual = GroundingCandidate(
        candidate_id="visual:target",
        semantic_target_id="semantic:target",
        source=GroundingSource.VISUAL,
        payload=VisualGroundingPayload("screen.png", (1600, 1200), point_xy=(800, 600)),
        compatible_executor="browsergym",
        observation_epoch_id="snap-1",
        environment_revision="rev-1",
        page_revision="page-1",
        target_fingerprint="visual-fingerprint",
        fingerprint_key="visual:target",
        supported_actions=frozenset({"point_activate"}),
        evidence_kinds=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
    )
    observation = Observation(
        "rev-1",
        screenshot_ref="screen.png",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"visual:target": "visual-fingerprint"},
        metadata={"viewport_size": [800, 600]},
    )

    contract = VisualContractBinder().bind_point_activate(
        RoutePlan("semantic:target", visual),
        observation,
        intent="activate target",
        verifier_plan=(VerifierSpec("state_delta_or_terminal", "target"),),
    )

    assert contract.locator["point"] == [400.0, 300.0]


def test_visual_contract_binder_rejects_blocking_overlay() -> None:
    with pytest.raises(ValueError, match="blocked by an overlay"):
        VisualContractBinder().bind_point_activate(
            RoutePlan("semantic:target", _svg_candidate()),
            _observation(blocking_overlays=[{"bbox": [100, 200, 100, 100]}]),
            intent="activate target",
            verifier_plan=(VerifierSpec("state_delta_or_terminal", "target"),),
        )


def test_browsergym_point_route_uses_unified_candidate_before_backend_encoding() -> None:
    candidate = _svg_candidate()
    legacy = Affordance(
        "svg_circle_1",
        Surface.SVG,
        "button",
        "Blue point",
        "point_activate",
        {
            "bbox": [120.0, 240.0, 8.0, 8.0],
            "coordinate_space": "viewport_pixels",
            "grounding_candidate_id": candidate.candidate_id,
        },
        AffordanceLease.issue(
            environment_revision="rev-1",
            ttl_ms=60_000,
            snapshot_id="snap-1",
            page_revision="page-1",
            target_fingerprint="svg-fingerprint",
        ),
        backend_candidates=["browsergym"],
    )
    observation = _observation()
    source_observations = (
        SourceObservation(GroundingSource.DOM, "dom", "snap-1", "rev-1", "page-1"),
        SourceObservation(GroundingSource.SVG, "svg", "snap-1", "rev-1", "page-1"),
        SourceObservation(GroundingSource.VISUAL, "screenshot", "snap-1", "rev-1", "page-1"),
    )
    unified = UnifiedAffordance(
        "semantic:target",
        "button",
        "Blue point",
        frozenset({"point_activate"}),
        grounding_candidates=(candidate,),
    )
    model = DomAdapter().transduce("<main></main>", environment_revision="rev-1", snapshot_id="snap-1")
    snapshot = BrowserSnapshot(
        observation,
        affordance_model=replace(model, affordances=[legacy], kept_node_count=1),
        source_observations=source_observations,
        grounding_candidates=(candidate,),
        unified_affordances=(unified,),
    )
    state = StateKernel("task-1", "Click the blue SVG point")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click the blue SVG point",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("Blue point",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("Blue point",)),
        success=SuccessExpression(
            expression_id="success:blue-point",
            operator="criterion",
            criterion_id="criterion:blue-point",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="point",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.POINT_ACTIVATE,
        target_affordance_id="semantic:target",
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, snapshot)

    assert contract.affordance_id == "semantic:target"
    assert contract.grounding_candidate == candidate
    assert contract.parameters["action"] == {
        "name": "mouse_click",
        "arguments": {"x": 124.0, "y": 244.0},
    }
