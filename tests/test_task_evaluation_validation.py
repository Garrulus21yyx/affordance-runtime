import asyncio

import pytest
from test_agent_loop import ScriptedPolicy, SharedActionEvaluator, _task, _world

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_task_evaluation
from affordance_runtime.testing import StaticEnvironment


def _evaluation(status=TaskEvaluationStatus.COMPLETE, **changes) -> TaskEvaluation:
    values = dict(
        task_id="enable-shared",
        observation_id="after",
        status=status,
        reason="proposal",
        criteria=(
            CriterionEvaluation(
                "criterion:enabled",
                CriterionEvaluationStatus.SATISFIED,
                ("fact:after:enabled",),
                "enabled is true",
            ),
        ),
        completion_evidence_refs=("fact:after:enabled",),
    )
    values.update(changes)
    return TaskEvaluation(**values)


def _criterion_task():
    return _task().__class__(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "criterion:enabled", "target_id": "shared-toggle", "enabled": True},),
        risk_profile=_task().risk_profile,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"task_id": "wrong"}, "task identity"),
        ({"observation_id": "wrong"}, "observation identity"),
        (
            {
                "criteria": (
                    CriterionEvaluation(
                        "criterion:invented",
                        CriterionEvaluationStatus.SATISFIED,
                        ("fact:after:enabled",),
                        "invented",
                    ),
                )
            },
            "criterion",
        ),
        ({"completion_evidence_refs": ("fact:invented",)}, "evidence"),
        ({"criteria": ()}, "criteria"),
    ),
)
def test_task_evaluation_validator_rejects_untrusted_complete(changes, message) -> None:
    observation = _world("after", True)
    with pytest.raises(ValueError, match=message):
        validate_task_evaluation(
            _evaluation(**changes),
            _criterion_task(),
            observation,
            WorldEvidenceIndex.from_observation(observation),
        )


def test_incomplete_cannot_claim_every_required_criterion_satisfied() -> None:
    observation = _world("after", True)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        validate_task_evaluation(
            _evaluation(TaskEvaluationStatus.INCOMPLETE),
            _criterion_task(),
            observation,
            WorldEvidenceIndex.from_observation(observation),
        )


def test_agent_loop_rejects_invalid_initial_complete_without_policy_or_execution() -> None:
    class UntrustedTaskEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.COMPLETE,
                "model says complete",
                completion_evidence_refs=("fact:invented",),
            )

    async def scenario() -> None:
        policy = ScriptedPolicy([])
        result = await AgentEpisodeRunner(
            AgentLoop(policy, SharedActionEvaluator(), UntrustedTaskEvaluator())
        ).run(StaticEnvironment([_world("after", True)]), _criterion_task())

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0
        assert "task evaluation" in result.message

    asyncio.run(scenario())
