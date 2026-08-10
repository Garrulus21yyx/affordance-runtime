from __future__ import annotations

import asyncio
import json
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobBreadthCase,
    MiniWobBreadthManifest,
)
from affordance_runtime.benchmarks.external_breadth.runner import REQUIRED_METRICS, run_breadth_campaign
from affordance_runtime.benchmarks.external_smoke.pacing import FixedPacingState, PacedAgentPolicy
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    BenchmarkCaseResult,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    MetricMeasurement,
)


def test_fake_sixty_case_campaign_is_strict_complete_and_failure_tolerant(monkeypatch, tmp_path: Path) -> None:
    results = tuple(_result(index, failed=index == 7) for index in range(1, 61))
    order: list[str] = []

    async def fake_run_suite(manifest, callback):
        assert [item.case_id for item in manifest.cases] == [item.case_id for item in _manifest().cases]
        for index, result in enumerate(results, 1):
            order.append(result.case_id)
            callback(index, result)
        return BenchmarkSuiteResult(_identity(), results, BenchmarkAcceptance(True, ()), {})

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(run_breadth_campaign(_manifest(), object(), tmp_path / "run"))
    assert order == [f"miniwob-60-{index:02d}" for index in range(1, 61)]
    assert outcome.acceptance.evidence_valid
    assert outcome.acceptance.completed_cases == 60
    assert outcome.acceptance.successful_cases == 59
    assert outcome.cases[6].outcome is MiniWobTaskOutcome.TURN_BUDGET_EXHAUSTED
    progress = (tmp_path / "run" / "campaign-progress.json").read_text()
    assert '"complete": true' in progress
    assert '"completed_cases": 60' in progress


def test_task_failure_does_not_invalidate_campaign_evidence(monkeypatch, tmp_path: Path) -> None:
    results = tuple(_result(index, failed=True) for index in range(1, 61))

    async def fake_run_suite(_manifest_value, callback):
        for index, result in enumerate(results, 1):
            callback(index, result)
        return BenchmarkSuiteResult(_identity(), results, BenchmarkAcceptance(False, ("task failures",)), {})

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.external_breadth.runner.run_suite",
        fake_run_suite,
    )
    outcome = asyncio.run(run_breadth_campaign(_manifest(), object(), tmp_path / "failure-run"))
    assert outcome.acceptance.evidence_valid
    assert outcome.acceptance.successful_cases == 0


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
        asyncio.run(run_breadth_campaign(_manifest(), object(), output))
    except RuntimeError:
        pass
    progress = json.loads((output / "campaign-progress.json").read_text())
    assert progress["complete"] is False
    assert progress["completed_cases"] == 1
    try:
        asyncio.run(run_breadth_campaign(_manifest(), object(), output))
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


def _identity() -> BenchmarkRunIdentity:
    return BenchmarkRunIdentity(
        "opaque-run", "0" * 40, False, "miniwob-60-seed7-v1", "digest",
        "mistral-format-only-v1", 7, "2026-08-10T00:00:00+00:00", "3.12", "test",
    )
