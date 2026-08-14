"""Immutable surface-neutral values exposed across the model boundary."""

from __future__ import annotations

import re
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
    constraints: BoundedSection[str]
    allowed_effects: BoundedSection[str]
    forbidden_effects: BoundedSection[str]
    success_criteria: BoundedSection[AgentSuccessCriterionView]
    requested_output_ids: BoundedSection[str]
    risk_profile: RiskProfile
    public_inputs: Mapping[str, object] = field(default_factory=dict)
    material_bindings: BoundedSection[AgentMaterialBindingView] = field(
        default_factory=lambda: BoundedSection((), 0, False)
    )
    public_inputs_total_count: int = 0
    public_inputs_truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_inputs", freeze_json(self.public_inputs))
        if self.public_inputs_total_count < len(self.public_inputs):
            raise ValueError("public input total cannot be smaller than its projection")
        if self.public_inputs_truncated != (self.public_inputs_total_count > len(self.public_inputs)):
            raise ValueError("public input truncation metadata is untruthful")


@dataclass(frozen=True)
class AgentDestinationView:
    destination_id: str
    label: str
    grounding_ref: str = ""
    semantics: Mapping[str, object] = field(default_factory=dict)
    grounding_rendered: bool = False
    grounding_context_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantics", freeze_json(self.semantics))
        if self.grounding_ref and re.fullmatch(r"E[1-9][0-9]{0,2}", self.grounding_ref) is None:
            raise ValueError("destination grounding ref is invalid")
        if any((self.grounding_ref, self.semantics, self.grounding_context_id)) and not all(
            (self.grounding_ref, self.semantics, self.grounding_context_id)
        ):
            raise ValueError("destination candidate projection is incomplete")


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
    operation: str = ""
    target_ref: str = ""
    target_semantics: Mapping[str, object] = field(default_factory=dict)
    target_role: str = ""
    target_state: Mapping[str, object] = field(default_factory=dict)
    target_marked: bool = False
    destination_mode: str = ""
    grounding_context_id: str = ""
    subject_kind: str = "entity"
    verification_contract_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "relevance_reason_codes", tuple(self.relevance_reason_codes))
        object.__setattr__(self, "target_semantics", freeze_json(self.target_semantics))
        object.__setattr__(self, "target_state", freeze_json(self.target_state))
        closed = bool(
            self.operation
            and self.target_ref
            and self.target_semantics
            and self.target_role
            and self.destination_mode
            and self.grounding_context_id
        )
        if any(
            (
                self.operation,
                self.target_ref,
                self.target_semantics,
                self.target_role,
                self.target_state,
                self.destination_mode,
                self.grounding_context_id,
            )
        ) and not closed:
            raise ValueError("action candidate target projection is incomplete")
        if self.target_ref and re.fullmatch(r"E[1-9][0-9]{0,2}", self.target_ref) is None:
            raise ValueError("action candidate target ref is invalid")
        if self.destination_mode and self.destination_mode not in {"forbidden", "required", "optional"}:
            raise ValueError("action candidate destination mode is invalid")
        if self.destination_mode == "required" and not self.destination_required:
            raise ValueError("required destination mode must conserve the ActionOption contract")
        if self.destination_mode == "forbidden" and self.destination_required:
            raise ValueError("forbidden destination mode cannot require a destination")


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
    semantic_summary: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_parameters", freeze_json(self.public_parameters))
        object.__setattr__(self, "semantic_summary", freeze_json(self.semantic_summary))


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
