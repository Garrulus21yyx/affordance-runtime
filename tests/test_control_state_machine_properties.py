from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_confirmation_continuation import _decision, _loop, _task, _world

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoopStatus
from affordance_runtime.agent.attempt_receipt import AttemptOperation
from affordance_runtime.benchmarks.target_loop.failure_origin import (
    OBSERVATION_FAILURE_ORIGINS,
    observation_failure_origin,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import ObservationRequestKind


@settings(max_examples=80, deadline=None)
@given(st.lists(st.sampled_from(("run", "confirm", "wrong")), min_size=1, max_size=16))
def test_generated_confirmation_sequences_preserve_control_invariants(operations) -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([
            _world("initial", False, "#private-initial"),
            _world("fresh", False, "#private-fresh"),
            _world("after", True, "#private-after"),
        ], [ActionResult("*", DispatchStatus.SENT, "dom", True)])
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
        terminal_truth = None
        for operation in operations:
            if operation == "run":
                value = await session.run_until_pause()
            else:
                current = await session.run_until_pause()
                request = current.confirmation_request
                if request is None:
                    value = await session.run_until_pause()
                elif operation == "confirm":
                    value = await session.resolve_confirmation(_decision(current))
                else:
                    wrong = replace(
                        _decision(current), confirmation_id="confirmation:wrong"
                    )
                    value = await session.resolve_confirmation(wrong)
            if terminal_truth is not None:
                assert value is terminal_truth
            if value.status in {
                AgentLoopStatus.DONE,
                AgentLoopStatus.BLOCKED,
                AgentLoopStatus.CANCELLED,
                AgentLoopStatus.FAILED,
            }:
                terminal_truth = value
            assert value.observation_count == session.accounting.observation_attempts
            assert value.execution_count == session.accounting.execution_attempts
            roots = session.state.recent_control_transitions
            assert session.state.control_transition_total_count == len(roots) == 1
            receipts = tuple(item for root in roots for item in root.attempt_receipts)
            assert session.accounting.receipt_count == len(receipts) + 1
            assert session.accounting.observation_attempts == 1 + sum(
                item.acquisition_attempts for item in receipts
            )
            assert session.accounting.execution_attempts == sum(
                item.execution_attempts for item in receipts
            )
            assert all("#private" not in repr(item) for item in receipts)
            assert sum(
                item.operation is AttemptOperation.EXECUTE for item in receipts
            ) == environment.execute_calls

    asyncio.run(scenario())


def test_observation_failure_origin_mapping_is_total_and_path_independent() -> None:
    assert set(OBSERVATION_FAILURE_ORIGINS) == set(ObservationRequestKind)
    for kind in ObservationRequestKind:
        assert observation_failure_origin(kind) is observation_failure_origin(kind.value)


def test_changed_fresh_risk_material_cannot_reuse_old_subject() -> None:
    selection = _selection_for_risk()
    assessment = RiskPolicy().assess(_task(), selection)
    with pytest.raises(ValueError, match="canonical semantics"):
        replace(
            assessment,
            decision=RiskDecisionKind.BLOCK,
            risk=type(assessment.risk).HIGH,
        )


def _selection_for_risk():
    from affordance_runtime.world.action_space import ActionSpaceBuilder

    world = _world("risk", False, "#private")
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    return ActionSpaceBuilder().admit(option, {})
