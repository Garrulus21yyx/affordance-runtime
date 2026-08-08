import asyncio

import pytest
from test_agent_loop import ScriptedPolicy, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def test_world_evidence_index_contains_current_facts_and_controlled_artifact_refs() -> None:
    source = SurfaceObservation(
        "surface:after",
        "visual",
        "revision:after",
        ObservationSourceProfile.visual(),
        facts=(StateFact("fact:after", "target:1", "enabled", True, "surface:after"),),
        artifacts={"screenshot": {"digest": "private-value"}},
    )
    world = WorldObservation(
        "world:after",
        (),
        source.facts,
        (),
        {"visual": CoverageState.COMPLETE},
        sources=(source,),
    )

    index = WorldEvidenceIndex.from_observation(world)

    assert index.resolve("fact:after")
    assert index.resolve("artifact:surface:after:screenshot")
    assert "private-value" not in repr(index)


def test_semantic_evidence_ids_may_contain_security_vocabulary() -> None:
    observation = WorldObservation(
        "obs-security-vocabulary",
        (),
        (StateFact("fact:api-token-enabled", "service", "authorization-ready", True, "source"),),
        (),
        {"dom": CoverageState.COMPLETE},
    )

    index = WorldEvidenceIndex.from_observation(observation)

    assert index.resolve("fact:api-token-enabled")


@pytest.mark.parametrize("refs", (("",), ("fact:after", "fact:after")))
def test_action_evaluation_rejects_blank_or_duplicate_evidence_refs(refs) -> None:
    with pytest.raises(ValueError, match="evidence"):
        ActionEvaluation(
            "request:1",
            "before:1",
            "after:1",
            ActionEvaluationStatus.UNKNOWN,
            "untrusted evidence",
            refs,
        )


def test_action_evaluation_rejects_secret_bearing_evidence_mapping() -> None:
    with pytest.raises(ValueError, match="secret"):
        ActionEvaluation(
            "request:1",
            "before:1",
            "after:1",
            ActionEvaluationStatus.UNKNOWN,
            "untrusted evidence",
            evidence={"credential": "raw-secret"},
        )


@pytest.mark.parametrize("evidence_ref", ("fact:invented", "fact:before:enabled"))
def test_agent_loop_rejects_evidence_not_resolved_in_after_world(evidence_ref: str) -> None:
    class InvalidEvidenceEvaluator:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.EFFECT_CONFIRMED,
                "model-like confirmation",
                (evidence_ref,),
            )

    class FailIfCalledTaskEvaluator(SharedTaskEvaluator):
        def __init__(self) -> None:
            self.calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("TaskEvaluator must not receive untrusted action evidence")
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        evaluator = FailIfCalledTaskEvaluator()
        environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])
        result = await AgentEpisodeRunner(
            AgentLoop(ScriptedPolicy(["first"]), InvalidEvidenceEvaluator(), evaluator)
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert "evidence" in result.message
        assert result.turns[-1].action_evaluation is None
        assert evaluator.calls == 1

    asyncio.run(scenario())
