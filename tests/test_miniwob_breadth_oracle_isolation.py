from __future__ import annotations

import asyncio

from affordance_runtime.benchmarks.external_smoke.browsergym_environment import BrowserGymMiniWobEnvironment


class _Gym:
    browser = None
    context = None
    unwrapped = None

    def __init__(self, _task_id: str, *, headless: bool = True) -> None:
        del headless
        self.unwrapped = self
        self.closed = False

    def reset(self, *, seed: int):
        del seed
        return (
            {"goal": "Click the public button.", "url": "file:///public-task", "axtree_object": {"nodes": []}},
            {"task_info": {"EPISODE_ID": 1}},
        )

    def close(self) -> None:
        self.closed = True


def test_campaign_task_id_is_private_to_environment() -> None:
    task_id = "browsergym/miniwob.campaign-fixture"
    environment, task = BrowserGymMiniWobEnvironment.open(
        task_id, 7, gym_factory=_Gym, admitted_task_ids=frozenset({task_id}), max_turns=10,
    )
    assert task_id not in repr(task)
    assert task.instruction == "Click the public button."
    assert environment.benchmark_task_id == task_id
    asyncio.run(environment.close())
    assert environment.gym_environment.closed


def test_unadmitted_campaign_task_fails_before_environment_creation() -> None:
    try:
        BrowserGymMiniWobEnvironment.open(
            "browsergym/miniwob.not-admitted", 7, gym_factory=_Gym,
            admitted_task_ids=frozenset({"browsergym/miniwob.allowed"}),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unadmitted campaign task was accepted")
