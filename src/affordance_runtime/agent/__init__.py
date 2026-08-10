"""Target short-loop API with a cycle-safe lazy package facade."""

# ruff: noqa: F401 -- TYPE_CHECKING imports preserve the public facade's static API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from affordance_runtime.agent.decisions import (
        Abort,
        AskUser,
        ProposeDone,
        RequestActionPage,
        RequestObservation,
        SelectAction,
        Wait,
    )
    from affordance_runtime.agent.episode_runner import AgentEpisodeRunner
    from affordance_runtime.agent.loop import AgentLoop
    from affordance_runtime.agent.result import AgentFailureCode, AgentResult
    from affordance_runtime.agent.session import AgentRunSession
    from affordance_runtime.agent.start_error import AgentSessionStartError
    from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus, Turn
    from affordance_runtime.task.contracts import TaskGoal

_EXPORTS = {
    "Abort": ("affordance_runtime.agent.decisions", "Abort"),
    "AgentEpisodeRunner": ("affordance_runtime.agent.episode_runner", "AgentEpisodeRunner"),
    "AgentFailureCode": ("affordance_runtime.agent.result", "AgentFailureCode"),
    "AgentLoop": ("affordance_runtime.agent.loop", "AgentLoop"),
    "AgentLoopState": ("affordance_runtime.agent.state", "AgentLoopState"),
    "AgentLoopStatus": ("affordance_runtime.agent.state", "AgentLoopStatus"),
    "AgentResult": ("affordance_runtime.agent.result", "AgentResult"),
    "AgentRunSession": ("affordance_runtime.agent.session", "AgentRunSession"),
    "AgentSessionStartError": ("affordance_runtime.agent.start_error", "AgentSessionStartError"),
    "AskUser": ("affordance_runtime.agent.decisions", "AskUser"),
    "ProposeDone": ("affordance_runtime.agent.decisions", "ProposeDone"),
    "RequestActionPage": ("affordance_runtime.agent.decisions", "RequestActionPage"),
    "RequestObservation": ("affordance_runtime.agent.decisions", "RequestObservation"),
    "SelectAction": ("affordance_runtime.agent.decisions", "SelectAction"),
    "TaskGoal": ("affordance_runtime.task.contracts", "TaskGoal"),
    "Turn": ("affordance_runtime.agent.state", "Turn"),
    "Wait": ("affordance_runtime.agent.decisions", "Wait"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
