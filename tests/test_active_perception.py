import pytest
from pydantic import ValidationError

from affordance_runtime.active_perception import (
    ActivePerceptionController,
    EvidenceGap,
    EvidenceGapExtractor,
    EvidenceGapKind,
    ObservationContinuationPolicy,
    PerceptionResolution,
    PerceptionResolutionStatus,
    ProbeAvailability,
    ProbeBudget,
    ProbeBudgetPolicy,
    ProbeCapability,
    ProbeCommand,
    ProbeKind,
    ProbePlan,
    ProbeReceipt,
    ProbeScope,
    probe_fingerprint,
)
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, RiskLevel, Surface
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    EvidenceKind,
    GroundingSource,
    PerceptionRequirements,
    SourceObservation,
    UnifiedAffordance,
)
from affordance_runtime.perception_session import PerceptionCapture, PerceptionSession
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.unified_grounding import candidate_from_affordance
from affordance_runtime.unified_observation import (
    CoverageCompleteness,
    CoverageStatus,
    SourceCoverage,
    UnifiedObservation,
)
from affordance_runtime.verification.contracts import ObservationDisposition


def _capture(snapshot: BrowserSnapshot) -> PerceptionCapture:
    return PerceptionCapture.from_browser_snapshot(snapshot)


@pytest.mark.parametrize(
    ("loading", "stable", "coverage_gap", "expected"),
    (
        (False, True, False, ObservationDisposition.REUSE),
        (False, True, True, ObservationDisposition.AUGMENT_TARGETED),
        (False, False, False, ObservationDisposition.RECAPTURE),
        (True, True, False, ObservationDisposition.WAIT_AND_RECAPTURE),
    ),
)
def test_observation_continuation_policy_has_four_typed_states(
    loading: bool,
    stable: bool,
    coverage_gap: bool,
    expected: ObservationDisposition,
) -> None:
    coverage = (
        SourceCoverage(
            source=GroundingSource.DOM,
            capture_policy_id="bounded",
            captured_item_count=1,
            truncated=False,
            omitted_item_count_estimate=None,
            completeness=CoverageCompleteness.BOUNDED,
            status=CoverageStatus.REQUIRED_PROPERTY_UNOBSERVED,
        ),
    ) if coverage_gap else ()
    observation = UnifiedObservation(
        epoch_id="epoch:1",
        page_revision="page:1",
        environment_revision="environment:1",
        observed_text="",
        targets=(),
        source_coverage=coverage,
        artifact_refs=(),
        captured_at_s=1.0,
        digest="sha256:test",
        metadata={"loading": loading},
    )

    decision = ObservationContinuationPolicy().decide(
        observation,
        environment_stable=stable,
    )

    assert decision.disposition == expected
    assert decision.observation_ref == "epoch:1"


def _gap() -> EvidenceGap:
    return EvidenceGap(
        gap_id="gap-1",
        run_id="run-1",
        task_revision=1,
        entity_key="semantic:target",
        property_key="appearance",
        gap_kind=EvidenceGapKind.VISUAL_PROPERTY_UNKNOWN,
        required_evidence_kind=EvidenceKind.VISUAL_APPEARANCE,
        preferred_sources=(GroundingSource.SVG, GroundingSource.VISUAL),
        reason="visual appearance is required but missing",
        risk_relevance=RiskLevel.MEDIUM,
    )


def _capability(**updates: object) -> ProbeCapability:
    values: dict[str, object] = {
        "capability_id": "visual-target",
        "source": GroundingSource.VISUAL,
        "probe_kind": ProbeKind.GROUND_VISUAL_TARGET,
        "supported_evidence_kinds": frozenset({EvidenceKind.VISUAL_APPEARANCE}),
        "supported_properties": frozenset({"appearance"}),
        "expected_latency_ms": 500,
        "estimated_cost": 0.01,
        "model_calls": 1,
    }
    values.update(updates)
    return ProbeCapability(**values)


