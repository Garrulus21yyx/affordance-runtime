"""Immutable target-loop benchmark case, identity, metric, and result contracts."""

from __future__ import annotations

import math
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.agent import AgentFailureCode, RunStatus
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.decision_capability import (
    DecisionCapability,
    normalize_decision_capabilities,
)
from affordance_runtime.agent.decisions import AbortCategory
from affordance_runtime.agent.policy import (
    ActionOutcomeProjector,
    AgentPolicy,
    TaskEvaluator,
)
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.benchmarks.target_loop.metric_registry import CANONICAL_METRICS
from affordance_runtime.evaluation import (
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluationStatus,
    TaskOutcomeKind,
)
from affordance_runtime.execution.contracts import ExecutionDiagnostic
from affordance_runtime.goals.compiler import GoalCompiler, NotRequiredGoalCompiler
from affordance_runtime.mission.contracts import ExecutionMode, MissionOutcome
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task import TaskGoal
from affordance_runtime.world.contracts import CoverageState
from affordance_runtime.world.environment import WorldEnvironment

if TYPE_CHECKING:
    from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation

CASE_SCHEMA_VERSION = "target-loop-case.v10"
SUPPORTED_CASE_SCHEMA_VERSIONS = frozenset(
    {
        "target-loop-case.v6",
        "target-loop-case.v7",
        "target-loop-case.v8",
        "target-loop-case.v9",
        CASE_SCHEMA_VERSION,
    }
)

_MISSION_FAILURE_OUTCOMES = frozenset(
    {
        MissionOutcome.PLANNER_FAILURE,
        MissionOutcome.AUDIT_UNAVAILABLE,
        MissionOutcome.BOUNDARY_REJECTED,
        MissionOutcome.EVIDENCE_GAP,
        MissionOutcome.FINALIZATION_NOT_READY,
        MissionOutcome.CANCELLED,
        MissionOutcome.OPERATIONAL_FAILURE,
        MissionOutcome.UNHANDLED_EPISODE_STATE,
        MissionOutcome.ROUND_BUDGET_EXHAUSTED,
    }
)


def mission_failure_code(outcome: str) -> str:
    """Project typed mission terminal truth without letting cleanup replace it."""

    return outcome if outcome in {str(item) for item in _MISSION_FAILURE_OUTCOMES} else ""


_FACT_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")
_EXCEPTION_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


@dataclass(frozen=True)
class MetricMeasurement:
    value: int | float | None
    measured: bool
    opportunities: int | None = None
    unit: str = "count"

    def __post_init__(self) -> None:
        if type(self.measured) is not bool:
            raise TypeError("metric measured flag must be boolean")
        if self.measured == (self.value is None):
            raise ValueError("measured metrics require a value and unmeasured metrics require None")
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, int | float)
            or not math.isfinite(self.value)
            or self.value < 0
        ):
            raise ValueError("measured metric values must be finite non-negative numbers")
        if self.opportunities is not None and (type(self.opportunities) is not int or self.opportunities < 0):
            raise ValueError("metric opportunities cannot be negative")
        if not isinstance(self.unit, str) or not self.unit or len(self.unit) > 32:
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
    NO_PROGRESS_CONTROL_REPETITION = "no_progress_control_repetition"
    BLOCKED_OTHER = "blocked_other"


_BLOCKED_TERMINAL_REASONS = {
    item.value: item
    for item in TerminalReasonCode
    if item
    not in {
        TerminalReasonCode.NO_PROGRESS_REPETITION,
        TerminalReasonCode.NO_PROGRESS_CONTROL_REPETITION,
        TerminalReasonCode.BLOCKED_OTHER,
    }
}


