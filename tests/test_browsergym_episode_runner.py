from __future__ import annotations

from pathlib import Path
from queue import Empty
from typing import Any, cast

from affordance_runtime.benchmarks import browsergym as facade
from affordance_runtime.benchmarks import browsergym_compatibility_episode as compatibility
from affordance_runtime.benchmarks import browsergym_episode_runner as runner


class _Queue:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload
        self.closed = False

    def get(self, *, timeout: int) -> dict[str, Any]:
        assert timeout == 1
        if self.payload is None:
            raise Empty
        return self.payload

    def close(self) -> None:
        self.closed = True


class _Process:
    def __init__(self, *, alive: bool, exitcode: int = 0) -> None:
        self.alive = alive
        self.exitcode = exitcode
        self.started = False
        self.terminated = False
        self.joins: list[float] = []

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float) -> None:
        self.joins.append(timeout)

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False


class _Context:
    def __init__(self, queue: _Queue, process: _Process) -> None:
        self.queue = queue
        self.process = process

    def Queue(self) -> _Queue:  # noqa: N802 - mirrors multiprocessing API
        return self.queue

    def Process(self, **kwargs: Any) -> _Process:  # noqa: N802 - mirrors multiprocessing API
        assert kwargs["target"] is runner._generalist_episode_worker
        return self.process


def _isolated(monkeypatch: Any, context: _Context) -> runner.BrowserGymEpisodeResult:
    monkeypatch.setattr(runner.mp, "get_context", lambda method: context if method == "fork" else None)
    return runner.run_browsergym_generalist_episode_isolated(
        cast(Any, object()),
        task_id="generic-task",
        seed=3,
        base_url="http://127.0.0.1:1",
        headless=True,
        artifact_root=Path("artifacts"),
        timeout_s=12,
        model_timeout_s=2,
        max_model_calls=4,
    )


def test_facade_preserves_episode_runner_exports() -> None:
    assert facade.BrowserGymExecutor is runner.BrowserGymExecutor
    assert facade.BrowserGymGeneralistPlanner is compatibility.BrowserGymGeneralistPlanner
    assert facade.run_browsergym_generalist_episode is runner.run_browsergym_generalist_episode


def test_isolated_episode_timeout_terminates_worker_and_closes_queue(monkeypatch: Any) -> None:
    queue = _Queue()
    process = _Process(alive=True)

    result = _isolated(monkeypatch, _Context(queue, process))

    assert result.runtime_error == "episode_timeout"
    assert process.started and process.terminated
    assert process.joins == [12, 5]
    assert queue.closed


def test_isolated_episode_empty_queue_retains_worker_exit_code(monkeypatch: Any) -> None:
    queue = _Queue()
    process = _Process(alive=False, exitcode=17)

    result = _isolated(monkeypatch, _Context(queue, process))

    assert result.runtime_error == "worker_exit:17"
    assert process.started and not process.terminated
    assert process.joins == [12]
    assert queue.closed
