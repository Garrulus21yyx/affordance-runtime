from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.active_perception import PerceptionResolutionStatus
from affordance_runtime.active_perception_flow import (
    ActivePerceptionFlow,
    ActivePerceptionFlowContext,
)
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    EvidenceKind,
    GroundingSource,
    PerceptionRequirements,
    SourceObservation,
    UnifiedAffordance,
)
from affordance_runtime.perception_session import PerceptionCapture, PerceptionSession
from affordance_runtime.unified_grounding import candidate_from_affordance


def _snapshot(sequence: int, *, resolved: bool) -> BrowserSnapshot:
    snapshot_id = f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        "<button>Save</button>" if resolved else "<main></main>",
        environment_revision="revision-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
    )
    observation = Observation(
        "revision-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
    )
    candidates = ()
    targets = ()
    if resolved:
        candidate = candidate_from_affordance(
            model.affordances[0],
            observation,
            semantic_target_id="semantic:save",
        )
        observation = Observation(
            "revision-1",
            snapshot_id=snapshot_id,
            page_revision="page-1",
            target_fingerprints={candidate.fingerprint_key: candidate.target_fingerprint},
        )
        candidates = (candidate,)
        targets = (
            UnifiedAffordance(
                "semantic:save",
                "button",
                "Save",
                frozenset({"activate"}),
                grounding_candidates=candidates,
            ),
        )
    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.STRUCTURAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM}),
        preferred_sources=(GroundingSource.DOM,),
        observation_budget=1,
        model_call_budget=0,
        latency_budget_ms=100,
        cost_budget=0.0,
    )
    return BrowserSnapshot(
        observation,
        model,
        source_observations=(
            SourceObservation(
                GroundingSource.DOM,
                "dom-adapter",
                snapshot_id,
                "revision-1",
                "page-1",
            ),
        ),
        grounding_candidates=candidates,
        unified_affordances=targets,
        active_perception_requests=(
            ()
            if resolved
            else (
                ActivePerceptionRequest(
                    "task:unresolved-target",
                    "semantic_target",
                    (GroundingSource.DOM,),
                    "semantic target is missing",
                ),
            )
        ),
        perception_requirements=requirements,
    )


def _snapshot_with_reobserve_and_spatial_gap() -> BrowserSnapshot:
    snapshot_id = "snapshot-spatial-gap"
    model = DomAdapter().transduce(
        '<input id="tt"><button>Submit</button>',
        environment_revision="revision-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
    )
    observation = Observation("revision-1", snapshot_id=snapshot_id, page_revision="page-1")
    candidate = candidate_from_affordance(
        model.affordances[0],
        observation,
        semantic_target_id="semantic:tt",
    )
    target = UnifiedAffordance(
        "semantic:tt",
        "textbox",
        "tt",
        frozenset({"type_text"}),
        grounding_candidates=(candidate,),
    )
    return BrowserSnapshot(
        observation,
        model,
        source_observations=(
            SourceObservation(GroundingSource.DOM, "dom-adapter", snapshot_id, "revision-1", "page-1"),
        ),
        grounding_candidates=(candidate,),
        unified_affordances=(target,),
        active_perception_requests=(
            ActivePerceptionRequest(
                "semantic:tt",
                "semantic_label",
                (GroundingSource.DOM,),
                "label reobservation requested by source arbitration",
            ),
        ),
        perception_requirements=PerceptionRequirements(
            required_properties=frozenset({EvidenceKind.SPATIAL}),
            acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.SVG}),
            preferred_sources=(GroundingSource.SVG, GroundingSource.DOM),
            observation_budget=1,
            model_call_budget=0,
            latency_budget_ms=100,
            cost_budget=0.0,
        ),
    )


@dataclass
class TargetedObserver:
    fail: bool = False
    calls: int = 0

    def capture(self) -> BrowserSnapshot:
        return _snapshot(1, resolved=False)

    def capture_targeted(self, requests: object) -> BrowserSnapshot:
        assert isinstance(requests, tuple) and len(requests) == 1
        self.calls += 1
        if self.fail:
            raise RuntimeError("controlled targeted capture failure")
        return _snapshot(2, resolved=True)


def _capture(snapshot: BrowserSnapshot) -> PerceptionCapture:
    return PerceptionCapture.from_browser_snapshot(snapshot)


def _context(snapshot: BrowserSnapshot) -> ActivePerceptionFlowContext:
    return ActivePerceptionFlowContext(
        snapshot=_capture(snapshot),
        run_id="run-1",
        task_revision=1,
        plan_version=0,
        active_subgoal_id="",
        state_version=0,
        remaining_observations=1,
        attempted_probe_fingerprints=frozenset(),
        effectful_action=False,
    )


def test_flow_returns_typed_resolution_from_targeted_capture_without_state_authority() -> None:
    observer = TargetedObserver()
    flow = ActivePerceptionFlow(PerceptionSession(observer))

    preparation = flow.prepare(_context(observer.capture()))
    result = flow.execute(preparation)

    assert preparation.decision is not None and preparation.decision.plan is not None
    assert preparation.selected_probe_fingerprint
    assert observer.calls == 1
    assert result.receipt.success
    assert result.targeted_snapshot is not None
    assert result.resolution.status == PerceptionResolutionStatus.RESOLVED


def test_flow_derives_required_evidence_probe_even_when_snapshot_has_reobserve_request() -> None:
    flow = ActivePerceptionFlow(PerceptionSession(TargetedObserver()))

    preparation = flow.prepare(
        ActivePerceptionFlowContext(
            snapshot=_capture(_snapshot_with_reobserve_and_spatial_gap()),
            run_id="run-1",
            task_revision=1,
            plan_version=0,
            active_subgoal_id="",
            state_version=0,
            remaining_observations=1,
            attempted_probe_fingerprints=frozenset(),
            effectful_action=True,
        )
    )

    assert preparation.decision is not None
    assert preparation.decision.plan is not None
    assert preparation.decision.plan.commands[0].scope.property_key == "spatial"
    assert preparation.decision.plan.commands[0].source == GroundingSource.SVG


def test_flow_returns_failed_receipt_and_no_delta_like_success_on_owner_failure() -> None:
    observer = TargetedObserver(fail=True)
    flow = ActivePerceptionFlow(PerceptionSession(observer))

    preparation = flow.prepare(_context(observer.capture()))
    result = flow.execute(preparation)

    assert observer.calls == 1
    assert not result.receipt.success
    assert result.receipt.error_code == "RuntimeError"
    assert result.targeted_snapshot is None
    assert result.resolution.status == PerceptionResolutionStatus.INCONCLUSIVE
