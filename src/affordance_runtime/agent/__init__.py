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
    ProtocolFeedback,
    ProtocolFeedbackKind,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
    YieldSubtask,
    YieldSubtaskKind,
)
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.run_state import EpisodeYieldReason, RunState, RunStatus, StepResult
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.working_facts import WorkingFact

__all__ = [
    "ALL_DECISION_CAPABILITIES",
    "Abort",
    "AgentFailureCode",
    "AskUser",
    "LocalToolResult",
    "ProtocolFeedback",
    "ProtocolFeedbackKind",
    "CoreAgentLoop",
    "CoreLoopStartError",
    "DecisionCapability",
    "EpisodeYieldReason",
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
    "WorkingFact",
    "YieldSubtask",
    "YieldSubtaskKind",
]
