"""Unified world contracts and runtime-owned action-space services."""

from affordance_runtime.world.action_paging import ActionPager, InternalActionPage
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import (
    ActionBinding,
    ActionOption,
    ActionRisk,
    ActionSpace,
    AdmittedActionSelection,
    CoverageState,
    ObservationConflict,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)
from affordance_runtime.world.relevance import (
    ActionRelevance,
    ActionRelevancePolicy,
    ActionRelevanceRole,
)
from affordance_runtime.world.source_profile import (
    AcquisitionCost,
    ObservationAssurance,
    ObservationModality,
    ObservationSourceProfile,
    VerificationStrength,
    assurance_satisfies,
)
from affordance_runtime.world.view import AgentTargetView, AgentWorldView, build_agent_world_view

__all__ = [
    "ActionBinder",
    "ActionPager",
    "ActionRelevance",
    "ActionRelevancePolicy",
    "ActionRelevanceRole",
    "ActionBinding",
    "ActionOption",
    "ActionRisk",
    "ActionSpace",
    "ActionSpaceBuilder",
    "AdmittedActionSelection",
    "AcquisitionCost",
    "AgentTargetView",
    "AgentWorldView",
    "BindingError",
    "CoverageState",
    "InternalActionPage",
    "ObservationAssurance",
    "ObservationConflict",
    "ObservationModality",
    "ObservationSourceProfile",
    "SemanticTarget",
    "StateFact",
    "SurfaceObservation",
    "WorldObservation",
    "VerificationStrength",
    "build_agent_world_view",
    "assurance_satisfies",
]
