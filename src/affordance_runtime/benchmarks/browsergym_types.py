"""BrowserGym bridge value objects and protocol boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from affordance_runtime.benchmarks.browsergym_action_schema import BrowserGymAction


@dataclass(frozen=True)
class BrowserGymPolicyRequest:
    task_id: str
    seed: int
    goal: str
    step: int
    affordances: list[dict[str, Any]]
    previous_actions: list[dict[str, Any]]
    accessibility_tree: str = ""


class BrowserGymPolicy(Protocol):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction | None: ...

    def close(self) -> None: ...


class BrowserGymEnvironment(Protocol):
    @property
    def unwrapped(self) -> Any: ...

    def reset(self, *, seed: int) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]: ...

    def close(self) -> None: ...


@dataclass
class BrowserGymEpisodeState:
    task_id: str
    seed: int
    goal: str
    observation: dict[str, Any]
    info: dict[str, Any]
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    actions: list[BrowserGymAction] = field(default_factory=list)


@dataclass(frozen=True)
class BrowserGymEpisodeResult:
    task_id: str
    seed: int
    runtime_status: str
    official_success: bool
    official_reward: float
    terminated: bool
    truncated: bool
    action_count: int
    action_families: list[str]
    unsupported_actions: list[str]
    runtime_error: str
    policy_stopped: bool
    trace_path: str
