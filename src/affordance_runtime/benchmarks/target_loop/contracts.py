"""Immutable target-loop benchmark case, identity, metric, and result contracts."""

from __future__ import annotations

import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task import TaskGoal
from affordance_runtime.world.environment import WorldEnvironment


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
    environment_factory: Callable[[], WorldEnvironment]
    composition_factory: Callable[[], BenchmarkComposition]
    expected_terminal_statuses: tuple[AgentLoopStatus, ...]
    timeout_s: float
    seed: int
    required_measurements: tuple[str, ...]
    acceptance_profile: str
    metric_expectations: tuple[MetricExpectation, ...] = ()
    auto_confirm: bool = False

    def __post_init__(self) -> None:
        if not self.case_id or not self.suite_id or not 0 < self.timeout_s <= 300:
            raise ValueError("benchmark case identity and timeout are required")


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

    @classmethod
    def create(cls, suite_id: str, digest: str, profile_id: str, seed: int) -> BenchmarkRunIdentity:
        sha = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--short"))
        started = datetime.now(UTC).isoformat()
        run_id = f"{suite_id}:{sha[:12]}:{digest[:12]}:{seed}"
        return cls(run_id, sha, dirty, suite_id, digest, profile_id, seed, started, sys.version.split()[0], platform.platform())


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    status: str
    execution_completed: bool
    failure_reason: str
    observations: int
    executions: int
    currentness_probes: int
    turns: int
    policy_calls: int
    semantic_judge_calls: int
    provider_attempts: int
    confirmations: int
    ask_user_count: int
    wait_count: int
    page_request_count: int
    sent_unknown_count: int
    duplicate_unknown_attempts: int
    forbidden_effect_attempts: int
    stale_opportunities: int
    stale_zero_call_violations: int
    latency_ms: float
    measurements: dict[str, MetricMeasurement] = field(default_factory=dict)


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
