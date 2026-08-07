from __future__ import annotations

from dataclasses import replace

import pytest
from test_coordinator import (
    CountingExecutor,
    FakeObserver,
    SingleStageTaskPlanner,
    _metadata_builder,
    _semantic_envelope,
)

from affordance_runtime.composition import (
    UnsafeProductRuntimeConfiguration,
    compose_run_coordinator,
)
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, Observation, RiskLevel, RuntimeErrorCode
from affordance_runtime.coordinator import RuntimeFeatures
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer
from affordance_runtime.verification.mechanical import VerifierLadder


class _NeverCalled:
    backend = "never"

    def capture(self):
        raise AssertionError("composition containment must fail before capture")

    def execute(self, contract, observation):
        raise AssertionError("composition containment must fail before execute")


@pytest.mark.parametrize(
    "features",
    (
        RuntimeFeatures(preflight=False),
        RuntimeFeatures(structural_verification=False),
        RuntimeFeatures(capability_gate=False),
    ),
)
def test_product_composition_rejects_safety_off_profiles(features: RuntimeFeatures) -> None:
    edge = _NeverCalled()
    with pytest.raises(UnsafeProductRuntimeConfiguration, match="mandatory safety gates"):
        compose_run_coordinator(edge, edge, features=features)


def test_required_capability_never_synthesizes_a_grant_when_gate_is_disabled() -> None:
    loop = ContractExecutionLoop(
        executor=_NeverCalled(),
        verifier=VerifierLadder(),
        gate=CapabilityGate(),
        task_policy=TaskConstraintPolicy(),
    )
    contract = ActionContract(
        id="contract:containment",
        intent="write",
        affordance_id="target",
        action="click",
        backend="dom",
        environment_revision="env-1",
        locator={"selector": "#target"},
        required_capabilities=["settings.write"],
    )
    observation = Observation(
        environment_revision="env-1",
        snapshot_id="epoch-1",
        page_revision="page-1",
    )

    class _Envelope:
        capabilities = []
        constraints = {}
        task_spec = None

    assert not loop.effective_gate(_Envelope()).granted_capabilities
    check = loop.initial_check(
        contract,
        _Envelope(),
        observation,
        capability_gate_enabled=False,
        preflight_enabled=True,
    )
    assert check.error == RuntimeErrorCode.CAPABILITY_DENIED


def test_contract_id_alone_is_never_an_approval_bypass() -> None:
    gate = CapabilityGate()
    contract = ActionContract(
        id="contract:approval-bypass",
        intent="send",
        affordance_id="send",
        action="click",
        backend="dom",
        environment_revision="env-1",
        locator={"selector": "#send"},
        risk=RiskLevel.HIGH,
    )

    assert not hasattr(gate, "approved_contract_ids")
    assert gate.check(contract) == RuntimeErrorCode.APPROVAL_REQUIRED


class _StaleContractBuilder(ActionTransactionMaterializer):
    def build(self, *args, **kwargs):
        contract = super().build(*args, **kwargs)
        return replace(contract, page_revision="page:stale", contract_hash="")


class _InvalidContractBuilder(ActionTransactionMaterializer):
    def build(self, *args, **kwargs):
        del args, kwargs
        raise ValueError("contract was not committed")


def _configured_builder(builder_type):
    configured = _metadata_builder("saved")
    return builder_type(requirements=configured.requirements)


def test_product_stale_contract_never_calls_executor() -> None:
    executor = CountingExecutor()
    result = compose_run_coordinator(
        observer=FakeObserver(),
        executor=executor,
        contract_builder=_configured_builder(_StaleContractBuilder),
        task_planner=SingleStageTaskPlanner(),
        features=RuntimeFeatures(recovery=False),
    ).run_sync(_semantic_envelope("c0-stale-contract"))

    assert result.status != RuntimeStep.DONE
    assert executor.calls == 0
    assert any(
        node.payload.get("error_code") == RuntimeErrorCode.STALE_PAGE_REVISION.value
        for node in result.trace.nodes
    )


def test_product_missing_capability_never_calls_executor() -> None:
    executor = CountingExecutor()
    envelope = replace(_semantic_envelope("c0-missing-capability"), capabilities=[])
    result = compose_run_coordinator(
        observer=FakeObserver(),
        executor=executor,
        contract_builder=_metadata_builder("saved"),
        task_planner=SingleStageTaskPlanner(),
        features=RuntimeFeatures(recovery=False),
    ).run_sync(envelope)

    assert result.status != RuntimeStep.DONE
    assert executor.calls == 0
    assert any(
        node.payload.get("error_code") == RuntimeErrorCode.CAPABILITY_DENIED.value
        for node in result.trace.nodes
    )


def test_product_uncommitted_contract_never_calls_executor() -> None:
    executor = CountingExecutor()
    result = compose_run_coordinator(
        observer=FakeObserver(),
        executor=executor,
        contract_builder=_configured_builder(_InvalidContractBuilder),
        task_planner=SingleStageTaskPlanner(),
        features=RuntimeFeatures(recovery=False),
    ).run_sync(_semantic_envelope("c0-invalid-contract"))

    assert result.status != RuntimeStep.DONE
    assert executor.calls == 0
    assert any(
        node.payload.get("error_code") == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value
        for node in result.trace.nodes
    )
