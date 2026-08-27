from __future__ import annotations

import asyncio

import pytest

from affordance_runtime.evaluation import TaskEvaluationStatus, TaskOutcomeKind
from affordance_runtime.surfaces.browsergym import (
    BrowserGymTaskEvaluator,
    BrowserGymTaskReason,
    BrowserGymTaskStateSnapshot,
    BrowserGymTaskStateSource,
    BrowserGymTaskStatus,
    assess_browsergym_task_state,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import ObservationSourceProfile, SurfaceObservation, WorldFusion


def _snapshot(
    source: BrowserGymTaskStateSource,
    *,
    observation_id: str = "source:current",
    reward: float = 0.0,
    raw_reward: float = 0.0,
    terminated: bool = False,
    truncated: bool = False,
    done: bool = False,
    ready: bool = True,
) -> BrowserGymTaskStateSnapshot:
    values = {
        "reward": reward,
        "raw_reward": raw_reward,
        "terminated": terminated,
        "truncated": truncated,
        "done": done,
        "ready": ready,
    }
    return BrowserGymTaskStateSnapshot(
        "browsergym:session",
        observation_id,
        observation_id,
        source,
        values,
        frozenset(values),
    )


@pytest.mark.parametrize(
    ("snapshot", "status", "reason"),
    (
        (
            _snapshot(BrowserGymTaskStateSource.RESET),
            BrowserGymTaskStatus.INCOMPLETE,
            BrowserGymTaskReason.VERIFIED_RUNNING,
        ),
        (
            _snapshot(
                BrowserGymTaskStateSource.POST_ACTION,
                reward=1.0,
                raw_reward=1.0,
                terminated=True,
                done=True,
            ),
            BrowserGymTaskStatus.SUCCESS,
            BrowserGymTaskReason.VERIFIED_SUCCESS,
        ),
        (
            _snapshot(
                BrowserGymTaskStateSource.POST_ACTION,
                terminated=True,
                done=True,
            ),
            BrowserGymTaskStatus.TERMINAL_FAILURE,
            BrowserGymTaskReason.VERIFIED_TERMINAL_FAILURE,
        ),
    ),
)
def test_browsergym_native_task_state_has_closed_typed_outcomes(snapshot, status, reason):
    assessment = assess_browsergym_task_state(snapshot)
    assert assessment.status is status
    assert assessment.reason is reason
    assert bool(assessment.evidence_refs) is (status is not BrowserGymTaskStatus.INCOMPLETE)


def test_browsergym_task_evaluator_requires_current_world_lineage():
    class Source:
        def current_task_state(self):
            return _snapshot(
                BrowserGymTaskStateSource.POST_ACTION,
                observation_id="source:stale",
                reward=1.0,
                raw_reward=1.0,
                terminated=True,
                done=True,
            )

    current = SurfaceObservation(
        "source:current",
        "browsergym",
        "revision:current",
        ObservationSourceProfile.dom(),
    )
    fused = WorldFusion().fuse((current,))
    assert fused.observation is not None
    result = asyncio.run(
        BrowserGymTaskEvaluator(Source()).evaluate(TaskGoal("task", "Complete task"), fused.observation)
    )
    assert result.status is TaskEvaluationStatus.UNKNOWN
    assert result.outcome is not None
    assert result.outcome.kind is TaskOutcomeKind.VERIFIER_UNAVAILABLE
    assert result.outcome.code == BrowserGymTaskReason.SOURCE_INSUFFICIENT.value
