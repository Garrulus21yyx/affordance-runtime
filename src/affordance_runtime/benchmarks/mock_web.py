"""Manifest-backed black-box tasks for the migrated mock web environments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from affordance_runtime.benchmarks.spec import BenchmarkTask


@dataclass(frozen=True)
class MockWebOracle:
    selector: str
    text: str = ""
    style_display: str = ""

    def __post_init__(self) -> None:
        if not self.selector.startswith("#"):
            raise ValueError("mock-web oracle selector must be an element id")
        if not (self.text or self.style_display):
            raise ValueError("mock-web oracle requires text or display state")


@dataclass(frozen=True)
class MockWebTask:
    task_id: str
    page: str
    goal: str
    oracle: MockWebOracle
    forbidden_side_effects: tuple[str, ...]
    seeded_layout_variants: tuple[str, ...]

    def __post_init__(self) -> None:
        if Path(self.page).name != self.page or not self.page.endswith(".html"):
            raise ValueError("mock-web task page must be a local HTML filename")
        if not self.task_id or not self.goal.strip() or not self.forbidden_side_effects:
            raise ValueError("mock-web task requires identity, goal, and forbidden side effects")

    def to_benchmark_task(self, base_url: str) -> BenchmarkTask:
        return BenchmarkTask(
            suite="mock-web-v1",
            task_id=self.task_id,
            start_url=urljoin(base_url.rstrip("/") + "/", self.page),
            goal=self.goal,
            tags=["mock-web", *self.seeded_layout_variants],
            oracle={
                "selector": self.oracle.selector,
                "text": self.oracle.text,
                "style_display": self.oracle.style_display,
                "forbidden_side_effects": list(self.forbidden_side_effects),
            },
        )


def default_mock_web_root() -> Path:
    return Path(__file__).resolve().parents[3] / "environments" / "mock_web"


def load_mock_web_tasks(root: Path | None = None) -> tuple[MockWebTask, ...]:
    environment_root = (root or default_mock_web_root()).resolve()
    raw_tasks = json.loads((environment_root / "tasks.json").read_text(encoding="utf-8"))
    if not isinstance(raw_tasks, list):
        raise ValueError("mock-web task manifest must be a list")
    tasks = tuple(_parse_task(item) for item in raw_tasks)
    if len({task.task_id for task in tasks}) != len(tasks):
        raise ValueError("mock-web task ids must be unique")
    for task in tasks:
        if not (environment_root / task.page).is_file():
            raise ValueError(f"mock-web page is missing: {task.page}")
    return tasks


def mock_web_benchmark_tasks(base_url: str, root: Path | None = None) -> tuple[BenchmarkTask, ...]:
    return tuple(task.to_benchmark_task(base_url) for task in load_mock_web_tasks(root))


def _parse_task(raw: Any) -> MockWebTask:
    if not isinstance(raw, dict) or not isinstance(raw.get("success"), dict):
        raise ValueError("invalid mock-web task entry")
    oracle = raw["success"]
    return MockWebTask(
        task_id=str(raw.get("task_id") or ""),
        page=str(raw.get("page") or ""),
        goal=str(raw.get("goal") or ""),
        oracle=MockWebOracle(
            selector=str(oracle.get("selector") or ""),
            text=str(oracle.get("text") or ""),
            style_display=str(oracle.get("style_display") or ""),
        ),
        forbidden_side_effects=tuple(str(item) for item in raw.get("forbidden_side_effects") or ()),
        seeded_layout_variants=tuple(str(item) for item in raw.get("seeded_layout_variants") or ()),
    )