def _command(**updates: object) -> ProbeCommand:
    values: dict[str, object] = {
        "command_id": "command-1",
        "gap_ids": ("gap-1",),
        "capability_id": "visual-target",
        "based_on_state_version": 3,
        "based_on_snapshot_id": "snapshot-1",
        "source": GroundingSource.VISUAL,
        "probe_kind": ProbeKind.GROUND_VISUAL_TARGET,
        "scope": ProbeScope(entity_key="semantic:target", property_key="appearance"),
        "expected_evidence_kind": EvidenceKind.VISUAL_APPEARANCE,
        "expected_information": "current target appearance",
        "budget": ProbeBudget(observations=1, timeout_ms=500, model_calls=1, estimated_cost=0.01),
        "reason": "close the blocking visual evidence gap",
    }
    values.update(updates)
    return ProbeCommand(**values)


def _visual_snapshot(*, stale: bool = False, orphan: bool = False, conflict: bool = False) -> BrowserSnapshot:
    snapshot_id = "snapshot-2" if stale else "snapshot-1"
    model = DomAdapter().transduce(
        "<main></main>",
        environment_revision="revision-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
    )
    affordance = Affordance(
        "visual-target",
        Surface.VISUAL,
        "region",
        "Blue target",
        "point_activate",
        {"bbox": [10, 20, 30, 40], "screenshot_ref": "screen.png"},
        AffordanceLease.issue(
            environment_revision="revision-1",
            snapshot_id="snapshot-1",
            page_revision="page-1",
            target_fingerprint="visual-fingerprint",
        ),
        backend_candidates=["visual"],
        evidence=["screen.png", "region-proposal.json"],
    )
    candidate_observation = Observation(
        "revision-1",
        screenshot_ref="screen.png",
        snapshot_id="snapshot-1",
        page_revision="page-1",
    )
    candidate = candidate_from_affordance(
        affordance,
        candidate_observation,
        semantic_target_id="semantic:visual-target",
        image_size=(100, 100),
    )
    observation = Observation(
        "revision-1",
        screenshot_ref="screen.png",
        snapshot_id=snapshot_id,
        page_revision="page-1",
        target_fingerprints={candidate.fingerprint_key: candidate.target_fingerprint},
    )
    target = UnifiedAffordance(
        candidate.semantic_target_id,
        "region",
        "Blue target",
        frozenset({"point_activate"}),
        unresolved_conflicts=(("appearance:conflict",) if conflict else ()),
        grounding_candidates=(candidate,),
    )
    return BrowserSnapshot(
        observation,
        model,
        source_observations=(
            SourceObservation(
                GroundingSource.VISUAL,
                "playwright-screenshot",
                snapshot_id,
                "revision-1",
                "page-1",
                artifact_refs=("screen.png",),
            ),
        ),
        grounding_candidates=(candidate,),
        unified_affordances=(() if orphan else (target,)),
        perception_requirements=PerceptionRequirements(
            required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
            acceptable_evidence=frozenset({GroundingSource.VISUAL}),
            preferred_sources=(GroundingSource.VISUAL,),
            model_call_budget=1,
            cost_budget=1.0,
        ),
    )


def test_probe_budget_policy_never_expands_declared_model_cost_or_latency() -> None:
    policy = ProbeBudgetPolicy()

    authority = policy.remaining_authority(
        PerceptionRequirements(
            observation_budget=1,
            model_call_budget=0,
            latency_budget_ms=499,
            cost_budget=0.0,
        ),
        remaining_observations=3,
    )

    assert authority == ProbeBudget(
        observations=1,
        timeout_ms=499,
        model_calls=0,
        estimated_cost=0.0,
        artifacts=1,
    )
    decision = ActivePerceptionController().decide(
        (_gap(),),
        (_capability(expected_latency_ms=500, estimated_cost=0.01, model_calls=1),),
        based_on_state_version=0,
        based_on_snapshot_id="snapshot-1",
        budget=authority,
    )
    assert decision.plan is None
    assert decision.resolution is not None
    assert decision.resolution.status == PerceptionResolutionStatus.INCONCLUSIVE


