"""Secret-free exact-head attestation for recurrent qualification reports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .contracts import ModelProfileIdentity
from .matrix_runner import DecisionMatrixResult
from .recurrent_qualification import RecurrentQualification


@dataclass(frozen=True)
class RecurrentReportFile:
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class RecurrentAttestation:
    schema_version: str
    git_sha: str
    git_dirty: bool
    profile_identity: ModelProfileIdentity
    grounding_profile: str
    decision_schema_digest: str
    result_summary_max_chars: int
    guide_schema_versions: tuple[str, ...]
    guide_digests: tuple[str, ...]
    mode: str
    repetitions: int
    decision_success_counts: tuple[tuple[str, int, int], ...]
    critical_success_counts: tuple[tuple[str, int, int], ...]
    runtime_success_count: int
    provider_failure_counts: tuple[tuple[str, int], ...]
    retry_count: int
    fallback_count: int
    safety_violation_count: int
    report_files: tuple[RecurrentReportFile, ...]
    accepted: bool
    errors: tuple[str, ...]


def attest_recurrent(
    result: DecisionMatrixResult,
    qualification: RecurrentQualification,
    report_paths: tuple[Path, ...],
    *,
    git_sha: str,
    git_dirty: bool,
) -> RecurrentAttestation:
    errors = []
    if git_dirty:
        errors.append("recurrent attestation requires a clean exact tree")
    if result.retry_count or result.fallback_count:
        errors.append("recurrent attestation requires zero retry and fallback")
    guide_versions = tuple(sorted({item.guide_schema_version for item in result.attempts if item.guide_schema_version}))
    guide_digests = tuple(sorted({item.guide_digest for item in result.attempts if item.guide_digest}))
    if guide_versions != (result.identity.grounding_profile_version,) or not guide_digests:
        errors.append("recurrent attestation lacks exact compact guide identity")
    files = tuple(_file(path) for path in report_paths)
    return RecurrentAttestation(
        "recurrent-agent-policy.v1", git_sha, git_dirty, result.identity,
        result.identity.grounding_profile_version, result.identity.decision_schema_digest,
        result.identity.result_summary_max_chars, guide_versions, guide_digests,
        qualification.mode, qualification.repetitions, qualification.decision_success_counts,
        qualification.critical_success_counts, qualification.runtime_success_count,
        qualification.failure_counts, qualification.retry_count, qualification.fallback_count,
        qualification.safety_violation_count, files, not errors, tuple(errors),
    )


def _file(path: Path) -> RecurrentReportFile:
    content = path.read_bytes()
    return RecurrentReportFile(path.name, f"sha256:{hashlib.sha256(content).hexdigest()}", len(content))
