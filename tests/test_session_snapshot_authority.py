from __future__ import annotations

import asyncio

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _task, _world

from affordance_runtime.agent import Abort, AgentEpisodeRunner, AgentLoop
from affordance_runtime.agent.control_transition import ControlTransitionScope
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.testing import StaticEnvironment


class UnusedPolicy:
    async def decide(self, context):
        return Abort(context.context_id, "unused", "policy")


@pytest.mark.parametrize(
    ("historical", "current"),
    (
        (TaskEvaluationStatus.INCOMPLETE, TaskEvaluationStatus.BLOCKED),
        (TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.UNKNOWN),
    ),
)
def test_snapshot_current_task_status_never_falls_back_to_transition_history(
    historical: TaskEvaluationStatus,
    current: TaskEvaluationStatus,
) -> None:
    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(UnusedPolicy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).start(StaticEnvironment([_world("current", False)]), _task())
        decision = Abort("context:history", "stop", "policy")
        old = TaskEvaluation(
            _task().task_id,
            "current",
            historical,
            "historical",
            completion_evidence_refs=("fact:historical",)
            if historical is TaskEvaluationStatus.COMPLETE
            else (),
        )
        scope = ControlTransitionScope(session.state, decision)
        scope.record_evaluations(task=old)
        scope.set_reason("abort_policy")
        scope.finalize(session.state, None)
        session.state.current_task_evaluation = TaskEvaluation(
            _task().task_id, "current", current, "current authority"
        )

        snapshot = session.snapshot_partial_episode()
        assert snapshot.latest_task_status == str(current)

    asyncio.run(scenario())


def test_snapshot_fails_closed_on_current_task_evaluation_lineage_mismatch() -> None:
    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(UnusedPolicy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).start(StaticEnvironment([_world("current", False)]), _task())
        session.state.current_task_evaluation = TaskEvaluation(
            _task().task_id,
            "stale-observation",
            TaskEvaluationStatus.COMPLETE,
            "stale",
            completion_evidence_refs=("fact:stale",),
        )
        assert session.snapshot_partial_episode().latest_task_status == ""

    asyncio.run(scenario())
