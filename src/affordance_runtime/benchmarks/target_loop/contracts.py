"""Immutable target-loop benchmark case, identity, metric, and result contracts."""

from __future__ import annotations

import platform
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task import TaskGoal
from affordance_runtime.world.environment import WorldEnvironment

if TYPE_CHECKING:
    from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation


@dataclass(frozen=True)
class MetricMeasurement:
    value: int | float | None
    measured: bool
    opportunities: int | None = None
    unit: str = "count"

    def __post_init__(self) -> None:
        if self.measured == (self.value is None):
            raise ValueError("measured metrics require a value and unmeasured metrics require None")
        if self.opportunities is not None and self.opportunities < 0:
            raise ValueError("metric opportunities cannot be negative")
        if not self.unit:
            raise ValueError("metric unit is required")


class MetricExpectationOperator(StrEnum):
    EQ = "eq"
    MIN = "min"
    MAX = "max"
    ZERO = "zero"
    NONZERO = "nonzero"


class TerminalReasonCode(StrEnum):
    ACTION_OUTSIDE_CURRENT_PAGE = "action_outside_current_page"
    DESTINATION_OUTSIDE_CURRENT_PAGE = "destination_outside_current_page"
    ACTION_OUTSIDE_ACTION_SPACE = "action_outside_action_space"
    INVALID_ACTION_PARAMETERS = "invalid_action_parameters"
    INVALID_COMPLETION_CLAIM = "invalid_completion_claim"
    COMPLETION_EVIDENCE_NOT_CURRENT = "completion_evidence_not_current"
    OBSERVATION_CAPABILITY_NOT_OFFERED = "observation_capability_not_offered"
    INVALID_ACTION_PAGE_REQUEST = "invalid_action_page_request"
    WAIT_BUDGET_EXHAUSTED = "wait_budget_exhausted"
    STALE_BOUND_REQUEST = "stale_bound_request"
    INVALID_CONFIRMATION_DECISION = "invalid_confirmation_decision"
    NO_PROGRESS_REPETITION = "no_progress_repetition"
    BLOCKED_OTHER = "blocked_other"


class CaseFailureOrigin(StrEnum):
    NONE = "none"
    ENVIRONMENT_FACTORY = "environment_factory"
    TASK_FACTORY = "task_factory"
    COMPOSITION_FACTORY = "composition_factory"
    LOOP_CONSTRUCTION = "loop_construction"
    SESSION_START = "session_start"
    ENVIRONMENT_RESET = "environment_reset"
    INITIAL_OBSERVATION = "initial_observation"
    OBSERVATION_PROJECTION = "observation_projection"
    POLICY_DECISION = "policy_decision"
    DECISION_CONTROL = "decision_control"
    ACTION_BINDING = "action_binding"
    CURRENTNESS = "currentness"
    EXECUTION = "execution"
    POST_ACTION_OBSERVATION = "post_action_observation"
    ACTION_EVALUATION = "action_evaluation"
    TASK_EVALUATION = "task_evaluation"
    HARNESS_WATCHDOG = "harness_watchdog"
    CLEANUP = "cleanup"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureFacts:
    """Orthogonal privacy-safe facts; primary classification is a projection."""

    runtime_reason_code: str = ""
    agent_failure_code: str = ""
    policy_failure_code: str = ""
    component_origin: CaseFailureOrigin = CaseFailureOrigin.NONE
    component_code: str = ""
    component_exception_class: str = ""
    watchdog_code: str = ""
    cleanup_code: str = ""
    cleanup_exception_class: str = ""
    harness_integrity_code: str = ""

    def __post_init__(self) -> None:
        for value in (
            self.runtime_reason_code, self.agent_failure_code, self.policy_failure_code,
            self.component_code, self.watchdog_code, self.cleanup_code,
            self.harness_integrity_code,
        ):
            if value and (len(value) > 96 or not value.replace("_", "").isalnum()):
                raise ValueError("failure fact codes must be bounded identifiers")
        for value in (self.component_exception_class, self.cleanup_exception_class):
            if value and (len(value) > 128 or not value.replace("_", "").isalnum()):
                raise ValueError("failure exception classes must be bounded names")
        has_component = self.component_origin is not CaseFailureOrigin.NONE
        if has_component != bool(self.component_code):
            raise ValueError("component failure origin and code must be present together")
        if not has_component and self.component_exception_class:
            raise ValueError("component exception class requires a component failure")
        if bool(self.cleanup_code) != bool(self.cleanup_exception_class):
            raise ValueError("cleanup failure code and exception class must be present together")


@dataclass(frozen=True)
class MetricExpectation:
    metric: str
    operator: MetricExpectationOperator
    value: int | float | None = None

    def __post_init__(self) -> None:
        if not self.metric:
            raise ValueError("metric expectation name is required")
        requires_value = self.operator in {
            MetricExpectationOperator.EQ,
            MetricExpectationOperator.MIN,
            MetricExpectationOperator.MAX,
        }
        if requires_value != (self.value is not None):
            raise ValueError("metric expectation value does not match its operator")


