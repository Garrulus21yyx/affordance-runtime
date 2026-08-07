import asyncio
from dataclasses import replace
from time import time

import pytest

from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProviderAck,
    RiskLevel,
    TransportState,
)
from affordance_runtime.environment_port import ObservationRequest
from affordance_runtime.execution.batch import ActionBatch, execute_action_batch
from affordance_runtime.testing import LegacyStaticEnvironment


def _action(identity: str, *, backend: str = "dom", action: str = "click") -> ActionContract:
    return ActionContract(
        id=identity,
        intent=identity,
        affordance_id=identity,
        action=action,
        backend=backend,
        environment_revision="rev-1",
        locator={"selector": f"#{identity}"},
        snapshot_id="snap-1",
        page_revision="page-1",
        expires_at_s=time() + 60,
    )


def _receipt(identity: str, *, success: bool = True, uncertain: bool = False) -> ExecutionReceipt:
    return ExecutionReceipt(
        identity,
        "dom",
        success,
        "rev-1",
        "rev-1",
        1,
        transport_state=TransportState.SENT_UNKNOWN if uncertain else TransportState.SENT,
        provider_ack=ProviderAck.UNKNOWN if uncertain else ProviderAck.ACKNOWLEDGED,
    )


def _environment(receipts: list[ExecutionReceipt]) -> LegacyStaticEnvironment:
    return LegacyStaticEnvironment(
        [Observation("rev-1", snapshot_id="snap-1", page_revision="page-1")],
        receipts,
    )


def test_action_batch_executes_at_most_three_low_risk_same_backend_actions() -> None:
    async def scenario() -> None:
        actions = (_action("one"), _action("two"), _action("three"))
        environment = _environment([_receipt(item.id) for item in actions])
        await environment.reset("task")
        await environment.observe(ObservationRequest("batch grounding"))

        result = await execute_action_batch(environment, ActionBatch("batch-1", actions))

        assert result.success
        assert len(result.receipts) == 3
        assert result.requires_reobservation

    asyncio.run(scenario())


def test_action_batch_stops_on_sent_unknown_without_executing_following_actions() -> None:
    async def scenario() -> None:
        actions = (_action("one"), _action("two"))
        environment = _environment([_receipt("one", success=False, uncertain=True), _receipt("two")])
        await environment.reset("task")
        await environment.observe(ObservationRequest("batch grounding"))
        result = await execute_action_batch(environment, ActionBatch("batch-1", actions))

        assert not result.success
        assert result.failed_action_index == 0
        assert len(environment.executed_contracts) == 1

    asyncio.run(scenario())


def test_action_batch_rejects_high_risk_mixed_backend_or_barrier_actions() -> None:
    low = _action("one")
    with pytest.raises(ValueError, match="low-risk"):
        ActionBatch("batch", (replace(low, risk=RiskLevel.MEDIUM, contract_hash=""),))
    with pytest.raises(ValueError, match="one backend"):
        ActionBatch("batch", (low, _action("two", backend="visual")))
    with pytest.raises(ValueError, match="observation barrier"):
        ActionBatch("batch", (_action("navigate", action="navigate"),))
    with pytest.raises(ValueError, match="one to three"):
        ActionBatch("batch", tuple(_action(str(index)) for index in range(4)))
