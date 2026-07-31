"""Stateless contract execution stages used by the serial Coordinator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.runtime import Executor, RunRequest
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.simplified_runtime_contracts import (
    ActionOutcome,
    ActionOutcomeStatus,
    ExecutionAttempt,
    ObservationIdentity,
    VerificationResult,
)
from affordance_runtime.simplified_runtime_contracts import (
    VerificationStatus as CanonicalVerificationStatus,
)
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
        envelope: RunRequest,
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
        envelope: RunRequest,
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
        envelope: RunRequest,
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

    def build_execution_attempt(
        self,
        contract: ActionContract,
        observation: Observation,
        *,
        issued_at_state_version: int,
        active_step_id: str = "",
    ) -> ExecutionAttempt:
        return ExecutionAttempt(
            attempt_id=_stable_id(
                "attempt",
                {
                    "contract_id": contract.id,
                    "contract_hash": contract.contract_hash,
                    "state_version": issued_at_state_version,
                    "snapshot_id": observation.snapshot_id,
                    "page_revision": observation.page_revision,
                    "environment_revision": observation.environment_revision,
                    "active_step_id": active_step_id,
                },
            ),
            contract_id=contract.id,
            contract_hash=contract.contract_hash,
            issued_at_state_version=issued_at_state_version,
            action_kind=contract.action,
            semantic_target_id=contract.affordance_id,
            pre_observation=_observation_identity(observation),
            active_step_id=active_step_id,
        )

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

    def record_action_outcome(
        self,
        *,
        attempt: ExecutionAttempt,
        receipt: ExecutionReceipt,
        verification: VerificationReport,
        post_observation: Observation,
        step_id: str,
    ) -> ActionOutcome:
        canonical_verification = _canonical_verification_result(
            attempt=attempt,
            verification=verification,
            post_observation=post_observation,
        )
        return ActionOutcome(
            outcome_id=_stable_id(
                "outcome",
                {
                    "attempt_id": attempt.attempt_id,
                    "receipt_contract_id": receipt.contract_id,
                    "receipt_success": receipt.success,
                    "verification_status": verification.status.value,
                    "post_snapshot_id": post_observation.snapshot_id,
                    "post_page_revision": post_observation.page_revision,
                    "post_environment_revision": post_observation.environment_revision,
                    "step_id": step_id,
                },
            ),
            attempt=attempt,
            verification=canonical_verification,
            status=_canonical_outcome_status(receipt=receipt, verification=verification),
            step_id=step_id,
            receipt_contract_id=receipt.contract_id,
            receipt_success=receipt.success,
            receipt_backend=receipt.backend,
            receipt_error_code=receipt.error_code.value if receipt.error_code is not None else "",
            receipt_evidence_refs=_receipt_evidence_refs(receipt),
        )

    def effective_gate(self, envelope: RunRequest) -> CapabilityGate:
        return CapabilityGate(
            granted_capabilities=self.gate.granted_capabilities | set(envelope.capabilities),
            approval_required_risks=set(self.gate.approval_required_risks),
            approval_required_capabilities=self.gate.approval_required_capabilities
            | set(str(item) for item in envelope.constraints.get("require_approval_for", [])),
            approval_tokens=self.gate.approval_tokens,
            approved_contract_ids=set(self.gate.approved_contract_ids),
        )


def _observation_identity(observation: Observation) -> ObservationIdentity:
    return ObservationIdentity(
        snapshot_id=observation.snapshot_id,
        page_revision=observation.page_revision,
        environment_revision=observation.environment_revision,
    )


def _canonical_verification_result(
    *,
    attempt: ExecutionAttempt,
    verification: VerificationReport,
    post_observation: Observation,
) -> VerificationResult:
    return VerificationResult(
        status=_canonical_verification_status(verification.status),
        contract_id=attempt.contract_id,
        contract_hash=attempt.contract_hash,
        pre_snapshot_id=attempt.pre_observation.snapshot_id,
        post_observation=_observation_identity(post_observation),
        verified_criterion_ids=_verified_criterion_ids(verification),
        evidence_refs=_verification_evidence_refs(verification),
    )


def _canonical_verification_status(status: VerificationStatus) -> CanonicalVerificationStatus:
    if status == VerificationStatus.PASSED:
        return CanonicalVerificationStatus.PASSED
    if status == VerificationStatus.FAILED:
        return CanonicalVerificationStatus.FAILED
    if status == VerificationStatus.INCONCLUSIVE:
        return CanonicalVerificationStatus.INCONCLUSIVE
    return CanonicalVerificationStatus.FAILED


def _canonical_outcome_status(
    *,
    receipt: ExecutionReceipt,
    verification: VerificationReport,
) -> ActionOutcomeStatus:
    if receipt.error_code in {
        RuntimeErrorCode.STALE_OBSERVATION,
        RuntimeErrorCode.STALE_PAGE_REVISION,
        RuntimeErrorCode.SNAPSHOT_MISMATCH,
        RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
    }:
        return ActionOutcomeStatus.STALE
    if not receipt.success:
        return ActionOutcomeStatus.FAILED
    if verification.status == VerificationStatus.PASSED:
        return ActionOutcomeStatus.VERIFIED_EFFECT
    if verification.status == VerificationStatus.INCONCLUSIVE:
        return ActionOutcomeStatus.RECOVERY_REQUIRED
    return ActionOutcomeStatus.NO_EFFECT


def _verification_evidence_refs(verification: VerificationReport) -> tuple[str, ...]:
    refs: list[str] = []
    for index, evidence in enumerate(verification.evidence):
        refs.append(evidence.evidence_id or evidence.source or f"verification:evidence:{index}")
    if not refs and verification.passed:
        refs.append("verification:structural-disabled")
    return tuple(dict.fromkeys(refs))


def _verified_criterion_ids(verification: VerificationReport) -> tuple[str, ...]:
    ids: list[str] = []
    for evidence in verification.evidence:
        if evidence.passed:
            ids.extend(evidence.criterion_ids)
    return tuple(dict.fromkeys(ids))


def _receipt_evidence_refs(receipt: ExecutionReceipt) -> tuple[str, ...]:
    refs = receipt.evidence.get("artifact_refs") if hasattr(receipt.evidence, "get") else ()
    if isinstance(refs, tuple):
        return tuple(str(item) for item in refs if str(item))
    if isinstance(refs, list):
        return tuple(str(item) for item in refs if str(item))
    return ()


def _stable_id(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}:sha256:{hashlib.sha256(encoded).hexdigest()}"
