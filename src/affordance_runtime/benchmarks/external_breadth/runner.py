"""Strictly serial MiniWoB breadth execution through the product Runtime."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from affordance_runtime.agent import RunStatus
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignAcceptance,
    MiniWobBreadthCampaignOutcome,
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
    ProviderCapacityEvidence,
)
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthManifest
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.progress import (
    CampaignProgressWriter,
    ProgressEventObserver,
    case_progress_digest,
)
from affordance_runtime.benchmarks.external_smoke.adapter_conformance import InstrumentedBrowserGymSurfaceAdapter
from affordance_runtime.benchmarks.external_smoke.case_environment import (
    ExternalEnvironmentTaskEvaluator,
    open_browsergym_case,
)
from affordance_runtime.benchmarks.external_smoke.pacing import (
    FixedPacingState,
    PacedAgentPolicy,
    validate_pacing_budget,
)
from affordance_runtime.benchmarks.model_protocol import (
    PRIMARY_BENCHMARK_REQUIRED_DECISIONS,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    CASE_SCHEMA_VERSION,
    BenchmarkCase,
    BenchmarkComposition,
    BenchmarkManifest,
    CaseFailureOrigin,
    MetricMeasurement,
    TerminalReasonCode,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest as target_manifest_digest
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.goals import GoalCompiler
from affordance_runtime.model.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.surfaces.visual.disambiguation import VisualCandidateDisambiguatorPort
from affordance_runtime.surfaces.visual.grounding import VisualGrounderPort, VisualRegionProposerPort
from affordance_runtime.surfaces.visual.predicate_classification import VisualPredicateClassifierPort

REQUIRED_METRICS = (
    "observations",
    "executions",
    "turns",
    "currentness_probes",
    "browsergym_reset_calls",
    "browsergym_step_calls",
    "browsergym_probe_calls",
    "click_calls",
    "fill_calls",
    "select_calls",
    "visual_proposer_calls",
    "visual_point_grounder_calls",
    "visual_point_grounder_success_count",
    "visual_disambiguator_calls",
    "visual_disambiguator_selection_count",
    "visual_predicate_classifier_calls",
    "visual_predicate_assessment_count",
    "visual_provider_failure_count",
    "visual_provider_structured_output_failure_count",
    "visual_provider_abstained_count",
    "visual_provider_transport_failure_count",
    "visual_provider_other_failure_count",
    "visual_point_grounding_failure_count",
    "visual_region_proposal_failure_count",
    "visual_candidate_disambiguation_failure_count",
    "visual_predicate_classification_failure_count",
    "structural_source_acquired_count",
    "visual_source_acquired_count",
    "visual_binding_acquired_count",
    "visual_gate_selected_count",
    "visual_gate_skipped_count",
    "visual_correspondence_matched_count",
    "visual_correspondence_unmatched_count",
    "visual_correspondence_ambiguous_count",
    "visual_correspondence_conflict_count",
    "structural_binding_dispatch_count",
    "visual_binding_dispatch_count",
    "policy_calls",
    "policy_schema_repair_count",
    "goal_compiler_calls",
    "goal_compiler_provider_attempts",
    "goal_compiler_schema_repair_count",
    "goal_compiler_contract_repair_count",
    "goal_compiler_ready_count",
    "goal_compiler_unavailable_count",
    "tool_argument_repair_count",
    "valid_tool_call_count",
    "zero_tool_call_count",
    "multiple_tool_call_count",
    "unknown_tool_call_count",
    "invalid_tool_argument_count",
    "stale_tool_catalog_count",
    "tool_grounding_gap_count",
    "tool_catalog_count",
    "tool_catalog_bytes",
    "provider_attempts",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "model_latency_ms",
    "already_satisfied_suppressions",
    "no_progress_terminations",
    "official_success_count",
    "sent_unknown_count",
    "duplicate_unknown_attempts",
    "forbidden_effect_attempts",
    "stale_zero_call_violations",
    "provider_retry_count",
    "fallback_count",
    "cleanup_failures",
    "observation_contract_exceptions",
)
_TERMINAL_STATUSES = tuple(item for item in RunStatus if item is not RunStatus.RUNNING)


async def run_breadth_campaign(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    output_dir: Path,
    *,
    provider_capacity: ProviderCapacityEvidence | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
    visual_point_grounder: VisualGrounderPort | None = None,
    visual_candidate_disambiguator: VisualCandidateDisambiguatorPort | None = None,
    visual_predicate_classifier: VisualPredicateClassifierPort | None = None,
    goal_compiler: GoalCompiler | None = None,
) -> MiniWobBreadthCampaignOutcome:
    if len(manifest.cases) != 60:
        raise ValueError("formal breadth campaign requires exactly 60 frozen cases")
    for case in manifest.cases:
        validate_pacing_budget(case.max_turns, manifest.minimum_policy_call_interval_s, case.timeout_s, 5.0)
    configured_identity = _validate_formal_policy(policy, manifest)
    output_dir.mkdir(parents=True, exist_ok=False)
    digest = breadth_manifest_digest(manifest)
    run_id = f"miniwob-60:{uuid.uuid4().hex}"
    progress = CampaignProgressWriter(
        output_dir / "campaign-progress.json",
        manifest.campaign_id,
        run_id,
        _git_sha(),
        digest,
        len(manifest.cases),
    )
    progress.write()
    pacing_state = FixedPacingState()
    instrumentations: list[BenchmarkInstrumentation] = []
    target_manifest = _target_manifest(
        manifest,
        policy,
        pacing_state,
        instrumentations,
        visual_region_proposer=visual_region_proposer,
        visual_point_grounder=visual_point_grounder,
        visual_candidate_disambiguator=visual_candidate_disambiguator,
        visual_predicate_classifier=visual_predicate_classifier,
        goal_compiler=goal_compiler,
    )
    harness_digest = target_manifest_digest(target_manifest)
    if harness_digest != expected_target_manifest_digest(manifest):
        raise ValueError("target-loop manifest identity is not canonical")
    suite = await run_suite(target_manifest, _progress_callback(progress))
    suite = replace(suite, cases=tuple(_derived_metrics(item) for item in suite.cases))
    records = tuple(
        _record(
            case,
            result,
            instrumentations[index] if index < len(instrumentations) else None,
        )
        for index, (case, result) in enumerate(zip(manifest.cases, suite.cases, strict=True))
    )
    provider, model, grounding = _model_identity(
        instrumentations,
        configured_identity,
    )
    final_sha, final_dirty = _final_git_identity()
    acceptance = _accept_campaign(
        manifest,
        suite,
        records,
        provider,
        model,
        grounding,
        provider_capacity,
        harness_digest,
        final_sha,
        final_dirty,
    )
    progress.completed_cases = len(records)
    progress.success_count = acceptance.successful_cases
    progress.failure_category_counts = _outcome_counts(records)
    progress.provider_attempts = sum(_integer(item.result, "provider_attempts") for item in records)
    progress.total_tokens = sum(_integer(item.result, "total_tokens") for item in records)
    progress.model_latency_ms = sum(_number(item.result, "model_latency_ms") for item in records)
    progress.write(current_case_id=records[-1].case_id, complete=True)
    return MiniWobBreadthCampaignOutcome(
        run_id,
        manifest,
        digest,
        suite,
        records,
        acceptance,
        provider,
        model,
        grounding,
        provider_capacity,
    )


def _target_manifest(
    manifest,
    policy,
    pacing_state,
    instrumentations,
    visual_region_proposer=None,
    visual_point_grounder=None,
    visual_candidate_disambiguator=None,
    visual_predicate_classifier=None,
    goal_compiler=None,
) -> BenchmarkManifest:
    cases = tuple(
        _target_case(
            item,
            manifest,
            policy,
            pacing_state,
            instrumentations,
            visual_region_proposer,
            visual_point_grounder,
            visual_candidate_disambiguator,
            visual_predicate_classifier,
            goal_compiler,
        )
        for item in manifest.cases
    )
    return BenchmarkManifest(
        manifest.schema_version,
        manifest.campaign_id,
        "mistral-format-only-v1",
        7,
        cases,
    )


def _target_case(
    case,
    manifest,
    base_policy,
    pacing_state,
    instrumentations,
    visual_region_proposer=None,
    visual_point_grounder=None,
    visual_candidate_disambiguator=None,
    visual_predicate_classifier=None,
    goal_compiler=None,
) -> BenchmarkCase:
    holder: dict[str, object] = {}
    admitted = frozenset(item.task_id for item in manifest.cases)

    def environment_factory(instrumentation):
        try:
            environment, task = open_browsergym_case(
                case.task_id,
                case.seed,
                max_turns=case.max_turns,
                admitted_task_ids=admitted,
                visual_region_proposer=visual_region_proposer,
                visual_point_grounder=visual_point_grounder,
                visual_candidate_disambiguator=visual_candidate_disambiguator,
                visual_predicate_classifier=visual_predicate_classifier,
                marked_candidate_policy_available=_marked_candidate_policy_available(base_policy),
            )
        except BaseException as exc:
            _initialize_custom_metrics(instrumentation)
            if isinstance(exc, Exception):
                instrumentation.record_failure(
                    CaseFailureOrigin.ENVIRONMENT_RESET,
                    "browsergym_open_exception",
                    exc,
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
            base_policy,
            manifest.minimum_policy_call_interval_s,
            state=pacing_state,
            context_observer=observer,
        )
        return BenchmarkComposition(
            paced,
            ProductionActionOutcomeProjector(),
            ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
            required_decisions=PRIMARY_BENCHMARK_REQUIRED_DECISIONS,
            goal_compiler=goal_compiler,
        )

    return BenchmarkCase(
        case.case_id,
        manifest.campaign_id,
        case.capability_profile,
        task_factory,
        environment_factory,
        composition_factory,
        _TERMINAL_STATUSES,
        case.timeout_s,
        case.seed,
        REQUIRED_METRICS,
    )


def _marked_candidate_policy_available(policy: object) -> bool:
    """Detect a policy that can consume marked visual evidence when acquired."""

    pending = [policy]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        profile = getattr(item, "perception_profile", None)
        if profile in {
            DecisionPerceptionProfile.SCREENSHOT_AX,
            DecisionPerceptionProfile.STRUCTURE_FIRST,
        }:
            return True
        for name in ("wrapped", "port"):
            nested = getattr(item, name, None)
            if nested is not None:
                pending.append(nested)
        ports = getattr(item, "ports", None)
        if isinstance(ports, tuple):
            pending.extend(ports)
    return False


class _BreadthEnvironment(InstrumentedBrowserGymSurfaceAdapter):
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
        "browsergym_reset_calls",
        "browsergym_step_calls",
        "browsergym_probe_calls",
        "dom_action_calls",
        "click_calls",
        "fill_calls",
        "select_calls",
        "visual_proposer_calls",
        "visual_point_grounder_calls",
        "visual_point_grounder_success_count",
        "visual_disambiguator_calls",
        "visual_disambiguator_selection_count",
        "visual_predicate_classifier_calls",
        "visual_predicate_assessment_count",
        "visual_provider_failure_count",
        "visual_provider_structured_output_failure_count",
        "visual_provider_abstained_count",
        "visual_provider_transport_failure_count",
        "visual_provider_other_failure_count",
        "visual_point_grounding_failure_count",
        "visual_region_proposal_failure_count",
        "visual_candidate_disambiguation_failure_count",
        "visual_predicate_classification_failure_count",
        "structural_source_acquired_count",
        "visual_source_acquired_count",
        "visual_binding_acquired_count",
        "visual_gate_selected_count",
        "visual_gate_skipped_count",
        "visual_correspondence_matched_count",
        "visual_correspondence_unmatched_count",
        "visual_correspondence_ambiguous_count",
        "visual_correspondence_conflict_count",
        "structural_binding_dispatch_count",
        "visual_binding_dispatch_count",
        "official_verifier_queries",
        "official_success_count",
        "fallback_count",
        "already_satisfied_suppressions",
        "no_progress_terminations",
    ):
        if name not in instrumentation.custom_metrics:
            instrumentation.set_custom_metric(name, 0)


def _derived_metrics(result):
    values = {
        name: result.measurements[name]
        for name in REQUIRED_METRICS
        if name != "no_progress_terminations" and name in result.measurements
    }
    values["no_progress_terminations"] = MetricMeasurement(
        int(result.terminal_reason_code is TerminalReasonCode.NO_PROGRESS_REPETITION),
        True,
    )
    return replace(result, measurements=values)


def _record(case, result, instrumentation=None) -> MiniWobBreadthCaseRecord:
    classified = classify_case(result)
    return MiniWobBreadthCaseRecord(
        case.case_id,
        case.task_id.removeprefix("browsergym/miniwob."),
        case.capability_profile,
        case.required_primitives,
        classified.outcome,
        classified.source,
        result,
        tuple(dict(item) for item in getattr(instrumentation, "policy_trace", ())),
    )


def _accept_campaign(
    manifest,
    suite,
    records,
    provider,
    model,
    grounding,
    provider_capacity,
    harness_digest,
    final_sha,
    final_dirty,
) -> MiniWobBreadthCampaignAcceptance:
    errors: list[str] = []
    identities = tuple(item.case_id for item in records)
    expected = tuple(item.case_id for item in manifest.cases)
    if len(records) != 60 or identities != expected or len(set(identities)) != 60:
        errors.append("campaign result set does not match the frozen 60-case manifest")
    underlying = tuple(item.result.case_id for item in records)
    if underlying != expected:
        errors.append("underlying case identities do not match the frozen manifest")
    identity = suite.identity
    if (
        identity.suite_id != manifest.campaign_id
        or identity.profile_id != "mistral-format-only-v1"
        or identity.seed != 7
        or identity.manifest_digest != harness_digest
        or identity.harness_schema_version != "target-loop-harness.v6"
    ):
        errors.append("suite identity/schema/digest does not match the frozen manifest")
    if suite.identity.git_dirty:
        errors.append("campaign git tree is dirty")
    if final_dirty or final_sha != suite.identity.git_sha:
        errors.append("campaign git identity changed during execution")
    if provider != "mistral" or model != manifest.model_profile or grounding != manifest.grounding_profile:
        errors.append("campaign model identity does not match the frozen profile")
    required_budget = sum(item.max_turns for item in manifest.cases)
    if (
        provider_capacity is None
        or provider_capacity.provider_id != provider
        or provider_capacity.model_id != model
        or provider_capacity.manifest_digest != breadth_manifest_digest(manifest)
        or provider_capacity.required_attempt_budget != required_budget
        or provider_capacity.grounding_profile != grounding
        or provider_capacity.retry_count != 0
        or provider_capacity.fallback_count != 0
        or not provider_capacity.sufficient
    ):
        errors.append("explicit provider capacity evidence is absent or insufficient")
    for record in records:
        missing = [
            name
            for name in REQUIRED_METRICS
            if name not in record.result.measurements or not record.result.measurements[name].measured
        ]
        if missing:
            errors.append(f"{record.case_id}: required metrics are incomplete")
        if record.outcome in {
            MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE,
            MiniWobTaskOutcome.OTHER_TYPED_FAILURE,
        }:
            errors.append(f"{record.case_id}: outcome is not fully classified")
        if record.result.harness_integrity_failures:
            errors.append(f"{record.case_id}: harness integrity failed")
        if record.result.cleanup_failures:
            errors.append(f"{record.case_id}: cleanup failed")
        if record.result.failure_facts.harness_integrity_code:
            errors.append(f"{record.case_id}: typed harness integrity fact is nonzero")
        if record.result.case_schema_version != CASE_SCHEMA_VERSION:
            errors.append(f"{record.case_id}: case evidence schema is unsupported")
        if record.result.harness_schema_version != "target-loop-harness.v6":
            errors.append(f"{record.case_id}: harness evidence schema is unsupported")
        if record.result.suite_id != manifest.campaign_id:
            errors.append(f"{record.case_id}: suite identity mismatch")
        if record.result.profile_id != "mistral-format-only-v1":
            errors.append(f"{record.case_id}: profile identity mismatch")
        if record.result.seed != 7 or record.result.manifest_digest != identity.manifest_digest:
            errors.append(f"{record.case_id}: seed or manifest identity mismatch")
        observation_exceptions = record.result.measurements.get("observation_contract_exceptions")
        if observation_exceptions is None or not observation_exceptions.measured:
            errors.append(f"{record.case_id}: observation contract exception gate is unmeasured")
        elif observation_exceptions.value != 0:
            errors.append(f"{record.case_id}: observation contract exception gate is nonzero")
    for name in (
        "provider_retry_count",
        "fallback_count",
        "cleanup_failures",
        "forbidden_effect_attempts",
        "duplicate_unknown_attempts",
        "stale_zero_call_violations",
    ):
        for item in records:
            measurement = item.result.measurements.get(name)
            if (
                measurement is None
                or not measurement.measured
                or type(measurement.value) is not int
                or measurement.value != 0
            ):
                errors.append(f"{item.case_id}: campaign safety metric {name} is unavailable or nonzero")
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
        progress.last_completed_case_digest = case_progress_digest(result)
        progress.write(current_case_id=result.case_id)

    return completed


def _model_identity(
    instrumentations,
    configured: tuple[str, str, str],
) -> tuple[str, str, str]:
    metadata = [item.model_metadata for item in instrumentations if item.model_metadata is not None]
    if not metadata:
        return configured
    providers = {item.provider_id for item in metadata}
    models = {item.model_id for item in metadata}
    grounding = {item.grounding_profile_version for item in metadata}
    observed = _single(providers), _single(models), _single(grounding)
    return observed if observed == configured else ("", "", "")


def _validate_formal_policy(
    policy: object,
    manifest: MiniWobBreadthManifest,
    *,
    provider_recovery: bool = False,
) -> tuple[str, str, str]:
    if not isinstance(policy, ModelBackedAgentPolicy):
        raise TypeError("formal breadth campaign requires ModelBackedAgentPolicy")
    composed = policy.port
    if provider_recovery:
        raise ValueError("provider recovery orchestration is outside the simplified Runtime")
    adapter = composed
    provider_port = getattr(adapter, "port", None)
    provider = getattr(provider_port, "provider", "")
    model = getattr(provider_port, "model", "")
    identity = provider, model, getattr(adapter, "grounding_profile_version", "")
    config = getattr(adapter, "config", None)
    if (
        identity != ("mistral", manifest.model_profile, manifest.grounding_profile)
        or config is None
        or config.rate_limit_retries != 0
        or config.transient_retries != 0
    ):
        raise ValueError("formal breadth policy identity is not the frozen profile")
    return identity


def expected_target_manifest_digest(manifest: MiniWobBreadthManifest) -> str:
    cases = tuple(
        BenchmarkCase(
            case.case_id,
            manifest.campaign_id,
            case.capability_profile,
            _unreachable_factory,
            _unreachable_factory,
            _unreachable_factory,
            _TERMINAL_STATUSES,
            case.timeout_s,
            case.seed,
            REQUIRED_METRICS,
        )
        for case in manifest.cases
    )
    return target_manifest_digest(
        BenchmarkManifest(
            manifest.schema_version,
            manifest.campaign_id,
            "mistral-format-only-v1",
            7,
            cases,
        )
    )


def _unreachable_factory(*_args):
    raise RuntimeError("identity-only benchmark factory")


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


def _git_sha() -> str:
    import subprocess

    return subprocess.run(("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True).stdout.strip()


def _final_git_identity() -> tuple[str, bool]:
    import subprocess

    sha = _git_sha()
    dirty = bool(
        subprocess.run(
            ("git", "status", "--short"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return sha, dirty
