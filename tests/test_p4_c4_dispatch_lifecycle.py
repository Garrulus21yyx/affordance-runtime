from __future__ import annotations

from dataclasses import replace
from threading import Event, RLock, Thread
from time import time

import pytest

from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProviderAck,
    RuntimeErrorCode,
    TransportState,
)
from affordance_runtime.dispatch_lifecycle import (
    DispatchAdmissionRejected,
    DispatchPermitRejected,
    FinalDispatchAdmission,
    PreparedDispatch,
)
from affordance_runtime.execution_context import (
    CoordinateBinding,
    ExecutionContextRequirementRef,
    ExecutorCapabilityDescriptor,
    RouteBinding,
    RunProvenanceManifest,
    deterministic_application_payload,
    digest_payload,
    issue_surface_binding,
)
from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.runtime_evidence import effect_settlement_status
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.simplified_runtime_contracts import (
    CollateralSettlementStatus,
    EffectSettlement,
    EffectSettlementStatus,
    ExecutionAttempt,
    ObservationIdentity,
)
from affordance_runtime.stage_protocol import RuntimeEvent
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
    VerifierLadder,
)


def _descriptor(schema: str = "schema:1") -> ExecutorCapabilityDescriptor:
    return ExecutorCapabilityDescriptor(
        "provider:test",
        digest_payload(schema),
        "adapter:test",
        "v1",
        ("dom",),
        ("activate",),
        ("activate",),
    )


def _contract(descriptor: ExecutorCapabilityDescriptor) -> tuple[ActionContract, Observation]:
    now = time()
    requirement = ExecutionContextRequirementRef(
        "context:task", "account:alice", "profile:work", "tenant:acme"
    )
    surface = issue_surface_binding(
        requirement,
        run_id="task:1",
        session_generation="session:1",
        window_id="window:1",
        tab_id="tab:1",
        frame_id="frame:top",
        document_generation="document:1",
        focus_generation="focus:1",
        issued_at_s=now,
    )
    coordinate = CoordinateBinding(
        "screenshot:1",
        1280,
        720,
        (0.0, 0.0, 1280.0, 720.0),
        (0.0, 0.0),
        1.0,
        1.0,
        1.0,
        "landscape",
        "viewport-top-left",
        "frame:top",
        "document:1",
    )
    manifest = RunProvenanceManifest(*(digest_payload(str(index)) for index in range(9)))
    payload = deterministic_application_payload(
        action="activate", target_id="candidate:save", destination_id="", named_parameters={}
    )
    route = RouteBinding(
        "dom",
        descriptor.provider_id,
        descriptor.tool_schema_digest,
        descriptor.adapter_id,
        descriptor.adapter_version,
        "dom:canonical-action-encoder",
        "p4-c3@v1",
        digest_payload("policy:1"),
        "activate",
        "candidate:save",
        "",
        digest_payload({"selector": "#save"}),
        "",
        (),
        {},
        payload,
        digest_payload(payload),
        digest_payload("observation:1"),
        surface.digest,
        coordinate.transform_digest,
        manifest.digest,
    )
    contract = ActionContract(
        id="contract:save",
        intent="save",
        affordance_id="target:save",
        action="activate",
        backend="dom",
        environment_revision="env:1",
        locator={"selector": "#save"},
        run_id="task:1",
        snapshot_id="epoch:1",
        page_revision="page:1",
        route_binding=route,
        live_surface_binding=surface,
        coordinate_binding=coordinate,
        provenance_manifest=manifest,
    )
    return contract, Observation("env:1", snapshot_id="epoch:1", page_revision="page:1")


def _attempt(contract: ActionContract, version: int) -> ExecutionAttempt:
    return ExecutionAttempt(
        "attempt:1",
        contract.id,
        contract.contract_hash,
        version,
        contract.action,
        contract.affordance_id,
        ObservationIdentity("epoch:1", "page:1", "env:1"),
    )


def _admission(state: StateKernel, gate: CapabilityGate):
    if state.phase == "created":
        state.phase = "preflight"
    contract, observation = _contract(gate.executor_descriptor)  # type: ignore[arg-type]
    return FinalDispatchAdmission.issue(
        contract=contract,
        observation=observation,
        expected_state_version=state.version,
        gate=gate,
        policy_check=lambda: None,
        surface_check=lambda: True,
    ), _attempt(contract, state.version)


