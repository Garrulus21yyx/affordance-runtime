"""Secret-free exact-head attestation for a two-stage suite report."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.model.policy.schema_identity import decision_schema_digest

from ..contracts import ModelProfileIdentity
from .reporting import TwoStageSuiteReport


@dataclass(frozen=True)
class TwoStageReportFile:
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class TwoStageAttestation:
    schema_version: str
    git_sha: str
    git_dirty: bool
    profile_identity: ModelProfileIdentity
    grounding_source_profile: str
    route_schema_version: str
    payload_schema_version: str
    progress_schema_version: str
    decision_schema_digest: str
    mode: str
    repetitions: int
    routing_attempts: int
    routing_success: int
    payload_attempts: int
    payload_success: int
    end_to_end_attempts: int
    end_to_end_success: int
    critical_attempts: int
    critical_success: int
    baseline_attempts: int
    baseline_success: int
    provider_calls: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    inter_stage_delay_s: float
    inter_attempt_delay_s: float
    retry_count: int
    fallback_count: int
    safety_violation_count: int
    report_files: tuple[TwoStageReportFile, ...]
    accepted: bool
    errors: tuple[str, ...]


def attest_two_stage(
    report: TwoStageSuiteReport,
    report_paths: tuple[Path, ...],
    *,
    git_sha: str,
    git_dirty: bool,
) -> TwoStageAttestation:
    errors = []
    if git_dirty:
        errors.append("two-stage attestation requires a clean exact tree")
    qualification = report.qualification
    if qualification.retry_count or qualification.fallback_count:
        errors.append("two-stage attestation requires zero retry and fallback")
    stages = (report.routing, report.payload, report.end_to_end, report.critical)
    return TwoStageAttestation(
        "two-stage-attestation.v1", git_sha, git_dirty, report.profile_identity,
        "compact-contract.v2", "decision-kind-route.v1", "canonical-branch-bound.v1",
        "two-stage-progress.v1", decision_schema_digest(), report.mode, report.repetitions,
        len(report.routing.attempts), report.routing.success_count,
        len(report.payload.attempts), report.payload.success_count,
        len(report.end_to_end.attempts), report.end_to_end.success_count,
        len(report.critical.attempts), report.critical.success_count,
        report.baseline.attempt_count, report.baseline.success_count,
        report.baseline.provider_calls + sum(item.provider_calls for item in stages),
        report.baseline.prompt_tokens + sum(item.prompt_tokens for item in stages),
        report.baseline.completion_tokens + sum(item.completion_tokens for item in stages),
        report.baseline.latency_ms + sum(item.latency_ms for item in stages),
        report.pacing.inter_stage_delay_s, report.pacing.inter_attempt_delay_s,
        qualification.retry_count, qualification.fallback_count, 0,
        tuple(_file(path) for path in report_paths), not errors, tuple(errors),
    )


def _file(path: Path) -> TwoStageReportFile:
    content = path.read_bytes()
    return TwoStageReportFile(path.name, "sha256:" + hashlib.sha256(content).hexdigest(), len(content))
