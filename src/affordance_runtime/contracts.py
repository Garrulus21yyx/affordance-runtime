"""Core contracts for planner-neutral GUI execution.

This module is the cleaned-up successor of the Modular Action System contracts.
It keeps the old repository's typed affordance idea, then adds environment
revision, lease, verifier, risk, and evidence fields needed by the new runtime.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from enum import StrEnum
from time import time
from typing import TYPE_CHECKING, Any

from affordance_runtime.immutable import FrozenSequence, freeze_json, to_json_compatible

if TYPE_CHECKING:
    from affordance_runtime.grounding import GroundingCandidate, RoutePlan


ACTION_CONTRACT_SCHEMA_VERSION = "1.2"


class Surface(StrEnum):
    DOM = "dom"
    SVG = "svg"
    VISUAL = "visual"
    ACCESSIBILITY = "accessibility"
    WOT = "wot"
    API = "api"
    DEVICE = "device"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


def risk_level_rank(value: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.IRREVERSIBLE: 3,
    }[value]


class ProgressEvidenceScope(StrEnum):
    """Owner-declared scope for materializing task-progress evidence links."""

    NONE = "none"
    ACTIVE_SUBGOAL = "active_subgoal"
    TASK_TERMINAL = "task_terminal"


class ScopeRelationKind(StrEnum):
    SEMANTIC_VALUE_UNIQUE_CONTROL = "semantic_value_unique_control"
    OBSERVED_VALUE_TRANSFER = "observed_value_transfer"
    ENTITY_PROPERTY = "entity_property"
    ORDINAL_COLLECTION_ITEM = "ordinal_collection_item"
    GLOBAL_ORDINAL_COLLECTION_ITEM = "global_ordinal_collection_item"
    PAGINATION_TRANSITION = "pagination_transition"


class RuntimeErrorCode(StrEnum):
    STALE_OBSERVATION = "stale_observation"
    STALE_PAGE_REVISION = "stale_page_revision"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"
    TARGET_FINGERPRINT_MISMATCH = "target_fingerprint_mismatch"
    LEASE_EXPIRED = "lease_expired"
    PRECONDITION_FAILED = "precondition_failed"
    CAPABILITY_DENIED = "capability_denied"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_INVALID = "approval_invalid"
    POLICY_DENIED = "policy_denied"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    EXECUTION_TIMEOUT = "execution_timeout"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    UNSAFE_ACTION = "unsafe_action"
    STALE_TASK_REVISION = "stale_task_revision"
    STALE_STATE_VERSION = "stale_state_version"
    PLANNER_PROPOSAL_REJECTED = "planner_proposal_rejected"
    PLANNER_FAILED = "planner_failed"
    EFFECT_ALREADY_SATISFIED = "effect_already_satisfied"
    NO_PROGRESS_REPEAT = "no_progress_repeat"
    PROGRESS_CREDIT_INVARIANT = "progress_credit_invariant"
    RATE_LIMIT_TRANSIENT = "rate_limit_transient"
    QUOTA_EXHAUSTED = "quota_exhausted"
    PROVIDER_CAPACITY = "provider_capacity"


@dataclass(frozen=True)
class Condition:
    predicate: str
    description: str = ""
    required: bool = True


@dataclass(frozen=True)
class Observation:
    environment_revision: str
    url: str = ""
    dom_hash: str = ""
    screenshot_ref: str = ""
    accessibility_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_id: str = ""
    page_revision: str = ""
    observed_at_s: float = field(default_factory=time)
    target_fingerprints: dict[str, str] = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # ``environment_revision`` is retained as the v0 skeleton compatibility
        # field. New contracts bind the narrower semantic page revision.
        if not self.page_revision:
            object.__setattr__(self, "page_revision", self.environment_revision)
        object.__setattr__(self, "metadata", freeze_json(self.metadata))
        object.__setattr__(self, "target_fingerprints", freeze_json(self.target_fingerprints))
        object.__setattr__(self, "artifact_refs", freeze_json(self.artifact_refs))


@dataclass(frozen=True)
class AffordanceLease:
    """Validity boundary for an affordance snapshot."""

    environment_revision: str
    issued_at_s: float
    ttl_ms: int = 2_000
    provenance: list[str] = field(default_factory=list)
    confidence: float = 1.0
    snapshot_id: str = ""
    page_revision: str = ""
    target_fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", freeze_json(self.provenance))

    @classmethod
    def issue(
        cls,
        *,
        environment_revision: str,
        ttl_ms: int = 2_000,
        provenance: list[str] | None = None,
        confidence: float = 1.0,
        snapshot_id: str = "",
        page_revision: str = "",
        target_fingerprint: str = "",
    ) -> "AffordanceLease":
        return cls(
            environment_revision=environment_revision,
            issued_at_s=time(),
            ttl_ms=ttl_ms,
            provenance=provenance or [],
            confidence=confidence,
            snapshot_id=snapshot_id,
            page_revision=page_revision or environment_revision,
            target_fingerprint=target_fingerprint,
        )

    @property
    def expires_at_s(self) -> float:
        return self.issued_at_s + self.ttl_ms / 1_000.0

    def is_current(
        self,
        observation: Observation,
        *,
        affordance_id: str = "",
        now_s: float | None = None,
    ) -> bool:
        current_time = time() if now_s is None else now_s
        if current_time > self.expires_at_s:
            return False
        if self.page_revision and self.page_revision != observation.page_revision:
            return False
        if self.snapshot_id and observation.snapshot_id and self.snapshot_id != observation.snapshot_id:
            return False
        current_fingerprint = observation.target_fingerprints.get(affordance_id)
        if self.target_fingerprint and current_fingerprint and self.target_fingerprint != current_fingerprint:
            return False
        return self.environment_revision == observation.environment_revision


@dataclass(frozen=True)
class Affordance:
    id: str
    surface: Surface
    role: str
    label: str
    action: str
    locator: dict[str, Any]
    lease: AffordanceLease
    backend_candidates: list[str] = field(default_factory=list)
    confidence: float = 1.0
    state: dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    risk_asserted: bool = False
    operation_ref: str = ""
    effect_class: str = ""
    externality: str = ""
    reversibility: str = ""
    resource_sensitivity: str = ""
    authority_source_assurance: str = ""
    evidence: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "locator", freeze_json(self.locator))
        object.__setattr__(self, "backend_candidates", freeze_json(self.backend_candidates))
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "evidence", freeze_json(self.evidence))
        object.__setattr__(self, "payload", freeze_json(self.payload))

    @property
    def target_fingerprint(self) -> str:
        return self.lease.target_fingerprint


@dataclass(frozen=True)
class GestureTargetBinding:
    """One semantic endpoint resolved during one coherent observation epoch."""

    semantic_target_id: str
    candidate_id: str
    locator: dict[str, Any]
    snapshot_id: str
    page_revision: str
    target_fingerprint: str
    target_fingerprint_key: str
    lease: AffordanceLease

    def __post_init__(self) -> None:
        object.__setattr__(self, "locator", freeze_json(self.locator))

    @classmethod
    def from_affordance(
        cls,
        affordance: Affordance,
        *,
        semantic_target_id: str = "",
        candidate_id: str = "",
        target_fingerprint_key: str = "",
    ) -> "GestureTargetBinding":
        return cls(
            semantic_target_id=semantic_target_id or affordance.id,
            candidate_id=candidate_id or affordance.id,
            locator=dict(affordance.locator),
            snapshot_id=affordance.lease.snapshot_id,
            page_revision=affordance.lease.page_revision,
            target_fingerprint=affordance.lease.target_fingerprint,
            target_fingerprint_key=target_fingerprint_key or semantic_target_id or affordance.id,
            lease=affordance.lease,
        )


@dataclass(frozen=True)
class GestureBinding:
    """Dual-target semantic binding, before any backend-specific encoding."""

    source: GestureTargetBinding
    destination: GestureTargetBinding
    selected_route: str = ""


class GestureBindingError(ValueError):
    """A backend-neutral failure to bind a two-endpoint gesture."""

    def __init__(self, code: RuntimeErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


@dataclass(frozen=True)
class ScopeAuthorization:
    """Task-authority decision bound to one current grounding candidate."""

    relation: ScopeRelationKind
    candidate_id: str
    snapshot_id: str
    target_fingerprint: str
    evidence_digest: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.candidate_id, self.snapshot_id, self.evidence_digest)):
            raise ValueError("scope authorization requires candidate, snapshot, and evidence identity")


@dataclass(frozen=True)
class GestureContractBinder:
    """Resolve and validate a gesture before any backend encodes it.

    The binder owns semantic endpoint compatibility, coherent-observation, and
    shared-route invariants.  It deliberately does not inspect backend handles,
    backend locators, or visual coordinates.
    """

    def bind(
        self,
        source: Affordance,
        destination: Affordance,
        *,
        selected_route: str,
        observation: Observation,
        source_semantic_target_id: str = "",
        source_candidate_id: str = "",
        source_fingerprint_key: str = "",
        destination_semantic_target_id: str = "",
        destination_candidate_id: str = "",
        destination_fingerprint_key: str = "",
    ) -> GestureBinding:
        if source.id == destination.id:
            raise GestureBindingError(
                RuntimeErrorCode.PRECONDITION_FAILED,
                "gesture source and destination must differ",
            )
        if source.action != "drag":
            raise GestureBindingError(
                RuntimeErrorCode.PRECONDITION_FAILED,
                f"gesture source does not support drag: {source.id}",
            )
        if destination.action not in {"drag", "drop"} and not bool(destination.state.get("accepts_drop")):
            raise GestureBindingError(
                RuntimeErrorCode.PRECONDITION_FAILED,
                f"gesture destination cannot accept a drop: {destination.id}",
            )
        if not selected_route:
            raise GestureBindingError(
                RuntimeErrorCode.BACKEND_UNAVAILABLE,
                "gesture route is missing",
            )
        if selected_route not in source.backend_candidates or selected_route not in destination.backend_candidates:
            raise GestureBindingError(
                RuntimeErrorCode.BACKEND_UNAVAILABLE,
                f"gesture endpoints do not share route: {selected_route}",
            )
        binding = GestureBinding(
            source=GestureTargetBinding.from_affordance(
                source,
                semantic_target_id=source_semantic_target_id,
                candidate_id=source_candidate_id,
                target_fingerprint_key=source_fingerprint_key,
            ),
            destination=GestureTargetBinding.from_affordance(
                destination,
                semantic_target_id=destination_semantic_target_id,
                candidate_id=destination_candidate_id,
                target_fingerprint_key=destination_fingerprint_key,
            ),
            selected_route=selected_route,
        )
        error = gesture_preflight(binding, observation)
        if error is not None:
            raise GestureBindingError(error, "gesture endpoint is not current")
        return binding


def gesture_preflight(
    binding: GestureBinding,
    observation: Observation,
    *,
    require_snapshot_identity: bool = True,
    require_environment_revision: bool = True,
) -> RuntimeErrorCode | None:
    """Validate every gesture endpoint against the current observation.

    This deliberately contains no backend-specific handle, locator, or coordinate logic.
    Backends receive a valid semantic binding and only encode their own gesture.
    """

    source = binding.source
    destination = binding.destination
    if source.semantic_target_id == destination.semantic_target_id:
        return RuntimeErrorCode.PRECONDITION_FAILED
    if (
        source.snapshot_id != destination.snapshot_id
        or source.page_revision != destination.page_revision
        or source.lease.environment_revision != destination.lease.environment_revision
    ):
        return RuntimeErrorCode.PRECONDITION_FAILED
    for target in (source, destination):
        if target.lease.expires_at_s < time():
            return RuntimeErrorCode.LEASE_EXPIRED
        if require_environment_revision and target.lease.environment_revision != observation.environment_revision:
            return RuntimeErrorCode.STALE_OBSERVATION
        if target.page_revision and target.page_revision != observation.page_revision:
            return RuntimeErrorCode.STALE_PAGE_REVISION
        if require_snapshot_identity and target.snapshot_id and target.snapshot_id != observation.snapshot_id:
            return RuntimeErrorCode.SNAPSHOT_MISMATCH
        if target.target_fingerprint and (
            observation.target_fingerprints.get(target.target_fingerprint_key or target.semantic_target_id)
            != target.target_fingerprint
        ):
            return RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH
    overlays = observation.metadata.get("blocking_overlays")
    if _gesture_endpoint_blocked(source, overlays) or _gesture_endpoint_blocked(destination, overlays):
        return RuntimeErrorCode.PRECONDITION_FAILED
    return None


def _gesture_endpoint_blocked(target: GestureTargetBinding, raw_overlays: Any) -> bool:
    """Check current generic viewport geometry without backend-specific handles."""

    if not isinstance(raw_overlays, Sequence) or isinstance(raw_overlays, (str, bytes)):
        return False
    point = _gesture_locator_point(target.locator)
    if point is None:
        return False
    for item in raw_overlays:
        if not hasattr(item, "get"):
            continue
        raw_box = item.get("bbox")
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            continue
        try:
            left, top, width, height = (float(value) for value in raw_box)
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0 and left <= point[0] <= left + width and top <= point[1] <= top + height:
            return True
    return False


def _gesture_locator_point(locator: dict[str, Any]) -> tuple[float, float] | None:
    for key in ("point", "center"):
        raw_point = locator.get(key)
        if isinstance(raw_point, (list, tuple)) and len(raw_point) == 2:
            try:
                return float(raw_point[0]), float(raw_point[1])
            except (TypeError, ValueError):
                return None
    raw_box = locator.get("bbox")
    if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
        try:
            left, top, width, height = (float(value) for value in raw_box)
        except (TypeError, ValueError):
            return None
        if width > 0 and height > 0:
            return left + width / 2, top + height / 2
    return None


@dataclass(frozen=True)
class VerifierSpec:
    kind: str
    target: str
    expected: Any = True
    strict: bool = True
    evidence_key: str = ""
    criterion_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    progress_scope: ProgressEvidenceScope = ProgressEvidenceScope.NONE

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", freeze_json(self.expected))
        object.__setattr__(self, "criterion_ids", tuple(self.criterion_ids))
        object.__setattr__(self, "requirement_ids", tuple(self.requirement_ids))


@dataclass(frozen=True)
class ActionContract:
    """Executable action with explicit state, safety, and verification bounds."""

    id: str
    intent: str
    affordance_id: str
    action: str
    backend: str
    environment_revision: str
    locator: dict[str, Any]
    choice_catalog_id: str = ""
    choice_catalog_digest: str = ""
    selected_choice_id: str = ""
    observation_ref: str = ""
    requirement_refs: tuple[str, ...] = ()
    effect_authorization_refs: tuple[str, ...] = ()
    choice_role: str = ""
    action_authority_proof: Any | None = None
    runtime_effect_signature: Any | None = None
    route_reason: str = ""
    grounding_candidate: GroundingCandidate | None = None
    scope_authorization: ScopeAuthorization | None = None
    route_plan: RoutePlan | None = None
    gesture_binding: GestureBinding | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    preconditions: list[Condition] = field(default_factory=list)
    expected_effects: list[Condition] = field(default_factory=list)
    verifier_plan: list[VerifierSpec] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW
    idempotency_key: str = ""
    compensation: str | None = None
    timeout_ms: int = 5_000
    fallback_backends: list[str] = field(default_factory=list)
    schema_version: str = ACTION_CONTRACT_SCHEMA_VERSION
    run_id: str = ""
    snapshot_id: str = ""
    page_revision: str = ""
    target_fingerprint: str = ""
    target_fingerprint_key: str = ""
    observed_at_s: float = 0.0
    expires_at_s: float = 0.0
    validity_policy: str = "snapshot_page_target_ttl"
    contract_hash: str = ""
    supersedes_contract_id: str = ""
    source_contract_id: str = ""
    fallback_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "locator", freeze_json(self.locator))
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        object.__setattr__(self, "requirement_refs", tuple(self.requirement_refs))
        object.__setattr__(self, "effect_authorization_refs", tuple(self.effect_authorization_refs))
        if any(not item.strip() for item in (*self.requirement_refs, *self.effect_authorization_refs)):
            raise ValueError("ActionContract authority refs must be nonblank")
        if len(set(self.requirement_refs)) != len(self.requirement_refs):
            raise ValueError("ActionContract requirement refs must be unique")
        if len(set(self.effect_authorization_refs)) != len(self.effect_authorization_refs):
            raise ValueError("ActionContract effect authorization refs must be unique")
        if self.effectful and not self.effect_authorization_refs:
            raise ValueError("effectful ActionContract requires effect authorization refs")
        object.__setattr__(self, "preconditions", FrozenSequence(self.preconditions))
        object.__setattr__(self, "expected_effects", FrozenSequence(self.expected_effects))
        object.__setattr__(self, "verifier_plan", FrozenSequence(self.verifier_plan))
        object.__setattr__(self, "required_capabilities", freeze_json(self.required_capabilities))
        object.__setattr__(self, "fallback_backends", freeze_json(self.fallback_backends))
        proof_risk = getattr(self.action_authority_proof, "risk", None)
        if isinstance(proof_risk, RiskLevel) and risk_level_rank(self.risk) < risk_level_rank(proof_risk):
            raise ValueError("ActionContract risk cannot be lower than sealed route authority risk")
        if not self.page_revision:
            object.__setattr__(self, "page_revision", self.environment_revision)
        computed_hash = self.compute_hash()
        if self.contract_hash and self.contract_hash != computed_hash:
            raise ValueError("ActionContract contract_hash does not match canonical payload")
        object.__setattr__(self, "contract_hash", computed_hash)
        if self.scope_authorization is not None:
            candidate = self.grounding_candidate
            authorization = self.scope_authorization
            if candidate is None:
                raise ValueError("scope authorization requires a grounding candidate")
            if (
                authorization.candidate_id != candidate.candidate_id
                or authorization.snapshot_id != candidate.observation_epoch_id
                or authorization.target_fingerprint != candidate.target_fingerprint
            ):
                raise ValueError("scope authorization does not match the grounded contract target")

    @property
    def effectful(self) -> bool:
        return bool(self.action_authority_proof and self.action_authority_proof.effectful)

    @property
    def authorization_scope_digest(self) -> str:
        proof = self.action_authority_proof
        return proof.authorization_scope_digest or "" if proof else ""

    def canonical_payload(self) -> dict[str, Any]:
        return {
            item.name: to_json_compatible(getattr(self, item.name))
            for item in fields(self)
            if item.name != "contract_hash"
        }

    def compute_hash(self) -> str:
        encoded = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @classmethod
    def from_affordance(
        cls,
        affordance: Affordance,
        *,
        intent: str,
        backend: str,
        expected_effects: list[Condition] | None = None,
        verifier_plan: list[VerifierSpec] | None = None,
        required_capabilities: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> "ActionContract":
        return cls(
            id=f"contract_{affordance.id}",
            intent=intent,
            affordance_id=affordance.id,
            action=affordance.action,
            backend=backend,
            environment_revision=affordance.lease.environment_revision,
            locator=affordance.locator,
            parameters=parameters or {},
            expected_effects=expected_effects or [],
            verifier_plan=verifier_plan or [],
            required_capabilities=required_capabilities or [],
            risk=affordance.risk,
            snapshot_id=affordance.lease.snapshot_id,
            page_revision=affordance.lease.page_revision,
            target_fingerprint=affordance.lease.target_fingerprint,
            observed_at_s=affordance.lease.issued_at_s,
            expires_at_s=affordance.lease.expires_at_s,
        )


@dataclass
class ApprovalToken:
    token_id: str
    run_id: str
    contract_hash: str
    snapshot_id: str
    page_revision: str
    environment_revision: str
    capability: str
    approver: str
    issued_at_s: float
    expires_at_s: float
    consumed_at_s: float | None = None

    @property
    def consumed(self) -> bool:
        return self.consumed_at_s is not None

    def matches(self, contract: ActionContract, *, now_s: float | None = None) -> bool:
        current_time = time() if now_s is None else now_s
        return (
            not self.consumed
            and current_time <= self.expires_at_s
            and self.run_id == contract.run_id
            and self.contract_hash == contract.contract_hash
            and self.snapshot_id == contract.snapshot_id
            and self.page_revision == contract.page_revision
            and self.environment_revision == contract.environment_revision
            and self.capability in contract.required_capabilities
            and bool(self.approver)
        )

    def consume(self, *, now_s: float | None = None) -> None:
        if self.consumed:
            raise ValueError(f"approval token already consumed: {self.token_id}")
        self.consumed_at_s = time() if now_s is None else now_s


@dataclass(frozen=True)
class ExecutionReceipt:
    contract_id: str
    backend: str
    success: bool
    started_revision: str
    ended_revision: str
    latency_ms: float
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: RuntimeErrorCode | None = None
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", freeze_json(self.evidence))
