"""Clean-tree attestation over secret-free exact-profile conformance reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.immutable import freeze_json, to_json_compatible

from .classification import ModelProfileSupportStatus
from .contracts import (
    ConformanceAttempt,
    ModelConformanceStage,
    ModelInputComplexity,
    ModelProfileConformanceResult,
    ModelProfileIdentity,
)

ATTESTATION_SCHEMA_VERSION = "model-profile-conformance.v1"


@dataclass(frozen=True)
class AttestedFile:
    relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ModelConformanceAttestation:
    schema_version: str
    git_sha: str
    git_dirty: bool
    profile_identity: ModelProfileIdentity
    grounding_variants: tuple[str, ...]
    levels: tuple[str, ...]
    repetitions: int
    input_complexity: ModelInputComplexity
    status: ModelProfileSupportStatus
    success_counts: Mapping[str, int]
    failure_stage_counts: Mapping[str, int]
    report_files: tuple[AttestedFile, ...]
    accepted: bool
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "success_counts", freeze_json(self.success_counts))
        object.__setattr__(self, "failure_stage_counts", freeze_json(self.failure_stage_counts))


def attest_results(
    report_paths: tuple[Path, ...],
    *,
    git_sha: str,
    git_dirty: bool,
) -> ModelConformanceAttestation:
    if not report_paths:
        raise ValueError("conformance attestation requires result reports")
    results = tuple(_load_result(path) for path in report_paths)
    identity = results[0].identity
    errors = []
    if git_dirty:
        errors.append("conformance attestation requires a clean exact tree")
    if any(result.identity != identity for result in results[1:]):
        errors.append("conformance reports do not share one exact profile identity")
    attempts = tuple(item for result in results for item in result.attempts)
    variants = tuple(sorted({item.grounding_variant for item in attempts}))
    levels = tuple(sorted({item.level for item in attempts}, key=int))
    repetitions = max(Counter((item.grounding_variant, item.level) for item in attempts).values())
    success = Counter(f"{item.grounding_variant}:L{item.level}" for item in attempts if item.success)
    failures = Counter(item.stage.value for item in attempts if not item.success)
    files = tuple(_attested_file(path) for path in sorted(report_paths))
    return ModelConformanceAttestation(
        ATTESTATION_SCHEMA_VERSION, git_sha, git_dirty, identity, variants, levels, repetitions,
        max((item.input_complexity for item in results), key=lambda item: item.total_input_bytes),
        _status(results, attempts), dict(sorted(success.items())), dict(sorted(failures.items())),
        files, not errors, tuple(errors),
    )


def write_attestation(path: Path, value: ModelConformanceAttestation) -> None:
    from dataclasses import asdict

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_json_compatible(asdict(value)), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_result(path: Path) -> ModelProfileConformanceResult:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = ModelProfileIdentity(**value["identity"])
    attempts = tuple(
        ConformanceAttempt(**{**item, "stage": ModelConformanceStage(item["stage"])})
        for item in value["attempts"]
    )
    return ModelProfileConformanceResult(
        identity, attempts, tuple(value["passed_levels"]), tuple(value["failed_levels"]),
        value["classification"], tuple(value["classification_reasons"]),
        ModelInputComplexity(**value["input_complexity"]),
    )


def _status(results, attempts) -> ModelProfileSupportStatus:
    statuses = tuple(ModelProfileSupportStatus(item.classification) for item in results)
    if ModelProfileSupportStatus.SUPPORTED in statuses:
        return ModelProfileSupportStatus.SUPPORTED
    if attempts and all(item.success for item in attempts):
        count = max(Counter((item.grounding_variant, item.level) for item in attempts).values())
        return ModelProfileSupportStatus.SINGLE_RUN_ATTESTED if count == 1 else ModelProfileSupportStatus.DIAGNOSTIC_PASS
    variants = {item.grounding_variant for item in attempts}
    if {"format-only", "compact-contract", "full-schema-text", "context-bound-schema"}.issubset(variants):
        return ModelProfileSupportStatus.UNSUPPORTED
    return statuses[-1]


def _attested_file(path: Path) -> AttestedFile:
    content = path.read_bytes()
    return AttestedFile(
        f"{path.parent.name}/{path.name}", f"sha256:{hashlib.sha256(content).hexdigest()}", len(content),
    )
