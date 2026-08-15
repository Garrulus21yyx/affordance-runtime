import asyncio
import os

import pytest

from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.model.evaluator import ModelPortSemanticCriterionJudge
from affordance_runtime.model.providers.port import ModelConfig, model_port_from_environment
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_MODEL_EVALUATOR_SMOKE") != "1",
    reason="live evaluator attestation is opt-in",
)


def test_opt_in_live_semantic_evaluator_is_one_attempt_and_side_effect_free() -> None:
    port = model_port_from_environment()
    config = ModelConfig(
        timeout_s=60, rate_limit_retries=0, transient_retries=0,
        prompt_version="p5-m2-live-semantic-smoke",
    )
    judge = ModelPortSemanticCriterionJudge(port, config, call_timeout_s=90)
    fact = StateFact(
        "fact:live-smoke", "report:live-smoke", "content",
        "This short report is clear. Conclusion: the internal smoke is side-effect free.",
        "source:live-smoke",
    )
    source = SurfaceObservation(
        "source:live-smoke", "static", "revision:1", ObservationSourceProfile.dom(),
        targets=(SemanticTarget("report:live-smoke", "content", "internal report"),), facts=(fact,)
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation
    task = TaskGoal(
        "task:live-smoke", "Evaluate an internal static sentence",
        success_criteria=({
            "id": "clear-conclusion", "adjudicator": "semantic", "kind": "semantic_rubric",
            "rubric": "The text is clear and explicitly contains a conclusion.",
            "evidence_scope_target_ids": ["report:live-smoke"],
        },),
    )

    result = asyncio.run(ProductionTaskEvaluator(judge).evaluate(task, world))

    assert result.status == TaskEvaluationStatus.COMPLETE
    assert judge.last_metadata is not None
    assert judge.last_metadata.rate_limit_retry_count == 0
    assert judge.last_metadata.transient_retry_count == 0
