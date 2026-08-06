"""Ordered in-process composition of independent action admission gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.contracts import ActionContract, Observation, RuntimeErrorCode
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.verification.mechanical import preflight


class AdmissionGate(StrEnum):
    TASK_AUTHORITY = "task_authority"
    CAPABILITY = "capability"
    APPROVAL = "approval"
    FRESHNESS_PREFLIGHT = "freshness_preflight"


@dataclass(frozen=True)
class AdmissionPolicyResult:
    gate: AdmissionGate
    allowed: bool
    error: RuntimeErrorCode | None = None


@dataclass(frozen=True)
class ActionAdmissionResult:
    allowed: bool
    policy_results: tuple[AdmissionPolicyResult, ...]

    @property
    def error(self) -> RuntimeErrorCode | None:
        return next((item.error for item in self.policy_results if not item.allowed), None)


@dataclass(frozen=True)
class ActionAdmissionService:
    task_policy: TaskConstraintPolicy

    def evaluate(
        self,
        contract: ActionContract,
        *,
        constraints: dict[str, object],
        capability_gate: CapabilityGate,
        observation: Observation,
        task_spec: TaskSpec | None = None,
        check_freshness: bool = True,
    ) -> ActionAdmissionResult:
        results: list[AdmissionPolicyResult] = []
        task_error = self.task_policy.check(contract, constraints, task_spec)
        results.append(AdmissionPolicyResult(AdmissionGate.TASK_AUTHORITY, task_error is None, task_error))
        if task_error is not None:
            return ActionAdmissionResult(False, tuple(results))

        missing = [
            value for value in contract.required_capabilities if value not in capability_gate.granted_capabilities
        ]
        capability_error = RuntimeErrorCode.CAPABILITY_DENIED if missing else None
        results.append(AdmissionPolicyResult(AdmissionGate.CAPABILITY, capability_error is None, capability_error))
        if capability_error is not None:
            return ActionAdmissionResult(False, tuple(results))

        approval_error = capability_gate.check(contract)
        results.append(AdmissionPolicyResult(AdmissionGate.APPROVAL, approval_error is None, approval_error))
        if approval_error is not None:
            return ActionAdmissionResult(False, tuple(results))

        freshness_error = preflight(contract, observation) if check_freshness else None
        results.append(
            AdmissionPolicyResult(
                AdmissionGate.FRESHNESS_PREFLIGHT,
                freshness_error is None,
                freshness_error,
            )
        )
        return ActionAdmissionResult(freshness_error is None, tuple(results))
