"""Immutable Task authority scopes, Runtime signatures, and proof contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.immutable import FrozenDict, freeze_json, to_json_compatible
from affordance_runtime.verification.contracts import AssuranceLevel

AUTHORITY_EVALUATOR_POLICY_VERSION = "action-authority@v1"


class EffectClass(StrEnum):
    READ = "read"
    NAVIGATE = "navigate"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SEND = "send"
    SHARE = "share"
    PAY = "pay"
    INVOKE = "invoke"
    EXECUTE = "execute"
    INTERACTION_ONLY = "interaction_only"
    UNKNOWN = "unknown"


class Externality(StrEnum):
    LOCAL = "local"
    SAME_ORIGIN = "same_origin"
    CROSS_ORIGIN = "cross_origin"
    EXTERNAL_SYSTEM = "external_system"
    PHYSICAL_WORLD = "physical_world"
    UNKNOWN = "unknown"


class Reversibility(StrEnum):
    REVERSIBLE = "reversible"
    COMPENSATABLE = "compensatable"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class RuntimeRiskTier(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class AuthorityStatus(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    UNPROVEN = "unproven"


def externality_rank(value: Externality) -> int:
    """One conservative ordering shared by classification and authorization."""

    return {
        Externality.LOCAL: 0,
        Externality.SAME_ORIGIN: 1,
        Externality.CROSS_ORIGIN: 2,
        Externality.EXTERNAL_SYSTEM: 3,
        Externality.PHYSICAL_WORLD: 4,
        Externality.UNKNOWN: 5,
    }[value]


def reversibility_rank(value: Reversibility) -> int:
    """One conservative ordering shared by classification and authorization."""

    return {
        Reversibility.REVERSIBLE: 0,
        Reversibility.COMPENSATABLE: 1,
        Reversibility.IRREVERSIBLE: 2,
        Reversibility.UNKNOWN: 3,
    }[value]


@dataclass(frozen=True)
class ResourceScopeRef:
    resource_ref: str
    source_anchor_refs: tuple[str, ...] = ()
    predicate_ref: str = ""

    def __post_init__(self) -> None:
        if not self.resource_ref.strip() and not self.predicate_ref.strip():
            raise ValueError("resource scope requires canonical identity or bounded predicate")


@dataclass(frozen=True)
class ParameterAuthorization:
    slot: str
    value: object
    value_ref: str = ""
    predicate_ref: str = ""

    def __post_init__(self) -> None:
        if not self.slot.strip():
            raise ValueError("parameter authorization requires a named slot")
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class EffectAuthorizationScope:
    requirement_ref: str
    effect_class: EffectClass
    resource_scope: ResourceScopeRef
    operation_constraint: str | None = None
    destination_scope: ResourceScopeRef | None = None
    parameters: tuple[ParameterAuthorization, ...] = ()
    externality: Externality = Externality.LOCAL
    reversibility: Reversibility = Reversibility.REVERSIBLE
    required_capabilities: frozenset[str] = frozenset()
    risk_policy_ref: str = "runtime-standard@v1"
    minimum_source_assurance: AssuranceLevel = AssuranceLevel.STRUCTURAL
    approval_policy_ref: str = ""
    completion_policy_ref: str = ""

    def __post_init__(self) -> None:
        if not self.requirement_ref.strip() or not self.risk_policy_ref.strip():
            raise ValueError("effect scope requires requirement and risk-policy refs")
        slots = tuple(item.slot for item in self.parameters)
        if len(slots) != len(set(slots)):
            raise ValueError("effect scope parameter slots must be unique")
        if self.effect_class == EffectClass.UNKNOWN:
            raise ValueError("UNKNOWN effect cannot be admitted as executable authority")

    @property
    def digest(self) -> str:
        return _digest(self)


@dataclass(frozen=True)
class RuntimeRiskVector:
    effect_class: RuntimeRiskTier
    externality: RuntimeRiskTier
    reversibility: RuntimeRiskTier
    resource_sensitivity: RuntimeRiskTier
    asserted_source: RuntimeRiskTier
    material_parameters: RuntimeRiskTier
    capability: RuntimeRiskTier
    source_uncertainty: RuntimeRiskTier
    conflict: RuntimeRiskTier

    @property
    def maximum(self) -> RuntimeRiskTier:
        return max(asdict(self).values(), key=_risk_rank)


@dataclass(frozen=True)
class RuntimeEffectSignature:
    observation_ref: str
    action_kind: str
    effect_class: EffectClass | None
    target_ref: str
    resource_ref: str | None
    destination_ref: str | None
    operation_ref: str | None
    parameter_values: FrozenDict = field(default_factory=lambda: FrozenDict({}))
    externality: Externality | None = None
    reversibility: Reversibility | None = None
    assurance: AssuranceLevel = AssuranceLevel.WEAK
    conflict_status: str = "inconclusive"
    coverage_complete: bool = False
    candidate_binding_digest: str = ""
    source_refs: tuple[str, ...] = ()
    backend_operation: str = ""
    risk_vector: RuntimeRiskVector | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameter_values",
            self.parameter_values
            if isinstance(self.parameter_values, FrozenDict)
            else FrozenDict(self.parameter_values),
        )

    @property
    def runtime_risk(self) -> RuntimeRiskTier:
        return self.risk_vector.maximum if self.risk_vector else RuntimeRiskTier.CRITICAL

    @property
    def digest(self) -> str:
        return _digest(self)


@dataclass(frozen=True)
class ActionAuthorityProof:
    status: AuthorityStatus
    task_ref: str
    authorization_scope_ref: str | None
    authorization_scope_digest: str | None
    enabling_policy_ref: str | None
    runtime_effect_signature_digest: str
    observation_ref: str
    candidate_binding_digest: str
    reason_codes: tuple[str, ...]
    evaluator_policy_version: str = AUTHORITY_EVALUATOR_POLICY_VERSION
    effect_refs: tuple[str, ...] = ()
    runtime_risk: RuntimeRiskTier = RuntimeRiskTier.CRITICAL
    effect_class: EffectClass | None = None
    proof_digest: str = ""

    def __post_init__(self) -> None:
        if not self.evaluator_policy_version.strip():
            raise ValueError("authority proof requires evaluator policy version")
        if self.status == AuthorityStatus.ALLOW:
            owners = int(self.authorization_scope_ref is not None) + int(self.enabling_policy_ref is not None)
            if owners != 1:
                raise ValueError("ALLOW proof requires exactly one authority owner")
        if not self.proof_digest:
            object.__setattr__(self, "proof_digest", _digest({**asdict(self), "proof_digest": ""}))

    @property
    def authorized(self) -> bool:
        return self.status == AuthorityStatus.ALLOW

    @property
    def reason_code(self) -> str:
        return self.reason_codes[0] if self.reason_codes else ""

    @property
    def scope_digest(self) -> str:
        return self.proof_digest

    @property
    def effectful(self) -> bool:
        return self.effect_class not in {None, EffectClass.READ, EffectClass.INTERACTION_ONLY}

    @property
    def risk(self) -> RiskLevel:
        return {
            RuntimeRiskTier.LOW: RiskLevel.LOW,
            RuntimeRiskTier.MODERATE: RiskLevel.MEDIUM,
            RuntimeRiskTier.HIGH: RiskLevel.HIGH,
            RuntimeRiskTier.CRITICAL: RiskLevel.IRREVERSIBLE,
        }[self.runtime_risk]


ActionAuthorityDecision = ActionAuthorityProof


def _risk_rank(value: RuntimeRiskTier | str) -> int:
    return {
        RuntimeRiskTier.LOW.value: 0,
        RuntimeRiskTier.MODERATE.value: 1,
        RuntimeRiskTier.HIGH.value: 2,
        RuntimeRiskTier.CRITICAL.value: 3,
    }[value.value if isinstance(value, RuntimeRiskTier) else value]


def _digest(value: Any) -> str:
    payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
    encoded = json.dumps(to_json_compatible(payload), sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
