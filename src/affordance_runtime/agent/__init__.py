"""Target short-loop API with a cycle-safe lazy package facade."""

# ruff: noqa: F401 -- TYPE_CHECKING imports preserve the public facade's static API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from affordance_runtime.agent.control_feedback import (
        ControlFeedback,
        ControlFeedbackKind,
        ControlFeedbackSource,
        NextDecisionDisposition,
    )
    from affordance_runtime.agent.control_transition import (
        AcquisitionSummary,
        AdmissionStatus,
        AdmissionSummary,
        ControlContinuation,
        ControlTransition,
        PendingKind,
        ProgressDelta,
    )
    from affordance_runtime.agent.decisions import (
        Abort,
        AgentDecisionPackage,
        AskUser,
        EstablishLocalObjective,
        ProposeDone,
        RequestActionPage,
        RequestObservation,
        SelectAction,
        Wait,
    )
    from affordance_runtime.agent.episode_runner import AgentEpisodeRunner
    from affordance_runtime.agent.loop import AgentLoop
    from affordance_runtime.agent.result import AgentFailureCode, AgentResult
    from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
    from affordance_runtime.agent.session import AgentRunSession
    from affordance_runtime.agent.start_error import AgentSessionStartError
    from affordance_runtime.agent.state import (
        AgentLoopState,
        AgentLoopStatus,
        Turn,
    )
    from affordance_runtime.task.contracts import TaskGoal

_EXPORTS = {
    "ControlFeedback": ("affordance_runtime.agent.control_feedback", "ControlFeedback"),
    "ControlFeedbackKind": ("affordance_runtime.agent.control_feedback", "ControlFeedbackKind"),
    "ControlFeedbackSource": ("affordance_runtime.agent.control_feedback", "ControlFeedbackSource"),
    "NextDecisionDisposition": (
        "affordance_runtime.agent.control_feedback",
        "NextDecisionDisposition",
    ),
    "AcquisitionSummary": ("affordance_runtime.agent.control_transition", "AcquisitionSummary"),
    "AdmissionSummary": ("affordance_runtime.agent.control_transition", "AdmissionSummary"),
    "AdmissionStatus": ("affordance_runtime.agent.control_transition", "AdmissionStatus"),
    "Abort": ("affordance_runtime.agent.decisions", "Abort"),
    "AgentDecisionPackage": (
        "affordance_runtime.agent.decisions",
        "AgentDecisionPackage",
    ),
    "AgentEpisodeRunner": ("affordance_runtime.agent.episode_runner", "AgentEpisodeRunner"),
    "AgentFailureCode": ("affordance_runtime.agent.result", "AgentFailureCode"),
    "AgentLoop": ("affordance_runtime.agent.loop", "AgentLoop"),
    "AgentLoopState": ("affordance_runtime.agent.state", "AgentLoopState"),
    "AgentLoopStatus": ("affordance_runtime.agent.state", "AgentLoopStatus"),
    "AgentResult": ("affordance_runtime.agent.result", "AgentResult"),
    "AgentRunSession": ("affordance_runtime.agent.session", "AgentRunSession"),
    "AgentSessionStartError": ("affordance_runtime.agent.start_error", "AgentSessionStartError"),
    "AskUser": ("affordance_runtime.agent.decisions", "AskUser"),
    "EstablishLocalObjective": (
        "affordance_runtime.agent.decisions",
        "EstablishLocalObjective",
    ),
    "FailureKind": ("affordance_runtime.agent.runtime_failure", "FailureKind"),
    "FailureStage": ("affordance_runtime.agent.runtime_failure", "FailureStage"),
    "ControlContinuation": ("affordance_runtime.agent.control_transition", "ControlContinuation"),
    "ControlTransition": ("affordance_runtime.agent.control_transition", "ControlTransition"),
    "PendingKind": ("affordance_runtime.agent.control_transition", "PendingKind"),
    "ProposeDone": ("affordance_runtime.agent.decisions", "ProposeDone"),
    "ProgressDelta": ("affordance_runtime.agent.control_transition", "ProgressDelta"),
    "RequestActionPage": ("affordance_runtime.agent.decisions", "RequestActionPage"),
    "RequestObservation": ("affordance_runtime.agent.decisions", "RequestObservation"),
    "RuntimeFailure": ("affordance_runtime.agent.runtime_failure", "RuntimeFailure"),
    "SelectAction": ("affordance_runtime.agent.decisions", "SelectAction"),
    "TaskGoal": ("affordance_runtime.task.contracts", "TaskGoal"),
    "Turn": ("affordance_runtime.agent.control_transition", "Turn"),
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
