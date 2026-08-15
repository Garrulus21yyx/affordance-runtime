import asyncio

import pytest

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.integration.agent.test_agent_loop import ScriptedPolicy, SharedTaskEvaluator, _sent, _task, _world


def test_world_evidence_index_contains_current_facts_and_controlled_artifact_refs() -> None:
    source = SurfaceObservation(
        "surface:after",
        "visual",
        "revision:after",
        ObservationSourceProfile.visual(),
        targets=(SemanticTarget("target:1", "control", "target"),),
        facts=(StateFact("fact:after", "target:1", "enabled", True, "surface:after"),),
        artifacts={"screenshot": {"digest": "private-value"}},
        visual_only_target_ids=("target:1",),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation

    index = WorldEvidenceIndex.from_observation(world)

    assert index.resolve("fact:after")
    assert index.resolve("artifact:surface:after:screenshot")
    assert "private-value" not in repr(index)


def test_semantic_evidence_ids_may_contain_security_vocabulary() -> None:
    source = SurfaceObservation(
        "obs-security-vocabulary",
        "dom",
        "revision:1",
        ObservationSourceProfile.dom(),
        targets=(SemanticTarget("service", "service", "service"),),
        facts=(
            StateFact(
                "fact:api-token-enabled",
                "service",
                "authorization-ready",
                True,
                "obs-security-vocabulary",
            ),
        ),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    observation = fused.observation

    index = WorldEvidenceIndex.from_observation(observation)

    assert index.resolve("fact:api-token-enabled")


def test_unicode_fact_and_artifact_identity_is_canonicalized_without_failure() -> None:
    source = SurfaceObservation(
        "surface:视觉",
        "visual",
        "revision:1",
        ObservationSourceProfile.visual(),
        targets=(SemanticTarget("设备 一", "device", "设备"),),
        artifacts={"截图 摘要": {"private": "value"}},
        facts=(StateFact("状态 已启用", "设备 一", "已启用", True, "surface:视觉"),),
        visual_only_target_ids=("设备 一",),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    observation = fused.observation

    index = WorldEvidenceIndex.from_observation(observation)

    assert len(index.refs) == 2
    assert all(item.startswith(("fact:", "artifact:")) and item.isascii() for item in index.refs)


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
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False), post_observations=(_world("after", True),), results=[_sent()]
        )
        result = await (AgentLoop(ScriptedPolicy(["first"]), InvalidEvidenceEvaluator(), evaluator)).run(
            environment, _task()
        )

        assert result.status == AgentLoopStatus.FAILED
        assert "evidence" in result.message
        assert result.control_transitions[-1].action_evaluation is None
        assert evaluator.calls == 1

    asyncio.run(scenario())
