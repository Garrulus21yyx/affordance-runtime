"""Strictly serial MiniWoB breadth execution through the existing AgentLoop."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignAcceptance,
    MiniWobBreadthCampaignOutcome,
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
)
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthManifest
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.progress import CampaignProgressWriter, ProgressEventObserver
from affordance_runtime.benchmarks.external_smoke.adapter_conformance import InstrumentedBrowserGymEnvironment
from affordance_runtime.benchmarks.external_smoke.browsergym_environment import BrowserGymMiniWobEnvironment
from affordance_runtime.benchmarks.external_smoke.composition import BrowserGymMechanicalActionEvaluator
from affordance_runtime.benchmarks.external_smoke.environment import ExternalEnvironmentTaskEvaluator
from affordance_runtime.benchmarks.external_smoke.pacing import (
    FixedPacingState,
    PacedAgentPolicy,
    validate_pacing_budget,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCase,
    BenchmarkComposition,
    BenchmarkManifest,
    CaseFailureOrigin,
    MetricMeasurement,
    TerminalReasonCode,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.model_policy import ModelBackedAgentPolicy

REQUIRED_METRICS = (
    "observations", "executions", "turns", "currentness_probes",
    "browsergym_reset_calls", "browsergym_step_calls", "browsergym_probe_calls",
    "click_calls", "fill_calls", "select_calls", "policy_calls", "provider_attempts",
    "prompt_tokens", "completion_tokens", "total_tokens", "model_latency_ms",
    "already_satisfied_suppressions", "no_progress_terminations", "official_success_count",
    "sent_unknown_count", "duplicate_unknown_attempts", "forbidden_effect_attempts",
    "stale_zero_call_violations", "provider_retry_count", "fallback_count", "cleanup_failures",
)
_TERMINAL_STATUSES = tuple(item for item in AgentLoopStatus if item is not AgentLoopStatus.RUNNING)


async def run_breadth_campaign(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    output_dir: Path,
) -> MiniWobBreadthCampaignOutcome:
    if len(manifest.cases) != 60:
        raise ValueError("formal breadth campaign requires exactly 60 frozen cases")
    for case in manifest.cases:
        validate_pacing_budget(case.max_turns, manifest.minimum_policy_call_interval_s, case.timeout_s, 5.0)
    output_dir.mkdir(parents=True, exist_ok=False)
    digest = breadth_manifest_digest(manifest)
    run_id = f"miniwob-60:{uuid.uuid4().hex}"
    progress = CampaignProgressWriter(
        output_dir / "campaign-progress.json", manifest.campaign_id, run_id,
        _git_sha(), digest, len(manifest.cases),
    )
    progress.write()
    pacing_state = FixedPacingState()
    instrumentations: list[BenchmarkInstrumentation] = []
    target_manifest = _target_manifest(manifest, policy, pacing_state, instrumentations)
    suite = await run_suite(target_manifest, _progress_callback(progress))
    suite = replace(suite, cases=tuple(_derived_metrics(item) for item in suite.cases))
    records = tuple(
        _record(case, result) for case, result in zip(manifest.cases, suite.cases, strict=True)
    )
    provider, model, grounding = _model_identity(instrumentations)
    acceptance = _accept_campaign(manifest, suite, records, provider, model, grounding)
    progress.completed_cases = len(records)
    progress.success_count = acceptance.successful_cases
    progress.failure_category_counts = _outcome_counts(records)
    progress.provider_attempts = sum(_integer(item.result, "provider_attempts") for item in records)
    progress.total_tokens = sum(_integer(item.result, "total_tokens") for item in records)
    progress.model_latency_ms = sum(_number(item.result, "model_latency_ms") for item in records)
    progress.write(current_case_id=records[-1].case_id, complete=True)
    return MiniWobBreadthCampaignOutcome(
        run_id, manifest, digest, suite, records, acceptance, provider, model, grounding,
    )


def _target_manifest(manifest, policy, pacing_state, instrumentations) -> BenchmarkManifest:
    cases = tuple(
        _target_case(item, manifest, policy, pacing_state, instrumentations)
        for item in manifest.cases
    )
    return BenchmarkManifest(
        manifest.schema_version, manifest.campaign_id, "mistral-format-only-v1", 7, cases,
    )


def _target_case(case, manifest, base_policy, pacing_state, instrumentations) -> BenchmarkCase:
    holder: dict[str, object] = {}
    admitted = frozenset(item.task_id for item in manifest.cases)

    def environment_factory(instrumentation):
        try:
            environment, task = BrowserGymMiniWobEnvironment.open(
                case.task_id, case.seed, max_turns=case.max_turns, admitted_task_ids=admitted,
            )
        except BaseException as exc:
            _initialize_custom_metrics(instrumentation)
            if isinstance(exc, Exception):
                instrumentation.record_failure(
                    CaseFailureOrigin.ENVIRONMENT_RESET, "browsergym_open_exception", exc,
                )
            raise
        holder.update(environment=environment, task=task)
        return _BreadthEnvironment(environment, instrumentation)

    def task_factory():
        return holder["task"]

    def composition_factory(instrumentation):
        environment = holder["environment"]
        _initialize_custom_metrics(instrumentation)
        instrumentations.append(instrumentation)
        observer = ProgressEventObserver(instrumentation)
        paced = PacedAgentPolicy(
            base_policy, manifest.minimum_policy_call_interval_s,
            state=pacing_state, context_observer=observer,
        )
        return BenchmarkComposition(
            paced,
            BrowserGymMechanicalActionEvaluator(),
            ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
        )

    return BenchmarkCase(
        case.case_id, manifest.campaign_id, case.capability_profile,
        task_factory, environment_factory, composition_factory, _TERMINAL_STATUSES,
        case.timeout_s, case.seed, REQUIRED_METRICS,
    )


class _BreadthEnvironment(InstrumentedBrowserGymEnvironment):
    async def close(self):
        try:
            await super().close()
        finally:
            self.instrumentation.set_custom_metric(
                "click_calls",
                max(0, self.wrapped.dom_action_calls - self.wrapped.fill_calls - self.wrapped.select_calls),
            )


def _initialize_custom_metrics(instrumentation: BenchmarkInstrumentation) -> None:
    for name in (
        "browsergym_reset_calls", "browsergym_step_calls", "browsergym_probe_calls",
        "dom_action_calls", "click_calls", "fill_calls", "select_calls",
        "official_verifier_queries", "official_success_count", "fallback_count",
        "already_satisfied_suppressions", "no_progress_terminations",
    ):
        if name not in instrumentation.custom_metrics:
            instrumentation.set_custom_metric(name, 0)


def _derived_metrics(result):
    values = dict(result.measurements)
    values["no_progress_terminations"] = MetricMeasurement(
        int(result.terminal_reason_code is TerminalReasonCode.NO_PROGRESS_REPETITION), True,
    )
    retry = values.get("provider_retry_count")
    if retry is not None and retry.value == -1:
        values["provider_retry_count"] = MetricMeasurement(0, True)
    for name in REQUIRED_METRICS:
        if name not in values:
            values[name] = MetricMeasurement(0, True)
    return replace(result, measurements=values)


def _record(case, result) -> MiniWobBreadthCaseRecord:
    classified = classify_case(result)
    return MiniWobBreadthCaseRecord(
        case.case_id,
        case.task_id.removeprefix("browsergym/miniwob."),
        case.capability_profile,
        case.required_primitives,
        classified.outcome,
        classified.source,
        result,
    )


def _accept_campaign(manifest, suite, records, provider, model, grounding) -> MiniWobBreadthCampaignAcceptance:
    errors: list[str] = []
    identities = tuple(item.case_id for item in records)
    expected = tuple(item.case_id for item in manifest.cases)
    if len(records) != 60 or identities != expected or len(set(identities)) != 60:
        errors.append("campaign result set does not match the frozen 60-case manifest")
    if suite.identity.git_dirty:
        errors.append("campaign git tree is dirty")
    if provider != "mistral" or model != manifest.model_profile or grounding != manifest.grounding_profile:
        errors.append("campaign model identity does not match the frozen profile")
    for record in records:
        missing = [name for name in REQUIRED_METRICS if not record.result.measurements[name].measured]
        if missing:
            errors.append(f"{record.case_id}: required metrics are incomplete")
    for name in (
        "provider_retry_count", "fallback_count", "cleanup_failures",
        "forbidden_effect_attempts", "duplicate_unknown_attempts", "stale_zero_call_violations",
    ):
        if sum(_integer(item.result, name) for item in records):
            errors.append(f"campaign safety metric {name} is nonzero")
    successful = sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in records)
    return MiniWobBreadthCampaignAcceptance(not errors, tuple(errors), 60, len(records), successful)


def _progress_callback(progress: CampaignProgressWriter):
    def completed(index, result):
        outcome = classify_case(_derived_metrics(result)).outcome.value
        progress.completed_cases = index
        progress.success_count += int(outcome == MiniWobTaskOutcome.SUCCESS.value)
        progress.failure_category_counts[outcome] = progress.failure_category_counts.get(outcome, 0) + 1
        progress.provider_attempts += _integer(result, "provider_attempts")
        progress.total_tokens += _integer(result, "total_tokens")
        progress.model_latency_ms += _number(result, "model_latency_ms")
        progress.last_completed_case_digest = _case_digest(result)
        progress.write(current_case_id=result.case_id)
    return completed


def _model_identity(instrumentations) -> tuple[str, str, str]:
    metadata = [item.model_metadata for item in instrumentations if item.model_metadata is not None]
    if not metadata:
        return "mistral", "mistral-medium-3-5", "format-only.v1"
    providers = {item.provider_id for item in metadata}
    models = {item.model_id for item in metadata}
    grounding = {item.grounding_profile_version for item in metadata}
    return _single(providers), _single(models), _single(grounding)


def _single(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else ""


def _outcome_counts(records) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        counts[item.outcome.value] = counts.get(item.outcome.value, 0) + 1
    return counts


def _integer(result, name: str) -> int:
    value = _number(result, name)
    return int(value)


def _number(result, name: str) -> float:
    item = result.measurements.get(name)
    value = item.value if item is not None and item.measured else 0
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _case_digest(result) -> str:
    import hashlib
    import json

    payload = (result.case_id, result.status, result.case_failure_code, result.terminal_reason_code)
    return "sha256:" + hashlib.sha256(json.dumps(payload, default=str).encode()).hexdigest()


def _git_sha() -> str:
    import subprocess

    return subprocess.run(("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True).stdout.strip()
