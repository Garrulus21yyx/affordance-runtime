"""Declared-supported, same-model text versus screenshot+AX diagnostic."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
)
from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobBreadthManifest,
    MiniWobRegistryCensus,
)
from affordance_runtime.benchmarks.external_breadth.inventory_v2 import (
    build_capability_inventory_v2,
    current_declared_capabilities,
    task_readiness,
)
from affordance_runtime.benchmarks.external_breadth.requirements import TaskReadiness
from affordance_runtime.benchmarks.external_breadth.runner import (
    _derived_metrics,
    _final_git_identity,
    _integer,
    _model_identity,
    _number,
    _outcome_counts,
    _record,
    _target_manifest,
)
from affordance_runtime.benchmarks.external_smoke.adapter_reporting import _atomic_json
from affordance_runtime.benchmarks.external_smoke.pacing import FixedPacingState
from affordance_runtime.benchmarks.target_loop.case_projection import public_case_evidence
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.model_policy import ModelBackedAgentPolicy
from affordance_runtime.model_policy.grounded_tool_port_bridge import GroundedToolDecisionAdapter
from affordance_runtime.model_policy.model_port_bridge import (
    DecisionPerceptionProfile,
    ModelPortDecisionAdapter,
)
from affordance_runtime.model_policy.provider_orchestrator import ProviderCallOrchestrator
from affordance_runtime.model_policy.requirement_proposer import (
    ModelRequirementHypothesisProposer,
)
from affordance_runtime.model_policy.tool_port_bridge import DynamicToolDecisionAdapter

SCHEMA_VERSION = "miniwob-perception-ab.v2"
PROFILE_ID = "MINIWOB_CAPABILITY_COVERED_PERCEPTION_AB"
CAPABILITY_COVERED_COHORT = "capability_covered"
UNASSESSED_COHORT = "unassessed"
DECLARED_GAP_COHORT = "declared_gap"
_SAFETY_METRICS = (
    "cleanup_failures",
    "duplicate_unknown_attempts",
    "fallback_count",
    "forbidden_effect_attempts",
    "stale_zero_call_violations",
)


@dataclass(frozen=True)
class PerceptionArmOutcome:
    perception_profile: DecisionPerceptionProfile
    records: tuple[MiniWobBreadthCaseRecord, ...]
    provider_id: str
    model_id: str
    grounding_profile: str
    errors: tuple[str, ...]
    provider_attempts: int
    total_tokens: int
    model_latency_ms: float
    requirement_hypotheses_enabled: bool
    requirement_hypothesis_calls: int

    @property
    def success_count(self) -> int:
        return sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in self.records)


def capability_covered_cases(
    manifest: MiniWobBreadthManifest,
    census: MiniWobRegistryCensus,
    *,
    source_root: Path | None = None,
) -> tuple:
    inventory = build_capability_inventory_v2(census, source_root)
    readiness = {item.task_id: task_readiness(item, current_declared_capabilities()) for item in inventory}
    return tuple(case for case in manifest.cases if readiness.get(case.task_id) is TaskReadiness.DECLARED_SUPPORTED)


def readiness_cohorts(
    manifest: MiniWobBreadthManifest,
    census: MiniWobRegistryCensus,
    *,
    source_root: Path | None = None,
) -> dict[str, tuple]:
    inventory = build_capability_inventory_v2(census, source_root)
    readiness = {
        item.task_id: task_readiness(item, current_declared_capabilities())
        for item in inventory
    }
    names = {
        TaskReadiness.DECLARED_SUPPORTED: CAPABILITY_COVERED_COHORT,
        TaskReadiness.UNASSESSED: UNASSESSED_COHORT,
        TaskReadiness.DECLARED_UNSUPPORTED: DECLARED_GAP_COHORT,
    }
    result: dict[str, list[object]] = {name: [] for name in names.values()}
    for case in manifest.cases:
        result[names[readiness.get(case.task_id, TaskReadiness.UNASSESSED)]].append(case)
    return {name: tuple(values) for name, values in result.items()}


def declared_supported_cases(
    manifest: MiniWobBreadthManifest,
    census: MiniWobRegistryCensus,
    *,
    source_root: Path | None = None,
) -> tuple:
    """Compatibility alias; public reports use capability-covered terminology."""

    return capability_covered_cases(manifest, census, source_root=source_root)


async def run_perception_arm(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    perception_profile: DecisionPerceptionProfile,
    *,
    enable_requirement_hypotheses: bool = False,
) -> PerceptionArmOutcome:
    return await _run_arm(
        manifest,
        policy,
        perception_profile,
        enable_requirement_hypotheses=enable_requirement_hypotheses,
        require_frozen_mistral=True,
    )


async def run_provider_cohort_arm(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    perception_profile: DecisionPerceptionProfile,
    *,
    enable_requirement_hypotheses: bool = False,
    visual_region_proposer=None,
) -> PerceptionArmOutcome:
    """Run one explicitly named provider cohort without weakening frozen A/B."""

    return await _run_arm(
        manifest,
        policy,
        perception_profile,
        enable_requirement_hypotheses=enable_requirement_hypotheses,
        require_frozen_mistral=False,
        visual_region_proposer=visual_region_proposer,
    )


async def _run_arm(
    manifest,
    policy,
    perception_profile,
    *,
    enable_requirement_hypotheses,
    require_frozen_mistral,
    visual_region_proposer=None,
):
    adapter = _adapter(policy, require_frozen_mistral=require_frozen_mistral)
    if adapter.perception_profile is not perception_profile:
        raise ValueError("perception A/B policy profile does not match its arm")
    if isinstance(adapter, GroundedToolDecisionAdapter) and enable_requirement_hypotheses:
        raise ValueError("grounded-tools short-loop profile forbids requirement-hypothesis calls")
    configured_identity = (
        getattr(adapter.port, "provider", ""),
        getattr(adapter.port, "model", ""),
        adapter.grounding_profile_version,
    )
    instrumentations: list[BenchmarkInstrumentation] = []
    proposer = (
        ModelRequirementHypothesisProposer(
            adapter.port,
            adapter.config,
            perception_profile,
        )
        if enable_requirement_hypotheses
        else None
    )
    target = _target_manifest(
        manifest,
        policy,
        FixedPacingState(),
        instrumentations,
        proposer,
        visual_region_proposer,
    )
    target = replace(
        target,
        profile_id=(
            (
                "grounded-tools-v2"
                if isinstance(adapter, GroundedToolDecisionAdapter)
                else "dynamic-tools-v1"
                if isinstance(adapter, DynamicToolDecisionAdapter)
                else "structured-package-v2"
            )
            + f"-{perception_profile.value}"
            + ("-requirement-hypotheses" if enable_requirement_hypotheses else "")
        ),
    )
    suite = await run_suite(target)
    suite = replace(suite, cases=tuple(_derived_metrics(item) for item in suite.cases))
    records = tuple(
        _record(case, result, instrumentation)
        for case, result, instrumentation in zip(
            manifest.cases,
            suite.cases,
            instrumentations,
            strict=True,
        )
    )
    provider, model, grounding = _model_identity(instrumentations, configured_identity)
    errors = _arm_errors(records, suite.identity.git_sha, suite.identity.git_dirty)
    hypothesis_calls = sum(
        _integer(item.result, "requirement_hypothesis_calls")
        for item in records
    )
    if enable_requirement_hypotheses:
        errors.extend(
            f"{item.case_id}: requirement hypothesis call metric is unavailable"
            for item in records
            if _integer(item.result, "requirement_hypothesis_calls") < 1
        )
    elif hypothesis_calls:
        errors.append("disabled requirement-hypothesis profile recorded model calls")
    return PerceptionArmOutcome(
        perception_profile,
        records,
        provider,
        model,
        grounding,
        tuple(errors),
        sum(_integer(item.result, "provider_attempts") for item in records),
        sum(_integer(item.result, "total_tokens") for item in records),
        sum(_number(item.result, "model_latency_ms") for item in records),
        enable_requirement_hypotheses,
        hypothesis_calls,
    )


def write_perception_ab(
    output_dir: Path,
    *,
    implementation_sha: str,
    case_ids: tuple[str, ...],
    arms: tuple[PerceptionArmOutcome, ...],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    for arm in arms:
        arm_dir = output_dir / arm.perception_profile.value
        arm_dir.mkdir()
        for record in arm.records:
            _atomic_json(
                arm_dir / f"{record.case_id}.json",
                {
                    "cohort": CAPABILITY_COVERED_COHORT,
                    "perception_profile": arm.perception_profile.value,
                    "typed_outcome": record.outcome.value,
                    "policy_trace": record.diagnostic_trace,
                    "case": public_case_evidence(record.result),
                },
            )
    report = output_dir / "report.json"
    public = {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE_ID,
        "implementation_sha": implementation_sha,
        "cohort": CAPABILITY_COVERED_COHORT,
        "primary_metric": "declared-capability-covered cohort success rate",
        "case_ids": case_ids,
        "same_model_required": True,
        "mixed_cohort_success_rate_prohibited": True,
        "arms": [
            {
                "perception_profile": arm.perception_profile.value,
                "provider_id": arm.provider_id,
                "model_id": arm.model_id,
                "grounding_profile": arm.grounding_profile,
                "completed_cases": len(arm.records),
                "success_count": arm.success_count,
                "outcome_counts": _outcome_counts(arm.records),
                "provider_attempts": arm.provider_attempts,
                "total_tokens": arm.total_tokens,
                "model_latency_ms": arm.model_latency_ms,
                "requirement_hypotheses_enabled": arm.requirement_hypotheses_enabled,
                "requirement_hypothesis_calls": arm.requirement_hypothesis_calls,
                "errors": arm.errors,
            }
            for arm in arms
        ],
    }
    identities = {(arm.provider_id, arm.model_id, arm.grounding_profile) for arm in arms}
    errors = [error for arm in arms for error in arm.errors]
    if len(arms) != 2 or {item.perception_profile for item in arms} != {
        DecisionPerceptionProfile.TEXT_ONLY,
        DecisionPerceptionProfile.SCREENSHOT_AX,
    }:
        errors.append("A/B requires exactly the text-only and screenshot+AX arms")
    if len(identities) != 1:
        errors.append("A/B arms did not use the same provider/model/grounding identity")
    if len({arm.requirement_hypotheses_enabled for arm in arms}) != 1:
        errors.append("A/B arms did not use the same requirement-hypothesis profile")
    inconclusive_pairs = _inconclusive_pairs(case_ids, arms)
    run_evidence_valid = not errors
    comparison_valid = run_evidence_valid and not inconclusive_pairs
    _atomic_json(
        report,
        {
            **public,
            "run_evidence_valid": run_evidence_valid,
            "comparison_valid": comparison_valid,
            "inconclusive_pairs": inconclusive_pairs,
            "evidence_valid": run_evidence_valid,
            "errors": errors,
        },
    )
    return report


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _adapter(
    policy: ModelBackedAgentPolicy,
    *,
    require_frozen_mistral: bool = True,
) -> ModelPortDecisionAdapter | DynamicToolDecisionAdapter | GroundedToolDecisionAdapter:
    composed = policy.port
    adapter = composed.primary_port if isinstance(composed, ProviderCallOrchestrator) else composed
    if not isinstance(
        adapter,
        ModelPortDecisionAdapter | DynamicToolDecisionAdapter | GroundedToolDecisionAdapter,
    ):
        raise TypeError("perception A/B requires the canonical model bridge")
    if require_frozen_mistral and (
        getattr(adapter.port, "provider", "") != "mistral"
        or getattr(adapter.port, "model", "") != "mistral-medium-3-5"
    ):
        raise ValueError("perception A/B requires the frozen Mistral model identity")
    if adapter.perception_profile is DecisionPerceptionProfile.SCREENSHOT_AX and not getattr(
        adapter.port, "supports_multimodal", False
    ):
        raise ValueError("screenshot+AX arm requires a multimodal model port")
    return adapter


def _arm_errors(records, initial_sha: str, initial_dirty: bool) -> list[str]:
    errors: list[str] = []
    final_sha, final_dirty = _final_git_identity()
    if initial_dirty or final_dirty or final_sha != initial_sha:
        errors.append("git identity was dirty or changed during the arm")
    if not records:
        errors.append("perception arm has no declared-supported cases")
    for record in records:
        for name in _SAFETY_METRICS:
            measurement = record.result.measurements.get(name)
            if measurement is None or not measurement.measured or measurement.value != 0:
                errors.append(f"{record.case_id}: safety metric {name} is unavailable or nonzero")
        if record.result.harness_integrity_failures:
            errors.append(f"{record.case_id}: harness integrity failed")
    return errors


def _inconclusive_pairs(
    case_ids: tuple[str, ...],
    arms: tuple[PerceptionArmOutcome, ...],
) -> tuple[str, ...]:
    inconclusive = {
        MiniWobTaskOutcome.PROVIDER_UNAVAILABLE,
        MiniWobTaskOutcome.PROVIDER_TIMEOUT,
        MiniWobTaskOutcome.PROVIDER_REFUSED,
        MiniWobTaskOutcome.STRUCTURED_OUTPUT_FAILURE,
        MiniWobTaskOutcome.CASE_TIMEOUT,
        MiniWobTaskOutcome.ENVIRONMENT_FAILURE,
        MiniWobTaskOutcome.CLEANUP_FAILURE,
    }
    by_arm = [{record.case_id: record for record in arm.records} for arm in arms]
    return tuple(
        case_id
        for case_id in case_ids
        if any(
            case_id not in records
            or records[case_id].outcome in inconclusive
            or bool(records[case_id].result.harness_integrity_failures)
            for records in by_arm
        )
    )
