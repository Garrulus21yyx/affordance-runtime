import asyncio
from dataclasses import dataclass
from time import time

from affordance_runtime.agent import (
    ActionEvaluation,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    LoopDecision,
    LoopDecisionKind,
    TaskGoal,
)
from affordance_runtime.agent.types import AgentTurn
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProviderAck,
    TransportState,
)
from affordance_runtime.testing import StaticEnvironment


def _observation(snapshot_id: str, power: str) -> Observation:
    return Observation(
        "rev-1",
        snapshot_id=snapshot_id,
        page_revision="page-1",
        target_fingerprints={"lamp": "fp-lamp"},
        metadata={"power": power},
    )


def _contract(snapshot_id: str = "snap-1") -> ActionContract:
    return ActionContract(
        id="contract-lamp-on",
        intent="turn on lamp",
        affordance_id="lamp",
        action="invoke",
        backend="wot",
        environment_revision="rev-1",
        locator={"thing_id": "lamp", "href": "http://fixture/lamp/on"},
        snapshot_id=snapshot_id,
        page_revision="page-1",
        target_fingerprint="fp-lamp",
        target_fingerprint_key="lamp",
        expires_at_s=time() + 60,
    )


@dataclass
class ScriptedPolicy:
    decisions: list[LoopDecision]

    async def decide(
        self,
        _goal: TaskGoal,
        _observation: Observation,
        _recent_turns: tuple[AgentTurn, ...],
    ) -> LoopDecision:
        return self.decisions.pop(0)


class PowerEvaluator:
    async def evaluate(
        self,
        _goal: TaskGoal,
        _before: Observation,
        _receipt: ExecutionReceipt,
        after: Observation,
    ) -> ActionEvaluation:
        enabled = after.metadata.get("power") == "on"
        return ActionEvaluation(enabled, enabled, "lamp is on" if enabled else "lamp remains off")


def _sent_unknown() -> ExecutionReceipt:
    return ExecutionReceipt(
        "contract-lamp-on",
        "wot",
        False,
        "rev-1",
        "rev-1",
        10,
        transport_state=TransportState.SENT_UNKNOWN,
        provider_ack=ProviderAck.UNKNOWN,
    )


def test_agent_episode_sent_unknown_reobserves_and_accepts_verified_effect_without_retry() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_observation("snap-1", "off"), _observation("snap-2", "on")],
            [_sent_unknown()],
        )
        policy = ScriptedPolicy([LoopDecision(LoopDecisionKind.EXECUTE, "invoke current WoT binding", _contract())])
        result = await AgentEpisodeRunner(AgentLoop(policy, PowerEvaluator())).run(
            environment,
            TaskGoal("lamp-on", "Turn on the lamp"),
        )

        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert result.observation_count == 2
        assert result.turns[0].receipt.transport_state == TransportState.SENT_UNKNOWN

    asyncio.run(scenario())


def test_agent_loop_does_not_blindly_retry_sent_unknown_when_effect_is_absent() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_observation("snap-1", "off"), _observation("snap-2", "off")],
            [_sent_unknown()],
        )
        policy = ScriptedPolicy(
            [
                LoopDecision(LoopDecisionKind.EXECUTE, "invoke current WoT binding", _contract()),
                LoopDecision(
                    LoopDecisionKind.ASK_USER,
                    "effect remains uncertain after fresh observation",
                    user_prompt="The lamp state is still uncertain. Continue?",
                ),
            ]
        )
        result = await AgentEpisodeRunner(AgentLoop(policy, PowerEvaluator())).run(
            environment,
            TaskGoal("lamp-on", "Turn on the lamp"),
        )

        assert result.status == AgentLoopStatus.WAITING_USER
        assert result.execution_count == 1
        assert len(environment.executed_contracts) == 1

    asyncio.run(scenario())


def test_agent_loop_blocks_stale_contract_before_environment_execution() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_observation("snap-2", "off")])
        policy = ScriptedPolicy(
            [
                LoopDecision(LoopDecisionKind.EXECUTE, "stale proposal", _contract("snap-1")),
                LoopDecision(LoopDecisionKind.STOP, "no current binding remains"),
            ]
        )
        result = await AgentEpisodeRunner(AgentLoop(policy, PowerEvaluator())).run(
            environment,
            TaskGoal("lamp-on", "Turn on the lamp"),
        )

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0
        assert environment.executed_contracts == []
        assert result.observation_count == 2

    asyncio.run(scenario())


def test_agent_loop_refuses_to_evaluate_reused_post_action_snapshot() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_observation("snap-1", "off"), _observation("snap-1", "on")],
            [_sent_unknown()],
        )
        policy = ScriptedPolicy([LoopDecision(LoopDecisionKind.EXECUTE, "invoke binding", _contract())])
        result = await AgentEpisodeRunner(AgentLoop(policy, PowerEvaluator())).run(
            environment,
            TaskGoal("lamp-on", "Turn on the lamp"),
        )

        assert result.status == AgentLoopStatus.FAILED
        assert "fresh post-action observation" in result.message
        assert result.turns[0].evaluation is None

    asyncio.run(scenario())
