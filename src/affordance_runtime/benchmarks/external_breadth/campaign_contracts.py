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
    PROVIDER_REFUSED = "provider_refused"
    POLICY_ABORTED = "policy_aborted"
    POLICY_DECISION_FAILURE = "policy_decision_failure"
    NO_ACTION_OFFERED = "no_action_offered"
    OBSERVATION_REQUEST_FAILED = "observation_request_failed"
    PAGE_REQUEST_FAILED = "page_request_failed"
    ASK_USER_UNRESOLVED = "ask_user_unresolved"
    WAITING_USER_EFFECT_UNKNOWN = "waiting_user_effect_unknown"
    WAITING_USER_TASK_UNKNOWN = "waiting_user_task_unknown"
    TASK_FAILED = "task_failed"
    TASK_BLOCKED = "task_blocked"
    TASK_EVALUATION_UNKNOWN = "task_evaluation_unknown"
    WRONG_ACTION = "wrong_action"
    WRONG_PARAMETERS = "wrong_parameters"
    WRONG_DESTINATION = "wrong_destination"
    RUNTIME_REJECTED = "runtime_rejected"
    NO_PROGRESS_REPETITION = "no_progress_repetition"
    NO_PROGRESS_CONTROL_REPETITION = "no_progress_control_repetition"
    TURN_BUDGET_EXHAUSTED = "turn_budget_exhausted"
    CASE_TIMEOUT = "case_timeout"
    RESET_FAILURE = "reset_failure"
    INITIAL_OBSERVATION_FAILURE = "initial_observation_failure"
    PROJECTION_FAILURE = "projection_failure"
    CURRENTNESS_FAILURE = "currentness_failure"
    EXECUTION_FAILURE = "execution_failure"
    POST_OBSERVATION_FAILURE = "post_observation_failure"
    ACTION_EVALUATOR_FAILURE = "action_evaluator_failure"
    TASK_EVALUATOR_FAILURE = "task_evaluator_failure"
    UNSUPPORTED_PRIMITIVE = "unsupported_primitive"
    OBSERVATION_COVERAGE_FAILURE = "observation_coverage_failure"
    VERIFIER_UNKNOWN = "verifier_unknown"
    SENT_UNKNOWN = "sent_unknown"
    ENVIRONMENT_FAILURE = "environment_failure"
    CLEANUP_FAILURE = "cleanup_failure"
    UNCLASSIFIED_TYPED_FAILURE = "unclassified_typed_failure"
    OTHER_TYPED_FAILURE = "other_typed_failure"


@dataclass(frozen=True)
class MiniWobBreadthCampaignAcceptance:
    evidence_valid: bool
    errors: tuple[str, ...]
    planned_cases: int
    completed_cases: int
    successful_cases: int


@dataclass(frozen=True)
class ProviderCapacityEvidence:
    """Frozen, explicit preflight evidence; never inferred from run outcomes."""

    schema_version: str
    provider_id: str
    model_id: str
    manifest_digest: str
    required_attempt_budget: int
    declared_attempt_budget: int
    checked: bool
    grounding_profile: str = ""
    retry_count: int = -1
    fallback_count: int = -1

    @property
    def sufficient(self) -> bool:
        return self.checked and self.declared_attempt_budget >= self.required_attempt_budget

    def __post_init__(self) -> None:
        if self.schema_version != "provider-capacity-preflight.v1":
            raise ValueError("provider capacity schema is unsupported")
        if (
            not self.provider_id
            or not self.model_id
            or not self.manifest_digest
            or not self.grounding_profile
        ):
            raise ValueError("provider capacity evidence requires frozen identity")
        if (
            type(self.required_attempt_budget) is not int
            or type(self.declared_attempt_budget) is not int
            or self.required_attempt_budget <= 0
            or self.declared_attempt_budget < 0
            or type(self.checked) is not bool
            or type(self.retry_count) is not int
            or type(self.fallback_count) is not int
        ):
            raise ValueError("provider capacity budgets are invalid")
        if self.retry_count != 0 or self.fallback_count != 0:
            raise ValueError("formal provider preflight requires zero retry and fallback")


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
    provider_capacity: ProviderCapacityEvidence | None = None
