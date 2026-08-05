from dataclasses import replace

import pytest

from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, Surface
from affordance_runtime.grounding import GroundingSource, PerceptionRequirements, UnifiedAffordance
from affordance_runtime.route_calibration import (
    RouteCalibrator,
    RouteOutcome,
    RouteOutcomeStatus,
    RouteScope,
)
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    UnifiedRoutePlanner,
    candidate_fingerprints,
    candidate_from_affordance,
)
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
)


def _scope(source: GroundingSource, *, environment: str = "settings-ui") -> RouteScope:
    return RouteScope(
        environment_family=environment,
        action_kind="activate",
        source=source,
        executor="visual" if source == GroundingSource.SOM else "dom",
        verifier_kinds=("dom_contains",),
    )


def _report(
    status: VerificationStatus,
    *,
    source: str = "post_action_observation",
    snapshot_id: str = "post-1",
) -> VerificationReport:
    return VerificationReport(
        status,
        evidence=[
            VerificationEvidence(
                verifier_kind="dom_contains",
                target="saved",
                passed=status == VerificationStatus.PASSED,
                source=source,
                evidence_id="evidence-1",
                snapshot_id=snapshot_id,
                strength="strong",
            )
        ],
    )


def _outcome(
    source: GroundingSource,
    status: VerificationStatus,
    *,
    environment: str = "settings-ui",
    evidence_source: str = "post_action_observation",
) -> RouteOutcome:
    return RouteOutcome.from_verification(
        outcome_id=f"outcome-{source.value}-{status.value}",
        scope=_scope(source, environment=environment),
        semantic_target_id="semantic:save",
        candidate_id=f"candidate:{source.value}",
        contract_id=f"contract:{source.value}",
        report=_report(status, source=evidence_source),
        post_snapshot_id="post-1",
        latency_ms=12,
        expected_cost=0.1,
    )


def _target(variant: str) -> tuple[UnifiedAffordance, Observation]:
    observation = Observation(
        "rev-1",
        snapshot_id=f"snap-{variant}",
        page_revision="page-1",
        metadata={"environment_family": "settings-ui"},
    )

    def affordance(identity: str, surface: Surface, backend: str) -> Affordance:
        lease = AffordanceLease.issue(
            environment_revision="rev-1",
            snapshot_id=f"snap-{variant}",
            page_revision="page-1",
            target_fingerprint=f"fp-{identity}",
            ttl_ms=60_000,
        )
        locator = (
            {"bid": identity}
            if surface == Surface.DOM
            else {"mark_id": identity, "bbox": [10, 10, 40, 20]}
        )
        return Affordance(
            identity,
            surface,
            "button",
            "Save",
            "click",
            locator,
            lease,
            backend_candidates=[backend],
            confidence=0.9,
        )

    dom = candidate_from_affordance(
        affordance(f"save-dom-{variant}", Surface.DOM, "dom"),
        observation,
        semantic_target_id="pending",
    )
    visual = candidate_from_affordance(
        affordance(f"save-visual-{variant}", Surface.VISUAL, "visual"),
        observation,
        semantic_target_id="pending",
        image_size=(800, 600),
    )
    target = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor("button", "Save", "click", "settings", dom),
            CandidateDescriptor("button", "Save", "click", "settings", visual),
        )
    )[0]
    return target, replace(observation, target_fingerprints=candidate_fingerprints((target,)))


def test_receipt_only_verification_is_inconclusive_and_cannot_train_reliability() -> None:
    calibrator = RouteCalibrator()
    outcome = _outcome(
        GroundingSource.DOM,
        VerificationStatus.PASSED,
        evidence_source="execution_receipt",
    )

    calibrator.record(outcome)

    assert outcome.status == RouteOutcomeStatus.INCONCLUSIVE
    assert calibrator.get(outcome.scope).verified_attempts == 0
    assert calibrator.get(outcome.scope).inconclusive == 1
    assert calibrator.failure_component(outcome.scope) is None


def test_weak_state_delta_evidence_is_inconclusive_and_cannot_train_reliability() -> None:
    calibrator = RouteCalibrator()
    report = _report(VerificationStatus.PASSED)
    report = replace(
        report,
        evidence=[
            replace(
                report.evidence[0],
                verifier_kind="state_delta_or_terminal",
                strength="weak",
            )
        ],
    )
    outcome = RouteOutcome.from_verification(
        outcome_id="outcome-weak-state-delta",
        scope=_scope(GroundingSource.DOM),
        semantic_target_id="semantic:save",
        candidate_id="candidate:dom",
        contract_id="contract:dom",
        report=report,
        post_snapshot_id="post-1",
        latency_ms=12,
        expected_cost=0.1,
    )

    calibrator.record(outcome)

    assert outcome.status == RouteOutcomeStatus.INCONCLUSIVE
    assert calibrator.get(outcome.scope).verified_attempts == 0