def _admit(committer, state, trace, parent, admission, attempt, *ignored):
    del ignored
    prepared = PreparedDispatch(
        contract=admission.contract,
        observation=admission.observation,
        attempt=attempt,
        admission=admission,
        expected_state_version=admission.expected_state_version,
    )
    return committer.admit_dispatch(state, trace, parent, prepared)


def test_attempt_and_dispatch_intent_are_visible_before_executor() -> None:
    state = StateKernel("task:1", "save")
    state.phase = "preflight"
    descriptor = _descriptor()
    gate = CapabilityGate(executor_descriptor=descriptor, product_allowed_actions=frozenset({"activate"}))
    admission, attempt = _admission(state, gate)
    trace = TraceDag("task:1")
    parent = trace.add("root", {})
    pre_events = tuple(
        RuntimeEvent(kind, {"contract_id": admission.contract.id})
        for kind in (
            "ContractBuilt",
            "RouteSelected",
            "PreflightPassed",
            "ExecutionAttemptIssued",
        )
    )
    permit, _parent = _admit(RuntimeCommitter(),
        state, trace, parent, admission, attempt, pre_events
    )

    class _Executor:
        def execute(self, contract, observation):
            assert state.phase == "acting"
            assert state.current_contract == contract
            assert state.current_execution_attempt == attempt
            kinds = [node.kind for node in trace.nodes]
            assert kinds[1:] == [
                "ContractBuilt",
                "RouteSelected",
                "CommittedObservationPreflightChecked",
                "PreflightPassed",
                "ExecutionAttemptIssued",
                "ExecutionAttemptCommitted",
                "DispatchIntentCommitted",
            ]
            assert kinds.index("ContractBuilt") < kinds.index("RouteSelected")
            assert kinds.index("RouteSelected") < kinds.index("PreflightPassed")
            assert kinds.index("PreflightPassed") < kinds.index("ExecutionAttemptCommitted")
            assert kinds.index("ExecutionAttemptCommitted") < kinds.index("DispatchIntentCommitted")
            return ExecutionReceipt(
                contract.id,
                contract.backend,
                True,
                observation.environment_revision,
                observation.environment_revision,
                1.0,
                transport_state=TransportState.SENT,
                provider_ack=ProviderAck.ACKNOWLEDGED,
            )

    loop = ContractExecutionLoop(_Executor(), VerifierLadder(), gate, TaskConstraintPolicy())
    receipt = loop.dispatch(permit)
    assert receipt.transport_state == TransportState.SENT
    replay = loop.dispatch(permit)
    assert replay.transport_state == TransportState.NOT_SENT
    assert replay.provider_ack == ProviderAck.NOT_APPLICABLE


def test_schema_revocation_and_state_cas_fail_before_executor() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    gate.executor_descriptor = _descriptor("schema:revoked")
    trace = TraceDag("task:1")
    parent = trace.add("root", {})
    with pytest.raises(DispatchAdmissionRejected):
        _admit(RuntimeCommitter(), state, trace, parent, admission, attempt)
    assert state.current_execution_attempt is None

    gate.executor_descriptor = _descriptor()
    admission, attempt = _admission(state, gate)
    state.version += 1
    with pytest.raises(DispatchAdmissionRejected):
        _admit(RuntimeCommitter(), state, trace, parent, admission, attempt)
    assert state.current_execution_attempt is None


def test_policy_drift_is_rechecked_at_linearization_before_permit() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    live_policy = {"denied": True}
    admission = replace(
        admission,
        policy_check=lambda: (
            RuntimeErrorCode.POLICY_DENIED if live_policy["denied"] else None
        ),
    )
    trace = TraceDag("task:1")
    parent = trace.add("root", {})

    with pytest.raises(DispatchAdmissionRejected) as rejected:
        _admit(RuntimeCommitter(), state, trace, parent, admission, attempt)
    assert rejected.value.code == RuntimeErrorCode.POLICY_DENIED
    assert state.current_execution_attempt is None
    assert not any(node.kind == "DispatchIntentCommitted" for node in trace.nodes)

    live_policy["denied"] = False
    permit, _ = _admit(RuntimeCommitter(), state, trace, parent, admission, attempt)
    assert permit.attempt == attempt


