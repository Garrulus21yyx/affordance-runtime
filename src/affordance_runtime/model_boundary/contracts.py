"""Immutable surface-neutral values exposed across the model boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.task.contracts import RiskProfile
from affordance_runtime.world.contracts import ActionRisk


@dataclass(frozen=True)
class AgentSuccessCriterionView:
    criterion_id: str
    definition: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition", freeze_json(self.definition))


@dataclass(frozen=True)
class AgentMaterialBindingView:
    name: str
    media_type: str
    public_reference: str


@dataclass(frozen=True)
class AgentTaskView:
    task_id: str
    instruction: str
    constraints: tuple[str, ...]
    allowed_effects: tuple[str, ...]
    forbidden_effects: tuple[str, ...]
    success_criteria: tuple[AgentSuccessCriterionView, ...]
    requested_output_ids: tuple[str, ...]
    risk_profile: RiskProfile
    public_inputs: Mapping[str, object] = field(default_factory=dict)
    material_bindings: tuple[AgentMaterialBindingView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "allowed_effects", tuple(self.allowed_effects))
        object.__setattr__(self, "forbidden_effects", tuple(self.forbidden_effects))
        object.__setattr__(self, "success_criteria", tuple(self.success_criteria))
        object.__setattr__(self, "requested_output_ids", tuple(self.requested_output_ids))
        object.__setattr__(self, "public_inputs", freeze_json(self.public_inputs))
        object.__setattr__(self, "material_bindings", tuple(self.material_bindings))


@dataclass(frozen=True)
class AgentDestinationView:
    destination_id: str
    label: str


@dataclass(frozen=True)
class AgentActionOptionView:
    action_id: str
    semantic_action: str
    target_id: str
    target_label: str
    destination_required: bool
    destinations: BoundedSection[AgentDestinationView]
    parameter_schema: Mapping[str, object]
    description: str
    semantic_effects: tuple[str, ...]
    risk: ActionRisk
    observation_barrier: bool
    effect_category: str = ""
    consequence_class: str = ""
    reversible: bool = True
    relevance_role: str = "other"
    relevance_score: float = 0.0
    relevance_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "relevance_reason_codes", tuple(self.relevance_reason_codes))


@dataclass(frozen=True)
class AgentActionSpaceView:
    options: tuple[AgentActionOptionView, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))


@dataclass(frozen=True)
class AgentActionPageView:
    options: tuple[AgentActionOptionView, ...]
    total_count: int
    page_size: int
    truncated: bool
    has_more: bool
    available_filters: tuple[str, ...] = ()
    active_query: str = ""
    active_target_filter: str = ""
    active_relevance_filter: str = ""
    next_cursor: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
        object.__setattr__(self, "available_filters", tuple(self.available_filters))
        if self.total_count < len(self.options) or self.page_size != len(self.options):
            raise ValueError("action page counts are inconsistent")
        if self.truncated != (self.total_count > len(self.options)):
            raise ValueError("action page truncation metadata is untruthful")
        if self.has_more != bool(self.next_cursor):
            raise ValueError("action page has_more requires a usable next cursor")


@dataclass(frozen=True)
class AgentTurnView:
    decision_kind: str
    semantic_action: str = ""
    target_id: str = ""
    destination_id: str = ""
    public_parameters: Mapping[str, object] = field(default_factory=dict)
    dispatch_status: str = ""
    action_evaluation_status: str = ""
    task_evaluation_status: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_parameters", freeze_json(self.public_parameters))


@dataclass(frozen=True)
class AgentMilestoneView:
    milestone_id: str
    objective: str
    dependency_ids: tuple[str, ...] = ()
    completion_criteria: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_ids", tuple(self.dependency_ids))
        object.__setattr__(self, "completion_criteria", freeze_json(self.completion_criteria))


@dataclass(frozen=True)
class AgentPlanView:
    milestones: tuple[AgentMilestoneView, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "milestones", tuple(self.milestones))
