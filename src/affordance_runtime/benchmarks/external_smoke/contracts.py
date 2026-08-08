"""Immutable external-smoke manifest, admission, and execution contracts."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.benchmarks.target_loop.contracts import MetricExpectation


@dataclass(frozen=True)
class ExternalSmokeCase:
    case_id: str
    benchmark_family: str
    benchmark_task_id: str
    description: str
    max_turns: int
    timeout_s: float
    seed: int
    allowed_primitives: tuple[str, ...]
    verifier_profile: str
    expected_terminal_statuses: tuple[str, ...]
    required_measurements: tuple[str, ...]
    metric_expectations: tuple[MetricExpectation, ...]

    def __post_init__(self) -> None:
        if not self.case_id or not self.benchmark_task_id or not self.description:
            raise ValueError("external smoke case identity is required")
        if not 0 < self.max_turns <= 20 or not 0 < self.timeout_s <= 300:
            raise ValueError("external smoke case exceeds its bounded execution profile")
        if self.verifier_profile != "environment-native-mechanical":
            raise ValueError("first external smoke profile must use its mechanical verifier")


@dataclass(frozen=True)
class ExternalSmokeManifest:
    schema_version: str
    manifest_id: str
    benchmark_family: str
    package_name: str
    package_version: str
    source_commit: str
    reviewed: bool
    mechanical_only: bool
    cases: tuple[ExternalSmokeCase, ...]

    def __post_init__(self) -> None:
        if not 3 <= len(self.cases) <= 5:
            raise ValueError("external smoke manifest must contain three to five fixed cases")
        ids = tuple(item.case_id for item in self.cases)
        tasks = tuple(item.benchmark_task_id for item in self.cases)
        if len(ids) != len(set(ids)) or len(tasks) != len(set(tasks)):
            raise ValueError("external smoke case and task IDs must be unique")
        if any(item.benchmark_family != self.benchmark_family for item in self.cases):
            raise ValueError("external smoke case family must match its manifest")


@dataclass(frozen=True)
class ExternalBenchmarkAdmissionEvidence:
    git_sha: str
    internal_git_sha: str
    full_ci_git_sha: str
    live_policy_git_sha: str
    internal_harness_attestation_sha256: str
    full_ci_attestation_sha256: str
    live_model_policy_attestation_sha256: str
    external_manifest_digest: str
    internal_harness_accepted: bool
    expected_internal_run_set_complete: bool
    full_ci_accepted: bool
    live_policy_accepted: bool
    live_evaluator_required: bool
    live_evaluator_accepted: bool | None
    forbidden_effect_attempts: int
    duplicate_unknown_attempts: int
    stale_zero_call_violations: int
    clean_tree: bool
    optional_dependency_available: bool
    optional_dependency_version: str
    target_loop_adapter_ready: bool


@dataclass(frozen=True)
class ExternalBenchmarkAdmission:
    admitted: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ExternalSmokeExecution:
    executed: bool
    status: str
    errors: tuple[str, ...]
    result_count: int = 0
