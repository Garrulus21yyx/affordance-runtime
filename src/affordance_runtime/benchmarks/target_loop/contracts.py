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
    harness_schema_version: str = "target-loop-harness.v2"

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

    def __post_init__(self) -> None:
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
})
