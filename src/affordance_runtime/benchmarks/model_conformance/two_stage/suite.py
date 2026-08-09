"""Compose one exact-profile two-stage candidate without production adoption."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.model_policy.grounding import DecisionGroundingVariant

from ..contracts import ModelProfileIdentity
from ..matrix_progress import write_json_report
from ..matrix_runner import DecisionMatrixResult, run_decision_matrix
from ..scenario import build_live_dom_scenario
from .cases import build_critical_cases, build_recurrent_cases
from .contracts import PacingConfiguration, TwoStageRunMode
from .qualification import qualify_candidate
from .reporting import SingleStageBaselineSummary, TwoStageSuiteReport
from .runner import run_two_stage_matrix


async def run_candidate_suite(
    identity: ModelProfileIdentity,
    port_factory,
    *,
    repetitions: int,
    output_dir: Path,
    pacing: PacingConfiguration,
    support: bool = False,
    diagnostic: bool = False,
) -> TwoStageSuiteReport:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("two-stage runs require a new empty output directory")
    if support and diagnostic:
        raise ValueError("two-stage suite mode is ambiguous")
    if support and repetitions != 20:
        raise ValueError("two-stage support requires exactly 20 repetitions")
    if diagnostic and repetitions != 1:
        raise ValueError("two-stage remote diagnostic requires exactly one repetition")
    if not support and not diagnostic and repetitions != 5:
        raise ValueError("two-stage candidate requires exactly 5 repetitions")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario = await build_live_dom_scenario()
    recurrent = build_recurrent_cases(scenario.serialized_context)
    critical_cases = build_critical_cases(scenario.serialized_context)
    baseline = await run_decision_matrix(
        identity, port_factory, repetitions=repetitions,
        output_dir=output_dir / "single-stage-baseline",
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2,
        cases_override=recurrent,
    )
    routing = await _mode(
        identity, "routing", TwoStageRunMode.ROUTING_ONLY, port_factory,
        recurrent, repetitions, output_dir, pacing,
    )
    payload = await _mode(
        identity, "payload", TwoStageRunMode.PAYLOAD_ONLY, port_factory,
        recurrent, repetitions, output_dir, pacing,
    )
    end_to_end = await _mode(
        identity, "end-to-end", TwoStageRunMode.END_TO_END, port_factory,
        recurrent, repetitions, output_dir, pacing,
    )
    critical = await _mode(
        identity, "critical", TwoStageRunMode.END_TO_END, port_factory,
        critical_cases, repetitions if not support else 1, output_dir, pacing,
    )
    baseline_summary = _baseline(baseline)
    qualification = qualify_candidate(
        routing, payload, end_to_end, critical,
        baseline_success=baseline_summary.success_count,
        baseline_total=baseline_summary.attempt_count,
        support=support,
    )
    report = TwoStageSuiteReport(
        "two-stage-suite.v1", f"suite:{identity.provider_id}:{identity.model_id}",
        identity, "support" if support else "diagnostic" if diagnostic else "candidate",
        repetitions, pacing,
        baseline_summary, routing, payload, end_to_end, critical, qualification,
    )
    write_json_report(output_dir / "suite-report.json", asdict(report))
    return report


async def _mode(identity, label, mode, port_factory, cases, repetitions, output_dir, pacing):
    return await run_two_stage_matrix(
        run_id=f"run:{identity.provider_id}:{identity.model_id}:{label}", mode=mode,
        port_factory=port_factory, cases=cases, repetitions=repetitions,
        output_dir=output_dir / label, pacing=pacing,
    )


def _baseline(result: DecisionMatrixResult) -> SingleStageBaselineSummary:
    failures = Counter(item.failure_stage for item in result.attempts if item.failure_stage)
    return SingleStageBaselineSummary(
        result.success_count, len(result.attempts), len(result.attempts),
        sum(item.prompt_tokens for item in result.attempts),
        sum(item.completion_tokens for item in result.attempts),
        sum(item.latency_ms for item in result.attempts), tuple(sorted(failures.items())),
    )
