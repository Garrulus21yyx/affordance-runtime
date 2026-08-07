"""Capability and side-effect gate."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Iterator
from urllib.parse import urlsplit

from affordance_runtime.action_choice_authority import contract_matches_task_authority
from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.contracts import (
    ActionContract,
    ApprovalToken,
    RiskLevel,
    RuntimeErrorCode,
    risk_level_rank,
)
from affordance_runtime.effect_authority_contracts import ActionAuthorityProof, EffectClass
from affordance_runtime.execution_context import EffectiveCapabilities, ExecutorCapabilityDescriptor
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation


class _LinearizedSet(set[Any]):
    def __init__(self, values: Any, lock: RLock):
        super().__init__(values)
        self._lock = lock

    def clear(self) -> None:
        with self._lock:
            super().clear()

    def add(self, element: Any) -> None:
        with self._lock:
            super().add(element)

    def discard(self, element: Any) -> None:
        with self._lock:
            super().discard(element)

    def remove(self, element: Any) -> None:
        with self._lock:
            super().remove(element)

    def update(self, *others: Any) -> None:
        with self._lock:
            super().update(*others)

    def pop(self) -> Any:
        with self._lock:
            return super().pop()

    def difference_update(self, *others: Any) -> None:
        with self._lock:
            super().difference_update(*others)

    def intersection_update(self, *others: Any) -> None:
        with self._lock:
            super().intersection_update(*others)

    def symmetric_difference_update(self, other: Any) -> None:
        with self._lock:
            super().symmetric_difference_update(other)

    def __ior__(self, other: Any) -> _LinearizedSet:  # type: ignore[override,misc]
        with self._lock:
            super().__ior__(other)
            return self

    def __iand__(self, other: Any) -> _LinearizedSet:  # type: ignore[override,misc]
        with self._lock:
            super().__iand__(other)
            return self

    def __isub__(self, other: Any) -> _LinearizedSet:  # type: ignore[override,misc]
        with self._lock:
            super().__isub__(other)
            return self

    def __ixor__(self, other: Any) -> _LinearizedSet:  # type: ignore[override,misc]
        with self._lock:
            super().__ixor__(other)
            return self

class _LinearizedDict(dict[str, ApprovalToken]):
    def __init__(self, values: dict[str, ApprovalToken], lock: RLock):
        super().__init__(values)
        self._lock = lock

    def clear(self) -> None:
        with self._lock:
            super().clear()

    def __setitem__(self, key: str, value: ApprovalToken) -> None:
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            super().__delitem__(key)

    def pop(self, key: str, default: Any = None) -> ApprovalToken | Any:
        with self._lock:
            return super().pop(key, default)

    def popitem(self) -> tuple[str, ApprovalToken]:
        with self._lock:
            return super().popitem()

    def setdefault(self, key: str, default: ApprovalToken | None = None) -> ApprovalToken:
        with self._lock:
            return super().setdefault(key, default)  # type: ignore[arg-type]

    def update(self, *args: Any, **kwargs: ApprovalToken) -> None:
        with self._lock:
            super().update(*args, **kwargs)

    def __ior__(self, other: Any) -> _LinearizedDict:  # type: ignore[override,misc]
        with self._lock:
            super().__ior__(other)
            return self


@dataclass
class CapabilityGate:
    granted_capabilities: set[str] = field(default_factory=set)
    approval_required_risks: set[RiskLevel] = field(default_factory=lambda: {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE})
    approval_required_capabilities: set[str] = field(default_factory=set)
    approval_tokens: dict[str, ApprovalToken] = field(default_factory=dict)
    executor_descriptor: ExecutorCapabilityDescriptor | None = None
    product_allowed_actions: frozenset[str] = frozenset()
    product_allowed_capabilities: frozenset[str] | None = None
    grant_source: "CapabilityGate | None" = field(default=None, repr=False)
    _linearization_lock: RLock = field(default_factory=RLock, repr=False)

    def __setattr__(self, name: str, value: Any) -> None:
        lock = self.__dict__.get("_linearization_lock")
        if lock is not None and name in {
            "granted_capabilities",
            "approval_required_risks",
            "approval_required_capabilities",
            "approval_tokens",
        }:
            with lock:
                if name == "approval_tokens" and not isinstance(value, _LinearizedDict):
                    value = _LinearizedDict(dict(value), lock)
                elif name != "approval_tokens" and not isinstance(value, _LinearizedSet):
                    value = _LinearizedSet(value, lock)
                object.__setattr__(self, name, value)
            return
        object.__setattr__(self, name, value)

    def __post_init__(self) -> None:
        self.granted_capabilities = _LinearizedSet(self.granted_capabilities, self._linearization_lock)
        self.approval_required_risks = _LinearizedSet(
            self.approval_required_risks, self._linearization_lock
        )
        self.approval_required_capabilities = _LinearizedSet(
            self.approval_required_capabilities, self._linearization_lock
        )
        self.approval_tokens = _LinearizedDict(self.approval_tokens, self._linearization_lock)

    @contextmanager
    def linearized_authority(self) -> Iterator[None]:
        """Hold every mutable grant owner through admission and intent commit."""

        owners: list[CapabilityGate] = []
        current: CapabilityGate | None = self
        while current is not None:
            if any(current is owner for owner in owners):
                raise ValueError("CapabilityGate grant_source cycle")
            owners.append(current)
            current = current.grant_source
        ordered = sorted(owners, key=id)
        for owner in ordered:
            owner._linearization_lock.acquire()
        try:
            yield
        finally:
            for owner in reversed(ordered):
                owner._linearization_lock.release()

    def check(self, contract: ActionContract) -> RuntimeErrorCode | None:
        with self._linearization_lock:
            return self._check_locked(contract)

    def _check_locked(self, contract: ActionContract) -> RuntimeErrorCode | None:
        inherited = self.grant_source.granted_capabilities if self.grant_source is not None else set()
        current_grants = frozenset(self.granted_capabilities | inherited)
        missing = [capability for capability in contract.required_capabilities if capability not in current_grants]
        descriptor = self.executor_descriptor
        if descriptor is not None:
            if contract.backend not in descriptor.supported_backends or contract.action not in descriptor.actions_for(contract.backend):
                return RuntimeErrorCode.BACKEND_UNAVAILABLE
            if self.product_allowed_actions and contract.action not in self.product_allowed_actions:
                return RuntimeErrorCode.CAPABILITY_DENIED
            policy_caps = (
                self.product_allowed_capabilities
                if self.product_allowed_capabilities is not None
                else current_grants
            )
            effective = EffectiveCapabilities.intersect(
                provider=descriptor.provider_capabilities_for(contract.backend),
                adapter=descriptor.adapter_capabilities_for(contract.backend),
                product_policy=policy_caps,
                user_grants=current_grants,
            )
            missing.extend(
                capability
                for capability in contract.required_capabilities
                if capability not in effective.capabilities
            )
        if missing:
            return RuntimeErrorCode.CAPABILITY_DENIED
        effective_risk = _effective_contract_risk(contract)
        requires_approval = effective_risk in self.approval_required_risks or bool(
            set(contract.required_capabilities) & self.approval_required_capabilities
        )
        if requires_approval:
            if not any(token.matches(contract) for token in self.approval_tokens.values()):
                return RuntimeErrorCode.APPROVAL_REQUIRED
        return None

    def authorize(self, contract: ActionContract) -> RuntimeErrorCode | None:
        """Check policy and atomically consume a matching approval token."""

        with self._linearization_lock:
            error = self._check_locked(contract)
            if error is not None:
                return error
            effective_risk = _effective_contract_risk(contract)
            requires_approval = effective_risk in self.approval_required_risks or bool(
                set(contract.required_capabilities) & self.approval_required_capabilities
            )
            if requires_approval:
                token = next(item for item in self.approval_tokens.values() if item.matches(contract))
                token.consume()
            return None


def _effective_contract_risk(contract: ActionContract) -> RiskLevel:
    proof_risk = getattr(contract.action_authority_proof, "risk", contract.risk)
    if isinstance(proof_risk, RiskLevel) and risk_level_rank(proof_risk) > risk_level_rank(contract.risk):
        return proof_risk
    return contract.risk


@dataclass(frozen=True)
class TaskConstraintPolicy:
    """Enforce typed task authority independently from planner/page suggestions."""

    def check(
        self,
        contract: ActionContract,
        constraints: dict[str, Any],
        task_spec: TaskSpec | None = None,
        canonical_observation: UnifiedObservation | None = None,
    ) -> RuntimeErrorCode | None:
        if task_spec is not None and contract.selected_choice_id:
            proof = self.evaluate_authority(contract, task_spec, canonical_observation)
            if not proof.authorized:
                return RuntimeErrorCode.POLICY_DENIED
        signature = contract.runtime_effect_signature
        effectful = (
            signature.effect_class not in {EffectClass.READ, EffectClass.NAVIGATE, EffectClass.INTERACTION_ONLY}
            if signature is not None
            else bool(contract.required_capabilities)
            or contract.risk != RiskLevel.LOW
            or contract.action in {"download", "write_property", "invoke"}
        )
        if constraints.get("read_only") and effectful:
            return RuntimeErrorCode.POLICY_DENIED
        forbidden = {
            "no_purchase": frozenset({EffectClass.PAY}),
            "no_delete": frozenset({EffectClass.DELETE}),
            "no_external_message": frozenset({EffectClass.SEND, EffectClass.SHARE}),
        }
        for constraint, effect_classes in forbidden.items():
            if constraints.get(constraint) and signature is not None and signature.effect_class in effect_classes:
                return RuntimeErrorCode.POLICY_DENIED
        allowed_domains = constraints.get("allowed_domains")
        if allowed_domains:
            target_url = str(
                contract.parameters.get("url") or contract.locator.get("url") or contract.locator.get("href") or ""
            )
            hostname = urlsplit(target_url).hostname if target_url else None
            if hostname and hostname not in set(str(item) for item in allowed_domains):
                return RuntimeErrorCode.POLICY_DENIED
        return None

    def evaluate_authority(
        self,
        contract: ActionContract,
        task_spec: TaskSpec,
        canonical_observation: UnifiedObservation | None,
    ) -> ActionAuthorityProof:
        signature = contract.runtime_effect_signature
        if canonical_observation is not None and signature is not None:
            candidate = next(
                (
                    item
                    for item in canonical_observation.bindings
                    if contract.grounding_candidate is not None
                    and item.candidate_id == contract.grounding_candidate.candidate_id
                ),
                None,
            )
            destination_candidate = None
            if contract.gesture_binding is not None:
                destination_candidate = next(
                    (
                        item
                        for item in canonical_observation.bindings
                        if item.candidate_id == contract.gesture_binding.destination.candidate_id
                    ),
                    None,
                )
            signature = classify_action(
                canonical_observation,
                target_id=signature.target_ref,
                destination_id=signature.destination_ref or "",
                action_kind=signature.action_kind,
                parameters=signature.parameter_values,
                candidate=candidate,
                destination_candidate=destination_candidate,
            )
        return contract_matches_task_authority(
            task_spec=task_spec,
            runtime_signature=signature,
            sealed_proof=contract.action_authority_proof,
            requirement_refs=contract.requirement_refs,
            choice_role=contract.choice_role,
        )
