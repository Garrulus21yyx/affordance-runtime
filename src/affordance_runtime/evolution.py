"""Harness evolution registry."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode
from affordance_runtime.coordinator import RuntimeFeatures
from affordance_runtime.immutable import FrozenSequence, freeze_json, to_json_compatible
from affordance_runtime.recovery_protocol import (
    RecoveryBudgetCost,
    RecoveryDimension,
    RuntimePhase,
)
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime, TaskSkillPayload


class EvolutionStatus(StrEnum):
    PROPOSED = "proposed"
    QUARANTINED = "quarantined"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class EvolutionRecoveryAction(StrEnum):
    """Quarantined harness response vocabulary, not Runtime recovery policy."""

    REOBSERVE = "reobserve"
    ACTIVE_PERCEPTION = "active_perception"
    COMPACT_CONTEXT = "compact_context"
    SWITCH_PROVIDER = "switch_provider"
    REPAIR_MODEL_SCHEMA = "repair_model_schema"
    CLARIFY_INTENT = "clarify_intent"
    REPLAN_TASK = "replan_task"
    REPLAN_STEP = "replan_step"
    REGROUND = "reground"
    REROUTE = "reroute"
    INSPECT_POST_STATE = "inspect_post_state"
    RETRY_IDEMPOTENT = "retry_idempotent"
    COMPENSATE = "compensate"
    REQUEST_APPROVAL = "request_approval"
    ASK_USER = "ask_user"
    ABORT = "abort"


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
    TASK_SKILL = "task_skill"
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "applicability", freeze_json(self.applicability))
        object.__setattr__(self, "validation_plan", FrozenSequence(self.validation_plan))


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_ids", FrozenSequence(self.task_ids))
        object.__setattr__(self, "feature_overrides", freeze_json(self.feature_overrides))

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
        return to_json_compatible(self)

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
    EvolutionRecoveryAction.REOBSERVE,
    EvolutionRecoveryAction.INSPECT_POST_STATE,
    EvolutionRecoveryAction.REROUTE,
    EvolutionRecoveryAction.REQUEST_APPROVAL,
    EvolutionRecoveryAction.COMPENSATE,
    EvolutionRecoveryAction.ABORT,
}
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.IRREVERSIBLE: 3,
}


@dataclass(frozen=True)
class EvolutionFailureSignature:
    phase: str
    normalized_error: str
    error_code: str
    action: str
    backend: str
    target_fingerprint: str
    verifier_kind: str
    state_revision: str

    @classmethod
    def from_failure(
        cls,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        *,
        phase: str,
        error_code: RuntimeErrorCode | None,
        state_revision: str,
    ) -> "EvolutionFailureSignature":
        code = error_code or (receipt.error_code if receipt else None)
        message = receipt.message if receipt else (code.value if code else "unknown")
        return cls(
            phase=phase,
            normalized_error=_normalize_error(message),
            error_code=code.value if code else "unknown",
            action=contract.action,
            backend=contract.backend,
            target_fingerprint=contract.target_fingerprint,
            verifier_kind=contract.verifier_plan[0].kind if contract.verifier_plan else "",
            state_revision=state_revision,
        )

    def key(self, *, include_revision: bool = False) -> str:
        value = {
            "phase": self.phase,
            "normalized_error": self.normalized_error,
            "error_code": self.error_code,
            "action": self.action,
            "backend": self.backend,
            "target_fingerprint": self.target_fingerprint,
            "verifier_kind": self.verifier_kind,
        }
        if include_revision:
            value["state_revision"] = self.state_revision
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class EvolutionRecoveryContext:
    attempt: int = 0
    recovery_count: int = 0
    tried_backends: tuple[str, ...] = field(default_factory=tuple)
    backend_fallback_count: int = 0
    effect_may_have_occurred: bool = False
    approval_available: bool = False
    failure_signature: EvolutionFailureSignature | None = None
    task_id: str = ""
    failure_id: str = "evolution-failure"
    current_state_version: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "tried_backends", FrozenSequence(self.tried_backends))


@dataclass(frozen=True)
class EvolutionRecoveryDecision:
    decision_id: str
    failure_id: str
    based_on_state_version: int
    strategy_key: str
    kind: EvolutionRecoveryAction
    reason_code: str
    reentry_phase: RuntimePhase
    changed_dimensions: tuple[RecoveryDimension, ...]
    preconditions: tuple[str, ...]
    budget_cost: RecoveryBudgetCost
    route_ref: str = ""
    idempotency_key: str = ""
    compensation_contract_id: str = ""


@dataclass
class EvolutionRecoveryPolicy:
    max_recoveries: int = 3
    max_retries: int = 1
    max_backend_fallbacks: int = 1
    decision_override: Callable[
        [ActionContract, ExecutionReceipt | None, EvolutionRecoveryContext, RuntimeErrorCode | None],
        EvolutionRecoveryDecision | None,
    ] | None = None

    def decide(
        self,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        context: EvolutionRecoveryContext,
        *,
        error_code: RuntimeErrorCode | None = None,
    ) -> EvolutionRecoveryDecision:
        if context.recovery_count >= self.max_recoveries:
            return _evolution_recovery_decision(EvolutionRecoveryAction.ABORT, context, "recovery budget exhausted")

        if self.decision_override is not None:
            override = self.decision_override(contract, receipt, context, error_code)
            if override is not None:
                return override

        code = error_code or (receipt.error_code if receipt else None)
        if code in {
            RuntimeErrorCode.STALE_OBSERVATION,
            RuntimeErrorCode.STALE_PAGE_REVISION,
            RuntimeErrorCode.SNAPSHOT_MISMATCH,
            RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
            RuntimeErrorCode.LEASE_EXPIRED,
        }:
            return _evolution_recovery_decision(EvolutionRecoveryAction.REOBSERVE, context, "contract state is stale")
        if code in {RuntimeErrorCode.CAPABILITY_DENIED, RuntimeErrorCode.UNSAFE_ACTION}:
            if context.approval_available:
                return _evolution_recovery_decision(
                    EvolutionRecoveryAction.REQUEST_APPROVAL,
                    context,
                    "capability or approval is required",
                )
            return _evolution_recovery_decision(EvolutionRecoveryAction.ABORT, context, "action is not authorized")

        if context.effect_may_have_occurred:
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.INSPECT_POST_STATE,
                context,
                "execution outcome is uncertain; inspect post-state before retry",
            )

        if receipt is not None and receipt.success:
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.INSPECT_POST_STATE,
                context,
                "execution succeeded; verify expected effects",
            )

        if (
            receipt is not None
            and receipt.evidence.get("dispatched") is False
            and contract.grounding_candidate is not None
            and code == RuntimeErrorCode.EXECUTION_FAILED
        ):
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.REROUTE,
                context,
                "selected grounding route failed before dispatch",
                route_ref=contract.backend,
            )

        route_alternatives = contract.route_plan.viable_alternatives if contract.route_plan else ()
        if route_alternatives:
            alternative = route_alternatives[0]
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.REROUTE,
                context,
                "exclude failed grounding candidate and bind a fresh route",
                route_ref=alternative.compatible_executor,
            )

        can_retry = (
            context.attempt < self.max_retries
            and bool(contract.idempotency_key)
            and contract.risk != RiskLevel.IRREVERSIBLE
        )
        if can_retry:
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.RETRY_IDEMPOTENT,
                context,
                "idempotent action may be retried once",
                idempotency_key=contract.idempotency_key,
            )

        if contract.compensation:
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.COMPENSATE,
                context,
                "contract declares a compensation action",
                compensation_contract_id=contract.compensation,
            )

        return _evolution_recovery_decision(EvolutionRecoveryAction.ABORT, context, "no safe recovery remains")


def _evolution_recovery_decision(
    kind: EvolutionRecoveryAction,
    context: EvolutionRecoveryContext,
    reason: str,
    *,
    route_ref: str = "",
    idempotency_key: str = "",
    compensation_contract_id: str = "",
    profile_artifact_id: str = "",
) -> EvolutionRecoveryDecision:
    return EvolutionRecoveryDecision(
        decision_id=f"evolution-recovery:{kind.value}:{context.current_state_version}",
        failure_id=context.failure_id,
        based_on_state_version=context.current_state_version,
        strategy_key=(
            f"strategy:{kind.value}:{profile_artifact_id}"
            if profile_artifact_id
            else f"strategy:{kind.value}:evolution"
        ),
        kind=kind,
        reason_code=reason,
        reentry_phase=_evolution_reentry_phase(kind),
        changed_dimensions=(_evolution_dimension(kind),),
        preconditions=(f"evolution policy selected {kind.value}",),
        budget_cost=RecoveryBudgetCost(
            recoveries=0 if kind == EvolutionRecoveryAction.ABORT else 1,
            observations=1
            if kind
            in {
                EvolutionRecoveryAction.REOBSERVE,
                EvolutionRecoveryAction.INSPECT_POST_STATE,
                EvolutionRecoveryAction.REROUTE,
                EvolutionRecoveryAction.RETRY_IDEMPOTENT,
                EvolutionRecoveryAction.COMPENSATE,
            }
            else 0,
            replans=1
            if kind
            in {
                EvolutionRecoveryAction.COMPACT_CONTEXT,
                EvolutionRecoveryAction.REPAIR_MODEL_SCHEMA,
                EvolutionRecoveryAction.SWITCH_PROVIDER,
                EvolutionRecoveryAction.REPLAN_TASK,
                EvolutionRecoveryAction.REPLAN_STEP,
            }
            else 0,
            user_escalations=1
            if kind
            in {
                EvolutionRecoveryAction.ASK_USER,
                EvolutionRecoveryAction.CLARIFY_INTENT,
                EvolutionRecoveryAction.REQUEST_APPROVAL,
            }
            else 0,
        ),
        route_ref=route_ref,
        idempotency_key=idempotency_key,
        compensation_contract_id=compensation_contract_id,
    )


def _evolution_dimension(kind: EvolutionRecoveryAction) -> RecoveryDimension:
    return {
        EvolutionRecoveryAction.REOBSERVE: RecoveryDimension.OBSERVATION,
        EvolutionRecoveryAction.INSPECT_POST_STATE: RecoveryDimension.EFFECT_STATUS,
        EvolutionRecoveryAction.REROUTE: RecoveryDimension.ROUTE,
        EvolutionRecoveryAction.REQUEST_APPROVAL: RecoveryDimension.APPROVAL,
        EvolutionRecoveryAction.COMPENSATE: RecoveryDimension.EFFECT_STATUS,
        EvolutionRecoveryAction.ABORT: RecoveryDimension.TERMINAL,
        EvolutionRecoveryAction.RETRY_IDEMPOTENT: RecoveryDimension.OBSERVATION,
    }.get(kind, RecoveryDimension.CONTEXT)


def _evolution_reentry_phase(kind: EvolutionRecoveryAction) -> RuntimePhase:
    return {
        EvolutionRecoveryAction.REOBSERVE: RuntimePhase.OBSERVING,
        EvolutionRecoveryAction.INSPECT_POST_STATE: RuntimePhase.VERIFYING,
        EvolutionRecoveryAction.REROUTE: RuntimePhase.PREFLIGHT,
        EvolutionRecoveryAction.REQUEST_APPROVAL: RuntimePhase.WAITING_APPROVAL,
        EvolutionRecoveryAction.COMPENSATE: RuntimePhase.PREFLIGHT,
        EvolutionRecoveryAction.ABORT: RuntimePhase.ABORTED,
        EvolutionRecoveryAction.RETRY_IDEMPOTENT: RuntimePhase.PREFLIGHT,
    }.get(kind, RuntimePhase.PLANNING)


def _recovery_kind(value: str) -> EvolutionRecoveryAction:
    legacy_aliases = {
        "verify_state": EvolutionRecoveryAction.INSPECT_POST_STATE,
        "retry": EvolutionRecoveryAction.RETRY_IDEMPOTENT,
    }
    if value in legacy_aliases:
        return legacy_aliases[value]
    return EvolutionRecoveryAction(value)


def _normalize_error(message: str) -> str:
    value = message.lower().strip()
    value = re.sub(r"https?://\S+", "<url>", value)
    value = re.sub(r"\b[0-9a-f]{16,}\b", "<id>", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", value)
    return re.sub(r"\s+", " ", value)[:240]


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_ids", FrozenSequence(self.task_ids))
        object.__setattr__(self, "signature_match", freeze_json(self.signature_match))
        object.__setattr__(self, "required_evidence", FrozenSequence(self.required_evidence))
        object.__setattr__(self, "postconditions", FrozenSequence(self.postconditions))

    def validate(self) -> None:
        if self.schema_version != "1.0" or self.patch_kind != "recovery_policy":
            raise ValueError("unsupported recovery policy payload schema or kind")
        unknown = sorted(set(self.signature_match) - _SIGNATURE_FIELDS)
        if unknown:
            raise ValueError(f"unsupported signature fields: {', '.join(unknown)}")
        try:
            response = _recovery_kind(self.response)
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

    def matches(self, task_id: str, signature: EvolutionFailureSignature, risk: RiskLevel) -> bool:
        if task_id not in self.task_ids or _RISK_ORDER[risk] > _RISK_ORDER[RiskLevel(self.max_risk)]:
            return False
        return all(str(getattr(signature, name)) == expected for name, expected in self.signature_match.items())

    def to_dict(self) -> dict[str, Any]:
        return to_json_compatible(self)

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

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_ids", FrozenSequence(self.task_ids))
        object.__setattr__(self, "signature_match", freeze_json(self.signature_match))
        object.__setattr__(self, "steps", FrozenSequence(self.steps))
        object.__setattr__(self, "required_evidence", FrozenSequence(self.required_evidence))
        object.__setattr__(self, "postconditions", FrozenSequence(self.postconditions))

    def validate(self) -> None:
        if self.schema_version != "1.0" or self.patch_kind != "recovery_skill":
            raise ValueError("unsupported recovery skill payload schema or kind")
        unknown = sorted(set(self.signature_match) - _SIGNATURE_FIELDS)
        if unknown:
            raise ValueError(f"unsupported signature fields: {', '.join(unknown)}")
        try:
            actions = [_recovery_kind(item) for item in self.steps]
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

    def matches(self, task_id: str, signature: EvolutionFailureSignature, risk: RiskLevel) -> bool:
        if task_id not in self.task_ids or _RISK_ORDER[risk] > _RISK_ORDER[RiskLevel(self.max_risk)]:
            return False
        return all(str(getattr(signature, name)) == expected for name, expected in self.signature_match.items())

    def to_dict(self) -> dict[str, Any]:
        return to_json_compatible(self)

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
        default_factory=RuntimeFeatures
    )
    loaded: dict[
        str,
        RuntimePatchPayload | RecoveryPolicyPatchPayload | RecoverySkillPayload | TaskSkillPayload,
    ] = field(
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
            payload: (
                RuntimePatchPayload
                | RecoveryPolicyPatchPayload
                | RecoverySkillPayload
                | TaskSkillPayload
            ) = runtime_payload
        elif artifact.artifact_type == EvolutionArtifactType.POLICY_PATCH.value:
            payload = RecoveryPolicyPatchPayload.from_dict(artifact.payload)
        elif artifact.artifact_type == EvolutionArtifactType.SKILL.value:
            payload = RecoverySkillPayload.from_dict(artifact.payload)
        elif artifact.artifact_type == EvolutionArtifactType.TASK_SKILL.value:
            payload = TaskSkillPayload.from_dict(artifact.payload)
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

    def recovery_policy(self) -> EvolutionRecoveryPolicy:
        return EvolutionRecoveryPolicy(decision_override=self._recovery_override)

    def task_skills_for(self, task_family: str) -> tuple[TaskSkillPayload, ...]:
        return tuple(
            payload
            for payload in self.loaded.values()
            if isinstance(payload, TaskSkillPayload)
            and payload.trigger.task_family == task_family.casefold().strip()
        )

    def _recovery_override(
        self,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        context: EvolutionRecoveryContext,
        error_code: RuntimeErrorCode | None,
    ) -> EvolutionRecoveryDecision | None:
        del receipt, error_code
        signature = context.failure_signature
        if signature is None:
            return None
        # Uncertain effects are always inspected before any learned response.
        if context.effect_may_have_occurred:
            return _evolution_recovery_decision(
                EvolutionRecoveryAction.INSPECT_POST_STATE,
                context,
                "candidate preserves inspect-before-recovery",
            )
        for artifact_id, payload in self.loaded.items():
            if not isinstance(payload, (RecoveryPolicyPatchPayload, RecoverySkillPayload)):
                continue
            if not payload.matches(context.task_id, signature, contract.risk):
                continue
            applied = self.recovery_applications.get(artifact_id, 0)
            if applied >= payload.max_applications:
                continue
            self.recovery_applications[artifact_id] = applied + 1
            if isinstance(payload, RecoveryPolicyPatchPayload):
                kind = _recovery_kind(payload.response)
            else:
                kind = _recovery_kind(payload.steps[min(applied, len(payload.steps) - 1)])
            return _evolution_recovery_decision(
                kind,
                context,
                f"declarative recovery artifact {artifact_id}",
                profile_artifact_id=artifact_id,
            )
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


@dataclass(frozen=True)
class LoadedRuntimeProfile:
    """Digest-bound accepted components ready for a normal Runtime entrypoint."""

    profile: CandidateRuntimeProfile
    profile_digest: str
    artifact_ids: tuple[str, ...]
    task_skill_runtime: AcceptedTaskSkillRuntime | None

    def recovery_policy(self) -> EvolutionRecoveryPolicy:
        return self.profile.recovery_policy()


@dataclass(frozen=True)
class AcceptedProfileLoader:
    """Load only accepted, payload-valid artifacts from a persisted registry."""

    path: Path

    def load(self) -> LoadedRuntimeProfile:
        encoded = self.path.read_bytes()
        profile_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        registry = EvolutionRegistryStore(self.path).load()
        accepted = tuple(
            artifact
            for _, artifact in sorted(registry.artifacts.items())
            if artifact.status == EvolutionStatus.ACCEPTED
        )
        if not accepted:
            raise ValueError("accepted runtime profile contains no accepted artifacts")
        profile = CandidateRuntimeProfile()
        for artifact in accepted:
            profile.load(artifact)
        task_skill_runtime = (
            AcceptedTaskSkillRuntime.from_profile(profile)
            if any(isinstance(item, TaskSkillPayload) for item in profile.loaded.values())
            else None
        )
        return LoadedRuntimeProfile(
            profile,
            profile_digest,
            tuple(artifact.id for artifact in accepted),
            task_skill_runtime,
        )
