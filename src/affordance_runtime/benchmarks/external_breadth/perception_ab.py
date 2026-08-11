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
from affordance_runtime.model_policy.model_port_bridge import (
    DecisionPerceptionProfile,
    ModelPortDecisionAdapter,
)
from affordance_runtime.model_policy.provider_orchestrator import ProviderCallOrchestrator

SCHEMA_VERSION = "miniwob-perception-ab.v1"
PROFILE_ID = "MINIWOB_DECLARED_SUPPORTED_PERCEPTION_AB"
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

    @property
    def success_count(self) -> int:
        return sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in self.records)


def declared_supported_cases(
    manifest: MiniWobBreadthManifest,
    census: MiniWobRegistryCensus,
    *,
    source_root: Path | None = None,
) -> tuple:
    inventory = build_capability_inventory_v2(census, source_root)
    readiness = {
        item.task_id: task_readiness(item, current_declared_capabilities())
        for item in inventory
    }
    return tuple(
        case for case in manifest.cases
        if readiness.get(case.task_id) is TaskReadiness.DECLARED_SUPPORTED
    )


async def run_perception_arm(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    perception_profile: DecisionPerceptionProfile,
) -> PerceptionArmOutcome:
    adapter = _adapter(policy)
    if adapter.perception_profile is not perception_profile:
        raise ValueError("perception A/B policy profile does not match its arm")
    configured_identity = (
        getattr(adapter.port, "provider", ""),
        getattr(adapter.port, "model", ""),
        adapter.grounding_profile_version,
    )
    instrumentations: list[BenchmarkInstrumentation] = []
    target = _target_manifest(manifest, policy, FixedPacingState(), instrumentations)
    target = replace(
        target,
        profile_id=f"mistral-format-only-{perception_profile.value}",
    )
    suite = await run_suite(target)
    suite = replace(suite, cases=tuple(_derived_metrics(item) for item in suite.cases))
    records = tuple(
        _record(case, result, instrumentation)
        for case, result, instrumentation in zip(
            manifest.cases, suite.cases, instrumentations, strict=True,
        )
    )
    provider, model, grounding = _model_identity(instrumentations, configured_identity)
    errors = _arm_errors(records, suite.identity.git_sha, suite.identity.git_dirty)
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
            _atomic_json(arm_dir / f"{record.case_id}.json", {
                "cohort": TaskReadiness.DECLARED_SUPPORTED.value,
                "perception_profile": arm.perception_profile.value,
                "typed_outcome": record.outcome.value,
                "policy_trace": record.diagnostic_trace,
                "case": public_case_evidence(record.result),
            })
    report = output_dir / "report.json"
    public = {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE_ID,
        "implementation_sha": implementation_sha,
        "cohort": TaskReadiness.DECLARED_SUPPORTED.value,
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
    _atomic_json(report, {**public, "evidence_valid": not errors, "errors": errors})
    return report


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _adapter(policy: ModelBackedAgentPolicy) -> ModelPortDecisionAdapter:
    composed = policy.port
    adapter = composed.primary_port if isinstance(composed, ProviderCallOrchestrator) else composed
    if not isinstance(adapter, ModelPortDecisionAdapter):
        raise TypeError("perception A/B requires the canonical model bridge")
    if (
        getattr(adapter.port, "provider", "") != "mistral"
        or getattr(adapter.port, "model", "") != "mistral-medium-3-5"
    ):
        raise ValueError("perception A/B requires the frozen Mistral model identity")
    if (
        adapter.perception_profile is DecisionPerceptionProfile.SCREENSHOT_AX
        and not getattr(adapter.port, "supports_multimodal", False)
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
