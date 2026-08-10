from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobTaskOutcome,
    ProviderCapacityEvidence,
)
from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobBreadthCase,
    MiniWobBreadthManifest,
)
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.runner import REQUIRED_METRICS, run_breadth_campaign
from affordance_runtime.benchmarks.external_smoke.pacing import FixedPacingState, PacedAgentPolicy
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    BenchmarkCaseResult,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    MetricMeasurement,
)
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest as target_manifest_digest
from affordance_runtime.model_policy import ModelBackedAgentPolicy
from affordance_runtime.model_policy.grounding import DecisionGroundingVariant
from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_port import ModelConfig


@pytest.fixture(autouse=True)
def _stable_final_git_identity(monkeypatch):
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner._final_git_identity",
        lambda: ("0" * 40, False),
    )


def test_fake_sixty_case_campaign_is_strict_complete_and_failure_tolerant(monkeypatch, tmp_path: Path) -> None:
    manifest = _manifest()
    results = _bound_results(manifest, failed=lambda index: index == 7)
    order: list[str] = []

    async def fake_run_suite(target_manifest, callback):
        assert [item.case_id for item in target_manifest.cases] == [item.case_id for item in manifest.cases]
        bound = _bind_target_results(results, target_manifest)
        for index, result in enumerate(bound, 1):
            order.append(result.case_id)
            callback(index, result)
        return BenchmarkSuiteResult(_target_identity(target_manifest), bound, BenchmarkAcceptance(True, ()), {})

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(run_breadth_campaign(
        manifest, _policy(), tmp_path / "run", provider_capacity=_capacity(manifest),
    ))
    assert order == [f"miniwob-60-{index:02d}" for index in range(1, 61)]
    assert outcome.acceptance.evidence_valid
    assert outcome.acceptance.completed_cases == 60
    assert outcome.acceptance.successful_cases == 59
    assert outcome.cases[6].outcome is MiniWobTaskOutcome.TURN_BUDGET_EXHAUSTED
    progress = (tmp_path / "run" / "campaign-progress.json").read_text()
    assert '"complete": true' in progress
    assert '"completed_cases": 60' in progress


def test_task_failure_does_not_invalidate_campaign_evidence(monkeypatch, tmp_path: Path) -> None:
    manifest = _manifest()
    results = _bound_results(manifest, failed=lambda _index: True)

    async def fake_run_suite(target_manifest, callback):
        bound = _bind_target_results(results, target_manifest)
        for index, result in enumerate(bound, 1):
            callback(index, result)
        return BenchmarkSuiteResult(_target_identity(target_manifest), bound, BenchmarkAcceptance(False, ("task failures",)), {})

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(run_breadth_campaign(
        manifest, _policy(), tmp_path / "failure-run", provider_capacity=_capacity(manifest),
    ))
    assert outcome.acceptance.evidence_valid
    assert outcome.acceptance.successful_cases == 0


def test_unclassified_campaign_cannot_be_accepted_as_evidence(monkeypatch, tmp_path: Path) -> None:
    manifest = _manifest()
    results = tuple(
        replace(item, case_failure_code="")
        for item in _bound_results(manifest, failed=lambda _index: True)
    )

    async def fake_run_suite(target_manifest, callback):
        bound = _bind_target_results(results, target_manifest)
        for index, result in enumerate(bound, 1):
            callback(index, result)
        return BenchmarkSuiteResult(_target_identity(target_manifest), bound, BenchmarkAcceptance(True, ()), {})

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(
        run_breadth_campaign(
            manifest, _policy(), tmp_path / "unclassified-run",
            provider_capacity=_capacity(manifest),
        )
    )
    assert not outcome.acceptance.evidence_valid
    assert len(outcome.acceptance.errors) == 60


def test_formal_acceptance_requires_explicit_provider_capacity(monkeypatch, tmp_path: Path) -> None:
    manifest = _manifest()
    results = _bound_results(manifest, failed=lambda _index: False)

    async def fake_run_suite(target_manifest, callback):
        bound = _bind_target_results(results, target_manifest)
        for index, result in enumerate(bound, 1):
            callback(index, result)
        return BenchmarkSuiteResult(
            _target_identity(target_manifest), bound, BenchmarkAcceptance(True, ()), {},
        )

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(run_breadth_campaign(
        manifest, _policy(), tmp_path / "no-capacity",
    ))
    assert not outcome.acceptance.evidence_valid
    assert "explicit provider capacity" in " ".join(outcome.acceptance.errors)


def test_spoofed_underlying_case_identity_is_rejected(monkeypatch, tmp_path: Path) -> None:
    manifest = _manifest()
    results = list(_bound_results(manifest, failed=lambda _index: False))
    results[0] = replace(results[0], case_id="spoofed-case")

    async def fake_run_suite(target_manifest, callback):
        bound = _bind_target_results(results, target_manifest)
        for index, result in enumerate(bound, 1):
            callback(index, result)
        return BenchmarkSuiteResult(
            _target_identity(target_manifest), bound, BenchmarkAcceptance(True, ()), {},
        )

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(run_breadth_campaign(
        manifest, _policy(), tmp_path / "spoofed",
        provider_capacity=_capacity(manifest),
    ))
    assert not outcome.acceptance.evidence_valid
    assert "underlying case identities" in " ".join(outcome.acceptance.errors)