def test_semantic_evidence_requires_current_linked_nonconflicting_candidate() -> None:
    extractor = EvidenceGapExtractor()

    current = extractor.extract(_capture(_visual_snapshot()), run_id="run", task_revision=1)
    orphan = extractor.extract(
        _capture(_visual_snapshot(orphan=True)), run_id="run", task_revision=1
    )
    stale = extractor.extract(
        _capture(_visual_snapshot(stale=True)), run_id="run", task_revision=1
    )
    conflict = extractor.extract(
        _capture(_visual_snapshot(conflict=True)), run_id="run", task_revision=1
    )

    assert not any(item.required_evidence_kind == EvidenceKind.VISUAL_APPEARANCE for item in current)
    assert any(item.required_evidence_kind == EvidenceKind.VISUAL_APPEARANCE for item in orphan)
    assert any(item.required_evidence_kind == EvidenceKind.VISUAL_APPEARANCE for item in stale)
    assert any(item.required_evidence_kind == EvidenceKind.VISUAL_APPEARANCE for item in conflict)


def test_screenshot_transport_alone_does_not_close_visual_evidence_gap() -> None:
    snapshot = _visual_snapshot(orphan=True)

    gaps = EvidenceGapExtractor().extract(_capture(snapshot), run_id="run", task_revision=1)

    assert snapshot.source_observations[0].artifact_refs == ("screen.png",)
    assert any(item.gap_kind == EvidenceGapKind.VISUAL_PROPERTY_UNKNOWN for item in gaps)


def test_active_perception_contracts_round_trip_without_execution_authority() -> None:
    gap = _gap()
    capability = _capability()
    command = _command()
    plan = ProbePlan(
        plan_id="probe-plan-1",
        based_on_state_version=3,
        based_on_snapshot_id="snapshot-1",
        gap_ids=(gap.gap_id,),
        commands=(command,),
        stop_conditions=("blocking_gap_resolved", "budget_exhausted"),
        total_budget=command.budget,
    )
    receipt = ProbeReceipt(
        command_id=command.command_id,
        started_at_s=1.0,
        completed_at_s=1.5,
        observation_epoch_id="snapshot-2",
        source=capability.source,
        success=True,
        assertion_refs=("assertion-2",),
        latency_ms=500,
        model_calls=1,
        estimated_cost=0.01,
    )
    resolution = PerceptionResolution(
        status=PerceptionResolutionStatus.RESOLVED,
        based_on_snapshot_id="snapshot-1",
        observation_epoch_id="snapshot-2",
        resolved_gap_ids=(gap.gap_id,),
        accepted_assertion_refs=("assertion-2",),
        probe_receipts=(receipt,),
        reason="fresh visual assertion resolved the gap",
    )

    assert EvidenceGap.model_validate_json(gap.model_dump_json()) == gap
    assert ProbeCapability.model_validate_json(capability.model_dump_json()) == capability
    assert ProbePlan.model_validate_json(plan.model_dump_json()) == plan
    assert PerceptionResolution.model_validate_json(resolution.model_dump_json()) == resolution
    assert "selector" not in plan.model_dump_json()
    assert "coordinate" not in plan.model_dump_json()


def test_effectful_or_cross_source_calibrated_probe_capability_is_rejected() -> None:
    with pytest.raises(ValidationError, match="read-only"):
        _capability(side_effect_class=OperationClass.REVERSIBLE_WRITE)
    with pytest.raises(ValidationError, match="cross-source"):
        _capability(confidence_semantics="globally_comparable")


def test_probe_plan_rejects_stale_binding_unknown_gap_and_budget_overrun() -> None:
    with pytest.raises(ValidationError, match="state and snapshot"):
        ProbePlan(
            plan_id="probe-plan-stale",
            based_on_state_version=4,
            based_on_snapshot_id="snapshot-1",
            gap_ids=("gap-1",),
            commands=(_command(),),
            stop_conditions=("budget_exhausted",),
            total_budget=_command().budget,
        )
    with pytest.raises(ValidationError, match="outside the plan"):
        ProbePlan(
            plan_id="probe-plan-unknown",
            based_on_state_version=3,
            based_on_snapshot_id="snapshot-1",
            gap_ids=("gap-other",),
            commands=(_command(),),
            stop_conditions=("budget_exhausted",),
            total_budget=_command().budget,
        )
    with pytest.raises(ValidationError, match="exceed"):
        ProbePlan(
            plan_id="probe-plan-over-budget",
            based_on_state_version=3,
            based_on_snapshot_id="snapshot-1",
            gap_ids=("gap-1",),
            commands=(_command(),),
            stop_conditions=("budget_exhausted",),
            total_budget=ProbeBudget(observations=1, timeout_ms=100, model_calls=0, estimated_cost=0.0),
        )


