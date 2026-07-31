from dataclasses import dataclass, field, replace
from pathlib import Path

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.verification import VerifierLadder


@dataclass
class RecordingExecutor:
    backend: str = "portable-web"
    contracts: list[ActionContract] = field(default_factory=list)

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        self.contracts.append(contract)
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": True},
        )


def _contract(*, action: str = "click") -> ActionContract:
    return ActionContract(
        id="contract-save",
        intent="save settings",
        affordance_id="save",
        action=action,
        backend="portable-web",
        environment_revision="environment-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        target_fingerprint="fingerprint-1",
        locator={"backend_handle": "opaque-save"},
        verifier_plan=[VerifierSpec("observation_metadata", "saved", True)],
    )


def _observation(*, saved: bool = False) -> Observation:
    return Observation(
        environment_revision="environment-1",
        snapshot_id="snapshot-1",
        page_revision="page-1",
        target_fingerprints={"save": "fingerprint-1"},
        metadata={"saved": saved},
    )


def _loop(tmp_path: Path | None = None) -> ContractExecutionLoop:
    return ContractExecutionLoop(
        executor=RecordingExecutor(),
        verifier=VerifierLadder(),
        gate=CapabilityGate(),
        task_policy=TaskConstraintPolicy(),
        artifacts=ArtifactStore(tmp_path / "artifacts") if tmp_path is not None else None,
    )


def test_contract_stages_bind_execute_and_verify_without_owning_run_state(tmp_path: Path) -> None:
    loop = _loop(tmp_path)
    envelope = RunRequest("run-contract", "save settings")
    bound = loop.bind_contract(_contract(), envelope, _observation())

    check = loop.initial_check(
        bound,
        envelope,
        _observation(),
        capability_gate_enabled=True,
        preflight_enabled=True,
    )
    receipt = loop.execute(bound, _observation())
    report = loop.verify(
        bound,
        receipt,
        _observation(saved=True),
        structural_verification_enabled=True,
        disabled_reason="",
    )

    assert bound.run_id == "run-contract"
    assert bound.snapshot_id == "snapshot-1"
    assert check.error is None
    assert report.passed
    assert isinstance(loop.executor, RecordingExecutor)
    assert loop.executor.contracts == [bound]


def test_contract_loop_records_canonical_execution_attempt_and_action_outcome() -> None:
    loop = _loop()
    contract = _contract()
    pre_observation = _observation()

    attempt = loop.build_execution_attempt(
        contract,
        pre_observation,
        issued_at_state_version=3,
        active_step_id="step:save",
    )
    receipt = loop.execute(contract, pre_observation)
    report = loop.verify(
        contract,
        receipt,
        _observation(saved=True),
        structural_verification_enabled=True,
        disabled_reason="",
    )
    outcome = loop.record_action_outcome(
        attempt=attempt,
        receipt=receipt,
        verification=report,
        post_observation=_observation(saved=True),
        step_id="step:save",
    )

    assert isinstance(loop.executor, RecordingExecutor)
    assert loop.executor.contracts == [contract]
    assert attempt.contract_id == contract.id
    assert attempt.contract_hash == contract.contract_hash
    assert attempt.pre_observation.snapshot_id == contract.snapshot_id
    assert attempt.active_step_id == "step:save"
    assert receipt.contract_id == contract.id
    assert outcome.attempt == attempt
    assert outcome.receipt_contract_id == contract.id
    assert outcome.receipt_success is True
    assert outcome.verification.contract_id == contract.id
    assert outcome.verification.evidence_refs
    assert outcome.status.value == "verified_effect"


def test_contract_loop_default_execution_does_not_expose_attribution_sidecar() -> None:
    loop = _loop()

    assert not hasattr(loop, "bind_action_execution")


def test_policy_capability_and_freshness_fail_closed_before_execution() -> None:
    loop = _loop()
    protected = replace(
        _contract(),
        required_capabilities=["settings.write"],
        idempotency_key="settings-save-v1",
        contract_hash="",
    )

    denied_policy = loop.initial_check(
        protected,
        RunRequest("run-contract", "save settings", constraints={"read_only": True}),
        _observation(),
        capability_gate_enabled=True,
        preflight_enabled=True,
    )
    denied_capability = loop.initial_check(
        protected,
        RunRequest("run-contract", "save settings"),
        _observation(),
        capability_gate_enabled=True,
        preflight_enabled=True,
    )
    stale = loop.revalidate(
        _contract(),
        RunRequest("run-contract", "save settings"),
        replace(_observation(), page_revision="page-2"),
        CapabilityGate(),
        capability_gate_enabled=False,
        include_policy=False,
    )

    assert denied_policy.error == RuntimeErrorCode.POLICY_DENIED
    assert denied_capability.error == RuntimeErrorCode.CAPABILITY_DENIED
    assert stale == RuntimeErrorCode.STALE_PAGE_REVISION
    assert isinstance(loop.executor, RecordingExecutor)
    assert loop.executor.contracts == []


def test_download_binding_is_artifact_scoped_and_disabled_verification_is_explicit(tmp_path: Path) -> None:
    loop = _loop(tmp_path)
    envelope = RunRequest("download-run", "download report")
    bound = loop.bind_contract(_contract(action="download"), envelope, _observation())
    receipt = loop.execute(bound, _observation())
    report = loop.verify(
        bound,
        receipt,
        _observation(),
        structural_verification_enabled=False,
        disabled_reason="disabled by explicit test profile",
    )

    assert bound.parameters["destination_dir"].endswith("download-run/downloads")
    assert report.passed
    assert report.reason == "disabled by explicit test profile"
