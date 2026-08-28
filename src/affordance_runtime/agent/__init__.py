"""Public contracts for the single thin GUI-agent Runtime."""

from affordance_runtime.agent.budgets import StandaloneRunBudget
from affordance_runtime.agent.context.world_region_index import RegionVersion
from affordance_runtime.agent.context.world_transition import (
    PublicWorldDelta,
    WorldTransitionProjector,
)
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
    InteractionRequestDraft,
    InteractionResponseKind,
    LocalToolResult,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.interactions import (
    InteractionRequest,
    InteractionResponse,
    PublicArtifact,
)
from affordance_runtime.agent.profile import AgentLoopProfile
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.run_state import (
    ControlTermination,
    ControlTerminationKind,
    RunState,
    RunStatus,
    StepResult,
)
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.workspace import (
    ActivitySummary,
    AgentWorkspace,
    DefaultWorkspaceReducer,
    SemanticEvent,
    WorkspaceReducer,
)

__all__ = [
    "ALL_DECISION_CAPABILITIES",
    "Abort",
    "AskUser",
    "AgentFailureCode",
    "AgentLoopProfile",
    "AgentWorkspace",
    "ActivitySummary",
    "LocalToolResult",
    "CoreAgentLoop",
    "CoreLoopStartError",
    "ControlTermination",
    "ControlTerminationKind",
    "DefaultWorkspaceReducer",
    "DecisionCapability",
    "DecisionKind",
    "FailureKind",
    "FailureStage",
    "FinalResponse",
    "InteractionRequest",
    "InteractionRequestDraft",
    "InteractionResponse",
    "InteractionResponseKind",
    "GROUNDED_ACTION_DECISION_CAPABILITIES",
    "RequestActionPage",
    "RequestObservation",
    "ReadRegionResult",
    "RegionVersion",
    "RunState",
    "RunStatus",
    "RuntimeFailure",
    "PublicWorldDelta",
    "PublicArtifact",
    "SelectAction",
    "SearchPageContentResult",
    "SemanticEvent",
    "StepResult",
    "StandaloneRunBudget",
    "ToolRejectedResult",
    "TOOL_ACTION_DECISION_CAPABILITIES",
    "UnsupportedComposition",
    "UnsupportedCompositionError",
    "Wait",
    "WorldTransitionProjector",
    "WorkspaceReducer",
]
