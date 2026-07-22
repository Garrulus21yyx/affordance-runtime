"""Stateless contract execution stages used by the serial Coordinator."""

from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.runtime import Executor, TaskEnvelope
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.verification import VerificationReport, VerificationStatus, VerifierLadder, preflight


@dataclass(frozen=True)
class ContractCheck:
    """One policy/capability/preflight decision with its run-scoped gate."""

    gate: CapabilityGate
    error: RuntimeErrorCode | None


@dataclass(frozen=True)
class ContractExecutionLoop:
    """Run pure/delegated contract stages without owning Runtime state."""

    executor: Executor
    verifier: VerifierLadder
    gate: CapabilityGate
    task_policy: TaskConstraintPolicy
    artifacts: ArtifactStore | None = None

    def bind_contract(
        self,
        contract: ActionContract,
        envelope: TaskEnvelope,
        observation: Observation,
    ) -> ActionContract:
        parameters = dict(contract.parameters)
        if contract.action == "download" and self.artifacts is not None:
            parameters.setdefault(
                "destination_dir",
                str(self.artifacts.run_dir(envelope.task_id) / "downloads"),
            )
        return replace(
            contract,
            run_id=envelope.task_id,
            snapshot_id=contract.snapshot_id or observation.snapshot_id,
            page_revision=contract.page_revision or observation.page_revision,
            observed_at_s=contract.observed_at_s or observation.observed_at_s,
            parameters=parameters,
            contract_hash="",
        )

    def initial_check(
        self,
        contract: ActionContract,
        envelope: TaskEnvelope,
        observation: Observation,
        *,
        capability_gate_enabled: bool,
        preflight_enabled: bool,
    ) -> ContractCheck:
        gate = self.effective_gate(envelope)
        error = self.task_policy.check(contract, envelope.constraints)
        if error is None and capability_gate_enabled:
            error = gate.check(contract)
        if error is None and preflight_enabled:
            error = preflight(contract, observation)
        return ContractCheck(gate=gate, error=error)

    def revalidate(
        self,
        contract: ActionContract,
        envelope: TaskEnvelope,
        observation: Observation,
        gate: CapabilityGate,
        *,
        capability_gate_enabled: bool,
        include_policy: bool,
        require_snapshot_identity: bool = True,
        require_environment_revision: bool = True,
    ) -> RuntimeErrorCode | None:
        error = self.task_policy.check(contract, envelope.constraints) if include_policy else None
        if error is None and capability_gate_enabled:
            error = gate.check(contract)
        if error is None:
            error = preflight(
                contract,
                observation,
                require_snapshot_identity=require_snapshot_identity,
                require_environment_revision=require_environment_revision,
            )
        return error

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return self.executor.execute(contract, observation)

    def verify(
        self,
        contract: ActionContract,
        receipt: ExecutionReceipt,
        observation: Observation,
        *,
        structural_verification_enabled: bool,
        disabled_reason: str,
    ) -> VerificationReport:
        if structural_verification_enabled:
            return self.verifier.verify_report(contract.verifier_plan, receipt, observation)
        return VerificationReport(VerificationStatus.PASSED, reason=disabled_reason)

    def effective_gate(self, envelope: TaskEnvelope) -> CapabilityGate:
        return CapabilityGate(
            granted_capabilities=self.gate.granted_capabilities | set(envelope.capabilities),
            approval_required_risks=set(self.gate.approval_required_risks),
            approval_required_capabilities=self.gate.approval_required_capabilities
            | set(str(item) for item in envelope.constraints.get("require_approval_for", [])),
            approval_tokens=self.gate.approval_tokens,
            approved_contract_ids=set(self.gate.approved_contract_ids),
        )
