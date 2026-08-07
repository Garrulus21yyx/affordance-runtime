"""Deprecated compatibility re-exports; remove after target-loop cutover."""

from affordance_runtime.agent.loop import AgentResult
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus, Turn
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.task.contracts import TaskGoal

__all__ = [
    "ActionEvaluation",
    "AgentLoopState",
    "AgentLoopStatus",
    "AgentResult",
    "TaskEvaluation",
    "TaskGoal",
    "Turn",
]