def test_internally_inconsistent_verification_report_cannot_train_success() -> None:
    report = _report(VerificationStatus.PASSED)
    report = replace(report, evidence=[replace(report.evidence[0], passed=False)])

    outcome = RouteOutcome.from_verification(
        outcome_id="outcome-inconsistent-report",
        scope=_scope(GroundingSource.DOM),
        semantic_target_id="semantic:save",
        candidate_id="candidate:dom",
        contract_id="contract:dom",
        report=report,
        post_snapshot_id="post-1",
        latency_ms=12,
        expected_cost=0.1,
    )

    assert outcome.status == RouteOutcomeStatus.INCONCLUSIVE


def test_verified_route_statistics_are_scoped_by_environment_action_source_and_verifier() -> None:
    calibrator = RouteCalibrator()
    failed = _outcome(GroundingSource.DOM, VerificationStatus.FAILED)
    succeeded = _outcome(GroundingSource.SOM, VerificationStatus.PASSED)
    calibrator.record(failed)
    calibrator.record(succeeded)
    calibrator.record(replace(failed, outcome_id="outcome-dom-failed-2"))
    calibrator.record(replace(succeeded, outcome_id="outcome-som-passed-2"))

    assert calibrator.failure_component(failed.scope) == 1.0
    assert calibrator.failure_component(succeeded.scope) == 0.0
    assert calibrator.failure_component(replace(failed.scope, environment_family="other-ui")) is None
    assert calibrator.failure_component(replace(failed.scope, action_kind="type_text")) is None
    assert calibrator.failure_component(replace(failed.scope, verifier_kinds=("http_json",))) is None

    with pytest.raises(ValueError, match="already recorded"):
        calibrator.record(failed)


def test_verifier_calibration_improves_held_out_candidate_route_without_cross_environment_leakage() -> None:
    baseline_target, baseline_observation = _target("baseline")
    calibrator = RouteCalibrator()
    planner = UnifiedRoutePlanner(calibrator=calibrator)
    requirements = PerceptionRequirements(
        preferred_sources=(GroundingSource.DOM, GroundingSource.SOM),
    )

    initial = planner.plan(
        baseline_target,
        action="activate",
        requirements=requirements,
        observation=baseline_observation,
        available_executors=frozenset({"dom", "visual"}),
        verifier_kinds=("dom_contains",),
        environment_scope="settings-ui",
    )
    assert initial.selected_candidate.source == GroundingSource.DOM

    calibrator.record(_outcome(GroundingSource.DOM, VerificationStatus.FAILED))
    calibrator.record(_outcome(GroundingSource.SOM, VerificationStatus.PASSED))
    calibrator.record(
        replace(
            _outcome(GroundingSource.DOM, VerificationStatus.FAILED),
            outcome_id="outcome-dom-failed-2",
        )
    )
    calibrator.record(
        replace(
            _outcome(GroundingSource.SOM, VerificationStatus.PASSED),
            outcome_id="outcome-som-passed-2",
        )
    )
    held_out_target, held_out_observation = _target("shifted-layout")
    held_out = planner.plan(
        held_out_target,
        action="activate",
        requirements=requirements,
        observation=held_out_observation,
        available_executors=frozenset({"dom", "visual"}),
        verifier_kinds=("dom_contains",),
        environment_scope="settings-ui",
    )
    unrelated_environment = planner.plan(
        held_out_target,
        action="activate",
        requirements=requirements,
        observation=held_out_observation,
        available_executors=frozenset({"dom", "visual"}),
        verifier_kinds=("dom_contains",),
        environment_scope="other-ui",
    )

    assert held_out.selected_candidate.source == GroundingSource.SOM
    assert held_out.selected_candidate.candidate_id != initial.selected_candidate.candidate_id
    assert (initial.selected_candidate.source == GroundingSource.SOM) is False
    assert (held_out.selected_candidate.source == GroundingSource.SOM) is True
    assert unrelated_environment.selected_candidate.source == GroundingSource.DOM
