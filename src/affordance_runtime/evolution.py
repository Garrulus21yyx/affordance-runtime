"""Harness evolution registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode
from affordance_runtime.coordinator import RuntimeFeatures
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    FailureSignature,
    RecoveryAction,
    RecoveryContext,
    RecoveryDecision,
)


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
    payload: dict[str, Any] = field(default_factory=dict)
    payload_digest: str = ""


@dataclass(frozen=True)
class RuntimePatchPayload:
    """Narrow executable payload supported by the first candidate runtime."""

    schema_version: str
    patch_kind: str
    task_ids: list[str]
    feature_overrides: dict[str, bool]

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError(f"unsupported payload schema: {self.schema_version}")
        if self.patch_kind != "runtime_features":
            raise ValueError(f"unsupported patch kind: {self.patch_kind}")
        allowed = {"preflight", "structural_verification", "capability_gate", "recovery"}
        unknown = sorted(set(self.feature_overrides) - allowed)
        if unknown:
            raise ValueError(f"unsupported runtime feature overrides: {', '.join(unknown)}")
        if not self.task_ids or not self.feature_overrides:
            raise ValueError("runtime patch must declare task_ids and feature_overrides")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimePatchPayload":
        raw_task_ids = value.get("task_ids", [])
        raw_overrides = value.get("feature_overrides", {})
        if not isinstance(raw_task_ids, list) or not all(isinstance(item, str) for item in raw_task_ids):
            raise ValueError("runtime patch task_ids must be a list of strings")
        if not isinstance(raw_overrides, dict) or not all(
            isinstance(name, str) and isinstance(enabled, bool) for name, enabled in raw_overrides.items()
        ):
            raise ValueError("runtime patch feature_overrides must map strings to booleans")
        payload = cls(
            schema_version=str(value.get("schema_version", "")),
            patch_kind=str(value.get("patch_kind", "")),
            task_ids=raw_task_ids,
            feature_overrides=raw_overrides,
        )
        payload.validate()
        return payload


_SIGNATURE_FIELDS = {
    "phase",
    "normalized_error",
    "error_code",
    "action",
    "backend",
    "target_fingerprint",
    "verifier_kind",
}
_SAFE_RECOVERY_RESPONSES = {
    RecoveryAction.REOBSERVE,
    RecoveryAction.VERIFY_STATE,
    RecoveryAction.REROUTE,
    RecoveryAction.REQUEST_APPROVAL,
    RecoveryAction.COMPENSATE,
    RecoveryAction.ABORT,
}
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.IRREVERSIBLE: 3,
}


@dataclass(frozen=True)
class RecoveryPolicyPatchPayload:
    schema_version: str
    patch_kind: str
    task_ids: list[str]
    signature_match: dict[str, str]
    response: str
    max_applications: int
    required_evidence: list[str]
    postconditions: list[str]
    max_risk: str = RiskLevel.LOW.value

    def validate(self) -> None:
        if self.schema_version != "1.0" or self.patch_kind != "recovery_policy":
            raise ValueError("unsupported recovery policy payload schema or kind")
        unknown = sorted(set(self.signature_match) - _SIGNATURE_FIELDS)
        if unknown:
            raise ValueError(f"unsupported signature fields: {', '.join(unknown)}")
        try:
            response = RecoveryAction(self.response)
            RiskLevel(self.max_risk)
        except ValueError as exc:
            raise ValueError(f"invalid recovery policy enum: {exc}") from exc
        if response not in _SAFE_RECOVERY_RESPONSES:
            raise ValueError("recovery policy cannot introduce blind retry")
        if not self.task_ids or not self.signature_match:
            raise ValueError("recovery policy must declare task_ids and a signature match")
        if self.max_applications < 1 or self.max_applications > 3:
            raise ValueError("recovery policy max_applications must be within 1..3")
        if not self.required_evidence or not self.postconditions:
            raise ValueError("recovery policy must require evidence and postconditions")

    def matches(self, task_id: str, signature: FailureSignature, risk: RiskLevel) -> bool:
        if task_id not in self.task_ids or _RISK_ORDER[risk] > _RISK_ORDER[RiskLevel(self.max_risk)]:
            return False
        return all(str(getattr(signature, name)) == expected for name, expected in self.signature_match.items())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        return _payload_digest(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RecoveryPolicyPatchPayload":
        payload = cls(
            schema_version=str(value.get("schema_version", "")),
            patch_kind=str(value.get("patch_kind", "")),
            task_ids=_string_list(value.get("task_ids"), "task_ids"),
            signature_match=_string_map(value.get("signature_match"), "signature_match"),
            response=str(value.get("response", "")),
            max_applications=int(value.get("max_applications", 0)),
            required_evidence=_string_list(value.get("required_evidence"), "required_evidence"),
            postconditions=_string_list(value.get("postconditions"), "postconditions"),
            max_risk=str(value.get("max_risk", RiskLevel.LOW.value)),
        )
        payload.validate()
        return payload


@dataclass(frozen=True)
class RecoverySkillPayload:
    schema_version: str
    patch_kind: str
    task_ids: list[str]
    signature_match: dict[str, str]
    steps: list[str]
    max_applications: int
    required_evidence: list[str]
    postconditions: list[str]
    max_risk: str = RiskLevel.LOW.value

    def validate(self) -> None:
        if self.schema_version != "1.0" or self.patch_kind != "recovery_skill":
            raise ValueError("unsupported recovery skill payload schema or kind")
        unknown = sorted(set(self.signature_match) - _SIGNATURE_FIELDS)
        if unknown:
            raise ValueError(f"unsupported signature fields: {', '.join(unknown)}")
        try:
            actions = [RecoveryAction(item) for item in self.steps]
            RiskLevel(self.max_risk)
        except ValueError as exc:
            raise ValueError(f"invalid recovery skill enum: {exc}") from exc
        if not actions or any(action not in _SAFE_RECOVERY_RESPONSES for action in actions):
            raise ValueError("recovery skill contains an unsafe or empty step sequence")
        if not self.task_ids or not self.signature_match:
            raise ValueError("recovery skill must declare task_ids and a signature match")
        if self.max_applications < 1 or self.max_applications > 3:
            raise ValueError("recovery skill max_applications must be within 1..3")
        if not self.required_evidence or not self.postconditions:
            raise ValueError("recovery skill must require evidence and postconditions")

    def matches(self, task_id: str, signature: FailureSignature, risk: RiskLevel) -> bool:
        if task_id not in self.task_ids or _RISK_ORDER[risk] > _RISK_ORDER[RiskLevel(self.max_risk)]:
            return False
        return all(str(getattr(signature, name)) == expected for name, expected in self.signature_match.items())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        return _payload_digest(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RecoverySkillPayload":
        payload = cls(
            schema_version=str(value.get("schema_version", "")),
            patch_kind=str(value.get("patch_kind", "")),
            task_ids=_string_list(value.get("task_ids"), "task_ids"),
            signature_match=_string_map(value.get("signature_match"), "signature_match"),
            steps=_string_list(value.get("steps"), "steps"),
            max_applications=int(value.get("max_applications", 0)),
            required_evidence=_string_list(value.get("required_evidence"), "required_evidence"),
            postconditions=_string_list(value.get("postconditions"), "postconditions"),
            max_risk=str(value.get("max_risk", RiskLevel.LOW.value)),
        )
        payload.validate()
        return payload


@dataclass
class CandidateRuntimeProfile:
    """Fresh runtime profile that applies only validated declarative patches."""

    base_features: RuntimeFeatures = field(
        default_factory=lambda: RuntimeFeatures(structural_verification=False)
    )
    loaded: dict[str, RuntimePatchPayload | RecoveryPolicyPatchPayload | RecoverySkillPayload] = field(
        default_factory=dict
    )
    recovery_applications: dict[str, int] = field(default_factory=dict)

    def load(self, artifact: EvolutionArtifact, *, allow_candidate: bool = False) -> None:
        if artifact.status != EvolutionStatus.ACCEPTED and not allow_candidate:
            raise ValueError("only accepted artifacts can be loaded outside candidate replay")
        if artifact.artifact_type == EvolutionArtifactType.VERIFIER_PATCH.value:
            runtime_payload = RuntimePatchPayload.from_dict(artifact.payload)
            if runtime_payload.feature_overrides != {"structural_verification": True}:
                raise ValueError("verifier patch may only enable structural verification")
            payload: RuntimePatchPayload | RecoveryPolicyPatchPayload | RecoverySkillPayload = runtime_payload
        elif artifact.artifact_type == EvolutionArtifactType.POLICY_PATCH.value:
            payload = RecoveryPolicyPatchPayload.from_dict(artifact.payload)
        elif artifact.artifact_type == EvolutionArtifactType.SKILL.value:
            payload = RecoverySkillPayload.from_dict(artifact.payload)
        else:
            raise ValueError(f"unsupported executable artifact type: {artifact.artifact_type}")
        if not artifact.payload_digest or payload.digest() != artifact.payload_digest:
            raise ValueError("artifact payload digest mismatch")
        self.loaded[artifact.id] = payload

    def features_for(self, task_id: str) -> RuntimeFeatures:
        features = self.base_features
        for payload in self.loaded.values():
            if isinstance(payload, RuntimePatchPayload) and task_id in payload.task_ids:
                features = replace(features, **payload.feature_overrides)
        return features

    def recovery_policy(self) -> BoundedRecoveryPolicy:
        return BoundedRecoveryPolicy(decision_override=self._recovery_override)

    def _recovery_override(
        self,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        context: RecoveryContext,
        error_code: RuntimeErrorCode | None,
    ) -> RecoveryDecision | None:
        del receipt, error_code
        signature = context.failure_signature
        if signature is None:
            return None
        # Uncertain effects are always inspected before any learned response.
        if context.effect_may_have_occurred:
            return RecoveryDecision(RecoveryAction.VERIFY_STATE, "candidate preserves inspect-before-recovery")
        for artifact_id, payload in self.loaded.items():
            if isinstance(payload, RuntimePatchPayload) or not payload.matches(
                context.task_id, signature, contract.risk
            ):
                continue
            applied = self.recovery_applications.get(artifact_id, 0)
            if applied >= payload.max_applications:
                continue
            self.recovery_applications[artifact_id] = applied + 1
            if isinstance(payload, RecoveryPolicyPatchPayload):
                action = RecoveryAction(payload.response)
            else:
                action = RecoveryAction(payload.steps[min(applied, len(payload.steps) - 1)])
            return RecoveryDecision(action, f"declarative recovery artifact {artifact_id}")
        return None

    def rollback(self, artifact_id: str) -> None:
        if artifact_id not in self.loaded:
            raise KeyError(artifact_id)
        del self.loaded[artifact_id]
        self.recovery_applications.pop(artifact_id, None)


def _payload_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return value


def _string_map(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise ValueError(f"{name} must map strings to strings")
    return value


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


@dataclass(frozen=True)
class EvolutionRegistryStore:
    path: Path

    def save(self, registry: EvolutionRegistry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "schema_version": "1.0",
            "artifacts": {key: asdict(artifact) for key, artifact in registry.artifacts.items()},
            "history": {
                key: [asdict(artifact) for artifact in artifacts]
                for key, artifacts in registry.history.items()
            },
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")
        temporary.replace(self.path)

    def load(self) -> EvolutionRegistry:
        if not self.path.exists():
            return EvolutionRegistry()
        value = json.loads(self.path.read_text(encoding="utf-8"))
        return EvolutionRegistry(
            artifacts={
                key: self._artifact(artifact)
                for key, artifact in value.get("artifacts", {}).items()
            },
            history={
                key: [self._artifact(artifact) for artifact in artifacts]
                for key, artifacts in value.get("history", {}).items()
            },
        )

    @staticmethod
    def _artifact(value: dict[str, Any]) -> EvolutionArtifact:
        item = dict(value)
        item["status"] = EvolutionStatus(item.get("status", EvolutionStatus.PROPOSED.value))
        return EvolutionArtifact(**item)