def terminal_reason_from_facts(
    status: str,
    runtime_reason_code: str,
    agent_failure_code: str,
) -> TerminalReasonCode | None:
    """Project a terminal reason from the closed public failure facts."""
    if agent_failure_code == AgentFailureCode.NO_PROGRESS_REPETITION.value:
        return TerminalReasonCode.NO_PROGRESS_REPETITION
    if agent_failure_code == AgentFailureCode.NO_PROGRESS_CONTROL_REPETITION.value:
        return TerminalReasonCode.NO_PROGRESS_CONTROL_REPETITION
    if status != RunStatus.BLOCKED.value:
        return None
    return _BLOCKED_TERMINAL_REASONS.get(
        runtime_reason_code,
        TerminalReasonCode.BLOCKED_OTHER,
    )


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
    ACTION_EVALUATION = "action_outcome"
    TASK_EVALUATION = "task_evaluation"
    HARNESS_WATCHDOG = "harness_watchdog"
    HARNESS_EXTERNAL_INTERRUPTION = "harness_external_interruption"
    HARNESS_PERSISTENCE = "harness_persistence"
    CLEANUP = "cleanup"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CaseFacts:
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
    runtime_failure: RuntimeFailure | None = None
    task_outcome_kind: str = ""
    task_outcome_code: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.component_origin, CaseFailureOrigin):
            raise TypeError("component failure origin must be typed")
        if self.runtime_failure is not None and not isinstance(self.runtime_failure, RuntimeFailure):
            raise TypeError("canonical Runtime failure must be typed")
        for value in (
            self.runtime_reason_code,
            self.agent_failure_code,
            self.policy_failure_code,
            self.component_code,
            self.watchdog_code,
            self.cleanup_code,
            self.harness_integrity_code,
            self.task_outcome_kind,
            self.task_outcome_code,
        ):
            if not isinstance(value, str):
                raise TypeError("failure fact codes must be strings")
            if value and _FACT_CODE.fullmatch(value) is None:
                raise ValueError("failure fact codes must be bounded identifiers")
        for value in (self.component_exception_class, self.cleanup_exception_class):
            if not isinstance(value, str):
                raise TypeError("failure exception classes must be strings")
            if value and _EXCEPTION_CLASS.fullmatch(value) is None:
                raise ValueError("failure exception classes must be bounded names")
        has_component = self.component_origin is not CaseFailureOrigin.NONE
        if has_component != bool(self.component_code):
            raise ValueError("component failure origin and code must be present together")
        if not has_component and self.component_exception_class:
            raise ValueError("component exception class requires a component failure")
        if bool(self.cleanup_code) != bool(self.cleanup_exception_class):
            raise ValueError("cleanup failure code and exception class must be present together")
        if self.agent_failure_code and self.agent_failure_code not in {str(item) for item in AgentFailureCode}:
            raise ValueError("agent failure code is outside the closed vocabulary")
        if self.policy_failure_code and self.policy_failure_code not in {str(item) for item in ModelFailureKind}:
            raise ValueError("policy failure code is outside the closed vocabulary")
        if self.task_outcome_kind not in {"", *(str(item) for item in TaskOutcomeKind)}:
            raise ValueError("task outcome kind is outside the closed vocabulary")
        if bool(self.task_outcome_kind) != bool(self.task_outcome_code):
            raise ValueError("task outcome kind and code must be present together")
        if self.task_outcome_code and _FACT_CODE.fullmatch(self.task_outcome_code) is None:
            raise ValueError("task outcome code must be bounded")
        if self.runtime_failure is not None:
            if self.policy_failure_code and (
                self.runtime_failure.stage is not FailureStage.POLICY
                or self.policy_failure_code != self.runtime_failure.code
            ):
                raise ValueError("canonical and legacy policy failure facts conflict")
            if self.policy_failure_code:
                policy_kind = ModelFailureKind(self.policy_failure_code)
                expected_kind = (
                    FailureKind.INVALID_OUTPUT
                    if policy_kind
                    in {
                        ModelFailureKind.INVALID_RESPONSE,
                        ModelFailureKind.SCHEMA_ERROR,
                    }
                    else FailureKind.CALL_FAILED
                )
                if self.runtime_failure.kind is not expected_kind:
                    raise ValueError("canonical policy failure kind contradicts its code")
            if self.agent_failure_code and self.runtime_failure.code != self.agent_failure_code:
                raise ValueError("canonical and legacy agent failure facts conflict")
            if self.agent_failure_code:
                agent_code = AgentFailureCode(self.agent_failure_code)
                if agent_code in {
                    AgentFailureCode.NO_PROGRESS_REPETITION,
                    AgentFailureCode.NO_PROGRESS_CONTROL_REPETITION,
                    AgentFailureCode.REPEATED_FAILURE_LIMIT,
                }:
                    expected_agent_failure = (
                        FailureStage.CONTROL,
                        FailureKind.NO_PROGRESS,
                    )
                elif agent_code in {
                    AgentFailureCode.OBSERVATION_CAPABILITY_UNAVAILABLE,
                    AgentFailureCode.POST_ACTION_CAPABILITY_UNAVAILABLE,
                }:
                    expected_agent_failure = (
                        FailureStage.ACQUISITION,
                        FailureKind.CAPABILITY_UNAVAILABLE,
                    )
                else:
                    expected_agent_failure = (
                        FailureStage.ACQUISITION,
                        FailureKind.CALL_FAILED,
                    )
                if (
                    self.runtime_failure.stage,
                    self.runtime_failure.kind,
                ) != expected_agent_failure:
                    raise ValueError("canonical agent failure kind contradicts its code")


