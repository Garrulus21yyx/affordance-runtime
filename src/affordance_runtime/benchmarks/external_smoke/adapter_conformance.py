"""Real fixed MiniWoB adapter conformance through the product Runtime."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent import RunStatus
from affordance_runtime.benchmarks.external_smoke.case_environment import (
    BrowserGymCaseEnvironment,
    open_browsergym_case,
)
from affordance_runtime.benchmarks.external_smoke.composition import (
    BrowserGymCapabilityDecisionPort,
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
from affordance_runtime.surfaces.browsergym.inventory import browsergym_api_inventory

_REQUIRED_METRICS = (
    "browsergym_reset_calls",
    "browsergym_step_calls",
    "browsergym_probe_calls",
    "dom_action_calls",
    "fill_calls",
    "select_calls",
    "scroll_calls",
    "press_calls",
    "keyboard_press_calls",
    "official_verifier_queries",
    "official_success_count",
    "observations",
    "executions",
    "post_action_acquisitions",
    "turns",
    "policy_calls",
    "provider_attempts",
    "provider_retry_count",
    "fallback_count",
    "sent_unknown_count",
    "duplicate_unknown_attempts",
    "forbidden_effect_attempts",
    "stale_zero_call_violations",
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
    "expected_answer",
    "target_answer",
    "reference_action",
    "reference_trajectory",
    "success_script",
    "hidden_state",
    "raw_reward",
    "benchmark_oracle",
    "selector",
    "private bid",
)


@dataclass(frozen=True)
class AdapterConformanceOutcome:
    suite: BenchmarkSuiteResult
    accepted: bool
    errors: tuple[str, ...]
    package_version: str
    target_loop_adapter_ready: bool


@dataclass(frozen=True)
class T1BrowserGymCapabilityCase:
    case_id: str
    semantic_action: str
    target_role: str
    dispatch_status: str
    physical_action: str
    post_observation_acquired: bool
    browsergym_step_calls: int
    browsergym_probe_calls: int
    scroll_calls: int
    press_calls: int
    keyboard_press_calls: int
    official_status: str = ""
    official_reason: str = ""


@dataclass(frozen=True)
class T1BrowserGymCapabilityConformanceOutcome:
    accepted: bool
    cases: tuple[T1BrowserGymCapabilityCase, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _T1BrowserGymCapabilitySpec:
    case_id: str
    semantic_action: str
    target_role: str
    parameters: dict[str, object]
    physical_action: str
    expected_statuses: tuple[RunStatus, ...]


@dataclass
class InstrumentedBrowserGymSurfaceAdapter:
    wrapped: BrowserGymCaseEnvironment
    instrumentation: object
    include_visual_semantic_metrics: bool = False

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    @property
    def observation_capabilities(self):
        return self.wrapped.observation_capabilities

    async def reset(self, task):
        return await self.wrapped.reset(task)

    async def capture(self, request):
        return await self.wrapped.capture(request)

    async def execute(self, request):
        return await self.wrapped.execute(request)

    def is_current(self, request):
        return self.wrapped.is_current(request)

    async def close(self):
        try:
            await self.wrapped.close()
        except BaseException:
            raise
        finally:
            metrics = {
                "browsergym_reset_calls": self.wrapped.reset_calls,
                "browsergym_logical_reset_calls": self.wrapped.logical_reset_calls,
                "browsergym_capture_calls": self.wrapped.capture_calls,
                "browsergym_step_calls": self.wrapped.step_calls,
                "browsergym_probe_calls": self.wrapped.probe_calls,
                "dom_action_calls": self.wrapped.dom_action_calls,
                "fill_calls": self.wrapped.fill_calls,
                "select_calls": self.wrapped.select_calls,
                "scroll_calls": self.wrapped.scroll_calls,
                "press_calls": self.wrapped.press_calls,
                "keyboard_press_calls": self.wrapped.keyboard_press_calls,
                "visual_proposer_calls": self.wrapped.visual_proposer_calls,
                "visual_point_grounder_calls": self.wrapped.visual_point_grounder_calls,
                "visual_point_grounder_success_count": self.wrapped.visual_point_grounder_success_count,
                "visual_disambiguator_calls": self.wrapped.visual_disambiguator_calls,
                "visual_disambiguator_selection_count": self.wrapped.visual_disambiguator_selection_count,
                "visual_predicate_classifier_calls": self.wrapped.visual_predicate_classifier_calls,
                "visual_predicate_assessment_count": self.wrapped.visual_predicate_assessment_count,
                "visual_provider_failure_count": self.wrapped.visual_provider_failure_count,
                "visual_provider_structured_output_failure_count": self.wrapped.visual_provider_structured_output_failure_count,
                "visual_provider_abstained_count": self.wrapped.visual_provider_abstained_count,
                "visual_provider_transport_failure_count": self.wrapped.visual_provider_transport_failure_count,
                "visual_provider_other_failure_count": self.wrapped.visual_provider_other_failure_count,
                "visual_point_grounding_failure_count": self.wrapped.visual_point_grounding_failure_count,
                "visual_region_proposal_failure_count": self.wrapped.visual_region_proposal_failure_count,
                "visual_candidate_disambiguation_failure_count": self.wrapped.visual_candidate_disambiguation_failure_count,
                "visual_predicate_classification_failure_count": self.wrapped.visual_predicate_classification_failure_count,
                "structural_source_acquired_count": self.wrapped.structural_source_acquired_count,
                "visual_source_acquired_count": self.wrapped.visual_source_acquired_count,
                "visual_binding_acquired_count": self.wrapped.visual_binding_acquired_count,
                "visual_gate_selected_count": self.wrapped.visual_gate_selected_count,
                "visual_gate_skipped_count": self.wrapped.visual_gate_skipped_count,
                "visual_correspondence_matched_count": self.wrapped.visual_correspondence_matched_count,
                "visual_correspondence_unmatched_count": self.wrapped.visual_correspondence_unmatched_count,
                "visual_correspondence_ambiguous_count": self.wrapped.visual_correspondence_ambiguous_count,
                "visual_correspondence_conflict_count": self.wrapped.visual_correspondence_conflict_count,
                "structural_binding_dispatch_count": self.wrapped.structural_binding_dispatch_count,
                "visual_binding_dispatch_count": self.wrapped.visual_binding_dispatch_count,
                "official_verifier_queries": self.wrapped.verifier_queries,
                "official_success_count": self.wrapped.official_success_count,
                "fallback_count": 0,
            }
            if self.include_visual_semantic_metrics:
                metrics.update({
                    "visual_text_reader_calls": self.wrapped.visual_text_reader_calls,
                    "visual_spatial_classifier_calls": self.wrapped.visual_spatial_classifier_calls,
                    "visual_change_classifier_calls": self.wrapped.visual_change_classifier_calls,
                    "visual_text_reading_failure_count": self.wrapped.visual_text_reading_failure_count,
                    "visual_spatial_classification_failure_count": self.wrapped.visual_spatial_classification_failure_count,
                    "visual_change_classification_failure_count": self.wrapped.visual_change_classification_failure_count,
                })
            for name, value in metrics.items():
                self.instrumentation.set_custom_metric(name, value)


async def run_adapter_conformance(seed: int = 7) -> AdapterConformanceOutcome:
    ports: list[BrowserGymStructuredDecisionPort] = []
    manifest = _manifest(seed, ports)
    suite = await run_suite(manifest)
    inventory = browsergym_api_inventory()
    errors = list(suite.acceptance.acceptance_errors)
    errors.extend(_oracle_errors(ports))
    if not inventory.accepted:
        errors.append("pinned BrowserGym dependency inventory is not accepted")
    registered = frozenset(inventory.registered_task_ids)
    missing_tasks = tuple(
        case.benchmark_task_id for case in EXTERNAL_SMOKE_MANIFEST.cases if case.benchmark_task_id not in registered
    )
    if missing_tasks:
        errors.append("reviewed benchmark tasks are absent from the BrowserGym registry")
    accepted = not errors and suite.acceptance.accepted and len(suite.cases) == 3
    return AdapterConformanceOutcome(suite, accepted, tuple(errors), inventory.package_version, accepted)


async def run_t1_browsergym_capability_conformance(seed: int = 7) -> T1BrowserGymCapabilityConformanceOutcome:
    specs = _t1_capability_specs()
    suite = await run_suite(_t1_manifest(seed, specs))
    cases = tuple(_t1_case_result(spec, result) for spec, result in zip(specs, suite.cases, strict=True))
    errors = list(suite.acceptance.acceptance_errors)
    for case in cases:
        if case.dispatch_status != "sent":
            errors.append(f"{case.case_id}: dispatch was not sent")
        if not case.post_observation_acquired:
            errors.append(f"{case.case_id}: fresh post-action World was not acquired")
        if case.semantic_action == "scroll" and case.scroll_calls != 1:
            errors.append(f"{case.case_id}: BrowserGym scroll primitive was not dispatched once")
        if case.semantic_action == "press_key" and case.press_calls != 1:
            errors.append(f"{case.case_id}: BrowserGym press primitive was not dispatched once")
    return T1BrowserGymCapabilityConformanceOutcome(
        not errors and len(cases) == len(specs),
        cases,
        tuple(errors),
    )


def _manifest(seed: int, ports: list[BrowserGymStructuredDecisionPort]) -> BenchmarkManifest:
    cases = tuple(_case(item, seed, ports) for item in EXTERNAL_SMOKE_MANIFEST.cases)
    return BenchmarkManifest(
        "browsergym-adapter-conformance.v1",
        "browsergym-adapter-conformance",
        "scripted-structured-mechanical",
        seed,
        cases,
    )


def _case(external_case, seed: int, ports: list[BrowserGymStructuredDecisionPort]) -> BenchmarkCase:
    holder: dict[str, object] = {}

    def environment_factory(instrumentation):
        environment, task = open_browsergym_case(
            external_case.benchmark_task_id,
            seed,
            max_turns=external_case.max_turns,
        )
        holder.update(environment=environment, task=task)
        return InstrumentedBrowserGymSurfaceAdapter(environment, instrumentation)

    def task_factory():
        return holder["task"]

    def composition_factory(_instrumentation):
        environment = holder["environment"]
        port = BrowserGymStructuredDecisionPort()
        ports.append(port)
        return adapter_conformance_composition(environment, port)

    expectations = (*_EXPECTATIONS, *_primitive_expectations(external_case.allowed_primitives))
    return BenchmarkCase(
        external_case.case_id,
        "browsergym-adapter-conformance",
        external_case.description,
        task_factory,
        environment_factory,
        composition_factory,
        (RunStatus.DONE,),
        external_case.timeout_s,
        seed,
        _REQUIRED_METRICS,
        expectations,
    )


def _t1_capability_specs() -> tuple[_T1BrowserGymCapabilitySpec, ...]:
    return (
        _T1BrowserGymCapabilitySpec(
            "t1-scroll-viewport",
            "scroll",
            "viewport",
            {"direction": "down", "extent": "small"},
            "scroll",
            (RunStatus.BLOCKED,),
        ),
        _T1BrowserGymCapabilitySpec(
            "t1-press-key-entity",
            "press_key",
            "button",
            {"key": "Enter"},
            "press",
            (RunStatus.DONE, RunStatus.BLOCKED),
        ),
    )


def _t1_manifest(seed: int, specs: tuple[_T1BrowserGymCapabilitySpec, ...]) -> BenchmarkManifest:
    return BenchmarkManifest(
        "browsergym-t1-capability-conformance.v1",
        "browsergym-t1-capability-conformance",
        "scripted-capability-mechanical",
        seed,
        tuple(_t1_case(spec, seed) for spec in specs),
    )


def _t1_case(spec: _T1BrowserGymCapabilitySpec, seed: int) -> BenchmarkCase:
    holder: dict[str, object] = {}

    def environment_factory(instrumentation):
        environment, task = open_browsergym_case(
            "browsergym/miniwob.click-button",
            seed,
            max_turns=1,
            admitted_task_ids=frozenset({"browsergym/miniwob.click-button"}),
        )
        holder.update(environment=environment, task=task)
        return InstrumentedBrowserGymSurfaceAdapter(environment, instrumentation)

    def task_factory():
        return holder["task"]

    def composition_factory(_instrumentation):
        environment = holder["environment"]
        port = BrowserGymCapabilityDecisionPort(
            spec.semantic_action,
            spec.target_role,
            spec.parameters,
        )
        return adapter_conformance_composition(environment, port)

    expectations = (
        MetricExpectation("browsergym_reset_calls", MetricExpectationOperator.EQ, 1),
        MetricExpectation("browsergym_step_calls", MetricExpectationOperator.EQ, 1),
        MetricExpectation("browsergym_probe_calls", MetricExpectationOperator.MIN, 1),
        MetricExpectation("executions", MetricExpectationOperator.EQ, 1),
        MetricExpectation("policy_calls", MetricExpectationOperator.EQ, 1),
        MetricExpectation("provider_attempts", MetricExpectationOperator.ZERO),
        MetricExpectation("provider_retry_count", MetricExpectationOperator.ZERO),
        MetricExpectation("fallback_count", MetricExpectationOperator.ZERO),
        MetricExpectation("sent_unknown_count", MetricExpectationOperator.ZERO),
        MetricExpectation("duplicate_unknown_attempts", MetricExpectationOperator.ZERO),
        MetricExpectation("forbidden_effect_attempts", MetricExpectationOperator.ZERO),
        MetricExpectation("stale_zero_call_violations", MetricExpectationOperator.ZERO),
        MetricExpectation("cleanup_failures", MetricExpectationOperator.ZERO),
    )
    primitive_expectation = (
        MetricExpectation("scroll_calls", MetricExpectationOperator.EQ, 1)
        if spec.semantic_action == "scroll"
        else MetricExpectation("press_calls", MetricExpectationOperator.EQ, 1)
    )
    return BenchmarkCase(
        spec.case_id,
        "browsergym-t1-capability-conformance",
        f"Dispatch {spec.semantic_action} through the public target loop",
        task_factory,
        environment_factory,
        composition_factory,
        spec.expected_statuses,
        30,
        seed,
        _REQUIRED_METRICS,
        (*expectations, primitive_expectation),
    )


def _t1_case_result(spec: _T1BrowserGymCapabilitySpec, result) -> T1BrowserGymCapabilityCase:
    official_success = _measurement(result, "official_success_count")
    return T1BrowserGymCapabilityCase(
        spec.case_id,
        spec.semantic_action,
        spec.target_role,
        "sent" if _measurement(result, "effectful_dispatches") >= 1 else "not_sent",
        spec.physical_action,
        _measurement(result, "post_action_acquisitions") >= 1 and _measurement(result, "observations") >= 2,
        _measurement(result, "browsergym_step_calls"),
        _measurement(result, "browsergym_probe_calls"),
        _measurement(result, "scroll_calls"),
        _measurement(result, "press_calls"),
        _measurement(result, "keyboard_press_calls"),
        "success" if official_success else "incomplete",
        result.runtime_reason_code,
    )


def _measurement(result, name: str) -> int:
    measurement = result.measurements[name]
    if not measurement.measured or not isinstance(measurement.value, int):
        raise ValueError(f"T1 conformance metric {name} is unavailable")
    return measurement.value


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
        for context in port.public_contexts:
            lowered = repr((
                context.task,
                context.goal_plan,
                context.actions,
                context.workspace.recent_steps,
                context.actor_world,
            )).casefold()
            if any(value in lowered for value in (*task_ids, *_ORACLE_MARKERS)):
                errors.append("private benchmark or oracle material entered AgentContext")
    return tuple(errors)