def test_unavailable_capability_is_typed_but_not_promoted_to_available() -> None:
    capability = _capability(availability=ProbeAvailability.UNAVAILABLE)
    assert capability.availability == ProbeAvailability.UNAVAILABLE


def test_blocked_resolution_must_explicitly_block_effectful_action() -> None:
    with pytest.raises(ValidationError, match="must block"):
        PerceptionResolution(
            status=PerceptionResolutionStatus.BLOCKED,
            based_on_snapshot_id="snapshot-1",
            observation_epoch_id="snapshot-2",
            unresolved_gap_ids=("gap-1",),
            reason="material conflict remains",
        )


def test_controller_selects_minimum_cost_preferred_read_only_probe() -> None:
    gap = _gap()
    svg = _capability(
        capability_id="svg-geometry",
        source=GroundingSource.SVG,
        probe_kind=ProbeKind.EXTRACT_SVG_GEOMETRY,
        expected_latency_ms=50,
        estimated_cost=0.0,
        model_calls=0,
    )
    visual = _capability()

    decision = ActivePerceptionController().decide(
        (gap,),
        (visual, svg),
        based_on_state_version=3,
        based_on_snapshot_id="snapshot-1",
        budget=ProbeBudget(observations=1, timeout_ms=1_000, model_calls=1, estimated_cost=1.0),
    )

    assert decision.plan is not None
    assert decision.plan.commands[0].capability_id == "svg-geometry"
    assert decision.plan.commands[0].source == GroundingSource.SVG


def test_controller_does_not_repeat_equivalent_probe_and_blocks_effectful_action() -> None:
    gap = _gap()
    capability = _capability()

    decision = ActivePerceptionController().decide(
        (gap,),
        (capability,),
        based_on_state_version=3,
        based_on_snapshot_id="snapshot-1",
        budget=ProbeBudget(observations=1, timeout_ms=1_000, model_calls=1, estimated_cost=1.0),
        attempted_probe_fingerprints=frozenset({probe_fingerprint(capability, gap)}),
        effectful_action=True,
    )

    assert decision.plan is None
    assert decision.resolution is not None
    assert decision.resolution.status == PerceptionResolutionStatus.BLOCKED
    assert decision.resolution.blocks_effectful_action


def test_controller_rejects_unavailable_irrelevant_and_over_budget_probes() -> None:
    gap = _gap()
    unavailable = _capability(availability=ProbeAvailability.UNAVAILABLE)
    irrelevant = _capability(
        capability_id="device",
        source=GroundingSource.WOT,
        probe_kind=ProbeKind.READ_DEVICE_PROPERTY,
        supported_evidence_kinds=frozenset({EvidenceKind.DEVICE_STATE}),
        supported_properties=frozenset({"power"}),
    )
    expensive = _capability(expected_latency_ms=2_000, model_calls=2, estimated_cost=2.0)

    decision = ActivePerceptionController().decide(
        (gap,),
        (unavailable, irrelevant, expensive),
        based_on_state_version=3,
        based_on_snapshot_id="snapshot-1",
        budget=ProbeBudget(observations=1, timeout_ms=500, model_calls=1, estimated_cost=1.0),
    )

    assert decision.plan is None
    assert decision.resolution is not None
    assert decision.resolution.status == PerceptionResolutionStatus.INCONCLUSIVE


