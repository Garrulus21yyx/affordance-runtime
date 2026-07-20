"""Small executable runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification import VerifierLadder, preflight


class RuntimeStep(StrEnum):
    CREATED = "created"
    OBSERVING = "observing"
    PLANNING = "planning"
    PREFLIGHT = "preflight"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_CLARIFICATION = "waiting_clarification"
    ACTING = "acting"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    DONE = "done"
    FAILED = "failed"
    ABORTED = "aborted"
    # Backwards-compatible names for the original debug API.
    INIT = "created"
    MODELING = "observing"


@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str = ""
    goal: str = ""
    target: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    task_spec: TaskSpec | None = None

    def __post_init__(self) -> None:
        if self.task_spec is None:
            if not self.task_id or not self.goal:
                raise ValueError("legacy TaskEnvelope requires task_id and goal")
            return
        if self.task_id and self.task_id != self.task_spec.task_id:
            raise ValueError("TaskEnvelope task_id does not match TaskSpec")
        if self.goal and self.goal != self.task_spec.objective:
            raise ValueError("TaskEnvelope goal does not match TaskSpec objective")
        object.__setattr__(self, "task_id", self.task_spec.task_id)
        object.__setattr__(self, "goal", self.task_spec.objective)
        if not self.target and self.task_spec.targets:
            object.__setattr__(self, "target", self.task_spec.targets[0])


class Executor(Protocol):
    backend: str

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        ...


@dataclass
class RuntimeResult:
    task_id: str
    status: RuntimeStep
    receipt: ExecutionReceipt | None
    trace: TraceDag
    error_code: RuntimeErrorCode | None = None


@dataclass
class AffordanceRuntime:
    executor: Executor
    verifier: VerifierLadder = field(default_factory=VerifierLadder)
    gate: CapabilityGate = field(default_factory=CapabilityGate)
    task_policy: TaskConstraintPolicy = field(default_factory=TaskConstraintPolicy)

    def run_contract(self, envelope: TaskEnvelope, contract: ActionContract, observation: Observation) -> RuntimeResult:
        state = StateKernel(task_id=envelope.task_id, goal=envelope.goal, constraints=envelope.constraints)
        state.remember_observation(observation)
        trace = TraceDag(run_id=envelope.task_id)
        observation_node = trace.add(
            "ObservationCaptured",
            {
                "state": RuntimeStep.OBSERVING.value,
                "environment_revision": observation.environment_revision,
                "page_revision": observation.page_revision,
                "snapshot_id": observation.snapshot_id,
                "url": observation.url,
                "artifact_refs": observation.artifact_refs,
            },
        )
        contract_node = trace.add(
            "ContractBuilt",
            {
                "state": RuntimeStep.PREFLIGHT.value,
                "id": contract.id,
                "contract_hash": contract.contract_hash,
                "schema_version": contract.schema_version,
                "backend": contract.backend,
            },
            parents=[observation_node.id],
        )

        effective_gate = CapabilityGate(
            granted_capabilities=self.gate.granted_capabilities | set(envelope.capabilities),
            approval_required_risks=set(self.gate.approval_required_risks),
            approval_required_capabilities=self.gate.approval_required_capabilities
            | set(str(item) for item in envelope.constraints.get("require_approval_for", [])),
            approval_tokens=self.gate.approval_tokens,
            approved_contract_ids=set(self.gate.approved_contract_ids),
        )
        error = self.task_policy.check(contract, envelope.constraints) or effective_gate.check(contract) or preflight(contract, observation)
        if error is not None:
            blocked_status = RuntimeStep.WAITING_APPROVAL if error == RuntimeErrorCode.APPROVAL_REQUIRED else RuntimeStep.ABORTED
            trace.add("PreflightBlocked", {"state": blocked_status.value, "error_code": error.value}, parents=[contract_node.id])
            return RuntimeResult(envelope.task_id, blocked_status, None, trace, error)
        authorization_error = effective_gate.authorize(contract)
        if authorization_error is not None:
            trace.add(
                "PreflightBlocked",
                {"state": RuntimeStep.ABORTED.value, "error_code": authorization_error.value},
                parents=[contract_node.id],
            )
            return RuntimeResult(envelope.task_id, RuntimeStep.ABORTED, None, trace, authorization_error)

        receipt = self.executor.execute(contract, observation)
        state.record_receipt(receipt)
        receipt_node = trace.add(
            "ActionCompleted",
            {"state": RuntimeStep.ACTING.value, "success": receipt.success, "backend": receipt.backend},
            parents=[contract_node.id],
        )
        if receipt.contract_id != contract.id:
            trace.add("PostconditionFailed", {"state": RuntimeStep.VERIFYING.value, "passed": False, "reason": "receipt contract mismatch"}, parents=[receipt_node.id])
            return RuntimeResult(envelope.task_id, RuntimeStep.FAILED, receipt, trace, RuntimeErrorCode.EXECUTION_FAILED)
        if not receipt.success:
            trace.add("PostconditionFailed", {"state": RuntimeStep.VERIFYING.value, "passed": False, "reason": "execution failed"}, parents=[receipt_node.id])
            return RuntimeResult(
                envelope.task_id,
                RuntimeStep.FAILED,
                receipt,
                trace,
                receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
            )
        verified = self.verifier.verify(contract.verifier_plan, receipt, observation)
        trace.add(
            "PostconditionPassed" if verified else "PostconditionFailed",
            {"state": RuntimeStep.VERIFYING.value, "passed": verified},
            parents=[receipt_node.id],
        )

        if verified:
            return RuntimeResult(envelope.task_id, RuntimeStep.DONE, receipt, trace)
        return RuntimeResult(envelope.task_id, RuntimeStep.FAILED, receipt, trace, RuntimeErrorCode.VERIFICATION_FAILED)
