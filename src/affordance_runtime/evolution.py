"""Harness evolution registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.benchmarks.spec import BenchmarkRun


class EvolutionStatus(StrEnum):
    PROPOSED = "proposed"
    QUARANTINED = "quarantined"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class FailureClass(StrEnum):
    PERCEPTION = "perception"
    PLANNING = "planning"
    GROUNDING = "grounding"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    SAFETY = "safety"


class EvolutionArtifactType(StrEnum):
    SKILL = "skill"
    POLICY_PATCH = "policy_patch"
    VERIFIER_PATCH = "verifier_patch"
    AFFORDANCE_RULE = "affordance_rule"
    BENCHMARK_FIXTURE = "benchmark_fixture"


@dataclass(frozen=True)
class EvolutionProposal:
    proposal_id: str
    source_trace: str
    failure_class: FailureClass
    artifact_type: EvolutionArtifactType
    change_summary: str
    applicability: dict[str, Any]
    validation_plan: list[str]


@dataclass(frozen=True)
class FailureClassifier:
    def classify_run(self, run: BenchmarkRun) -> FailureClass:
        reason = run.failure_reason.lower()
        if run.unsafe_side_effects or run.constraint_violations:
            return FailureClass.SAFETY
        if run.verifier_false_accepts:
            return FailureClass.VERIFICATION
        if run.recovery_attempts and not run.recovery_successes:
            return FailureClass.RECOVERY
        if "locator" in reason or "selector" in reason or run.stale_action_opportunities > run.stale_actions_blocked:
            return FailureClass.GROUNDING
        if "execution" in reason or "timeout" in reason:
            return FailureClass.EXECUTION
        if "planner" in reason or "plan" in reason:
            return FailureClass.PLANNING
        return FailureClass.PERCEPTION

    def propose(self, run: BenchmarkRun) -> EvolutionProposal:
        failure = self.classify_run(run)
        artifact_type = {
            FailureClass.SAFETY: EvolutionArtifactType.POLICY_PATCH,
            FailureClass.VERIFICATION: EvolutionArtifactType.VERIFIER_PATCH,
            FailureClass.GROUNDING: EvolutionArtifactType.AFFORDANCE_RULE,
            FailureClass.RECOVERY: EvolutionArtifactType.SKILL,
        }.get(failure, EvolutionArtifactType.BENCHMARK_FIXTURE)
        return EvolutionProposal(
            proposal_id=f"proposal-{run.task_id}-{run.variant}-seed-{run.seed}",
            source_trace=run.trace_path,
            failure_class=failure,
            artifact_type=artifact_type,
            change_summary=f"Address {failure.value} failure in {run.task_id} for {run.variant}",
            applicability={"task_id": run.task_id, "variant": run.variant},
            validation_plan=["replay_original", "replay_task_family", "run_global_smoke", "run_safety_smoke"],
        )


@dataclass(frozen=True)
class RegressionRule:
    metric: str
    direction: MetricDirection
    threshold: float
    baseline: float | None = None
    allowed_regression: float = 0.0

    def passes(self, value: float) -> bool:
        if self.direction == MetricDirection.HIGHER_IS_BETTER:
            threshold_passed = value >= self.threshold
            regression_passed = self.baseline is None or value >= self.baseline - self.allowed_regression
        else:
            threshold_passed = value <= self.threshold
            regression_passed = self.baseline is None or value <= self.baseline + self.allowed_regression
        return threshold_passed and regression_passed


@dataclass
class EvolutionArtifact:
    id: str
    artifact_type: str
    summary: str
    applicability: dict[str, Any]
    source_traces: list[str]
    negative_examples: list[str] = field(default_factory=list)
    ttl_runs: int = 100
    status: EvolutionStatus = EvolutionStatus.PROPOSED
    regression_results: dict[str, float] = field(default_factory=dict)
    version: str = "1.0.0"
    source_runtime_version: str = ""
    target_suite_versions: list[str] = field(default_factory=list)
    rollback_artifact: str = ""
    reviewer: str = ""
    decision_reason: str = ""


@dataclass
class EvolutionRegistry:
    artifacts: dict[str, EvolutionArtifact] = field(default_factory=dict)
    history: dict[str, list[EvolutionArtifact]] = field(default_factory=dict)

    def propose(self, artifact: EvolutionArtifact) -> None:
        existing = self.artifacts.get(artifact.id)
        if existing is not None and existing.version == artifact.version:
            raise ValueError(f"artifact version already exists: {artifact.id}@{artifact.version}")
        if existing is not None:
            self.history.setdefault(artifact.id, []).append(existing)
        self.artifacts[artifact.id] = artifact

    def rollback(self, artifact_id: str, *, reason: str, reviewer: str) -> EvolutionStatus:
        artifact = self.artifacts[artifact_id]
        if artifact.status != EvolutionStatus.ACCEPTED:
            raise ValueError("only accepted artifacts can be rolled back")
        artifact.status = EvolutionStatus.ROLLED_BACK
        artifact.decision_reason = reason
        artifact.reviewer = reviewer
        return artifact.status

    def accept_if_regression_passes(
        self,
        artifact_id: str,
        *,
        rules: list[RegressionRule],
    ) -> EvolutionStatus:
        artifact = self.artifacts[artifact_id]
        missing = [rule.metric for rule in rules if rule.metric not in artifact.regression_results]
        failed = [
            rule.metric
            for rule in rules
            if rule.metric in artifact.regression_results and not rule.passes(artifact.regression_results[rule.metric])
        ]
        if rules and not missing and not failed:
            artifact.status = EvolutionStatus.ACCEPTED
            artifact.decision_reason = "all direction-aware regression rules passed"
        else:
            artifact.status = EvolutionStatus.QUARANTINED
            details = []
            if not rules:
                details.append("no regression rules supplied")
            if missing:
                details.append(f"missing metrics: {', '.join(sorted(missing))}")
            if failed:
                details.append(f"failed metrics: {', '.join(sorted(failed))}")
            artifact.decision_reason = "; ".join(details)
        return artifact.status
