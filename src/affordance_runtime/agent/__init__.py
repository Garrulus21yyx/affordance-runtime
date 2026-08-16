"""Public contracts for the single thin GUI-agent Runtime."""

from affordance_runtime.agent.core_loop import CoreAgentLoop, CoreLoopStartError
from affordance_runtime.agent.decision_capability import (
    ALL_DECISION_CAPABILITIES,
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    TOOL_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
    UnsupportedComposition,
    UnsupportedCompositionError,
)
from affordance_runtime.agent.decisions import (
    Abort,
    AskUser,
    FinalResponse,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure

__all__ = [
    "ALL_DECISION_CAPABILITIES",
    "Abort",
    "AgentFailureCode",
    "AskUser",
    "LocalToolResult",
    "CoreAgentLoop",
    "CoreLoopStartError",
    "DecisionCapability",
    "FailureKind",
    "FailureStage",
    "FinalResponse",
    "GROUNDED_ACTION_DECISION_CAPABILITIES",
    "RequestActionPage",
    "RequestObservation",
    "RunState",
    "RunStatus",
    "RuntimeFailure",
    "SelectAction",
    "StepResult",
    "TOOL_ACTION_DECISION_CAPABILITIES",
    "UnsupportedComposition",
    "UnsupportedCompositionError",
    "Wait",
]