@dataclass(frozen=True)
class BenchmarkComposition:
    policy: AgentPolicy
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    risk_policy: RiskPolicy | None = None


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    suite_id: str
    description: str
    task_factory: Callable[[], TaskGoal]
    environment_factory: Callable[[BenchmarkInstrumentation], WorldEnvironment]
    composition_factory: Callable[[BenchmarkInstrumentation], BenchmarkComposition]
    expected_terminal_statuses: tuple[AgentLoopStatus, ...]
    timeout_s: float
    seed: int
    required_measurements: tuple[str, ...]
    metric_expectations: tuple[MetricExpectation, ...] = ()
    auto_confirm: bool = False

    def __post_init__(self) -> None:
        if not self.case_id or not self.suite_id or not 0 < self.timeout_s <= 300:
            raise ValueError("benchmark case identity and timeout are required")
        names = tuple(item.metric for item in self.metric_expectations)
        if len(names) != len(set(names)):
            raise ValueError("benchmark metric expectations must be unique")
        if any(name not in _KNOWN_METRICS for name in (*self.required_measurements, *names)):
            raise ValueError("benchmark case references an unknown metric")


@dataclass(frozen=True)
class BenchmarkManifest:
    schema_version: str
    suite_id: str
    profile_id: str
    seed: int
    cases: tuple[BenchmarkCase, ...]

    def __post_init__(self) -> None:
        if not self.schema_version or not self.suite_id or not self.profile_id or not self.cases:
            raise ValueError("benchmark manifest identity and cases are required")
        identities = tuple(item.case_id for item in self.cases)
        if any(not item for item in identities) or len(identities) != len(set(identities)):
            raise ValueError("benchmark manifest case IDs must be nonblank and unique")
        if any(item.suite_id != self.suite_id or item.seed != self.seed for item in self.cases):
            raise ValueError("benchmark case suite and seed must match its manifest")


