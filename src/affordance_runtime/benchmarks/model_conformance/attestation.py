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
    ConformanceCellSummary,
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
    structured_output_status: str
    action_selection_status: str
    full_recurrent_decision_status: str
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
    if not (
        identity.decision_schema_digest
        and identity.result_summary_max_chars
        and identity.grounding_variant
        and identity.grounding_profile_version
    ):
        errors.append("conformance report lacks the current exact support identity")
    attempts = tuple(item for result in results for item in result.attempts)
    variants = tuple(sorted({item.grounding_variant for item in attempts}))
    levels = tuple(sorted({item.level for item in attempts}, key=_level_sort_key))
    repetitions = max(Counter((item.grounding_variant, item.level) for item in attempts).values())
    success = Counter(f"{item.grounding_variant}:L{item.level}" for item in attempts if item.success)
    failures = Counter(item.stage.value for item in attempts if not item.success)
    files = tuple(_attested_file(path) for path in sorted(report_paths))
    return ModelConformanceAttestation(
        ATTESTATION_SCHEMA_VERSION, git_sha, git_dirty, identity, variants, levels, repetitions,
        max((item.input_complexity for item in results), key=lambda item: item.total_input_bytes),
        _status(results, attempts),
        _result_status(results, "structured_output_status"),
        _result_status(results, "action_selection_status"),
        _result_status(results, "full_recurrent_decision_status"),
        dict(sorted(success.items())), dict(sorted(failures.items())),
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
        tuple(ConformanceCellSummary(**item) for item in value.get("cell_summaries", ())),
        value.get("structured_output_status", ""),
        value.get("action_selection_status", ""),
        value.get("full_recurrent_decision_status", ""),
    )


def _level_sort_key(level: str) -> tuple[int, int]:
    return (int(level[1:]) if level.startswith("D") else int(level), int(level.startswith("D")))


def _status(results, attempts) -> ModelProfileSupportStatus:
    statuses = tuple(ModelProfileSupportStatus(item.classification) for item in results)
    if ModelProfileSupportStatus.FULL_RECURRENT_POLICY_SUPPORTED in statuses:
        return ModelProfileSupportStatus.FULL_RECURRENT_POLICY_SUPPORTED
    if ModelProfileSupportStatus.ACTION_SELECTION_SUPPORTED in statuses:
        return ModelProfileSupportStatus.ACTION_SELECTION_SUPPORTED
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


def _result_status(results, field: str) -> str:
    values = tuple(getattr(item, field) for item in results if getattr(item, field))
    return values[-1] if values else "not_admitted"
