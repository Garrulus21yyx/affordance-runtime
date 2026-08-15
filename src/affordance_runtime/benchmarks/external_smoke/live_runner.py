"""Admitted fixed-manifest live policy execution through TargetRuntime."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.external_smoke.adapter_conformance import (
    InstrumentedBrowserGymEnvironment,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_environment import BrowserGymMiniWobEnvironment
from affordance_runtime.benchmarks.external_smoke.environment import ExternalEnvironmentTaskEvaluator
from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST
from affordance_runtime.benchmarks.external_smoke.pacing import (
    PacedAgentPolicy,
    validate_pacing_budget,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCase,
    BenchmarkComposition,
    BenchmarkManifest,
    BenchmarkSuiteResult,
    MetricExpectation,
    MetricExpectationOperator,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import ProductionActionEvaluator
from affordance_runtime.model_policy import ModelBackedAgentPolicy

_REQUIRED = (
    "observations", "executions", "turns", "currentness_probes",
    "browsergym_step_calls", "browsergym_probe_calls", "policy_calls", "provider_attempts",
    "prompt_tokens", "completion_tokens", "total_tokens", "model_latency_ms",
    "official_success_count", "sent_unknown_count", "duplicate_unknown_attempts",
    "forbidden_effect_attempts", "stale_zero_call_violations", "provider_retry_count",
    "fallback_count", "cleanup_failures",
)


@dataclass(frozen=True)
class FixedExternalSmokeOutcome:
    suite: BenchmarkSuiteResult
    accepted: bool
    errors: tuple[str, ...]
    provider_id: str
    model_id: str
    grounding_profile: str
    minimum_policy_call_interval_s: float


async def run_fixed_external_smoke(
    policy: ModelBackedAgentPolicy,
    *,
    seed: int = 7,
    minimum_policy_call_interval_s: float = 7.5,
) -> FixedExternalSmokeOutcome:
    for case in EXTERNAL_SMOKE_MANIFEST.cases:
        validate_pacing_budget(
            case.max_turns,
            minimum_policy_call_interval_s,
            case.timeout_s,
            5.0,
        )
    paced = PacedAgentPolicy(policy, minimum_policy_call_interval_s)
    instrumentations: list[BenchmarkInstrumentation] = []
    manifest = _manifest(seed, paced, instrumentations)
    suite = await run_suite(manifest)
    metadata = next(
        (item.model_metadata for item in reversed(instrumentations) if item.model_metadata is not None),
        None,
    )
    errors = list(suite.acceptance.acceptance_errors)
    if minimum_policy_call_interval_s != 7.5:
        errors.append("fixed external smoke requires 7.5-second pacing")
    if metadata is None:
        errors.append("live provider metadata is unavailable")
    provider = getattr(metadata, "provider_id", "")
    model = getattr(metadata, "model_id", "")
    grounding = getattr(metadata, "grounding_profile_version", "")
    if model != "mistral-medium-3-5":
        errors.append("fixed external smoke requires mistral-medium-3-5")
    if grounding != "format-only.v1":
        errors.append("fixed external smoke requires format-only.v1")
    accepted = not errors and suite.acceptance.accepted and len(suite.cases) == 3
    return FixedExternalSmokeOutcome(
        suite, accepted, tuple(errors), provider, model, grounding, minimum_policy_call_interval_s,
    )


def _manifest(seed: int, policy, instrumentations: list[BenchmarkInstrumentation]) -> BenchmarkManifest:
    cases = tuple(_case(item, seed, policy, instrumentations) for item in EXTERNAL_SMOKE_MANIFEST.cases)
    return BenchmarkManifest(
        "browsergym-fixed-external-smoke.v1", "browsergym-fixed-external-smoke",
        "mistral-format-only-mechanical", seed, cases,
    )


def _case(external_case, seed, policy, instrumentations) -> BenchmarkCase:
    holder: dict[str, object] = {}

    def environment_factory(instrumentation):
        environment, task = BrowserGymMiniWobEnvironment.open(
            external_case.benchmark_task_id, seed, max_turns=external_case.max_turns,
        )
        holder.update(environment=environment, task=task)
        instrumentations.append(instrumentation)
        return InstrumentedBrowserGymEnvironment(environment, instrumentation)

    def task_factory():
        return holder["task"]

    def composition_factory(_instrumentation):
        environment = holder["environment"]
        return BenchmarkComposition(
            policy, ProductionActionEvaluator(),
            ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
        )

    expectations = (
        MetricExpectation("official_success_count", MetricExpectationOperator.EQ, 1),
        MetricExpectation("provider_retry_count", MetricExpectationOperator.ZERO),
        MetricExpectation("fallback_count", MetricExpectationOperator.ZERO),
        MetricExpectation("sent_unknown_count", MetricExpectationOperator.ZERO),
        MetricExpectation("duplicate_unknown_attempts", MetricExpectationOperator.ZERO),
        MetricExpectation("forbidden_effect_attempts", MetricExpectationOperator.ZERO),
        MetricExpectation("stale_zero_call_violations", MetricExpectationOperator.ZERO),
        MetricExpectation("cleanup_failures", MetricExpectationOperator.ZERO),
    )
    return BenchmarkCase(
        external_case.case_id, "browsergym-fixed-external-smoke", external_case.description,
        task_factory, environment_factory, composition_factory, (AgentLoopStatus.DONE,),
        external_case.timeout_s, seed, _REQUIRED, expectations,
    )