# Compatibility name for the pre-convergence public schema. New owners use CaseFacts.
FailureFacts = CaseFacts


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
    action_outcome_projector: ActionOutcomeProjector
    task_evaluator: TaskEvaluator
    risk_policy: RiskPolicy | None = None
    required_decisions: frozenset[DecisionCapability] = field(default_factory=frozenset)
    goal_compiler: GoalCompiler | None = None
    mission_planner: object | None = None
    mission_auditor: object | None = None
    execution_mode: ExecutionMode = ExecutionMode.STANDALONE

    @classmethod
    def atomic(
        cls,
        policy: AgentPolicy,
        action_outcome_projector: ActionOutcomeProjector,
        task_evaluator: TaskEvaluator,
        risk_policy: RiskPolicy | None = None,
        required_decisions: frozenset[DecisionCapability] = frozenset(),
    ) -> BenchmarkComposition:
        """Explicitly declare a benchmark composition's tasks as atomic."""

        return cls(
            policy,
            action_outcome_projector,
            task_evaluator,
            risk_policy,
            required_decisions,
            NotRequiredGoalCompiler("atomic_benchmark_task"),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("benchmark execution mode must be typed")
        if self.execution_mode is ExecutionMode.MISSION and self.mission_planner is None:
            raise ValueError("mission composition requires a MilestonePlanner port")
        if self.execution_mode is ExecutionMode.STANDALONE and (
            self.mission_planner is not None or self.mission_auditor is not None
        ):
            raise ValueError("standalone composition cannot install mission roles")
        object.__setattr__(
            self,
            "required_decisions",
            normalize_decision_capabilities(
                self.required_decisions,
                field_name="benchmark composition required_decisions",
            ),
        )


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    suite_id: str
    description: str
    task_factory: Callable[[], TaskGoal]
    environment_factory: Callable[[BenchmarkInstrumentation], WorldEnvironment]
    composition_factory: Callable[[BenchmarkInstrumentation], BenchmarkComposition]
    expected_terminal_statuses: tuple[RunStatus, ...]
    timeout_s: float
    seed: int
    required_measurements: tuple[str, ...]
    metric_expectations: tuple[MetricExpectation, ...] = ()
    auto_confirm: bool = False

    def __post_init__(self) -> None:
        if not self.case_id or not self.suite_id or not 0 < self.timeout_s <= 900:
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
    runtime: str = "core"

    @classmethod
    def create(cls, suite_id: str, digest: str, profile_id: str, seed: int) -> BenchmarkRunIdentity:
        sha = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--short"))
        started = datetime.now(UTC).isoformat()
        run_id = f"{suite_id}:{profile_id}:{sha[:12]}:{digest[:12]}:{seed}"
        return cls(
            run_id, sha, dirty, suite_id, digest, profile_id, seed, started, sys.version.split()[0], platform.platform()
        )


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    status: str
    execution_completed: bool
    failure_reason: str
    latency_ms: float
    measurements: Mapping[str, MetricMeasurement] = field(default_factory=dict)
    terminal_reason_code: TerminalReasonCode | None = None
    termination_origin: str = "runtime"
    case_failure_code: str = ""
    partial_episode_available: bool = False
    latest_task_status: str = ""
    latest_action_observed_change: str = ""
    latest_action_local_postcondition: str = ""
    latest_action_evidence_method: str = ""
    latest_semantic_attempt_key_digest: str = ""
    same_attempt_streak: int = 0
    no_progress_count: int = 0
    last_progress_event_type: str = ""
    failure_origin: CaseFailureOrigin = CaseFailureOrigin.NONE
    failure_code: str = ""
    exception_class: str = ""
    last_decision_kind: str = ""
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
    cleanup_status: str = ""
    primary_failure_code: str = ""
    primary_failure_phase: str = ""
    primary_diagnostic_ref: str = ""
    recovery_failure_codes: tuple[str, ...] = ()
    secondary_failure_codes: tuple[str, ...] = ()
    terminal_failure_code: str = ""
    cleanup_diagnostic: ExecutionDiagnostic | None = None
    watchdog_triggered: bool = False
    harness_integrity_code: str = ""
    harness_integrity_failures: int = 0
    mission_outcome: str = ""
    mission_last_ref: str = ""
    failure_facts: FailureFacts = field(default_factory=FailureFacts)
    case_schema_version: str = CASE_SCHEMA_VERSION
    suite_id: str = ""
    profile_id: str = ""
    seed: int = 0
    manifest_digest: str = ""
    harness_schema_version: str = "target-loop-harness.v6"

    def __post_init__(self) -> None:
        if not self.cleanup_status:
            object.__setattr__(
                self,
                "cleanup_status",
                "failed" if self.cleanup_failures else "not_run",
            )
        text_fields = (
            self.case_id,
            self.status,
            self.failure_reason,
            self.termination_origin,
            self.case_failure_code,
            self.latest_task_status,
            self.latest_action_observed_change,
            self.latest_action_local_postcondition,
            self.latest_action_evidence_method,
            self.latest_semantic_attempt_key_digest,
            self.last_progress_event_type,
            self.failure_code,
            self.exception_class,
            self.last_decision_kind,
            self.last_policy_failure_code,
            self.last_world_coverage,
            self.pending_kind,
            self.runtime_reason_code,
            self.agent_failure_code,
            self.cleanup_failure_code,
            self.cleanup_exception_class,
            self.cleanup_status,
            self.primary_failure_code,
            self.primary_failure_phase,
            self.primary_diagnostic_ref,
            self.terminal_failure_code,
            self.harness_integrity_code,
            self.mission_outcome,
            self.mission_last_ref,
            self.case_schema_version,
            self.suite_id,
            self.profile_id,
            self.manifest_digest,
            self.harness_schema_version,
        )
        if any(
            not isinstance(value, str) or len(value) > 512 or any(ord(character) < 32 for character in value)
            for value in text_fields
        ):
            raise TypeError("benchmark case text fields must be bounded strings")
        object.__setattr__(self, "recovery_failure_codes", tuple(self.recovery_failure_codes))
        object.__setattr__(self, "secondary_failure_codes", tuple(self.secondary_failure_codes))
        if any(
            not isinstance(value, str) or _FACT_CODE.fullmatch(value) is None
            for value in (*self.recovery_failure_codes, *self.secondary_failure_codes)
        ):
            raise ValueError("benchmark chronological failure codes must be bounded identifiers")
        if self.primary_failure_phase not in {"", "pre_dispatch", "dispatch_wait", "post_capture", "cleanup"}:
            raise ValueError("benchmark primary failure phase is outside the closed vocabulary")
        if (
            self.primary_diagnostic_ref
            and re.fullmatch(
                r"execution-diagnostic:[0-9a-f]{24}",
                self.primary_diagnostic_ref,
            )
            is None
        ):
            raise ValueError("benchmark primary diagnostic reference is invalid")
        if self.cleanup_diagnostic is not None:
            if not isinstance(self.cleanup_diagnostic, ExecutionDiagnostic):
                raise TypeError("benchmark cleanup diagnostic must be typed")
            if self.cleanup_diagnostic.phase.value != "cleanup":
                raise ValueError("benchmark cleanup diagnostic phase must be cleanup")
        if (
            not self.case_id
            or self.status not in {str(item) for item in RunStatus if item is not RunStatus.RUNNING}
            or self.termination_origin
            not in {
                "",
                "runtime",
                "component",
                "cleanup",
                "harness_watchdog",
                "harness_external",
            }
            or type(self.execution_completed) is not bool
            or isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, int | float)
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("benchmark case scalar contract is invalid")
        if self.terminal_reason_code is not None and not isinstance(self.terminal_reason_code, TerminalReasonCode):
            raise TypeError("terminal reason code must be typed")
        if not isinstance(self.failure_origin, CaseFailureOrigin):
            raise TypeError("failure origin must be typed")
        integer_fields = (
            self.same_attempt_streak,
            self.no_progress_count,
            self.last_action_space_option_count,
            self.last_world_target_count,
            self.seed,
            self.cleanup_failures,
            self.harness_integrity_failures,
        )
        if any(type(value) is not int or value < 0 for value in integer_fields):
            raise ValueError("benchmark case counts must be non-negative integers")
        if type(self.partial_episode_available) is not bool or type(self.watchdog_triggered) is not bool:
            raise TypeError("benchmark case flags must be boolean")
        if self.partial_episode_available and self.execution_completed:
            raise ValueError("partial episode evidence cannot be execution-complete")
        if self.pending_kind not in {"", "unknown_effect", "user_question", "confirmation"}:
            raise ValueError("benchmark pending kind is outside the closed vocabulary")
        expected_pending_status = {
            "unknown_effect": RunStatus.WAITING_USER.value,
            "user_question": RunStatus.WAITING_USER.value,
            "confirmation": RunStatus.WAITING_CONFIRMATION.value,
        }.get(self.pending_kind)
        if expected_pending_status is not None and self.status != expected_pending_status:
            raise ValueError("benchmark pending kind contradicts terminal status")
        if (self.status == RunStatus.WAITING_CONFIRMATION and self.pending_kind != "confirmation") or (
            self.status == RunStatus.WAITING_USER
            and not self.pending_kind
            and self.latest_task_status != TaskEvaluationStatus.UNKNOWN
        ):
            raise ValueError("benchmark waiting status lacks its typed pending fact")
        if self.latest_task_status not in {"", *(str(item) for item in TaskEvaluationStatus)}:
            raise ValueError("benchmark task status is outside the closed vocabulary")
        if self.latest_action_observed_change not in {"", *(str(item) for item in ObservedChange)}:
            raise ValueError("benchmark action effect status is outside the closed vocabulary")
        if self.latest_action_local_postcondition not in {"", *(str(item) for item in LocalPostconditionStatus)}:
            raise ValueError("benchmark action postcondition status is outside the closed vocabulary")
        if self.latest_action_evidence_method not in {"", *(str(item) for item in EvidenceMethod)}:
            raise ValueError("benchmark action verification method is outside the closed vocabulary")
        if self.mission_outcome and self.mission_outcome not in {str(item) for item in MissionOutcome}:
            raise ValueError("benchmark mission outcome is outside the closed vocabulary")
        if self.last_decision_kind:
            from affordance_runtime.agent.decisions import DecisionKind

            try:
                DecisionKind(self.last_decision_kind)
            except ValueError as exc:
                raise ValueError("benchmark decision kind is outside the closed vocabulary") from exc
        if self.last_progress_event_type not in {
            "",
            "already_satisfied_selection",
            "action_effect_evaluated",
            "action_postcondition_satisfied",
            "action_postcondition_unsatisfied_change_strategy",
            "action_unchanged_change_strategy",
            "action_outcome_unknown",
            "repeated_no_progress_selection",
        }:
            raise ValueError("benchmark progress event is outside the closed vocabulary")
        if self.last_world_coverage not in {"", *(str(item) for item in CoverageState)}:
            raise ValueError("benchmark coverage is outside the closed vocabulary")
        if (
            self.latest_semantic_attempt_key_digest
            and re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                self.latest_semantic_attempt_key_digest,
            )
            is None
        ):
            raise ValueError("benchmark semantic attempt digest is malformed")
        if not isinstance(self.measurements, Mapping) or any(
            not isinstance(name, str) or not isinstance(value, MetricMeasurement)
            for name, value in self.measurements.items()
        ):
            raise TypeError("benchmark measurements must be typed")
        if not isinstance(self.failure_facts, FailureFacts):
            raise TypeError("benchmark failure facts must be typed")
        blocked = self.status == str(RunStatus.BLOCKED)
        task_terminal = self.failure_facts.task_outcome_kind == TaskOutcomeKind.TERMINAL_FAILURE.value
        if blocked and self.terminal_reason_code is None and not task_terminal:
            raise ValueError("blocked case result requires a terminal reason code")
        no_progress = self.status == str(RunStatus.FAILED) and self.terminal_reason_code in {
            TerminalReasonCode.NO_PROGRESS_REPETITION,
            TerminalReasonCode.NO_PROGRESS_CONTROL_REPETITION,
        }
        if not blocked and not no_progress and self.terminal_reason_code is not None:
            raise ValueError("non-blocked case result cannot carry a terminal reason code")
        if self.exception_class and _EXCEPTION_CLASS.fullmatch(self.exception_class) is None:
            raise ValueError("benchmark exception metadata must be a bounded class name")
        if self.cleanup_exception_class and _EXCEPTION_CLASS.fullmatch(self.cleanup_exception_class) is None:
            raise ValueError("cleanup exception metadata must be a bounded class name")
        if self.cleanup_failures not in {0, 1}:
            raise ValueError("cleanup failure count must be zero or one")
        if self.cleanup_status not in {
            "not_run",
            "succeeded",
            "already_closed",
            "timeout",
            "failed",
        }:
            raise ValueError("cleanup status is outside the closed vocabulary")
        if (self.cleanup_status in {"timeout", "failed"}) != bool(self.cleanup_failures):
            raise ValueError("cleanup status and failure fact are inconsistent")
        if self.harness_integrity_failures not in {0, 1}:
            raise ValueError("harness integrity failure count must be zero or one")
        if self.case_schema_version not in SUPPORTED_CASE_SCHEMA_VERSIONS:
            raise ValueError("benchmark case evidence schema is unsupported")
        if self.case_schema_version == "target-loop-case.v6" and self.failure_facts.runtime_failure is not None:
            raise ValueError("legacy case evidence cannot carry canonical RuntimeFailure")
        if self.case_schema_version in {"target-loop-case.v6", "target-loop-case.v7"} and (
            self.failure_facts.task_outcome_kind or self.failure_facts.task_outcome_code
        ):
            raise ValueError("legacy case evidence cannot carry canonical task outcome")
        if self.harness_schema_version != "target-loop-harness.v6":
            raise ValueError("benchmark harness evidence schema is unsupported")
        identity_values = (self.suite_id, self.profile_id, self.manifest_digest)
        if any(identity_values) and not all(identity_values):
            raise ValueError("benchmark case evidence identity must be complete")
        facts = self.failure_facts
        if facts.task_outcome_kind:
            task_kind = TaskOutcomeKind(facts.task_outcome_kind)
            expected_status = {
                TaskOutcomeKind.TERMINAL_SUCCESS: RunStatus.DONE.value,
                TaskOutcomeKind.TERMINAL_FAILURE: RunStatus.BLOCKED.value,
                TaskOutcomeKind.VERIFIER_UNAVAILABLE: RunStatus.WAITING_USER.value,
            }.get(task_kind)
            if expected_status is not None and self.status != expected_status:
                raise ValueError("canonical task outcome contradicts case status")
            expected_task_status = {
                TaskOutcomeKind.TERMINAL_SUCCESS: TaskEvaluationStatus.COMPLETE.value,
                TaskOutcomeKind.TERMINAL_FAILURE: TaskEvaluationStatus.BLOCKED.value,
                TaskOutcomeKind.VERIFIER_UNAVAILABLE: TaskEvaluationStatus.UNKNOWN.value,
                TaskOutcomeKind.RUNNING_INCOMPLETE: TaskEvaluationStatus.INCOMPLETE.value,
            }[task_kind]
            if self.latest_task_status and self.latest_task_status != expected_task_status:
                raise ValueError("canonical task outcome contradicts task evaluation status")
        abort_codes = {f"abort_{item.value}" for item in AbortCategory}
        if self.last_decision_kind == "abort" and facts.runtime_reason_code not in abort_codes:
            raise ValueError("benchmark abort decision and Runtime fact are inconsistent")
        if (
            self.runtime_reason_code != facts.runtime_reason_code
            or self.agent_failure_code != facts.agent_failure_code
            or self.last_policy_failure_code != facts.policy_failure_code
            or self.cleanup_failure_code != facts.cleanup_code
            or self.cleanup_exception_class != facts.cleanup_exception_class
            or self.harness_integrity_code != facts.harness_integrity_code
        ):
            raise ValueError("benchmark case duplicate failure projections are inconsistent")
        if (
            self.failure_origin is not facts.component_origin
            or self.failure_code != facts.component_code
            or self.exception_class != facts.component_exception_class
        ):
            raise ValueError("benchmark component failure projection is inconsistent")
        # Projection precedence belongs solely to case_projection.  This value
        # object validates shape and direct duplicate facts; it must not run a
        # second failure interpreter with its own compatibility table.
        if self.watchdog_triggered != bool(facts.watchdog_code):
            raise ValueError("benchmark watchdog projection is inconsistent")
        if (
            facts.component_origin
            not in {
                CaseFailureOrigin.NONE,
                CaseFailureOrigin.HARNESS_EXTERNAL_INTERRUPTION,
                CaseFailureOrigin.CLEANUP,
            }
            and not facts.watchdog_code
            and self.termination_origin != "component"
        ):
            raise ValueError("benchmark termination origin contradicts its direct component fact")
        if bool(self.cleanup_failures) != bool(facts.cleanup_code):
            raise ValueError("benchmark cleanup projection is inconsistent")
        if bool(self.harness_integrity_failures) != bool(facts.harness_integrity_code):
            raise ValueError("benchmark integrity projection is inconsistent")
        official = self.measurements.get("official_success_count")
        has_primary_failure_fact = any(
            (
                facts.runtime_failure,
                facts.runtime_reason_code,
                facts.agent_failure_code,
                facts.policy_failure_code,
                facts.component_code,
                facts.harness_integrity_code,
            )
        )
        secondary_lifecycle_codes = {code for code in (facts.watchdog_code, facts.cleanup_code) if code}
        if (
            self.status == str(RunStatus.DONE)
            and official is not None
            and official.measured
            and official.value == 1
            and (
                has_primary_failure_fact
                or self.case_failure_code not in {"", *secondary_lifecycle_codes}
                or self.failure_code
                or self.exception_class
                or self.terminal_reason_code is not None
            )
        ):
            raise ValueError("successful benchmark evidence cannot carry failure facts")
        if (
            self.status == str(RunStatus.DONE)
            and official is not None
            and official.measured
            and official.value == 1
            and not self.execution_completed
        ):
            raise ValueError("successful benchmark evidence must be execution-complete")
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