def test_live_coordinate_transform_drift_is_rejected_at_final_admission() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    admission = replace(admission, coordinate_check=lambda _binding: False)
    trace = TraceDag("task:1")
    parent = trace.add("root", {})

    with pytest.raises(DispatchAdmissionRejected) as exc_info:
        _admit(RuntimeCommitter(), state, trace, parent, admission, attempt)

    assert exc_info.value.code == RuntimeErrorCode.STALE_OBSERVATION
    assert state.current_execution_attempt is None
    assert not any(node.kind == "DispatchIntentCommitted" for node in trace.nodes)


def test_concurrent_consumers_receive_only_one_permit() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    trace = TraceDag("task:1")
    parent = trace.add("root", {})
    outcomes: list[str] = []

    def consume() -> None:
        try:
            _admit(RuntimeCommitter(), state, trace, parent, admission, attempt)
            outcomes.append("permit")
        except DispatchAdmissionRejected:
            outcomes.append("rejected")

    threads = [Thread(target=consume), Thread(target=consume)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["permit", "rejected"]


def test_transport_ack_is_not_business_effect_settlement() -> None:
    receipt = ExecutionReceipt(
        "contract:1",
        "dom",
        True,
        "env:1",
        "env:2",
        1.0,
        transport_state=TransportState.SENT,
        provider_ack=ProviderAck.ACKNOWLEDGED,
    )
    assert receipt.success
    with pytest.raises(ValueError, match="post-action evidence"):
        EffectSettlement(
            "attempt:1",
            EffectSettlementStatus.OCCURRED,
            (),
            CollateralSettlementStatus.UNRESOLVED,
        )
    settlement = EffectSettlement(
        "attempt:1",
        EffectSettlementStatus.STILL_UNCERTAIN,
        (),
        CollateralSettlementStatus.UNRESOLVED,
    )
    assert settlement.status == EffectSettlementStatus.STILL_UNCERTAIN


def test_receipt_only_verification_cannot_prove_business_effect() -> None:
    contract, _observation = _contract(_descriptor())
    attempt = _attempt(contract, 0)
    report = VerificationReport(
        VerificationStatus.PASSED,
        [
            VerificationEvidence(
                "evidence",
                "provider_ack",
                True,
                "execution_receipt",
                evidence_id="receipt:ack",
                strength="weak",
            )
        ],
    )
    assert effect_settlement_status(report, contract, attempt) == EffectSettlementStatus.STILL_UNCERTAIN


def test_capability_revocation_before_linearization_issues_no_permit() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(
        granted_capabilities={"settings.write"},
        product_allowed_capabilities=frozenset({"settings.write"}),
        executor_descriptor=_descriptor(),
    )
    admission, attempt = _admission(state, gate)
    contract = replace(
        admission.contract,
        required_capabilities=["settings.write"],
        transaction_seal="",
        contract_hash="",
    )
    admission = FinalDispatchAdmission.issue(
        contract=contract,
        observation=admission.observation,
        expected_state_version=state.version,
        gate=gate,
        policy_check=lambda: None,
        surface_check=lambda: True,
    )
    attempt = replace(attempt, contract_hash=contract.contract_hash)
    gate.granted_capabilities.clear()
    trace = TraceDag("task:1")
    with pytest.raises(DispatchAdmissionRejected):
        _admit(RuntimeCommitter(), state, trace, trace.add("root", {}), admission, attempt)
    assert state.current_execution_attempt is None
    assert not any(node.kind == "DispatchIntentCommitted" for node in trace.nodes)


def test_root_grant_revocation_invalidates_run_scoped_gate_before_linearization() -> None:
    state = StateKernel("task:1", "save")
    descriptor = _descriptor()
    root = CapabilityGate(
        granted_capabilities={"settings.write"},
        product_allowed_capabilities=frozenset({"settings.write"}),
        executor_descriptor=descriptor,
    )
    run_gate = CapabilityGate(
        granted_capabilities=set(),
        product_allowed_capabilities=root.product_allowed_capabilities,
        executor_descriptor=descriptor,
        grant_source=root,
        _linearization_lock=root._linearization_lock,
    )
    admission, attempt = _admission(state, run_gate)
    contract = replace(
        admission.contract,
        required_capabilities=["settings.write"],
        transaction_seal="",
        contract_hash="",
    )
    admission = FinalDispatchAdmission.issue(
        contract=contract,
        observation=admission.observation,
        expected_state_version=state.version,
        gate=run_gate,
        policy_check=lambda: None,
        surface_check=lambda: True,
    )
    attempt = replace(attempt, contract_hash=contract.contract_hash)
    root.granted_capabilities.clear()
    trace = TraceDag("task:1")

    with pytest.raises(DispatchAdmissionRejected) as rejected:
        _admit(RuntimeCommitter(),
            state, trace, trace.add("root", {}), admission, attempt
        )
    assert rejected.value.code == RuntimeErrorCode.CAPABILITY_DENIED
    assert state.current_execution_attempt is None
    assert not any(node.kind == "DispatchIntentCommitted" for node in trace.nodes)


def test_grant_revocation_cannot_linearize_between_authorize_and_intent_commit() -> None:
    authorized = Event()
    resume = Event()
    revoked = Event()

    class _HookGate(CapabilityGate):
        def authorize(self, contract):
            result = super().authorize(contract)
            authorized.set()
            assert resume.wait(timeout=2)
            return result

    state = StateKernel("task:1", "save")
    descriptor = replace(
        _descriptor(),
        provider_capabilities=("settings.write",),
        adapter_capabilities=("settings.write",),
    )
    gate = _HookGate(
        granted_capabilities={"settings.write"},
        product_allowed_capabilities=frozenset({"settings.write"}),
        executor_descriptor=descriptor,
    )
    admission, attempt = _admission(state, gate)
    contract = replace(
        admission.contract,
        required_capabilities=["settings.write"],
        transaction_seal="",
        contract_hash="",
    )
    admission = FinalDispatchAdmission.issue(
        contract=contract,
        observation=admission.observation,
        expected_state_version=state.version,
        gate=gate,
        policy_check=lambda: None,
        surface_check=lambda: True,
    )
    attempt = replace(attempt, contract_hash=contract.contract_hash)
    trace = TraceDag("task:1")
    result: list[object] = []
    commit_thread = Thread(
        target=lambda: result.append(
            _admit(RuntimeCommitter(),
                state, trace, trace.add("root", {}), admission, attempt
            )
        )
    )
    commit_thread.start()
    assert authorized.wait(timeout=2)

    def revoke() -> None:
        gate.granted_capabilities -= {"settings.write"}
        revoked.set()

    revoke_thread = Thread(target=revoke)
    revoke_thread.start()
    assert not revoked.wait(timeout=0.05)
    resume.set()
    commit_thread.join(timeout=2)
    revoke_thread.join(timeout=2)
    assert len(result) == 1
    assert revoked.is_set()
    assert any(node.kind == "DispatchIntentCommitted" for node in trace.nodes)


def test_surface_drift_after_permit_issue_blocks_executor_call() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    current = {"matches": True}
    admission, attempt = _admission(state, gate)
    admission = replace(admission, surface_check=lambda: current["matches"])
    trace = TraceDag("task:1")
    permit, _ = _admit(RuntimeCommitter(),
        state, trace, trace.add("root", {}), admission, attempt
    )
    current["matches"] = False

    class _RecordingExecutor:
        calls = 0

        def execute(self, contract, observation):
            self.calls += 1
            raise AssertionError("stale surface must not reach executor")

    executor = _RecordingExecutor()
    receipt = ContractExecutionLoop(
        executor, VerifierLadder(), gate, TaskConstraintPolicy()
    ).dispatch(permit)
    assert receipt.transport_state == TransportState.NOT_SENT
    assert executor.calls == 0


def test_surface_owner_lock_closes_check_to_executor_gap() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    fence = RLock()
    current = {"matches": True}
    checks = {"count": 0}
    checked = Event()
    release_check = Event()
    mutated = Event()
    admission, attempt = _admission(state, gate)

    def surface_check() -> bool:
        checks["count"] += 1
        if checks["count"] == 1:
            return current["matches"]
        checked.set()
        assert release_check.wait(timeout=2)
        return current["matches"]

    admission = replace(admission, surface_check=surface_check, fence_lock=fence)
    trace = TraceDag("task:1")
    permit, _ = _admit(RuntimeCommitter(),
        state, trace, trace.add("root", {}), admission, attempt
    )

    class _RecordingExecutor:
        calls = 0

        def execute(self, contract, observation):
            self.calls += 1
            assert not mutated.is_set()
            return ExecutionReceipt(
                contract.id,
                contract.backend,
                True,
                observation.environment_revision,
                observation.environment_revision,
                0.0,
            )

    executor = _RecordingExecutor()
    receipts: list[ExecutionReceipt] = []
    dispatch_thread = Thread(
        target=lambda: receipts.append(
            ContractExecutionLoop(
                executor, VerifierLadder(), gate, TaskConstraintPolicy()
            ).dispatch(permit)
        )
    )
    dispatch_thread.start()
    assert checked.wait(timeout=2)

    def mutate_surface() -> None:
        with fence:
            current["matches"] = False
            mutated.set()

    mutation_thread = Thread(target=mutate_surface)
    mutation_thread.start()
    assert not mutated.wait(timeout=0.05)
    release_check.set()
    dispatch_thread.join(timeout=2)
    mutation_thread.join(timeout=2)
    assert executor.calls == 1
    assert receipts[0].transport_state == TransportState.SENT
    assert mutated.is_set()


def test_attempt_identity_mismatch_is_rejected_before_admission_consumption() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    trace = TraceDag("task:1")
    with pytest.raises(ValueError, match="prepared dispatch attempt"):
        _admit(RuntimeCommitter(),
            state,
            trace,
            trace.add("root", {}),
            admission,
            replace(attempt, contract_hash=digest_payload("wrong")),
        )
    assert admission.consume_if_current(state_version=state.version) is None


@pytest.mark.parametrize("failure", (TimeoutError("timeout"), ConnectionResetError("reset"), ValueError("schema")))
def test_executor_failures_default_to_sent_unknown(failure: Exception) -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    trace = TraceDag("task:1")
    permit, _ = _admit(RuntimeCommitter(), state, trace, trace.add("root", {}), admission, attempt)

    class _FailingExecutor:
        def execute(self, contract, observation):
            raise failure

    receipt = ContractExecutionLoop(
        _FailingExecutor(), VerifierLadder(), gate, TaskConstraintPolicy()
    ).dispatch(permit)
    assert receipt.transport_state == TransportState.SENT_UNKNOWN
    assert receipt.provider_ack == ProviderAck.UNKNOWN


def test_provider_exception_named_like_fence_rejection_is_still_sent_unknown() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    trace = TraceDag("task:1")
    permit, _ = _admit(RuntimeCommitter(),
        state, trace, trace.add("root", {}), admission, attempt
    )

    class _Executor:
        calls = 0

        def execute(self, contract, observation):
            self.calls += 1
            raise DispatchPermitRejected("provider collision after invocation")

    executor = _Executor()
    receipt = ContractExecutionLoop(
        executor, VerifierLadder(), gate, TaskConstraintPolicy()
    ).dispatch(permit)
    assert executor.calls == 1
    assert receipt.transport_state == TransportState.SENT_UNKNOWN
    assert receipt.provider_ack == ProviderAck.UNKNOWN
    assert not receipt.success


def test_wrong_surface_fence_cannot_construct_a_dispatch_permit() -> None:
    state = StateKernel("task:1", "save")
    gate = CapabilityGate(executor_descriptor=_descriptor())
    admission, attempt = _admission(state, gate)
    trace = TraceDag("task:1")
    permit, _ = _admit(RuntimeCommitter(), state, trace, trace.add("root", {}), admission, attempt)
    with pytest.raises(ValueError, match="fence mismatch"):
        replace(permit, session_generation="session:other")
