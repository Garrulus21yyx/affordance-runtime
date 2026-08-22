"""Public contracts for the single thin GUI-agent Runtime."""

from affordance_runtime.agent.budgets import EpisodeBudget, StandaloneRunBudget
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
    DecisionKind,
    FinalResponse,
    LocalToolResult,
    PinFactResult,
    ProtocolFeedback,
    ProtocolFeedbackKind,
    ReadRegionResult,
    ReplanReasonCode,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    SetFormFields,
    ToolRejectedResult,
    Wait,
    YieldMilestone,
    YieldMilestoneKind,
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
    "PinFactResult",
    "ProtocolFeedback",
    "ProtocolFeedbackKind",
    "CoreAgentLoop",
    "CoreLoopStartError",
    "DecisionCapability",
    "DecisionKind",
    "EpisodeBudget",
    "EpisodeYieldReason",
    "FailureKind",
    "FailureStage",
    "FinalResponse",
    "GROUNDED_ACTION_DECISION_CAPABILITIES",
    "RequestActionPage",
    "RequestObservation",
    "ReadRegionResult",
    "ReplanReasonCode",
    "RunState",
    "RunStatus",
    "RuntimeFailure",
    "SelectAction",
    "SetFormFields",
    "SearchPageContentResult",
    "StepResult",
    "StandaloneRunBudget",
    "ToolRejectedResult",
    "TOOL_ACTION_DECISION_CAPABILITIES",
    "UnsupportedComposition",
    "UnsupportedCompositionError",
    "Wait",
    "WorkingFact",
    "YieldMilestone",
    "YieldMilestoneKind",
]
