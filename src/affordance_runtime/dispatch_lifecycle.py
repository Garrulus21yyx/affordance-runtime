"""Linearized final admission and single-use dispatch fencing."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock, RLock
from time import time
from typing import Callable

from affordance_runtime.contracts import ActionContract, Observation, RuntimeErrorCode
from affordance_runtime.execution_context import CoordinateBinding, digest_payload
from affordance_runtime.safety import CapabilityGate
from affordance_runtime.simplified_runtime_contracts import ExecutionAttempt


@dataclass(frozen=True)
class FinalDispatchAdmission:
    admission_id: str
    contract: ActionContract
    observation: Observation
    expected_state_version: int
    policy_revision: str
    capability_revision: str
    schema_digest: str
    surface_binding_digest: str
    coordinate_transform_digest: str
    contract_hash: str
    run_id: str
    session_generation: str
    surface_id: str
    issued_at_s: float
    expires_at_s: float
    gate: CapabilityGate = field(repr=False)
    policy_check: Callable[[], RuntimeErrorCode | None] = field(repr=False)
    surface_check: Callable[[], bool] = field(repr=False)
    coordinate_check: Callable[[CoordinateBinding], bool] = field(default=lambda _binding: True, repr=False)
    fence_lock: object = field(default_factory=RLock, repr=False)
    _consumed: bool = field(default=False, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @classmethod
    def issue(
        cls,
        *,
        contract: ActionContract,
        observation: Observation,
        expected_state_version: int,
        gate: CapabilityGate,
        policy_check: Callable[[], RuntimeErrorCode | None],
        surface_check: Callable[[], bool],
        coordinate_check: Callable[[CoordinateBinding], bool] | None = None,
        fence_lock: object | None = None,
        ttl_s: float = 2.0,
    ) -> "FinalDispatchAdmission":
        route = contract.route_binding
        if (
            route is None
            or contract.live_surface_binding is None
            or contract.coordinate_binding is None
            or not contract.transaction_seal
            or not contract.contract_hash
        ):
            raise ValueError("final admission requires a sealed transaction binding")
        issued = time()
        payload = {
            "contract_hash": contract.contract_hash,
            "state_version": expected_state_version,
            "policy": route.route_policy_digest,
            "capability": route.tool_schema_digest,
            "surface": route.surface_binding_digest,
            "coordinate": route.coordinate_transform_digest,
            "issued": issued,
        }
        return cls(
            admission_id="dispatch-admission:" + digest_payload(payload).split(":", 1)[1],
            contract=contract,
            observation=observation,
            expected_state_version=expected_state_version,
            policy_revision=route.route_policy_digest,
            capability_revision=route.tool_schema_digest,
            schema_digest=route.tool_schema_digest,
            surface_binding_digest=route.surface_binding_digest,
            coordinate_transform_digest=route.coordinate_transform_digest,
            contract_hash=contract.contract_hash,
            run_id=contract.run_id,
            session_generation=contract.live_surface_binding.session_generation,
            surface_id=contract.live_surface_binding.surface_id,
            issued_at_s=issued,
            expires_at_s=issued + ttl_s,
            gate=gate,
            policy_check=policy_check,
            surface_check=surface_check,
            coordinate_check=coordinate_check or (lambda _binding: True),
            fence_lock=fence_lock or RLock(),
        )

    def consume_if_current(self, *, state_version: int, now_s: float | None = None) -> RuntimeErrorCode | None:
        with self._lock:
            current_time = time() if now_s is None else now_s
            if self._consumed or current_time > self.expires_at_s or state_version != self.expected_state_version:
                return RuntimeErrorCode.STALE_OBSERVATION
            route = self.contract.route_binding
            surface = self.contract.live_surface_binding
            coordinate = self.contract.coordinate_binding
            descriptor = self.gate.executor_descriptor
            if (
                route is None
                or surface is None
                or coordinate is None
                or self.contract.contract_hash != self.contract_hash
                or self.contract.run_id != self.run_id
                or surface.session_generation != self.session_generation
                or surface.surface_id != self.surface_id
                or route.route_policy_digest != self.policy_revision
                or route.tool_schema_digest != self.schema_digest
                or route.surface_binding_digest != self.surface_binding_digest
                or route.coordinate_transform_digest != self.coordinate_transform_digest
                or descriptor is None
                or descriptor.tool_schema_digest != self.capability_revision
                or not surface.lease.current(surface, now_s=current_time)
                or not coordinate.current_for(surface)
                or not self.coordinate_check(coordinate)
                or not self.surface_check()
            ):
                return RuntimeErrorCode.STALE_OBSERVATION
            error = self.policy_check()
            if error is None:
                error = self.gate.authorize(self.contract)
            if error is not None:
                return error
            object.__setattr__(self, "_consumed", True)
            return None


@dataclass(frozen=True)
class DispatchPermit:
    permit_id: str
    admission_id: str
    contract: ActionContract
    observation: Observation
    attempt: ExecutionAttempt
    committed_state_version: int
    issued_at_s: float
    expires_at_s: float
    contract_hash: str
    run_id: str
    session_generation: str
    surface_id: str
    surface_check: Callable[[], bool] = field(repr=False)
    coordinate_check: Callable[[CoordinateBinding], bool] = field(default=lambda _binding: True, repr=False)
    fence_lock: object = field(default_factory=RLock, repr=False)
    _used: bool = field(default=False, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        surface = self.contract.live_surface_binding
        if (
            surface is None
            or self.contract.contract_hash != self.contract_hash
            or self.contract.run_id != self.run_id
            or surface.session_generation != self.session_generation
            or surface.surface_id != self.surface_id
            or self.attempt.contract_hash != self.contract_hash
            or self.attempt.contract_id != self.contract.id
        ):
            raise ValueError("DispatchPermit fence mismatch")

    def consume(self, *, now_s: float | None = None) -> None:
        with self._lock, self.fence_lock:  # type: ignore[attr-defined]
            self._consume_locked(now_s=now_s)

    def execute(self, callback: Callable[[], object], *, now_s: float | None = None) -> object:
        """Consume and invoke the provider while holding the surface-owner fence."""

        with self._lock, self.fence_lock:  # type: ignore[attr-defined]
            self._consume_locked(now_s=now_s)
            try:
                return callback()
            except Exception as exc:
                raise ProviderDispatchError(exc) from exc

    def _consume_locked(self, *, now_s: float | None = None) -> None:
        if self._used:
            raise DispatchPermitRejected("DispatchPermit is single-use")
        current_time = time() if now_s is None else now_s
        surface = self.contract.live_surface_binding
        coordinate = self.contract.coordinate_binding
        if (
            current_time > self.expires_at_s
            or surface is None
            or coordinate is None
            or not surface.lease.current(surface, now_s=current_time)
            or not coordinate.current_for(surface)
            or not self.coordinate_check(coordinate)
            or not self.surface_check()
            or self.contract.contract_hash != self.contract_hash
            or self.contract.run_id != self.run_id
            or surface.session_generation != self.session_generation
            or surface.surface_id != self.surface_id
        ):
            raise DispatchPermitRejected("DispatchPermit is stale or fenced to another runtime surface")
        object.__setattr__(self, "_used", True)


DispatchCommitter = Callable[[FinalDispatchAdmission, ExecutionAttempt], DispatchPermit]


class DispatchAdmissionRejected(RuntimeError):
    def __init__(self, code: RuntimeErrorCode):
        super().__init__(code.value)
        self.code = code


class DispatchPermitRejected(RuntimeError):
    """The provider was not invoked because the single-use fence was stale."""


class ProviderDispatchError(RuntimeError):
    """The provider was invoked and then raised; transport is therefore ambiguous."""

    def __init__(self, cause: Exception):
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.cause = cause