_KNOWN_METRICS = (
    frozenset(
        {
            "observations",
            "executions",
            "currentness_probes",
            "turns",
            "policy_calls",
            "semantic_judge_calls",
            "provider_attempts",
            "confirmations",
            "ask_user_count",
            "wait_count",
            "page_request_count",
            "sent_unknown_count",
            "duplicate_unknown_attempts",
            "forbidden_effect_attempts",
            "stale_opportunities",
            "stale_zero_call_violations",
            "effectful_dispatches",
            "dom_click_calls",
            "visual_proposer_calls",
            "pointer_calls",
            "td_requests",
            "property_reads",
            "wot_action_calls",
            "browsergym_reset_calls",
            "browsergym_step_calls",
            "browsergym_probe_calls",
            "dom_action_calls",
            "fill_calls",
            "select_calls",
            "scroll_calls",
            "press_calls",
            "keyboard_press_calls",
            "official_verifier_queries",
            "structural_source_acquired_count",
            "visual_source_acquired_count",
            "visual_binding_acquired_count",
            "visual_gate_selected_count",
            "visual_gate_skipped_count",
            "visual_point_grounder_calls",
            "visual_point_grounder_success_count",
            "visual_disambiguator_calls",
            "visual_disambiguator_selection_count",
            "visual_predicate_classifier_calls",
            "visual_predicate_assessment_count",
            "visual_provider_failure_count",
            "visual_provider_structured_output_failure_count",
            "visual_provider_abstained_count",
            "visual_provider_transport_failure_count",
            "visual_provider_other_failure_count",
            "visual_point_grounding_failure_count",
            "visual_region_proposal_failure_count",
            "visual_candidate_disambiguation_failure_count",
            "visual_predicate_classification_failure_count",
            "visual_correspondence_matched_count",
            "visual_correspondence_unmatched_count",
            "visual_correspondence_ambiguous_count",
            "visual_correspondence_conflict_count",
            "structural_binding_dispatch_count",
            "visual_binding_dispatch_count",
            "official_success_count",
            "provider_retry_count",
            "fallback_count",
            "cleanup_failures",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "model_latency_ms",
            "mission_planner_calls",
            "mission_auditor_calls",
            "final_response_boundary_admission_count",
            "final_response_boundary_rejection_count",
            "stop_send_count",
            "post_stop_capture_count",
            "native_evaluator_count",
            "optional_auditor_calls",
            "mission_state_version",
            "mission_working_outcomes",
            "mission_accepted_facts",
            "mission_boundary_rejections",
            "mission_final_response_delivered",
            "click_calls",
            "already_satisfied_suppressions",
            "no_progress_terminations",
            "observation_contract_exceptions",
        }
    )
    | CANONICAL_METRICS
)
