"""Immutable typed breadth execution and evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthManifest
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCaseResult, BenchmarkSuiteResult


class MiniWobTaskOutcome(StrEnum):
    SUCCESS = "success"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    STRUCTURED_OUTPUT_FAILURE = "structured_output_failure"
    NO_ACTION_OFFERED = "no_action_offered"
    WRONG_ACTION = "wrong_action"
    WRONG_PARAMETERS = "wrong_parameters"
    WRONG_DESTINATION = "wrong_destination"
    RUNTIME_REJECTED = "runtime_rejected"
    NO_PROGRESS_REPETITION = "no_progress_repetition"
    TURN_BUDGET_EXHAUSTED = "turn_budget_exhausted"
    CASE_TIMEOUT = "case_timeout"
    UNSUPPORTED_PRIMITIVE = "unsupported_primitive"
    OBSERVATION_COVERAGE_FAILURE = "observation_coverage_failure"
    VERIFIER_UNKNOWN = "verifier_unknown"
    SENT_UNKNOWN = "sent_unknown"
    ENVIRONMENT_FAILURE = "environment_failure"
    CLEANUP_FAILURE = "cleanup_failure"
    OTHER_TYPED_FAILURE = "other_typed_failure"


@dataclass(frozen=True)
class MiniWobBreadthCampaignAcceptance:
    evidence_valid: bool
    errors: tuple[str, ...]
    planned_cases: int
    completed_cases: int
    successful_cases: int


@dataclass(frozen=True)
class MiniWobBreadthCaseRecord:
    case_id: str
    task_family_label: str
    capability_profile: str
    required_primitives: tuple[str, ...]
    outcome: MiniWobTaskOutcome
    classification_source: str
    result: BenchmarkCaseResult


@dataclass(frozen=True)
class MiniWobBreadthCampaignOutcome:
    run_id: str
    manifest: MiniWobBreadthManifest
    manifest_digest: str
    suite: BenchmarkSuiteResult
    cases: tuple[MiniWobBreadthCaseRecord, ...]
    acceptance: MiniWobBreadthCampaignAcceptance
    provider_id: str
    model_id: str
    grounding_profile: str
