"""Stable Affordance Runtime public API."""

from affordance_runtime.agent import RunState, RunStatus, StepResult
from affordance_runtime.app import (
    TargetRuntime,
    TargetRuntimeRunOutcome,
    compose_target_runtime_from_environment,
)
from affordance_runtime.task import NaturalLanguageTaskRequest, TaskBoundary, TaskGoal

__all__ = [
    "NaturalLanguageTaskRequest",
    "RunState",
    "RunStatus",
    "StepResult",
    "TargetRuntime",
    "TargetRuntimeRunOutcome",
    "TaskBoundary",
    "TaskGoal",
    "compose_target_runtime_from_environment",
]