def test_gap_extractor_derives_missing_visual_requirement_with_task_risk() -> None:
    model = DomAdapter().transduce(
        '<button id="save">Save</button>',
        environment_revision="revision-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
    )
    observation = Observation(
        "revision-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    snapshot = BrowserSnapshot(
        observation,
        model,
        source_observations=(
            SourceObservation(
                GroundingSource.DOM,
                "dom-test",
                "snapshot-1",
                "revision-1",
                "page-1",
            ),
        ),
        perception_requirements=PerceptionRequirements(
            required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
            acceptable_evidence=frozenset({GroundingSource.SVG, GroundingSource.VISUAL}),
            preferred_sources=(GroundingSource.SVG, GroundingSource.VISUAL),
            observation_budget=1,
            model_call_budget=1,
            cost_budget=1.0,
            risk=RiskLevel.HIGH,
        ),
    )

    gaps = EvidenceGapExtractor().extract(
        _capture(snapshot),
        run_id="run-1",
        task_revision=2,
        plan_version=3,
        active_step_id="inspect-visual",
    )

    by_kind = {item.gap_kind: item for item in gaps}
    assert set(by_kind) == {
        EvidenceGapKind.AMBIGUOUS_TARGET,
        EvidenceGapKind.VISUAL_PROPERTY_UNKNOWN,
    }
    visual_gap = by_kind[EvidenceGapKind.VISUAL_PROPERTY_UNKNOWN]
    target_gap = by_kind[EvidenceGapKind.AMBIGUOUS_TARGET]
    assert visual_gap.required_evidence_kind == EvidenceKind.VISUAL_APPEARANCE
    assert visual_gap.risk_relevance == RiskLevel.HIGH
    assert visual_gap.task_revision == 2
    assert visual_gap.plan_version == 3
    assert target_gap.entity_key == "task:unresolved-target"
    assert target_gap.property_key == "semantic_target"


def test_probe_fingerprint_allows_retry_after_a_fresh_gap_epoch() -> None:
    capability = _capability()
    first = _gap()
    fresh = first.model_copy(update={"gap_id": "gap-2"})

    assert probe_fingerprint(capability, first) != probe_fingerprint(capability, fresh)


def test_source_conflict_prefers_an_independent_source_before_cost() -> None:
    gap = _gap().model_copy(
        update={
            "gap_kind": EvidenceGapKind.SOURCE_CONFLICT,
            "current_sources": (GroundingSource.SVG,),
        }
    )
    same_source = _capability(
        capability_id="same-source",
        source=GroundingSource.SVG,
        probe_kind=ProbeKind.EXTRACT_SVG_GEOMETRY,
        expected_latency_ms=1,
        estimated_cost=0.0,
        model_calls=0,
    )
    independent = _capability(
        capability_id="independent-source",
        source=GroundingSource.VISUAL,
        expected_latency_ms=500,
        estimated_cost=0.01,
        model_calls=1,
    )

    decision = ActivePerceptionController().decide(
        (gap,),
        (same_source, independent),
        based_on_state_version=3,
        based_on_snapshot_id="snapshot-1",
        budget=ProbeBudget(observations=1, timeout_ms=1_000, model_calls=1, estimated_cost=1.0),
    )

    assert decision.plan is not None
    assert decision.plan.commands[0].capability_id == "independent-source"


def test_targeted_capture_rejects_cross_epoch_source_mixture() -> None:
    model = DomAdapter().transduce(
        '<button id="save">Save</button>',
        environment_revision="revision-1",
        snapshot_id="snapshot-2",
        page_revision="page-1",
    )
    snapshot = BrowserSnapshot(
        Observation("revision-1", snapshot_id="snapshot-2", page_revision="page-1"),
        model,
        source_observations=(
            SourceObservation(
                GroundingSource.DOM,
                "dom-test",
                "snapshot-old",
                "revision-1",
                "page-1",
            ),
        ),
    )

    class MixedEpochObserver:
        def capture(self) -> BrowserSnapshot:
            return snapshot

        def capture_targeted(self, requests: object) -> BrowserSnapshot:
            del requests
            return snapshot

    request = ActivePerceptionRequest(
        "semantic:save",
        "visible",
        (GroundingSource.DOM,),
        "refresh current visibility",
    )

    with pytest.raises(ValueError, match="coherent epoch"):
        PerceptionSession(MixedEpochObserver()).capture_targeted((request,))
