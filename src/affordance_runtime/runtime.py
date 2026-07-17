"""Small executable runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.safety import CapabilityGate
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification import VerifierLadder, preflight


class RuntimeStep(StrEnum):
    INIT = "init"
    OBSERVING = "observing"
    MODELING = "modeling"
    PLANNING = "planning"
    ACTING = "acting"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    DONE = "done"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str
    goal: str
    target: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)


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

    def run_contract(self, envelope: TaskEnvelope, contract: ActionContract, observation: Observation) -> RuntimeResult:
        state = StateKernel(task_id=envelope.task_id, goal=envelope.goal, constraints=envelope.constraints)
        state.remember_observation(observation)
        trace = TraceDag(run_id=envelope.task_id)
        observation_node = trace.add("observation", {"environment_revision": observation.environment_revision, "url": observation.url})
        contract_node = trace.add("contract", {"id": contract.id, "backend": contract.backend}, parents=[observation_node.id])

        error = self.gate.check(contract) or preflight(contract, observation)
        if error is not None:
            trace.add("blocked", {"error_code": error.value}, parents=[contract_node.id])
            return RuntimeResult(envelope.task_id, RuntimeStep.ABORTED, None, trace, error)

        receipt = self.executor.execute(contract, observation)
        state.record_receipt(receipt)
        receipt_node = trace.add("receipt", {"success": receipt.success, "backend": receipt.backend}, parents=[contract_node.id])
        verified = self.verifier.verify(contract.verifier_plan, receipt, observation)
        trace.add("verification", {"passed": verified}, parents=[receipt_node.id])

        if receipt.success and verified:
            return RuntimeResult(envelope.task_id, RuntimeStep.DONE, receipt, trace)
        return RuntimeResult(envelope.task_id, RuntimeStep.FAILED, receipt, trace, RuntimeErrorCode.VERIFICATION_FAILED)