def test_interrupted_campaign_stays_incomplete_and_cannot_resume(monkeypatch, tmp_path: Path) -> None:
    async def interrupted(_manifest_value, callback):
        callback(1, _result(1, failed=False))
        raise RuntimeError("interrupted")

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        interrupted,
    )
    output = tmp_path / "interrupted"
    try:
        asyncio.run(run_breadth_campaign(_manifest(), _policy(), output))
    except RuntimeError:
        pass
    progress = json.loads((output / "campaign-progress.json").read_text())
    assert progress["complete"] is False
    assert progress["completed_cases"] == 1
    try:
        asyncio.run(run_breadth_campaign(_manifest(), _policy(), output))
    except FileExistsError:
        pass
    else:
        raise AssertionError("campaign output directory was reused")


def test_pacing_state_is_shared_across_case_policy_wrappers() -> None:
    now = [0.0]
    waits: list[float] = []

    class Policy:
        async def decide(self, context):
            return context

    async def sleeper(delay):
        waits.append(delay)
        now[0] += delay

    state = FixedPacingState()
    first = PacedAgentPolicy(Policy(), 7.5, clock=lambda: now[0], sleeper=sleeper, state=state)
    second = PacedAgentPolicy(Policy(), 7.5, clock=lambda: now[0], sleeper=sleeper, state=state)
    asyncio.run(first.decide("first"))
    asyncio.run(second.decide("second"))
    assert waits == [7.5]
    assert state.calls == 2


def test_formal_runner_rejects_unbound_policy_before_creating_output(tmp_path: Path) -> None:
    output = tmp_path / "invalid-policy"
    with pytest.raises(TypeError, match="ModelBackedAgentPolicy"):
        asyncio.run(run_breadth_campaign(_manifest(), object(), output))
    assert not output.exists()


def _manifest() -> MiniWobBreadthManifest:
    cases = tuple(
        MiniWobBreadthCase(
            f"miniwob-60-{index:02d}", f"browsergym/miniwob.fake-{index:02d}",
            "current_primitives", ("activate",), 10, 120.0, 7,
        )
        for index in range(1, 61)
    )
    return MiniWobBreadthManifest(
        "miniwob-breadth-manifest.v1", "miniwob-60-seed7-v1", "browsergym-miniwob",
        "0.14.3", "7fd85d71a4b60325c6585396ec4f48377d049838", "sha256:registry",
        "sha256:inventory", "miniwob-60-seeded-breadth.v1", "mistral-medium-3-5",
        "format-only.v1", 7.5, cases,
    )


def _result(index: int, *, failed: bool) -> BenchmarkCaseResult:
    measurements = {name: MetricMeasurement(0, True) for name in REQUIRED_METRICS}
    measurements["official_success_count"] = MetricMeasurement(0 if failed else 1, True)
    measurements["observations"] = MetricMeasurement(2, True)
    measurements["policy_calls"] = MetricMeasurement(1, True)
    measurements["provider_attempts"] = MetricMeasurement(1, True)
    return BenchmarkCaseResult(
        f"miniwob-60-{index:02d}", "failed" if failed else "done", True, "", 2.0,
        measurements, case_failure_code="turn_budget_exhausted" if failed else "",
    )


def _identity(manifest) -> BenchmarkRunIdentity:
    return BenchmarkRunIdentity(
        "opaque-run", "0" * 40, False, manifest.campaign_id,
        breadth_manifest_digest(manifest),
        "mistral-format-only-v1", 7, "2026-08-10T00:00:00+00:00", "3.12", "test",
    )


def _bound_results(manifest, *, failed):
    identity = _identity(manifest)
    return tuple(
        replace(
            _result(index, failed=failed(index)),
            suite_id=identity.suite_id,
            profile_id=identity.profile_id,
            seed=identity.seed,
            manifest_digest=identity.manifest_digest,
            harness_schema_version=identity.harness_schema_version,
        )
        for index in range(1, 61)
    )


def _capacity(manifest) -> ProviderCapacityEvidence:
    return ProviderCapacityEvidence(
        "provider-capacity-preflight.v1", "mistral", manifest.model_profile,
        breadth_manifest_digest(manifest), 600, 600, True,
        manifest.grounding_profile, 0, 0,
    )


def _policy() -> ModelBackedAgentPolicy:
    port = SimpleNamespace(
        provider="mistral",
        model="mistral-medium-3-5",
        endpoint_class="test",
        last_call=None,
    )
    adapter = ModelPortDecisionAdapter(
        port,
        ModelConfig(timeout_s=30.0, rate_limit_retries=0, transient_retries=0),
        DecisionGroundingVariant.FORMAT_ONLY,
    )
    return ModelBackedAgentPolicy(adapter)


def _target_identity(target_manifest) -> BenchmarkRunIdentity:
    return replace(
        _identity(_manifest()),
        manifest_digest=target_manifest_digest(target_manifest),
    )


def _bind_target_results(results, target_manifest):
    identity = _target_identity(target_manifest)
    return tuple(
        replace(
            result,
            suite_id=identity.suite_id,
            profile_id=identity.profile_id,
            seed=identity.seed,
            manifest_digest=identity.manifest_digest,
        )
        for result in results
    )
