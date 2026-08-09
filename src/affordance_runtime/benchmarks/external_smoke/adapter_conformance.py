"""Real fixed MiniWoB adapter conformance through the unchanged AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.external_smoke.browsergym_environment import BrowserGymMiniWobEnvironment
from affordance_runtime.benchmarks.external_smoke.browsergym_inventory import browsergym_api_inventory
from affordance_runtime.benchmarks.external_smoke.composition import (
    BrowserGymStructuredDecisionPort,
    adapter_conformance_composition,
)
from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCase,
    BenchmarkManifest,
    BenchmarkSuiteResult,
    MetricExpectation,
    MetricExpectationOperator,
)
from affordance_runtime.benchmarks.target_loop.runner import run_suite

_REQUIRED_METRICS = (
    "browsergym_reset_calls", "browsergym_step_calls", "browsergym_probe_calls",
    "dom_action_calls", "fill_calls", "select_calls", "official_verifier_queries",
    "official_success_count", "observations", "executions", "turns", "policy_calls",
    "provider_attempts", "provider_retry_count", "fallback_count", "sent_unknown_count",
    "duplicate_unknown_attempts", "forbidden_effect_attempts", "stale_zero_call_violations",
    "cleanup_failures",
)
_EXPECTATIONS = (
    MetricExpectation("browsergym_reset_calls", MetricExpectationOperator.EQ, 1),
    MetricExpectation("browsergym_step_calls", MetricExpectationOperator.MIN, 1),
    MetricExpectation("browsergym_probe_calls", MetricExpectationOperator.MIN, 1),
    MetricExpectation("dom_action_calls", MetricExpectationOperator.MIN, 1),
    MetricExpectation("official_success_count", MetricExpectationOperator.EQ, 1),
    MetricExpectation("provider_retry_count", MetricExpectationOperator.ZERO),
    MetricExpectation("fallback_count", MetricExpectationOperator.ZERO),
    MetricExpectation("sent_unknown_count", MetricExpectationOperator.ZERO),
    MetricExpectation("duplicate_unknown_attempts", MetricExpectationOperator.ZERO),
    MetricExpectation("forbidden_effect_attempts", MetricExpectationOperator.ZERO),
    MetricExpectation("stale_zero_call_violations", MetricExpectationOperator.ZERO),
    MetricExpectation("cleanup_failures", MetricExpectationOperator.ZERO),
)
_ORACLE_MARKERS = (
    "expected_answer", "target_answer", "reference_action", "reference_trajectory",
    "success_script", "hidden_state", "raw_reward", "benchmark_oracle", "selector", "private bid",
)


@dataclass(frozen=True)
class AdapterConformanceOutcome:
    suite: BenchmarkSuiteResult
    accepted: bool
    errors: tuple[str, ...]
    package_version: str
    target_loop_adapter_ready: bool


@dataclass
class InstrumentedBrowserGymEnvironment:
    wrapped: BrowserGymMiniWobEnvironment
    instrumentation: object

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    async def reset(self, task):
        return await self.wrapped.reset(task)

    async def observe(self, reason):
        return await self.wrapped.observe(reason)

    async def execute(self, request):
        return await self.wrapped.execute(request)

    def is_current(self, request):
        return self.wrapped.is_current(request)

    async def close(self):
        cleanup = 0
        try:
            await self.wrapped.close()
        except BaseException:
            cleanup = 1
            raise
        finally:
            metrics = {
                "browsergym_reset_calls": self.wrapped.reset_calls,
                "browsergym_step_calls": self.wrapped.step_calls,
                "browsergym_probe_calls": self.wrapped.probe_calls,
                "dom_action_calls": self.wrapped.dom_action_calls,
                "fill_calls": self.wrapped.fill_calls,
                "select_calls": self.wrapped.select_calls,
                "official_verifier_queries": self.wrapped.verifier_queries,
                "official_success_count": self.wrapped.official_success_count,
                "fallback_count": 0,
                "cleanup_failures": cleanup,
            }
            self.instrumentation.custom_metrics.update(metrics)


async def run_adapter_conformance(seed: int = 7) -> AdapterConformanceOutcome:
    ports: list[BrowserGymStructuredDecisionPort] = []
    manifest = _manifest(seed, ports)
    suite = await run_suite(manifest)
    inventory = browsergym_api_inventory()
    errors = list(suite.acceptance.acceptance_errors)
    errors.extend(_oracle_errors(ports))
    if not inventory.accepted:
        errors.append("pinned BrowserGym dependency inventory is not accepted")
    accepted = not errors and suite.acceptance.accepted and len(suite.cases) == 3
    return AdapterConformanceOutcome(suite, accepted, tuple(errors), inventory.package_version, accepted)


def _manifest(seed: int, ports: list[BrowserGymStructuredDecisionPort]) -> BenchmarkManifest:
    cases = tuple(_case(item, seed, ports) for item in EXTERNAL_SMOKE_MANIFEST.cases)
    return BenchmarkManifest(
        "browsergym-adapter-conformance.v1", "browsergym-adapter-conformance",
        "scripted-structured-mechanical", seed, cases,
    )


def _case(external_case, seed: int, ports: list[BrowserGymStructuredDecisionPort]) -> BenchmarkCase:
    holder: dict[str, object] = {}

    def environment_factory(instrumentation):
        environment, task = BrowserGymMiniWobEnvironment.open(
            external_case.benchmark_task_id, seed, max_turns=external_case.max_turns,
        )
        holder.update(environment=environment, task=task)
        return InstrumentedBrowserGymEnvironment(environment, instrumentation)

    def task_factory():
        return holder["task"]

    def composition_factory(_instrumentation):
        environment = holder["environment"]
        port = BrowserGymStructuredDecisionPort()
        ports.append(port)
        return adapter_conformance_composition(environment, port)

    expectations = (*_EXPECTATIONS, *_primitive_expectations(external_case.allowed_primitives))
    return BenchmarkCase(
        external_case.case_id, "browsergym-adapter-conformance", external_case.description,
        task_factory, environment_factory, composition_factory, (AgentLoopStatus.DONE,),
        external_case.timeout_s, seed, _REQUIRED_METRICS, expectations,
    )


def _primitive_expectations(primitives: tuple[str, ...]) -> tuple[MetricExpectation, ...]:
    expected = []
    if "fill" in primitives:
        expected.append(MetricExpectation("fill_calls", MetricExpectationOperator.MIN, 1))
    if "select" in primitives:
        expected.append(MetricExpectation("select_calls", MetricExpectationOperator.MIN, 1))
    return tuple(expected)


def _oracle_errors(ports: list[BrowserGymStructuredDecisionPort]) -> tuple[str, ...]:
    errors = []
    task_ids = tuple(item.benchmark_task_id.casefold() for item in EXTERNAL_SMOKE_MANIFEST.cases)
    for port in ports:
        for serialized in port.serialized_contexts:
            lowered = serialized.casefold()
            if any(value in lowered for value in (*task_ids, *_ORACLE_MARKERS)):
                errors.append("private benchmark or oracle material entered serialized AgentContext")
    return tuple(errors)
