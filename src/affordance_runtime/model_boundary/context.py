"""Disposable model-facing AgentContext and opaque Runtime identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.contracts import AgentActionPageView, AgentTaskView, AgentTurnView
from affordance_runtime.model_boundary.control_feedback_projection import AgentControlFeedbackView
from affordance_runtime.model_boundary.world_projection import ModelWorldView, PublicFactView


class DecisionMode(StrEnum):
    ACT = "act"
    RECOVER = "recover"


@dataclass(frozen=True)
class ContextIdentity:
    task_revision: int
    observation_id: str
    action_space_id: str
    action_page_id: str
    progress_revision: int
    pending_revision: int
    context_generation: int = 0

    def __post_init__(self) -> None:
        if (
            self.task_revision <= 0
            or self.progress_revision < 0
            or self.pending_revision < 0
            or self.context_generation < 0
        ):
            raise ValueError("context revisions are invalid")
        if not all(value.strip() for value in (self.observation_id, self.action_space_id, self.action_page_id)):
            raise ValueError("context identity requires current observation, action space, and page")

    @property
    def context_id(self) -> str:
        payload = (
            self.task_revision,
            self.observation_id,
            self.action_space_id,
            self.action_page_id,
            self.progress_revision,
            self.pending_revision,
            self.context_generation,
        )
        digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        return f"context:{digest}"


@dataclass(frozen=True)
class IntentExcerptView:
    text: str
    source_kind: str
    source_ref: str
    digest: str


@dataclass(frozen=True)
class IntentContextView:
    excerpts: BoundedSection[IntentExcerptView]
    authority: str = "context_only"


@dataclass(frozen=True)
class AgentProgressEventView:
    event_type: str
    semantic_action: str
    target_id: str
    attempt_key_digest: str
    effect_status: str
    task_status: str
    strategy_transition_required: bool


@dataclass(frozen=True)
class AgentRequirementStateView:
    requirement_id: str
    status: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRequirementHypothesisView:
    hypothesis_id: str
    summary: str
    predicate: Mapping[str, object]
    candidate_entity_ids: tuple[str, ...]
    status: str
    assessment: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate", freeze_json(self.predicate))


@dataclass(frozen=True)
class AgentObjectiveView:
    objective_id: str
    intended_requirement_ids: tuple[str, ...]
    predicate: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate", freeze_json(self.predicate))


@dataclass(frozen=True)
class AgentObjectiveCheckpointView:
    objective_id: str
    intended_requirement_ids: tuple[str, ...]
    predicate: Mapping[str, object]
    status: str
    observation_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate", freeze_json(self.predicate))


@dataclass(frozen=True)
class AgentTaskFrontierView:
    requirements: tuple[AgentRequirementStateView, ...]
    current_frontier: tuple[str, ...]
    active_objective: AgentObjectiveView | None
    recent_checkpoints: tuple[AgentObjectiveCheckpointView, ...]
    verified_fact_refs: tuple[str, ...]
    next_objective_required: bool
    must_advance_from_objective_id: str
    strategy_change_required: bool
    requirement_hypotheses: tuple[AgentRequirementHypothesisView, ...] = ()
    hypothesis_set_completeness: str = "unknown"
    hypothesis_failure_reason: str = ""
    hypothesis_rejections: tuple["AgentHypothesisRejectionView", ...] = ()


@dataclass(frozen=True)
class AgentHypothesisRejectionView:
    item_index: int
    code: str


@dataclass(frozen=True)
class AgentProgressView:
    active_objective: str
    validated_task_status: str
    verified_public_facts: tuple[PublicFactView, ...]
    unresolved_criteria: BoundedSection[str]
    unresolved_outputs: BoundedSection[str]
    events: BoundedSection[AgentProgressEventView]
    task_frontier: AgentTaskFrontierView | None = None
    local_objective_open: bool = False
    truncated: bool = False


@dataclass(frozen=True)
class AgentPendingView:
    waiting_user_summary: str = ""
    waiting_confirmation_summary: str = ""
    uncertain_effect_summary: str = ""


@dataclass(frozen=True)
class AgentBudgetView:
    remaining_turns: int
    remaining_observations: int
    remaining_wait_ms: int
    section_truncation: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_truncation", freeze_json(self.section_truncation))


@dataclass(frozen=True)
class AgentImageInput:
    evidence_ref: str
    mime_type: str
    data: bytes = field(repr=False)
    sha256: str = ""

    def __post_init__(self) -> None:
        if (
            not self.evidence_ref.startswith("artifact:")
            or self.mime_type not in {"image/png", "image/jpeg"}
            or not isinstance(self.data, bytes)
            or not self.data
            or len(self.data) > 5 * 1024 * 1024
            or len(self.sha256) != 64
        ):
            raise ValueError("agent image input is invalid")


@dataclass(frozen=True)
class AgentGroundingEntityView:
    ref: str
    role: str
    label: str
    state: Mapping[str, object] = field(default_factory=dict)
    relation_hints: tuple[str, ...] = ()
    verbs: tuple[str, ...] = ()
    marked: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"E[1-9][0-9]{0,2}", self.ref):
            raise ValueError("grounding entity requires a bounded call-local ref")
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "relation_hints", tuple(self.relation_hints))
        object.__setattr__(self, "verbs", tuple(self.verbs))


@dataclass(frozen=True)
class AgentGroundingIndexView:
    entities: tuple[AgentGroundingEntityView, ...] = ()
    target_refs: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        entities = tuple(self.entities)
        refs = {item.ref for item in entities}
        if len(refs) != len(entities):
            raise ValueError("grounding refs must be unique")
        mapping = dict(self.target_refs)
        if set(mapping.values()) != refs or len(mapping) != len(entities):
            raise ValueError("grounding target/ref mapping must be bijective")
        object.__setattr__(self, "entities", entities)
        object.__setattr__(self, "target_refs", freeze_json(mapping))


@dataclass(frozen=True)
class AgentContext:
    context_id: str
    task: AgentTaskView
    intent: IntentContextView
    progress: AgentProgressView
    world: ModelWorldView
    actions: AgentActionPageView
    history: BoundedSection[AgentTurnView]
    pending: AgentPendingView
    budgets: AgentBudgetView
    decision_mode: DecisionMode
    control_feedback: AgentControlFeedbackView | None = None
    image_inputs: tuple[AgentImageInput, ...] = ()
    grounding: AgentGroundingIndexView = field(default_factory=AgentGroundingIndexView)

    def __post_init__(self) -> None:
        if not self.context_id.startswith("context:"):
            raise ValueError("AgentContext requires opaque context identity")
        object.__setattr__(self, "image_inputs", tuple(self.image_inputs))
        if len(self.image_inputs) > 2 or any(not isinstance(item, AgentImageInput) for item in self.image_inputs):
            raise TypeError("AgentContext image inputs must be bounded and typed")
        if not isinstance(self.grounding, AgentGroundingIndexView):
            raise TypeError("AgentContext grounding index must be typed")
