import asyncio
from dataclasses import replace
from time import time

import pytest

from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProviderAck,
    TransportState,
)
from affordance_runtime.environment_port import ObservationRequest, contract_is_current
from affordance_runtime.testing import LegacyStaticEnvironment as StaticEnvironment
from affordance_runtime.testing import StaleEnvironmentBinding


def _contract() -> ActionContract:
    return ActionContract(
        id="contract-1",
        intent="turn on lamp",
        affordance_id="lamp-power",
        action="invoke",
        backend="wot",
        environment_revision="rev-1",
        locator={"href": "http://fixture/lamp/on"},
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="fingerprint-1",
        target_fingerprint_key="lamp-power",
        expires_at_s=time() + 60,
    )


def _observation(revision: str = "rev-1", *, snapshot_id: str = "snap-1", power: str = "off") -> Observation:
    return Observation(
        environment_revision=revision,
        snapshot_id=snapshot_id,
        page_revision="page-1",
        target_fingerprints={"lamp-power": "fingerprint-1"},
        metadata={"power": power},
    )


def test_contract_is_current_requires_matching_observation_identity() -> None:
    contract = _contract()

    assert contract_is_current(contract, _observation())
    assert not contract_is_current(contract, _observation(snapshot_id="snap-2"))
    assert not contract_is_current(
        replace(contract, expires_at_s=1, contract_hash=""),
        _observation(),
        now_s=2,
    )


def test_static_environment_models_sent_unknown_then_fresh_changed_state() -> None:
    async def scenario() -> None:
        receipt = ExecutionReceipt(
            contract_id="contract-1",
            backend="wot",
            success=False,
            started_revision="rev-1",
            ended_revision="rev-1",
            latency_ms=10,
            transport_state=TransportState.SENT_UNKNOWN,
            provider_ack=ProviderAck.UNKNOWN,
        )
        environment = StaticEnvironment(
            observations=[_observation(power="off"), _observation(power="on")],
            receipts=[receipt],
        )
        await environment.reset({"goal": "turn on lamp"})
        before = await environment.observe(ObservationRequest("initial grounding"))
        result = await environment.execute(_contract())
        after = await environment.observe(ObservationRequest("verify postcondition"))

        assert before.metadata["power"] == "off"
        assert result.transport_state == TransportState.SENT_UNKNOWN
        assert after.metadata["power"] == "on"
        assert [item.reason for item in environment.observation_requests] == [
            "initial grounding",
            "verify postcondition",
        ]

    asyncio.run(scenario())


def test_static_environment_rejects_stale_execution() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_observation(snapshot_id="snap-2")])
        await environment.reset("task")
        await environment.observe(ObservationRequest("initial grounding"))
        with pytest.raises(StaleEnvironmentBinding):
            await environment.execute(_contract())

    asyncio.run(scenario())


def test_static_environment_requires_reset_and_bounded_sequences() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_observation()], repeat_last_observation=False)
        with pytest.raises(RuntimeError, match="reset"):
            await environment.observe(ObservationRequest("initial grounding"))
        await environment.reset("task")
        await environment.observe(ObservationRequest("initial grounding"))
        with pytest.raises(IndexError, match="exhausted"):
            await environment.observe(ObservationRequest("second observation"))

    asyncio.run(scenario())