@dataclass(frozen=True)
class BenchmarkRunIdentity:
    run_id: str
    git_sha: str
    git_dirty: bool
    suite_id: str
    manifest_digest: str
    profile_id: str
    seed: int
    started_at_utc: str
    python_version: str
    platform: str
    manifest_schema_version: str = "target-loop-manifest.v1"
    harness_schema_version: str = "target-loop-harness.v6"

    @classmethod
    def create(cls, suite_id: str, digest: str, profile_id: str, seed: int) -> BenchmarkRunIdentity:
        sha = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--short"))
        started = datetime.now(UTC).isoformat()
        run_id = f"{suite_id}:{profile_id}:{sha[:12]}:{digest[:12]}:{seed}"
        return cls(run_id, sha, dirty, suite_id, digest, profile_id, seed, started, sys.version.split()[0], platform.platform())


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    status: str
    execution_completed: bool
    failure_reason: str
    latency_ms: float
    measurements: Mapping[str, MetricMeasurement] = field(default_factory=dict)
    terminal_reason_code: TerminalReasonCode | None = None
    termination_origin: str = ""
    case_failure_code: str = ""
    partial_episode_available: bool = False
    latest_task_status: str = ""
    latest_action_evaluation_status: str = ""
    latest_semantic_attempt_key_digest: str = ""
    same_attempt_streak: int = 0
    no_progress_count: int = 0
    last_progress_event_type: str = ""
    failure_origin: CaseFailureOrigin = CaseFailureOrigin.NONE
    failure_code: str = ""
    exception_class: str = ""
    last_decision_type: str = ""
    last_policy_failure_code: str = ""
    last_action_space_option_count: int = 0
    last_world_target_count: int = 0
    last_world_coverage: str = ""
    pending_kind: str = ""
    runtime_reason_code: str = ""
    agent_failure_code: str = ""
    cleanup_failure_code: str = ""
    cleanup_exception_class: str = ""
    cleanup_failures: int = 0
    watchdog_triggered: bool = False
    harness_integrity_code: str = ""
    harness_integrity_failures: int = 0
    failure_facts: FailureFacts = field(default_factory=FailureFacts)
    case_schema_version: str = "target-loop-case.v6"
    suite_id: str = ""
    profile_id: str = ""
    seed: int = 0
    manifest_digest: str = ""
    harness_schema_version: str = "target-loop-harness.v6"

    def __post_init__(self) -> None:
        blocked = self.status == str(AgentLoopStatus.BLOCKED)
        if blocked and self.terminal_reason_code is None:
            raise ValueError("blocked case result requires a terminal reason code")
        no_progress = (
            self.status == str(AgentLoopStatus.FAILED)
            and self.terminal_reason_code == TerminalReasonCode.NO_PROGRESS_REPETITION
        )
        if not blocked and not no_progress and self.terminal_reason_code is not None:
            raise ValueError("non-blocked case result cannot carry a terminal reason code")
        if self.exception_class and (
            len(self.exception_class) > 128 or not self.exception_class.replace("_", "").isalnum()
        ):
            raise ValueError("benchmark exception metadata must be a bounded class name")
        if self.cleanup_exception_class and (
            len(self.cleanup_exception_class) > 128
            or not self.cleanup_exception_class.replace("_", "").isalnum()
        ):
            raise ValueError("cleanup exception metadata must be a bounded class name")
        if self.cleanup_failures not in {0, 1}:
            raise ValueError("cleanup failure count must be zero or one")
        if self.harness_integrity_failures not in {0, 1}:
            raise ValueError("harness integrity failure count must be zero or one")
        if not self.case_schema_version or not self.harness_schema_version:
            raise ValueError("benchmark case evidence requires schema identity")
        identity_values = (self.suite_id, self.profile_id, self.manifest_digest)
        if any(identity_values) and not all(identity_values):
            raise ValueError("benchmark case evidence identity must be complete")
        facts = self.failure_facts
        if (
            self.runtime_reason_code != facts.runtime_reason_code
            or self.agent_failure_code != facts.agent_failure_code
            or self.last_policy_failure_code != facts.policy_failure_code
            or self.cleanup_failure_code != facts.cleanup_code
            or self.cleanup_exception_class != facts.cleanup_exception_class
            or self.harness_integrity_code != facts.harness_integrity_code
        ):
            raise ValueError("benchmark case duplicate failure projections are inconsistent")
        if facts.component_origin is not CaseFailureOrigin.NONE and (
            self.failure_origin is not facts.component_origin
            or self.failure_code != facts.component_code
            or self.exception_class != facts.component_exception_class
        ):
            raise ValueError("benchmark component failure projection is inconsistent")
        if self.watchdog_triggered != bool(facts.watchdog_code):
            raise ValueError("benchmark watchdog projection is inconsistent")
        if bool(self.cleanup_failures) != bool(facts.cleanup_code):
            raise ValueError("benchmark cleanup projection is inconsistent")
        if bool(self.harness_integrity_failures) != bool(facts.harness_integrity_code):
            raise ValueError("benchmark integrity projection is inconsistent")
        official = self.measurements.get("official_success_count")
        has_failure_fact = any((
            facts.runtime_reason_code,
            facts.agent_failure_code,
            facts.policy_failure_code,
            facts.component_code,
            facts.watchdog_code,
            facts.cleanup_code,
            facts.harness_integrity_code,
        ))
        if (
            self.status == str(AgentLoopStatus.DONE)
            and official is not None
            and official.measured
            and official.value == 1
            and has_failure_fact
        ):
            raise ValueError("successful benchmark evidence cannot carry failure facts")
        object.__setattr__(self, "measurements", FrozenMeasurements(self.measurements))


class FrozenMeasurements(dict[str, MetricMeasurement]):
    """JSON-serializable mapping with no mutation path after result construction."""

    def _immutable(self, *_args, **_kwargs):
        raise TypeError("benchmark measurements are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


@dataclass(frozen=True)
class BenchmarkAcceptance:
    accepted: bool
    acceptance_errors: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkSuiteResult:
    identity: BenchmarkRunIdentity
    cases: tuple[BenchmarkCaseResult, ...]
    acceptance: BenchmarkAcceptance
    rates: dict[str, float | None]


def _git(*args: str) -> str:
    result = subprocess.run(("git", *args), check=True, capture_output=True, text=True)
    value = result.stdout.strip()
    if args[:2] == ("rev-parse", "HEAD") and len(value) != 40:
        raise RuntimeError("benchmark run requires an exact git identity")
    return value


_KNOWN_METRICS = frozenset({
    "observations", "executions", "currentness_probes", "turns", "policy_calls",
    "semantic_judge_calls", "provider_attempts", "confirmations", "ask_user_count",
    "wait_count", "page_request_count", "sent_unknown_count", "duplicate_unknown_attempts",
    "forbidden_effect_attempts", "stale_opportunities", "stale_zero_call_violations",
    "effectful_dispatches", "dom_click_calls", "visual_proposer_calls", "pointer_calls",
    "td_requests", "property_reads", "wot_action_calls",
    "browsergym_reset_calls", "browsergym_step_calls", "browsergym_probe_calls",
    "dom_action_calls", "fill_calls", "select_calls", "official_verifier_queries",
    "official_success_count", "provider_retry_count", "fallback_count", "cleanup_failures",
    "prompt_tokens", "completion_tokens", "total_tokens", "model_latency_ms",
    "click_calls", "already_satisfied_suppressions", "no_progress_terminations",
    "observation_contract_exceptions",
})
